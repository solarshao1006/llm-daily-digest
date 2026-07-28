# Multi-Topic Daily Digests

每天北京时间 08:00 由 GitHub Actions 分别生成三份日报，并通过 Server 酱推送到三个不同微信：

- AI/LLM 论文与资讯
- 中国网络安全、数据安全、信息智能化安全策略
- 辅助生殖 AI 与胚胎植入前遗传学检测（PGT）

## GitHub Secrets

在仓库 `Settings -> Secrets and variables -> Actions` 里添加 repository secrets。

- `AI_LLM_SERVERCHAN_SENDKEY`
- `CHINA_CYBER_SERVERCHAN_SENDKEY`
- `REPRO_SERVERCHAN_SENDKEY`
- `AI_LLM_DEEPSEEK_API_KEY` 或 `DEEPSEEK_API_KEY`

每个 `SERVERCHAN_SENDKEY` 通常以 `SCT` 开头。

如果日志出现 `Missing or invalid SERVERCHAN_SENDKEY`，检查对应主题的 secret：

- `ai_llm` -> `AI_LLM_SERVERCHAN_SENDKEY`
- `china_cyber_strategy` -> `CHINA_CYBER_SERVERCHAN_SENDKEY`
- `repro_ai_pgt` -> `REPRO_SERVERCHAN_SENDKEY`

默认三个主题共用 `AI_LLM_DEEPSEEK_API_KEY`；如果没有配置它，则回退到旧变量 `DEEPSEEK_API_KEY`。如需单独计费或隔离限额，可额外配置：

- `CHINA_CYBER_DEEPSEEK_API_KEY`
- `REPRO_DEEPSEEK_API_KEY`

可选 repository variables：

- `DEEPSEEK_MODEL`：默认 `deepseek-v4-flash`
- `DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`
- `PAPER_INSIGHT_SKILL_CHARS`：默认 `6000`
- `SOURCE_LINK_LIMIT`：自动来源清单最多链接数，默认 `16`
- `ARXIV_TIMEOUT_SECONDS`：arXiv API 读取超时时间，workflow 默认 `60`
- `NCBI_REQUEST_DELAY_SECONDS`：PubMed/NCBI 请求间隔，workflow 默认 `1`
- `AI_LLM_ENABLED`：设为 `false` 可关闭 AI/LLM 推送
- `CHINA_CYBER_ENABLED`：设为 `false` 可关闭中国网络安全策略推送
- `REPRO_AI_PGT_ENABLED`：设为 `false` 可关闭辅助生殖 AI/PGT 推送

未设置这些开关变量时，三个主题默认全部开启。

## Paper Insight Skill

workflow 运行时会 clone：

`https://github.com/Stars-Shen/Paper-insight-skill.git`

并读取：

`paper-insight/SKILL.md`

AI/LLM 和辅助生殖/PGT 主题会优先使用该 skill 的轻量论文精读规则。中国网络安全主题使用 repo 内置的政策、标准、监管、产业安全策略分析框架。

## 手动测试

进入 GitHub 仓库页面：

`Actions -> Multi-Topic Daily Digests -> Run workflow`

一次手动运行会启动 3 个 matrix job：

- `ai_llm`
- `china_cyber_strategy`
- `repro_ai_pgt`

成功后，三个微信分别收到对应主题日报。

## 成本控制

默认限制：

- 每个主题候选最多 12 条
- AI/LLM 主题最多读取前 3 篇 arXiv PDF，每篇最多前 8 页、9000 字符
- 每个主题最终重点展开 1 条内容
- DeepSeek 输出上限 2600 tokens
- 不做 citation chaining、长综述或代码复现深挖

## 内容边界

- 中国网络安全日报以中国官方政策、标准、监管、产业报告为主，不以国外来源或漏洞新闻为主线。
- 辅助生殖 AI/PGT 日报只做文献和研究进展解读，不提供诊疗建议；医学论文来源包含 PubMed/PMC、Human Reproduction、RBMO、Fertility and Sterility、ESHRE，并额外关注 New England Journal of Medicine、The Lancet、BMJ、JAMA、Cell、Nature、Science。
- 所有主题都会在正文后自动追加“自动来源清单”，最多默认 16 条，确保原文链接不会因为模型漏写而丢失；无法确认的信息必须标注待核验。
