# 07 架构调研与决策记录

检索日期：2026-11-02。仅使用厂商官方文档和官方源代码仓库；未安装或复制这些框架，以下为设计思想参考，不构成版本兼容或生产性能背书。

## 官方依据与采纳范围
| 公开方案 | 已核对内容 | 本项目采纳 | 本项目不引入及原因 |
|---|---|---|---|
| 阿里 AgentScope | SDK 分离 ReAct、Toolkit、Model、Context 等职责 | 模型适配、工具接口、循环和证据状态分层，便于独立测试 | 完整服务和长期记忆对本题单进程 CLI 没有必要 |
| 百度 ERNIE Bot Agent | 基于模型 Function Calling 的多工具自动编排；工具、插件与知识库组件分离 | 工具返回标准结果；调度权归模型；知识库替换不影响循环接口 | 不绑定平台知识库，以可审查合成原文验证正确性 |
| 字节 DeerFlow | Agent 核心、middleware、工具执行、上下文与沙箱职责划分 | 执行预算、输入/输出路径边界、观察记录、资料与指令分离 | 浏览器、长任务、多租户和分布式执行超出题目范围 |
| 阿里云百炼 Chat Completions API | 提供兼容 HTTP 接口，可传 messages 和工具定义 | 可配置 URL、模型与密钥的真实 HTTP 模型适配器 | 当前无凭据，不声称真实调用成功 |

## 参考链接
- [AgentScope 官方 README](https://github.com/agentscope-ai/agentscope/blob/main/README.md)
- [阿里云 AgentScope 接入说明](https://www.alibabacloud.com/help/en/agentloop/connecting-to-an-agentscope-python-application-1)
- [百度 ERNIE-SDK 官方仓库](https://github.com/PaddlePaddle/ERNIE-SDK)
- [DeerFlow 官方架构文档](https://github.com/bytedance/deer-flow/blob/main/backend/docs/ARCHITECTURE.md)
- [阿里云百炼 Chat Completions 协议](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)

## ADR-001：使用标准库实现小规模 Agent 内核
决策：Python 3.11+ 标准库，不依赖大型 Agent 框架。优点是离线可复制、依赖少、动态循环可直接审查。代价是仅实现本题需要的模型协议、错误边界与工具注册方式。借鉴的是模块职责，不声称实现了上述框架的全部能力。

## ADR-002：搜索摘要与读取原文分离
决策：search 只给候选摘要，read 提供可核验原文。回答引用必须来自本轮成功读取证据。这样能够测试“搜索后读原文”和“冲突后补查”的真实动作路径，避免摘要被直接当成答案依据。

## ADR-003：冲突保持显式、保守输出
决策：未给适用范围、优先级或废止关系的文档不得以发布日期、较短天数、检索排名自动决胜。先补查，再输出双方原文和缺口。人工 facts 标注只用于合成数据，不可覆盖实际原文。

## ADR-004：区分三类证据
- 单元与黑盒测试：验证确定性代码行为。
- Mock 场景评估：验证输入到输出的执行流程与保护机制。
- 本地 HTTP stub：验证真实适配器协议和新 observation 回传，不代表外部模型智能。
真实模型效果必须后续使用模型凭据另跑并记录，不能将前三类改名为真实效果。
