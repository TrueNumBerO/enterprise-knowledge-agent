# DeepSeek Flash 真实模型评测说明

## 1. 填写本地配置

首次克隆项目时，把根目录的 [`.env.example`](../.env.example) 复制为 `.env`；已有 `.env` 时不要覆盖。打开本地 `.env`，只需在这一行的等号后填写你的 API Key：

```dotenv
KB_AGENT_API_KEY=
```

其他三项已经填好：

```dotenv
KB_AGENT_BASE_URL=https://api.deepseek.com
KB_AGENT_MODEL=deepseek-flash
KB_AGENT_TIMEOUT=60
```

保存 `.env` 后，CLI 和评估脚本在 `live` 模式下会自动读取；无需安装依赖或把密钥设置为系统环境变量。**真正的密钥只放在 `.env`，不要写入本说明、README、案例 JSON 或聊天。** `.gitignore` 已排除 `.env`；可提交的 `.env.example` 始终保持空密钥。如果复制到新机器后没有 `.env`，先把 `.env.example` 复制为 `.env`。

配置采用 UTF-8 文本 `KEY=VALUE`，支持空行、整行 `#` 注释和成对单/双引号；不要添加行尾注释。配置文件不会执行命令或展开变量。不能把文件路径指到项目外。

## 2. 检查配置，不调用模型

在 PowerShell 中执行：

```powershell
Set-Location -LiteralPath 'D:\小影科技\agent题'
python -B scripts/evaluate.py --mode live --check-config
```

成功时显示 `configured: true`、`network_called: false`、模型名称和接口地址；不会显示 API Key，也不会发送请求、产生模型费用或覆盖评测结果。这个检查只验证本地配置格式，不能验证密钥是否真实有效、账户余额和网络连通性。

若显示未配置密钥，检查是否保存了 `.env`，以及是否误保存为 `.env.txt`。若读取到旧模型/旧地址，可能是当前终端的环境变量覆盖了文件。仅在当前终端清除相关覆盖后重试：

```powershell
Remove-Item Env:KB_AGENT_API_KEY,Env:DEEPSEEK_API_KEY,Env:DASHSCOPE_API_KEY,Env:KB_AGENT_BASE_URL,Env:KB_AGENT_MODEL,Env:KB_AGENT_TIMEOUT -ErrorAction SilentlyContinue
```

配置优先级：代码显式参数 > 当前进程环境变量 > 项目 `.env` > 程序内置默认值。进程变量即使为空也覆盖文件。同一来源的密钥优先级为 `KB_AGENT_API_KEY`、`DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`；按本文填写第一项即可。

## 3. 先跑一条真实问题

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -B -m kb_agent --mode live --question '年假需要提前多久申请？' --output examples/deepseek-smoke.json
```

此命令会真正请求 DeepSeek 并产生 API 用量。期望读取 D04，回答提前3个工作日，并提供版本日期和原文。`model_mode` 应为 `live`，Trace 应展示模型选择工具、实际工具结果和后续动作。程序不会在失败时偷偷切换 Mock。

CLI 为保护现有结果拒绝覆盖输出文件；第二次运行请换文件名，例如 `examples/deepseek-smoke-02.json`，或去掉 `--output` 只查看终端输出。

## 4. 执行全部13组场景

```powershell
python -B scripts/evaluate.py --mode live
```

结果保存到：

- `examples/live-evaluation.json`：逐项预期/实际状态、通过数、耗时、模型配置和源码 SHA-256。
- `examples/live-outputs/*.json`：每个用例的输入、实际回答、引用、资料缺口和完整动作 Trace。

默认每个场景最多8轮决策；步数上限场景只执行1轮。按当前13条案例，全套最多97次模型决策调用，每次 DeepSeek 输出上限4096 tokens。每次请求超时为 `.env` 中的60秒，允许配置范围大于0且不超过120秒。实际调用数和费用取决于模型行动和服务商计费；这里没有自动运行，也不预估固定费用。

评估脚本会刷新专用的 `live-outputs` 和 `live-evaluation.json`；若要比较多次实验，请先把上一轮结果复制到**项目内**另一个目录。Mock 结果保留在独立的 `outputs` 和 `evaluation.json`。

退出码：评估 `0` 表示结构化检查全部通过，`1` 表示存在未通过场景，`2` 表示输入或配置错误。单题 CLI 的 `3` 表示未完成或工具失败；`conflict` 和 `needs_clarification` 是合法业务结果，并非程序崩溃。

## 5. 正确理解评测结果

自动检查状态、必要引用、关键片段、引用是否来自本次读取，以及执行上限；通过这些检查不等于所有语义均正确。请重点人工核对：

1. 是否真正回答所问：不能用年假申请提前期回答年度额度，也不能用报销期限回答报销金额上限。
2. 冲突是否读取双方并补查：30天与15天须并列引用，不能擅自选最新日期。
3. 资料外/资料不足是否明确缺口，工具失败是否选择合理重试或停止。
4. Trace 中每一步是否对应实际工具返回；短 `reason` 是动作依据，不是内部思维过程。

当前答案会经过程序的引用校验与抽取式规范化。因此这是**真实模型加现有 Agent 执行器的端到端评测**，并非单独测模型自由生成能力；应同时查看 Trace 里的模型 finish 参数和最终经过验证的输出。报告记录的是请求的模型别名，服务商可能更新别名对应的后端版本。

## 6. DeepSeek 接口选择与边界

官方模型名为 `deepseek-flash`，兼容接口根地址为 `https://api.deepseek.com`；已按 [DeepSeek 官方快速开始](https://api-docs.deepseek.com/) 核对（2026-11-03）。

当前 Agent 每轮执行一个工具动作；若模型提出多个合法只读动作，按顺序只执行首个并在下一轮根据观察重新决策。请求使用 `tool_choice=required`。DeepSeek 官方说明该参数不支持思考模式，因此针对 `api.deepseek.com` 的请求显式设置 `thinking={"type":"disabled"}`，采用非思考模式进行首轮评测；同时省略官方接口未列出的 `parallel_tool_calls` 参数。依据：[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[工具调用示例](https://api-docs.deepseek.com/guides/tool_calls/)。

这仍然是真实大模型驱动的工具决策循环。当前适配器不提供思考模式开关；如以后需要评测思考模式，须另行适配工具调用和消息回传协议，不能仅修改模型名就宣称已支持。

## 7. 常见失败

| 现象 | 检查项 |
|---|---|
| 本地配置读取失败 | `.env` 编码、KEY=VALUE、重复项、未闭合引号；错误只显示行号，不回显内容 |
| `model_error` / incomplete | 密钥有效性、账户状态、网络、接口地址与模型名、请求超时；失败不会降级为Mock |
| 配置检查成功但真实请求失败 | 配置检查没有请求服务器，不能证明密钥有效 |
| `validation_error` 后继续行动 | 引用、未读候选、冲突或事实维度校验要求模型补证，检查后续是否恢复 |
| 达到步数上限 | 查看Trace；评估使用案例内预算，单题可通过 `--max-steps` 调整（最多50） |

2026-11-03 已按用户授权开始真实模型评测；首轮9/13暴露适配问题，原始记录已保留；修复后针对性4/4通过、最终完整13/13通过。完整结果见 [10-live-evaluation.md](10-live-evaluation.md)。密钥不会进入模型消息、Trace、配置检查输出或报告；不要主动把它放进问题或资料中。
