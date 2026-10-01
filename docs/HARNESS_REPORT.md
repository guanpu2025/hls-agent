# 初期 HLS Harness 报告

日期：2026-10-01  
代码：`/data/guanpu/hls-agent`  
题：`c2hlsc / ShiftRows`（短 prompt + Vitis HLS 2025.2 CSim）

## 结论

**初期 harness 已立住，本地工具链已跑通。**  
参考实现走完整条「代码 → Vitis CSim → golden 比对」为 **通过**；故意写错的实现被 golden 判 **失败**。  
**模型在 EVO 上实时生成 ShiftRows 这次没有跑完**（halogen prefill 超时）。因此「LLM 生成 → 反馈 → 再修」的**代码路径已写好**，但**端到端模型实验仍受 64GB + PIN=0 卡住**。

---

## Harness 在哪

入口：

| 路径 | 作用 |
|------|------|
| `/data/guanpu/hls-agent/run_harness.py` | 生成 / 播种代码 → CSim → 失败则最多再修一轮 |
| `/data/guanpu/hls-agent/run_harness.sh` | 设好 Vitis / HLS-Eval / API 环境再跑 |
| `/data/guanpu/hls-agent/agent/vitis_runner.py` | 调 HLS-Eval `VitisHLSCSimTool`（可选 synth） |
| `/data/guanpu/hls-agent/agent/prompts.py` | 把工具日志拼成 repair user 消息 |
| `/data/guanpu/hls-agent/designs/shift_rows/` | 本题 bundle：头文件、TB、参考 cpp、golden |
| `/data/guanpu/hls-agent/skill/shift_rows_short_prompt.txt` | 给模型的短 prompt |

题目文件：

```
designs/shift_rows/shift_rows.h
designs/shift_rows/shift_rows_tb.cpp
designs/shift_rows/shift_rows.cpp          # 参考实现（HLS-Eval）
designs/shift_rows/broken_shift_rows.cpp   # 空操作，用来测失败路径
designs/shift_rows/golden_stdout.txt       # 0055aaff4499ee3388dd2277cc1166bb
designs/shift_rows/top.txt                 # ShiftRows
```

成功 / 失败输出：

```
outputs/harness_ref_seed/meta.json          final_ok=true
outputs/harness_broken_seed/meta.json       final_ok=false, failed_stage=golden_mismatch
```

用法：

```bash
cd /data/guanpu/hls-agent
# 不调模型，用已有 cpp 走工具
./run_harness.sh \
  --prompt skill/shift_rows_short_prompt.txt \
  --design-dir designs/shift_rows \
  --cpp-name shift_rows.cpp \
  --seed-cpp designs/shift_rows/shift_rows.cpp \
  --out outputs/harness_ref_seed \
  --max-rounds 1

# 调 halogen（EVO 需已起 lean server）
HLS_API_BASE=http://192.168.0.157:8731/v1 \
./run_harness.sh \
  --prompt skill/shift_rows_short_prompt.txt \
  --design-dir designs/shift_rows \
  --cpp-name shift_rows.cpp \
  --out outputs/harness_shift_rows_llm \
  --max-tokens 256 --max-rounds 2
```

默认 FPGA part：`xczu3eg-sbva484-1-e`（可用 `HLS_FPGA_PART` 改）。  
必须有环境变量：`XILINX_VIVADO=/data/guanpu/Xilinx/2025.2/Vivado`（脚本已设）。

---

## 测试结果

| 用例 | 结果 |
|------|------|
| HLS-Eval 参考 `shift_rows.cpp` + 原 TB | CSim 编译/运行成功，stdout `0055aaff4499ee3388dd2277cc1166bb` |
| harness `--seed-cpp` 同一文件 | `final_ok=true`，`golden_match=true`，`csim_return_code=0` |
| harness `--seed-cpp broken_shift_rows.cpp` | CSim 仍返回 0（原 TB 不检查对错），但 golden **不匹配**（实际 `00112233...`），`failed_stage=golden_mismatch`，进程退出码 3 |
| 笔记本经局域网调 halogen 生成短 prompt | 600s 超时，无产物 |
| EVO 本机调 halogen（268 字节 ultra prompt，`max_tokens=256`） | 约 400s 超时，日志停在 prefill 路径，无 `generated.cpp` |

Vitis 版本：2025.2。CSim 编译+运行大约 2～3 秒（不含模型）。

---

## 遇到的问题与解决

1. **`set_part` 报 part 未安装 / `failed to find any device libraries`**  
   只把 `vitis_hls` 放进 PATH 不够。2025.2 需要 `XILINX_VIVADO` 指向 Vivado 根目录。设好后 `xczu3eg-sbva484-1-e` 可用。

2. **CSim「Cannot find C test bench」**  
   HLS-Eval 把源文件路径写进 TCL，而 `vitis_hls` 的 cwd 在 build 子目录，相对路径失效。改为传入**绝对路径**后通过。

3. **原 `shift_rows_tb.cpp` 永远 `return 0`**  
   只打印状态，空实现也会「CSim 通过」。加了 `golden_stdout.txt` 比对，错实现才能触发 repair。

4. **完整 Luna prompt（约 1200 token）在 PIN=0 下 prefill 停在 0**  
   EVO（系统可见约 60Gi，整机 64GB）跑 `w4b.hgn`（常驻约 68Gi 量级 + 47.7Gi mmap 表）时，长 prefill 会满 CPU 空转。短请求有时可以，长请求经常不行。这不是笔记本内存问题。

5. **笔记本直连 `192.168.0.157` 或过早探测 `/v1/models`**  
   客户端超时后单 slot 引擎可能楔死；同时拉起服务又立刻请求会连不上。需要等服务真正 ready，且不要在 prefill 中途杀进程。

---

## 目前不足

- 只接了 **CSim + golden stdout**，默认不算 csynth / PPA（有 `--synth`，未在本题上稳定跑完）。
- Repair 轮已实现，但**依赖第二次 LLM 调用**；这次没有一次成功的模型返回，所以修复轮没有实测成功。
- Prompt 必须压短；完整轨迹原文在这台机器上不可靠。
- 只验证了 ShiftRows 一道题。
- 原 TB 函数语义和数学上的「按行左旋」并不直观（参考实现是按列旋转的 tiny-AES 写法）；golden 对齐的是**现有 TB 输出**，不是另一套实现。

## 目前解决不了（在这套硬件上）

- **64GB EVO + halogen w4b + PIN=0** 无法稳定完成哪怕几百字节的 HLS prompt prefill。官方推荐 128GB；`v2.hgn` 常驻约 62Gi + 47.7Gi ngram，仍建议 128GB，换文件也救不了「从容 pin」。
- 未 pin 权重时，服务可能长时间 `prefill 0/N`、满 CPU、无输出，不是脚本 bug。
- 队友更小的 SFT 权重若未部署到这台 API 上，harness 暂时只能挂现有 halogen。

## 下一步

模型能稳定返回时，同一命令去掉 `--seed-cpp` 即是「生成 → 失败反馈 → 再生成」。在此之前应优先换 128GB 机器、或换能在 64GB 上 pin 住的更小模型。
