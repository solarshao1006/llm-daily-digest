# LLM Daily Digest

每天北京时间 08:00 由 GitHub Actions 生成低 token 预算的 LLM/AI 日报，并通过 Server 酱推送到微信。

## GitHub Secrets

在仓库 `Settings -> Secrets and variables -> Actions` 里添加：

- `DEEPSEEK_API_KEY`：DeepSeek API key
- `SERVERCHAN_SENDKEY`：Server 酱 Turbo SendKey，通常以 `SCT` 开头

可选变量：

- `DEEPSEEK_MODEL`：默认 `deepseek-v4-flash`
- `DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`

## 手动测试

进入 GitHub 仓库页面：

`Actions -> LLM Daily Digest -> Run workflow`

成功后，微信会收到标题类似 `LLM 日报 2026-07-26` 的消息。

## 成本控制

默认限制：

- arXiv 候选最多 12 篇
- 最终论文最多 3 篇
- 每天重点展开 1 篇论文，讲清核心原理和方法流程
- 最终资讯最多 3 条
- DeepSeek 输出上限 2600 tokens
- 不做 citation chaining、相关工作扩展或代码复现深挖
