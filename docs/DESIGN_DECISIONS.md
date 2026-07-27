# v2.0.2 设计依据

本文件记录 2026-07-27 开发时采用的外部依据与后续使用反馈。v2.0.2 保留 v2.0.1 的轻量山门，只在底部增加默认工作台与联机状态，不恢复高密度仪表盘。

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

## 游戏化服务于科研意义

Sailer 等人的实验表明，不同游戏元素对自主、胜任和社会联结的作用并不相同；2024 年的元分析也指出，教育游戏化对内在动机的证据并非简单一致。积分、等级和徽章不能自动让学习变得有趣。

因此 v2.0 不增加公共排行榜、随机奖励或断签惩罚，而把游戏化用于：

- **自主**：用户可在今日修炼、闭关专注和资料检索之间选择合适的起点；
- **胜任**：真实交付、固定奖励和本阶进度在对应页面中提供反馈；
- **意义**：论文卡、最小交付和能力里程碑都指向真实科研资产；
- **恢复**：漏一天不会抹掉近七天的行动，也不会生成补课债务。

奖励只来自已经写入活动与资材账本的真实行动；未完成时不会生成虚假的随机宝箱。

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

## 稳定启动线索与轻量首页

Lally 等人的真实世界研究让参与者在相同情境中重复一个自选行为；后续习惯研究也将稳定情境下的重复视为形成情境—行动联结的关键。Gollwitzer 与 Sheeran 的实施意图研究则表明，把目标转成明确的“何时、何地、如何开始”能缓解启动失败。

科研闭环仍保持同一条行动顺序：

```text
看见唯一下一步 → 10 分钟启动 → 提交证据 → 次日温故
```

v2.0 的实际使用反馈表明，把闭环的每一步、论文轮播、主动回忆、闪念、奖励和备份同时放入首页，会增加扫描与选择负担。v2.0.1 因此采用渐进呈现：首页只保留山门氛围、四个核心入口和本地/联网双检索，其余动作回到职责明确的独立页面。v2.0.2 只补一条低密度工作台坞，承载 ML、MD、COMSOL 和联机状态；它不显示任务、奖励、论文轮播或可编辑表单。窄屏允许自然滚动，避免为了形式上的一屏裁掉内容。

联网检索仍只在用户点击时发生，首页加载不自动发送研究关键词。论文卡与知识条目没有删除，继续保存在藏经阁、搜索结果和条目详情中。

## 可行动反馈，而非数据堆积

学习分析仪表盘研究强调，反馈需要帮助学习者理解目标并采取下一步行动，而不是只展示描述性数字。v2.0.1 进一步把这些反馈放回今日修炼、温故与个人主页：首页不再承担仪表盘职责，只负责“找到资料或进入正确场景”。

## 可改名但保持稳定

W3C 的一致导航与一致识别原则要求同一功能在一组页面中保持可预测的顺序与标识。系统因此只让用户修改显示名称，不允许显示名称替代内部路由键：

- 境界使用稳定 `realm key`；
- 导航使用稳定 `nav key`；
- 工作区使用稳定 `workspace_key`；
- 个性化包改变外观名称，数据库关联仍保持不变。

用户发起的改名会在所有页面一致应用。

## 个人工作区

EG 实验、LAMMPS、数据集、ML、MD 和 COMSOL 被降级为可改名的默认模板。动态工作区定义只保存名称、图标、类型、排序和启用状态；科研记录仍使用结构化表与附件。这样别人的导航可以完全不同，又不需要为每个人复制一套程序代码。

ML 与 MD 不被混成同一数据表：公共数据只作为先验与边界，自己的实验决定最终验证；MD 轨迹与描述符独立建模，再在结论层与实验互证。COMSOL 工作区同样把模型假设、边界条件、网格无关性和实验校核放在同一证据链中。

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

## 轻量联机的故障隔离

Google Cloud 的重试建议强调：只重试可重试且幂等的操作，使用带抖动的指数退避，区分永久错误并设置上限；RFC 9110 定义了服务端可通过 `Retry-After` 指示等待时间。v2.0.2 因此采用“本地成功与联机成功分离”的策略：

- 自动同步超时 1.5 秒，避免网络拖慢正常交付；
- 唯一事件 UUID 使重复请求保持幂等；
- 临时错误指数退避并加入确定性抖动，同时遵守服务端 `Retry-After`；
- 连续失败触发至少 5 分钟熔断，避免级联重试；
- 认证与参数错误直接转人工处理；
- 服务器健康检查真实访问 SQLite，降级时返回 503 与 `Retry-After`；
- SQLite 使用 WAL、忙等待和 Backup API，数据库文件不放进共享盘让多人直接打开。

管理员采用“首次自动创建、之后不可自助提权”的最小权限模型。随机初始凭据只留在中心主机；管理员修改密码后一次性文件销毁。网页登录具有 CSRF 校验、登录限速、安全响应头与可选 Trusted Host；公网部署仍必须放在 HTTPS 反向代理后。

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
- https://pubmed.ncbi.nlm.nih.gov/16507066/
- https://doi.org/10.1002/ejsp.674
- https://www.sciencedirect.com/science/article/pii/S074756321630855X
- https://link.springer.com/article/10.1007/s11423-023-10337-7
- https://www.sciencedirect.com/science/article/pii/S1096751620300348
- https://hbr.org/2011/05/the-power-of-small-wins
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
- https://docs.cloud.google.com/storage/docs/retry-strategy
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/backup.html
- https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
