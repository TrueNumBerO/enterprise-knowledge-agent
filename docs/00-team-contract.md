# 协作边界与接口（项目经理维护）

- 唯一工作目录：D:\小影科技\agent题。禁止修改或生成目录外文件；Python 使用 -B 或 PYTHONDONTWRITEBYTECODE=1；缓存、临时文件、依赖如需要均放项目内。
- 原始题目.md 保持不变。用 Python 3.11+ 标准库实现，默认不安装依赖。
- 包：src/kb_agent；命令 python -B -m kb_agent（先设 PYTHONPATH=src）。unittest discover -s tests。
- 决策接口：Model.decide(messages: list[dict], tools: list[dict]) -> dict。动作字典为 {"action":"search"|"read"|"finish", "arguments":{...}, "reason":"简短依据"}。finish arguments 包含 status(answered/conflict/needs_clarification/out_of_scope/tool_error/incomplete)、answer、citations（[{doc_id,version_date,quote}]）、gaps（字符串列表）。不要求输出内部思维。
- 工具：KnowledgeBase(path, fail_searches=0, fail_reads=0)；search(query, limit=5)->dict；read(doc_id)->dict。检索返回候选摘要（不可直接作为引用依据），读取返回完整原文。返回 {ok:bool,...}，失败有 error/code/retryable。KnowledgeBase 可选中文同义词检索。
- 数据格式 JSON：{"documents":[{"doc_id":"D01","version_date":"2026-01-01","title":"...","content":"...","topic":"expense_deadline","facts":[{"key":"expense_deadline","value":"30天","quote":"..."}]}]}。facts 为合成资料的人工标注，用于离线验证和确定性证据检查，不声称自动理解任意文档。禁止只改 content 后仍相信过期 facts。
- 运行器：Agent(model, knowledge_base, max_steps=8).run(question, history=None)->dict。输出含 question,status,answer,citations,gaps,trace,model_mode；trace 包含 step,action,arguments,observation,reason，仅记录实际发生动作，不预编造日志。
- 模型真实模式：标准兼容 Chat Completions HTTP，模型每步看到最新 observation，输出结构化动作；限制超时/次数/参数，禁止网络错误后悄悄切 mock。离线模型明确 model_mode=mock；根据观测动态执行，是流程验证而非真实模型能力证据。
- 引用校验：只允许本次 read 成功的文档，ID/版本/逐字片段一致；无引用不可 answered；未知动作、解析错误、步数耗尽返回明确未完成。对本地标注同主题冲突需防止任意选答案。
- CLI：--question, --history PATH(JSON list), --data PATH(默认 data/knowledge.json), --mode mock|live(默认 mock), --max-steps, --fail-searches, --fail-reads, --output PATH(JSON)。输入和输出路径限定本项目；不打印密钥。
- 分工：开发 agent 拥有 runtime.py/models.py/cli.py/__main__.py/__init__.py；检索 agent 拥有 retrieval.py、data/*、examples/cases.json；测试 agent 拥有 tests/*、scripts/evaluate.py；项目经理拥有 docs/*、README.md、配置与集成，并协调跨模块修改。
- 所有 agent 主动向项目经理报告接口疑问、阶段结果和缺陷，结束提交文件清单与验证结果。各模块先汇报再做跨归属修改。
