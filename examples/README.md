# 验证材料索引

- [test-results.txt](test-results.txt)：实际 unittest 命令、环境、时间及逐项结果。
- [evaluation.json](evaluation.json)：13组场景汇总、环境、源码SHA-256；[cases.json](cases.json)为输入及预期。
- [outputs/](outputs/)：逐场景输入、实际输出、Trace及检查结果。文件由 `python -B scripts/evaluate.py` 生成。
- [content-replacement.json](content-replacement.json)：原文30天→仅正文改7天→同步更新标注后的三次实际运行，由 `python -B scripts/check_mutation.py` 生成。
- [retrieval-comparison.json](retrieval-comparison.json)：两个手工查询关闭/开启同义词后的实际检索结果。对比断言在 `tests/test_retrieval_comparison.py`。
- [history.json](history.json)：可传入CLI的上下文示例。

以上早期outputs/evaluation及内容替换是 **Mock流程证据**。真实DeepSeek结果现在单独保存在 [live-evaluation.json](live-evaluation.json)、[live-outputs/](live-outputs/)；首轮9/13、针对性4/4、最终13/13的原始记录保存在 [live-runs/](live-runs/)。详细结论见 [真实评测报告](../docs/10-live-evaluation.md)。HTTP协议单元测试仍使用本地stub，不与真实运行混淆。
