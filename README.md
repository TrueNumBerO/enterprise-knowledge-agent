# 企业知识问答 Agent

小影 AI Agent 开发题本地交付：版本化合成制度 → 模型选择搜索/读原文/结束 → 工具结果反馈 → 有依据回答或明确资料缺口。

**当前交付：本地项目、离线验证及DeepSeek Flash真实评测。** 最新真实评测13/13通过，首轮9/13和修复记录完整保留。GitHub提交尚未执行。

上传与正式提交步骤见 [GitHub交付指南](docs/12-github-submission.md)。

本地验收：**79 项测试、13 组场景、3 组内容替换实验全部通过**。详见 [测试报告](docs/03-evaluation.md)。

真实模型结果：[DeepSeek评测报告](docs/10-live-evaluation.md)（最终一轮51次模型决策、约76.8秒；固定合成测试集，不代表通用准确率）。

## 评审入口

1. 阅读原题 `题目.md`、[需求](docs/01-requirements.md)与[方案](docs/02-solution.md)。
2. 执行下面的测试和场景评估，查看 [评估说明](docs/03-evaluation.md)、`examples/evaluation.json` 和 `examples/outputs/`。
3. 对照[AI 使用记录](docs/04-ai-usage.md)、[复盘](docs/05-retrospective.md)、[分工计划](docs/06-development-plan.md)和[大厂架构调研](docs/07-architecture-research.md)。

## 环境与快速运行

需要 Python 3.11+；本机验证使用 Python 3.13.9。零第三方依赖，无需 pip install。所有运行、输出、测试临时文件均在项目目录内。

Windows PowerShell：

```powershell
Set-Location -LiteralPath 'D:\小影科技\agent题'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
python -B -m kb_agent --question '报销期限多久？'
python -B -m unittest discover -s tests -v
python -B scripts/evaluate.py
python -B scripts/check_mutation.py
```

Linux/macOS（复制整个项目后在项目根目录运行）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B -m kb_agent --question '报销期限多久？'
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/evaluate.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/check_mutation.py
```

## 真实模型入口

现已支持自动读取项目根目录 `.env`，并在 [配置模板](.env.example) 中为 **DeepSeek Flash** 预填接口和模型名称。首次克隆项目时，将 `.env.example` 复制为 `.env`；已有 `.env` 时保留原文件。在本地 `.env` 的 `KB_AGENT_API_KEY=` 后填写密钥并保存，该文件已被 Git 忽略。离线 Mock 无需配置密钥。详细步骤见 [DeepSeek真实评测说明](docs/09-deepseek-evaluation.md)。

```powershell
# 只检查配置，不请求网络，不显示密钥。
python -B scripts/evaluate.py --mode live --check-config
# 填好密钥后，主动执行此命令开始真实评测。
python -B scripts/evaluate.py --mode live
```

程序在 live 模式自动读取 `.env`，Mock 不读取配置。当前进程环境变量优先于文件；如果存在旧设置，请按说明清除。配置快照固定于一次评测开始时，报告只记录不含密钥的模型与接口信息。真实调用会发送问题、历史和检索到的合成资料；未执行真实调用时不声称模型质量已验收。

## 命令参数与输出

`--question` 必填；`--mode mock|live` 默认 mock；`--data` 默认 `data/knowledge.json`；`--history` 为 JSON 对话数组；`--max-steps` 默认 8；`--fail-searches` / `--fail-reads` 注入前 N 次工具故障；`--output` 保存 JSON。传入路径必须在项目目录内；CLI 拒绝覆盖已有输出文件，保存时请选择新文件名。评估脚本会刷新其专用的 examples/outputs 和汇总文件。运行 `python -B -m kb_agent --help` 查看参数。

每份 JSON 包含 question、status、answer、citations（doc_id/version_date/quote）、gaps、trace、model_mode。Trace 逐条记录实际动作、参数、观察、简短依据，不输出内部思维过程。

| 状态 | 含义 | CLI 退出码 |
|---|---|---|
| answered | 有原文支持的回答 | 0 |
| conflict | 多份证据矛盾，无法确定适用制度 | 0 |
| needs_clarification | 缺少必要信息，需要追问 | 0 |
| out_of_scope | 检索资料无法支持问题 | 0 |
| tool_error | 工具失败，无法完成 | 3 |
| incomplete | 步数耗尽、模型错误或验证未通过 | 3 |
| 配置/输入错误 | 参数、路径或配置无效 | 2 |

## 设计取舍

采用单 Agent 有界循环，模型、检索、证据验证和 CLI 分离。开发工作由项目经理、开发、检索资料和测试 agent 协作完成；产品本身不需要多 Agent。借鉴阿里 AgentScope、百度 ERNIE Bot Agent、字节 DeerFlow 的组件边界，未引入其完整运行时。原始来源和取舍见 [调研记录](docs/07-architecture-research.md)。

最终回答采用保守的原文抽取，防止“引用是真的、答案却捏造”。中文同义词规则与人工事实标注适用于这里的有限合成资料，不是通用语义检索或自动事实证明系统。

