# v1.5 设计依据

本文件记录 2026-07-27 开发时采用的外部依据，避免功能只凭直觉堆砌。

## 修炼任务与每日任务分层

PMI 将项目描述为由任务、活动与交付构成、为特定结果服务的临时工作；Gollwitzer 的实施意图研究则强调把目标落实为“何时、何地、如何行动”的具体计划。

因此本系统将两层数据分开：

- 修炼任务保存跨天能力或成果及验收证据；
- 每日任务保存当天可执行行动、时长与最小交付；
- 每日行动可关联里程碑，但不能自动完成里程碑。

这避免把“学会 CV 判读”和“今天看一张 CV 图”当作同一件事。

## 固定经验规则

经验值属于软件规则，不属于学习计划内容：

- 导入文本中的 `XP / 经验 / 修为` 全部忽略；
- 每日行动仅按统一时长档位计算；
- 修炼里程碑仅按小成、进阶、突破三档计算；
- 导入计划本身不奖励经验，避免反复导入刷取修为。

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

## 首页渐进呈现

Nielsen Norman Group 将渐进式呈现定义为把高级或低频功能推迟到次级界面，以降低学习和操作负担。因此山门首页只保留一个主动作和四个大入口；完整菜单、工作区与设置进入侧栏，不删除低频能力。

## 可改名但保持稳定

W3C 的一致导航与一致识别原则要求同一功能在一组页面中保持可预测的顺序与标识。系统因此只让用户修改显示名称，不允许显示名称替代内部路由键：

- 境界使用稳定 `realm key`；
- 导航使用稳定 `nav key`；
- 工作区使用稳定 `workspace_key`；
- 个性化包改变外观名称，数据库关联仍保持不变。

用户发起的改名会在所有页面一致应用。

## 个人工作区

EG 实验、LAMMPS 和数据集被降级为可改名的默认模板。动态工作区定义只保存名称、图标、类型、排序和启用状态；科研记录仍使用结构化表与附件。这样别人的导航可以完全不同，又不需要为每个人复制一套程序代码。

## 高频导航保持展开

W3C 建议使用清晰、可识别且一致的导航，并通过标题、留白和分组帮助用户理解页面结构。因此桌面侧栏不再把“我的工作区”与“系统工具”折叠起来，而是按使用频率固定为：

1. 今日修炼；
2. 知识与交付；
3. 我的工作区；
4. 秘境与成长；
5. 协作与系统。

移动端受可用宽度限制，仍使用整栏抽屉，但抽屉内部的功能组保持展开。首页继续采用渐进呈现，不把完整侧栏内容重复堆到山门页面。

## 复盘、秘境与雷劫分离

“温故知新”只承担低压力主动回忆；万象秘境承担跨材料综合迁移；五问雷劫只承担大境界突破。三个入口仍复用同一套受控证据来源与开放题评分，但记录、奖励和使用条件相互独立。

雷劫不是可反复刷取的复盘模式。第一道关口位于金丹后期进入元婴前期之前；此后只在修为达到下一大境界门槛、且该关口尚未通过时开启。通过记录使用稳定 `gate_key` 保存，避免改名影响进度。

## 39 阶境界与经验曲线

境界严格使用 39 个稳定阶段：凡人；锻体、练气、筑基、金丹、元婴、化神、练虚、合体、大乘、渡劫各前中后期；再到人仙、地仙、天仙、玄仙、金仙、大罗金仙、准圣、圣人。

每一阶的所需修为都显式写在 `services/progression.py`，并满足逐阶不同、总体递增。系统不使用难以核查的隐藏倍率公式；页面同时显示“本阶所需”和“累计门槛”。固定日课奖励仍保持小幅、可预测，避免导入计划改变公共成长规则。

## 规模化联机只预留接口

OpenAPI 用语言无关的格式描述 HTTP 接口，适合先固定客户端与未来服务端的边界。v1.5 因此增加：

- 可替换的同步后端协议；
- 默认关闭且不排队的 `disabled` 实现；
- 兼容旧小团队中心的 `legacy_hub` 适配器；
- 不可启用的 `cloud_v2` 预留槽；
- 能力发现端点与 OpenAPI 草案。

这不等于已经建设千人服务。真正上线仍需 OAuth 2.0/OIDC、支持租户隔离的 PostgreSQL、幂等写入、审计、限流、游标同步、对象存储和恢复演练。OAuth 令牌安全遵循 RFC 9700；数据隔离可使用 PostgreSQL 行级安全策略。科研原文件默认继续只保存在本人节点。

## 每日古诗

诗句池保存在本地，使用日期序号确定当天诗句。同一天刷新结果稳定，第二天自动轮换；用户可导入自己的诗句池。该功能不依赖联网、后台任务或外部 API。

## 开放格式知识库

CommonMark 将 Markdown 定义为用于结构化文档的纯文本格式，并强调跨实现兼容性。知识库导出因此同时提供 Markdown、JSON 和原附件；SQLite 完整备份仍保留，但不作为唯一可读格式。

## 闭关倒计时与动效

- MDN 说明 `localStorage` 数据可跨浏览会话保存，因此闭关目标和结束时间保存在当前站点的浏览器存储中；
- 浏览器后台计时回调可能延迟，所以倒计时按绝对结束时间重新计算，而不是假设每次回调都恰好间隔一秒；
- W3C 建议支持用户的减少动态偏好并去掉不必要动画，因此山雾等装饰动效遵守 `prefers-reduced-motion`。

## 参考链接

- https://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf
- https://pubmed.ncbi.nlm.nih.gov/26173288/
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/graders
- https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- https://sqlite.org/backup.html
- https://docs.python.org/3/library/sqlite3.html
- https://m3.material.io/components/navigation-drawer/overview
- https://m3.material.io/components/search/overview
- https://www.nngroup.com/articles/progressive-disclosure/
- https://www.pmi.org/about/what-is-a-project
- https://cancercontrol.cancer.gov/sites/default/files/2020-06/goal_intent_attain.pdf
- https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html
- https://www.w3.org/WAI/WCAG21/Understanding/consistent-identification.html
- https://commonmark.org/
- https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout
- https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html
- https://www.w3.org/WAI/tips/designing/
- https://spec.openapis.org/oas/v3.2.0.html
- https://www.rfc-editor.org/rfc/rfc9700.html
- https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- https://www.rfc-editor.org/rfc/rfc9110.html
