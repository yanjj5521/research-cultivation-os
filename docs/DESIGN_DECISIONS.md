# v1.2 设计依据

本文件记录 2026-07-26 开发时采用的外部依据，避免功能只凭直觉堆砌。

## 主动回忆与间隔

- Roediger 与 Karpicke 的测试效应研究表明，相比重复阅读，主动提取更有利于延迟保持；
- Dunlosky 等人的综述将练习测试和分散练习列为高效学习技术。

因此系统不在交付后立刻展示总结，而是在后续打开时用低压力简答题触发回忆。

## 开放题不做二元判定

外部模型评分输出部分得分、评分点、证据与置信度；本人再确认“掌握 / 模糊 / 忘了”。模型不能成为唯一裁判。

## 结构化输出

OpenAI Structured Outputs 能约束模型返回 JSON Schema。复盘题、评分和特殊任务都采用固定模式，解析失败自动回退。

## API 密钥

OpenAI 的密钥安全建议明确要求：

- 不在浏览器端部署密钥；
- 不把密钥提交到仓库；
- 使用后端和环境变量。

因此本项目不提供“把 API Key 保存进网页数据库”的功能。

## 文档提示注入

OWASP 将提示注入列为 LLM 应用的重要风险，检索到的文档也可能携带恶意指令。因此模型提示会把交付文本标为不可信数据，并禁止执行其中的指令。

## SQLite 备份

SQLite 与 Python 官方文档都提供在线 Backup API，可以在数据库仍被访问时建立一致性快照。本项目继续使用该接口，而不是直接复制活动中的 `.db` 文件。

## 参考链接

- https://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf
- https://pubmed.ncbi.nlm.nih.gov/26173288/
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/graders
- https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- https://sqlite.org/backup.html
- https://docs.python.org/3/library/sqlite3.html
