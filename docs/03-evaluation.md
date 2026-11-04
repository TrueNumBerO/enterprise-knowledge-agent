# 03 评估、实际结果与边界

## 评估结论
本地离线验收已通过。场景评估 **13/13** 通过，文档替换实验 **3/3** 通过；完整 unittest **79/79** 通过，逐项结果见 [test-results.txt](../examples/test-results.txt)。其中 HTTP 适配器测试采用传输边界 stub，不是外部模型效果证明。

最终场景记录时间（Asia/Shanghai）：2026-11-03 21:01:40 +0800。环境：Python 3.13.9，Windows-11-10.0.26200-SP0。本节记录离线测试；用户随后授权的DeepSeek真实评测见 [10-live-evaluation.md](10-live-evaluation.md)，最终13/13通过。未发布GitHub。

## 可复制命令
在项目根目录设置 `PYTHONPATH=src` 后执行：

```text
python -B -m unittest discover -s tests -v
python -B scripts/evaluate.py
python -B scripts/check_mutation.py
```

评估脚本会刷新其专用输出，不会修改原始知识库或题目。每个场景文件包含原始 input、实际 output（含 trace）和 checks。`evaluation.json` 与 `content-replacement.json` 记录源码 SHA-256；代码变更后应重新生成，不能沿用旧通过结果。

## 全场景结果
| 场景 | 预期状态 | 实际状态 | 步数 | 证据 |
|---|---|---|---|---|
| normal | answered | answered | 3 | [实际输入/输出/Trace](../examples/outputs/normal.json) |
| conflict | conflict | conflict | 6 | [实际输入/输出/Trace](../examples/outputs/conflict.json) |
| out_of_scope | out_of_scope | out_of_scope | 3 | [实际输入/输出/Trace](../examples/outputs/out_of_scope.json) |
| paraphrase | conflict | conflict | 6 | [实际输入/输出/Trace](../examples/outputs/paraphrase.json) |
| context | answered | answered | 3 | [实际输入/输出/Trace](../examples/outputs/context.json) |
| transient_search_failure | answered | answered | 4 | [实际输入/输出/Trace](../examples/outputs/transient_search_failure.json) |
| persistent_search_failure | tool_error | tool_error | 3 | [实际输入/输出/Trace](../examples/outputs/persistent_search_failure.json) |
| single_policy | answered | answered | 3 | [实际输入/输出/Trace](../examples/outputs/single_policy.json) |
| transient_read_failure | answered | answered | 4 | [实际输入/输出/Trace](../examples/outputs/transient_read_failure.json) |
| step_limit | incomplete | incomplete | 1 | [实际输入/输出/Trace](../examples/outputs/step_limit.json) |
| clarification | needs_clarification | needs_clarification | 1 | [实际输入/输出/Trace](../examples/outputs/clarification.json) |
| missing_annual_allowance | needs_clarification | needs_clarification | 3 | [实际输入/输出/Trace](../examples/outputs/missing_annual_allowance.json) |
| missing_expense_limit | needs_clarification | needs_clarification | 6 | [实际输入/输出/Trace](../examples/outputs/missing_expense_limit.json) |

六个题目验收点分别由 normal（明确答案）、conflict（冲突）、out_of_scope（资料外）、paraphrase（改写）、context（上下文）和三类工具故障场景覆盖。clarification、missing_annual_allowance 和 missing_expense_limit 补充信息不足验证。step_limit 验证上限不是假成功。

## 不同观察产生不同路径
- 单制度：search → read D01 → finish answered。见 [single_policy](../examples/outputs/single_policy.json)。
- 冲突：search → read D01 → read D02 → search 适用范围/优先级 → read D06 → finish conflict。见 [conflict](../examples/outputs/conflict.json)。
- 暂时检索故障：search 失败 → 模型再次选择 search → read → finish。见 [transient_search_failure](../examples/outputs/transient_search_failure.json)。
- 持续故障：两次实际失败后 finish tool_error。见 [persistent_search_failure](../examples/outputs/persistent_search_failure.json)。

