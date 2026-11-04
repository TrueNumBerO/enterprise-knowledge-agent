# GitHub 上传与考核提交指南

本文是操作指南，不表示已创建远程仓库或已上传。所有本地项目命令均在 `D:\小影科技\agent题` 执行，Git 身份配置只作用于本仓库。

## 1. 创建空仓库

登录 GitHub 账号 `TrueNumBerO`，打开 <https://github.com/new>。

- Owner：`TrueNumBerO`。
- Repository name：建议 `enterprise-knowledge-agent`；下文命令按此名称编写，换名时一并替换远程 URL。
- Description：企业知识问答 Agent：DeepSeek 工具决策、引用校验与真实评测。
- Visibility：建议先选 Private；若考核方允许公开且你愿意公开全部提交材料，也可选 Public。
- 不勾选初始化 README，不添加 .gitignore 或 License，本地已有项目文件。

点击 Create repository。账号主页不是项目仓库地址；创建成功后，本例仓库地址应为 `https://github.com/TrueNumBerO/enterprise-knowledge-agent`。本指南未验证该名称是否已被占用。

依据：[GitHub 官方本地代码上传说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 2. 提交前补齐真实信息

现有项目已包含 README、src、tests、examples、data、docs/01–05、依赖说明和空密钥配置模板。examples 中保留真实模型首轮失败、修复和最终评测记录。

- 当前原题只写“企业知识问答 Agent”，未给明确数字题号；按考核方正式编号填写，不能自行编造。
- 阅读 `docs/04-ai-usage.md`，按实际情况补充自己完成的修改和验证。AI 已执行的测试不能写成自己亲自执行。
- `docs/05-retrospective.md` 已记录可核对时间片段及未精确计时的事实；只补充能核实的用时。
- README 中“GitHub提交尚未执行”是准备阶段状态；实际上传成功后更新，再提交新 commit。最终提交 SHA 以所有修改推送完成后的值为准。

## 3. 初始化本地仓库并检查提交内容

在 PowerShell 依次执行，每一步成功后再执行下一步。以下初始化命令用于当前尚无 `.git` 的项目，不要在其他目录执行：

```powershell
Set-Location -LiteralPath 'D:\小影科技\agent题'
git init -b main
git config --local user.name "TrueNumBerO"
$submissionEmail = Read-Host '请输入 GitHub Settings > Emails 中显示的提交邮箱（可用 noreply 邮箱）'
git config --local user.email "$submissionEmail"

git check-ignore .env
git add -- .gitattributes .gitignore .env.example README.md requirements.txt 题目.md src tests scripts data docs examples
git ls-files -- .env
git diff --cached --stat
git status --short
```

检查结果：`git check-ignore .env` 应输出 `.env`；`git ls-files -- .env` 应没有输出。待提交文件应包括 `.env.example`，不能包括真实 `.env`、密钥或隐私资料。不要使用强制添加被忽略文件的 `git add -f`。

上述 `user.email` 是 Git 提交邮箱，不是 GitHub 密码或模型 API Key。可从 GitHub Settings → Emails 复制 GitHub 提供的 noreply 地址；`--local` 不改变其他仓库的配置。依据：[GitHub 提交邮箱设置](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)。

## 4. 提交并推送

确认文件清单正确后执行：

```powershell
git commit -m "Complete enterprise knowledge agent with evaluation evidence"
git remote add origin https://github.com/TrueNumBerO/enterprise-knowledge-agent.git
git remote -v
git push -u origin main
```

按本机 Git 凭据管理器提示完成 GitHub 登录；不要将 DeepSeek API Key 用于 GitHub 认证。`git push` 成功后刷新仓库页面，根目录应直接显示 README、src、tests、examples、data、docs，而不是再包一层 `agent题` 文件夹。上传失败时先处理报错，不要使用强制推送绕过问题。

若提示 origin 已存在，先运行 `git remote -v` 核对地址，不重复添加；若远程已经有 README 等提交，不直接覆盖远程历史。

后续修改项目文件后，检查 `git status --short`，按修改文件的实际路径执行 `git add -- <路径>`、`git commit -m "说明本次修改"`、`git push`。每次成功推送后，最终 SHA 都可能变化。

## 5. 开放评审访问

Private 仓库需要考核方指定的 GitHub 评审账号：仓库 Settings → Collaborators → Add people，邀请该账号，并确认对方接受邀请。仅填写仓库 URL 不能使私有仓库自动可读。个人仓库的协作者权限由 GitHub 的个人仓库权限模型决定。

依据：[GitHub 邀请个人仓库协作者说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。

## 6. 获取最终 SHA 并交付

所有修改已提交、推送成功后执行：

```powershell
git status --short
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

`git status --short` 应无未提交变更；后两条命令的 commit SHA 应一致。复制完整的 40 位 SHA，填写考核提交入口：

```text
题号：按考核方正式编号填写（企业知识问答 Agent）
GitHub URL：https://github.com/TrueNumBerO/enterprise-knowledge-agent
最终 commit SHA：填写实际输出的完整 40 位 SHA
运行方式：Python CLI，命令见仓库 README
评审权限：公开可读 / 私有仓库已邀请指定账号且对方已接受
```

不能在产生该 commit 前把它自己的 SHA 写入该 commit 内容；最终 SHA 放在考核提交表单或交付消息中即可。报告中的源码 SHA-256 是文件指纹，与此处 Git commit SHA 不同。

评审者可直接按 README 运行离线测试；需要复跑真实模型时，自行从 `.env.example` 创建本地 `.env` 并配置自己的密钥。历史真实评测记录已在 examples 中，无需你的真实密钥即可查阅。
