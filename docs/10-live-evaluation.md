# 10 DeepSeek Flash 真实评测报告

## 结论

2026-11-03 已使用用户本地配置的真实 DeepSeek API 完成评测，最终一轮 **13/13通过**。本轮共有 **51次模型决策调用**，用例执行耗时合计 **76.784秒**，平均 **5.906秒/用例**。离线回归 **79/79** 通过。

该结论针对现有13条固定合成用例的单次端到端运行，不是开放域准确率或模型独立能力测量。时间包含网络、工具和程序开销；没有采集token用量和实际账单，不能据此推算费用。

## 环境与复现

- 记录时间（Asia/Shanghai）：2026-11-03 21:02:19 +0800。
- 请求模型：`deepseek-flash`；接口：`https://api.deepseek.com/chat/completions`。
- 非思考模式，temperature=0，每次最多4096输出tokens，每次请求超时60秒。
- 案例未改预期：`examples/cases.json`；默认预算8步，上限场景1步。
- Python 3.13.9，Windows-11-10.0.26200-SP0。
- 运行命令：`python -B scripts/evaluate.py --mode live`。

本机首次受限沙箱连接报WinError10013，请求未到达服务；随后在获准联网的执行环境中运行成功。所有项目输入和输出仍位于项目目录，密钥只从本地.env读取，不写入报告、Trace或模型消息。

## 原始证据与修复过程

| 阶段 | 实际结果 | 证据 |
|---|---|---|
| 单题连通性 | 年假问题3步完成，准确引用D04 | [原始输出](../examples/deepseek-smoke-20261103-205049.json) |
| 首轮完整评测 | 9/13通过，4项失败 | [首轮存档](../examples/live-runs/20261103-205226-baseline/live-evaluation.json) |
| 失败点协议诊断 | 冲突响应一次返回3个read；原适配器拒绝多动作 | [脱敏结构诊断](../examples/deepseek-protocol-diagnostic.json) |
| 修复后针对性复测 | 原4个失败场景4/4通过 | [针对性结果](../examples/live-runs/20261103-205950-targeted/live-evaluation.json) |
| 最终完整回归 | 13/13通过 | [最终存档](../examples/live-runs/20261103-210219-final/live-evaluation.json) |

首轮失败并未删除：conflict、paraphrase、missing_expense_limit在响应解析处中断，missing_annual_allowance使用了incomplete状态。协议诊断直接确认冲突用例的多read响应；同类兼容修复及状态说明明确后，再以原用例、原预算复测。

修复内容：仅在多个提议均为合法search/read时，按模型顺序执行首个，其余不执行、不排队；下一轮仍把实际观察送回模型重新决策。包含finish、非法工具或畸形参数的批次仍拒绝。系统提示明确“有相关资料但缺所问事实”为needs_clarification，而非执行失败。没有硬编码最终模型状态、放宽引用校验或增加默认步数。

## 最终逐项结果

| 场景 | 实际状态 | 检查 | 决策步数 | 耗时（秒） | 原始记录 |
|---|---|---|---|---|---|
| normal | answered | 通过 | 3 | 5.020 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/normal.json) |
| conflict | conflict | 通过 | 8 | 13.543 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/conflict.json) |
| out_of_scope | out_of_scope | 通过 | 3 | 4.316 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/out_of_scope.json) |
| paraphrase | conflict | 通过 | 8 | 11.852 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/paraphrase.json) |
| context | answered | 通过 | 3 | 4.251 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/context.json) |
| transient_search_failure | answered | 通过 | 4 | 5.504 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/transient_search_failure.json) |
| persistent_search_failure | tool_error | 通过 | 4 | 6.040 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/persistent_search_failure.json) |
| single_policy | answered | 通过 | 3 | 4.559 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/single_policy.json) |
| transient_read_failure | answered | 通过 | 4 | 4.285 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/transient_read_failure.json) |
| step_limit | incomplete | 通过 | 1 | 1.304 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/step_limit.json) |
| clarification | needs_clarification | 通过 | 1 | 1.899 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/clarification.json) |
| missing_annual_allowance | needs_clarification | 通过 | 5 | 7.334 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/missing_annual_allowance.json) |
| missing_expense_limit | needs_clarification | 通过 | 4 | 6.876 | [Trace](../examples/live-runs/20261103-210219-final/live-outputs/missing_expense_limit.json) |

## 实际行为核对

项目经理agent逐项审阅最终回答、资料缺口和引用，并检查了冲突的完整动作路径：

- 明确答案：D04支持提前3个工作日；只有D01时回答30天；上下文材料问题引用D03的费用申请单与发票要求。
- 冲突与改写：并列引用D01的30天、D02的15天，并引用D06说明缺少适用范围/优先级。模型第一次尝试结束时被运行器要求补搜，收到校验观察后继续搜索，再结束为conflict。这是实际模型根据反馈调整行动的证据。
- 资料外和信息不足：火星问题不编造答案；年度年假天数与报销额度明确指出缺少所问事实。
- 工具故障：暂时失败后重试并恢复，持续失败结束为tool_error；步数上限返回incomplete。

最终回答经过引用检查与抽取式规范化；原始模型finish参数同时保留在Trace。首轮年假原始草稿曾带入语料未提供的年假天数示例，最终规范化回答未发布这些断言。通过率衡量整个Agent系统，不意味着裸模型不会编造或混淆状态。

## 仍需关注

1. **两组冲突都用满8步。** 其中有一次结束校验失败和额外搜索；当前预算余量小，不应仅凭本轮通过就承诺所有重跑均成功。
2. **测试集是已知合成用例。** 当前修复针对已观察到的协议问题，尚无独立留出集和多次随机运行统计。
3. **模型版本与计费。** 记录的是服务商别名，未固定后端版本；未采集token与实际费用。此次使用非思考模式，不代表思考模式也已验证。
4. **保守输出的边界。** 引用、预算和有限域事实检查由代码保护，通用语义理解、否定/废止关系及复杂适用条件仍不保证。

源码SHA-256见各轮报告。存档中的record字段保留当时的运行路径，查阅历史时应使用同一存档目录下live-outputs中的文件。最新结果另位于 `examples/live-evaluation.json` 和 `examples/live-outputs/`，将来复跑会刷新最新结果，但不会改变上述存档。