这些 trace 是执行程序记录的真实工具操作，动作选择来自显式 Mock，只证明不同观察下的工程流程。真实模式逐轮模型请求和观察回送的构造另由 `tests/test_live_protocol.py` 验证。

## 内容替换实验
[content-replacement.json](../examples/content-replacement.json) 保存三次实际输入与完整输出：

| 替换条件 | 预期/实际 | 检查含义 |
|---|---|---|
| 原文和标注均为30天 | answered，引用30天 | 原始资料可用 |
| 正文改7天，旧标注仍30天 | needs_clarification | 不保留过期30天结论，要求核实资料 |
| 正文和标注都改7天 | answered，引用7天 | 答案依赖当前资料，不是写死30天 |

此外，runtime 测试用同主题多文档检查未读候选、读取失败、缺失标注、正文与标注不一致，防止“没检测到冲突”被误判为“已证明一致”。

## 检索改进
[retrieval-comparison.json](../examples/retrieval-comparison.json) 对同一检索函数关闭/开启同义词进行实测。两个手工查询的平均 Recall@2 从 **0.5 → 1.0**；“垫付最迟何时报账？”从无候选变为 D01/D02 排前两。输入见 [retrieval-evaluation.json](../data/retrieval-evaluation.json)，可执行对比测试见 `tests/test_retrieval_comparison.py`。样本仅2条，不能代表真实企业召回率。

## 独立测试覆盖与修复
测试分别覆盖检索、CLI、运行器、评估工具和真实适配器协议；包含伪造引用、引用错误版本、摘要冒充原文、真引用下的假结论、未读冲突文档、步数耗尽、异常模型、历史泄漏、同领域资料不足、非法 JSON 字段类型和输出路径越界。

初版曾有失效标注计数未传到模型、资料外问题误判为指代、中文编码不一致的问题；续办审查还发现年度额度与申请提前期混淆、历史意图污染、非字符串 action/role 未受控，以及双方引用共有句却声称展示冲突。均已针对性修复。测试团队修正了只断言 `status != answered` 的弱测试，改为检查正确追问状态和明确缺口，并确保冲突测试先经过实际搜索、读取和补查。

## 未验证与已知限制
1. **真实验证限于固定样本。** 已另行完成DeepSeek的13组真实场景，见10号报告。没有独立留出集、多次重复统计、token用量或费用数据；Mock和HTTP stub仍不能单独作为模型效果证明。
2. **有限域语义。** 同义词、主题和事实维度是有限规则；复杂改写、多主题问题和超长对话不保证正确理解。
3. **标注只做结构一致性验证。** quote 在 content、value 在 quote 不等于通用语义蕴含；否定、废止、适用范围或优先级变化须人工审核。多份资料无可靠标注时保守追问。
4. **不能自动消解所有冲突。** 已知同键不同值会被披露，不按日期或更严格值裁决；明确废止和复杂适用关系不是当前通用求解能力。
5. **抽取式输出。** 可以阻止额外编造事实，但仅引用原文不自动证明完整回答了任意问题；真实模式仍需语义审查。
6. **工程规模。** 单进程只读 CLI、合成资料、无企业权限或持久化会话服务；不代表生产部署和大规模负载已通过。
7. **平台。** 本机在 Windows/Python 3.13.9 验证。README 提供其他平台启动方法，未在其他操作系统执行测试。

真实评测复现：配置模型后运行 `python -B scripts/evaluate.py --mode live`，独立保存 live 输出，再逐项人工检查，不把格式/状态检查当成最终语义判定。远程 GitHub URL 与 commit SHA 按用户确认范围留待后续提交。

## DeepSeek配置增量验证

新增本地.env自动加载、进程/文件配置优先级、密钥别名、配置错误脱敏、项目路径限制、Mock不读取密钥、DeepSeek非思考模式请求参数及无网络配置检查。测试使用人工fixture密钥和HTTP stub；未调用真实DeepSeek。使用步骤见 [09-deepseek-evaluation.md](09-deepseek-evaluation.md)。
