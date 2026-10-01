# HLS-Agent Baseline Smoke 跑通报告

日期：2026-09-30  
机器：笔记本 `guanpu-Legion` + EVO-X2（`192.168.0.157`，halogen-flash-server 0.15.1，w4b）

## 结论

**baseline 单次生成流程已跑通。**  
在 EVO 上调用 halogen OpenAI 兼容 API，`run_baseline.py` 能稳定产出可解析的 C++，并同步回笔记本。

| 用例 | 结果 | 耗时（约） |
|------|------|------------|
| 最小纯代码 prompt | EXIT 0，`parse_ok=true` | ~31s |
| `<OUTPUT_CODE>` 格式 prompt | EXIT 0，抽出 `add.cpp` | ~20s |

---

## 成功产物位置

### 笔记本（下一步请直接看这里）

```
/data/guanpu/hls-agent/outputs/smoke_minimal/
  generated.cpp      # int add_one(int x) { return x + 1; }
  raw_output.txt
  meta.json

/data/guanpu/hls-agent/outputs/smoke_output_code/
  generated.cpp
  add.cpp            # 同内容，按 name 抽出
  raw_output.txt     # 含完整 <OUTPUT_CODE>...</OUTPUT_CODE>
  meta.json
```

### EVO 上（同源）

```
~/hls-agent/outputs/smoke_minimal/
~/hls-agent/outputs/smoke_output_code/
```

### 相关脚本 / prompt

| 路径 | 用途 |
|------|------|
| `/data/guanpu/hls-agent/run_baseline.py` | 单次生成入口 |
| `/data/guanpu/hls-agent/run_baseline.sh` | 清代理 + 默认走 SSH tunnel `18731` |
| `/data/guanpu/hls-agent/scripts/start_halogen_lean.sh` | EVO 上启动 lean halogen |
| `/data/guanpu/hls-agent/skill/smoke_minimal_prompt.txt` | 无 XML 的最小 prompt |
| `/data/guanpu/hls-agent/skill/smoke_output_code_prompt.txt` | 竞赛格式 OUTPUT_CODE |
| `/data/guanpu/hls-agent/agent/extract.py` | 解析 OUTPUT_CODE；无标签时回退到裸 C++ |

---

## 遇到的问题与解决

### 1. `HTTP 502 Bad Gateway`

**现象**：笔记本 `./run_baseline.sh` 打 `http://192.168.0.157:8731/v1` 报 502。  

**原因**：EVO 上 halogen 未在跑，或引擎已楔死；API 面偶发仍能响应 `/v1/models`，chat 失败。本地 Clash 等代理对 LAN IP 也不友好。  

**解决**：
- 在 EVO 上起服务；笔记本优先 `./start_tunnel.sh`，`HLS_API_BASE=http://127.0.0.1:18731/v1`
- `run_baseline.sh` 已 `NO_PROXY` + 清掉 `http(s)_proxy`

### 2. 请求挂起数分钟 / 超时，日志没有新的 `POST`

**现象**：TCP 已连上 `8731`，`flash_serve` 长期 ~100% CPU，却长时间无 token、无 POST 完成日志；客户端最终 `TimeoutError`。中途 `kill` 客户端后，后续连 `hi` 也会挂（`KV_SLOTS=1` 僵尸槽）。  

**根因（服务日志原文要点）**：
- `HALOGEN_FLASH_PIN_TRUNK=0` 时权重靠 **page cache 读盘**，不钉在 RAM
- KV 池过大 + 桌面其它进程抢内存时，会 **空转数分钟（满 CPU、无磁盘、无输出）**——不是死机，也不必立刻当崩溃重启
- 客户端超时断开后，单 slot 可能被占死，必须 **整容器重启**

**解决**：
- Lean 配置：`CTX=8192`，`KV_POOL=8192`，`MAX_TOK=128`，`PIN=0`，`WATCHDOG=0`，`ENABLE_THINKING=0`
- 用 `scripts/start_halogen_lean.sh` 启动
- **不要**在生成中途杀客户端；超时先看 `/tmp/halogen-smoke.log` 和 `flash_serve` CPU
- 楔死后：`podman kill` + 脚本重启

### 3. 带 `<think> ... </think>` 的长 smoke prompt 极易拖死/空转

**现象**：`skill/smoke_short_prompt.txt`（要求 think + OUTPUT_CODE）作为首包或大包时，常进入上述空转，600s 仍无结果。  

**解决（smoke 阶段）**：
- 先用 **无 think 标签** 的短 prompt（`smoke_minimal_prompt.txt` / `smoke_output_code_prompt.txt`）
- 正式轨迹再逐步加长；需要 think 时保持 `HALOGEN_ENABLE_THINKING=0`，并避免在 user 里塞复杂 `</think>` 示范（易踩 Qwen3 chat template）

### 4. 解析器只认 `<OUTPUT_CODE>`

**现象**：模型有时只回裸 `int add_one...`，旧 `extract.py` 判失败。  

**解决**：`extract.py` 增加 fallback：无 OUTPUT_CODE 时接受 fenced code 或含 `int `/`#include` 的裸文本。

### 5. 其它已处理环境项（背景）

- UMA Frame Buffer 需偏小，才能给 halogen 足够系统内存  
- tokenizer 需单独放到 `~/halogen-models/tokenizer`  
- 钉权重（大 PIN）在 64GB + 桌面上容易直接 refuse；smoke 用 PIN=0  

---

## 已验证的可复现步骤

**在 EVO：**

```bash
~/hls-agent/scripts/start_halogen_lean.sh
# 可选暖机
curl -sS http://127.0.0.1:8731/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"halogen-qwen3.8-flash-next","messages":[{"role":"user","content":"hi"}],"max_tokens":8}'
export HLS_API_BASE=http://127.0.0.1:8731/v1 HLS_API_TIMEOUT=300
cd ~/hls-agent
python3 run_baseline.py \
  --prompt skill/smoke_output_code_prompt.txt \
  --out outputs/smoke_output_code \
  --max-tokens 64
```

**在笔记本（隧道）：**

```bash
cd /data/guanpu/hls-agent
./start_tunnel.sh   # 若尚未建立
./run_baseline.sh \
  --prompt skill/smoke_output_code_prompt.txt \
  --out outputs/smoke_output_code_laptop \
  --max-tokens 64
```

---

## 下一步建议（你醒了以后）

1. **短真实题**：用缩短版 Luna prompt（去掉冗长 think 示范），仍走 `OUTPUT_CODE`，在 lean 8192 ctx 下试。  
2. **长轨迹 / add_round_key**：需要更大 `HALOGEN_CTX`（如 32k），同时尽量关掉桌面占内存进程，或接受 PIN=0 下更慢、偶发空转；失败先重启 lean 服务再单发一条。  
3. **接反馈环**：把 Vitis HLS / HLS-Eval 接到 `run.py --feedback`（当前只证明了「能生成」）。  
4. **赛题包装**：稳定后再考虑 2-step repair，而不是先上长 RL。

---

## 当前 EVO 服务状态（写报告时）

- 容器名：`halogen-smoke`  
- 日志：`/tmp/halogen-smoke.log`  
- API：`http://127.0.0.1:8731/v1`（笔记本经隧道则 `127.0.0.1:18731`）  
- 配置：CTX/KV=8192，thinking off，PIN=0  
