# v2.2.0 设计依据

本文件记录截至 2026-07-28 采用的外部依据与后续使用反馈。v2.2 保留轻量山门与个性化工作区，同时增加证据驱动的课题推进，并把个人节点 EXE、轻量中心 EXE、源码开发和两类运行数据清晰分开。

## 课题推进使用证据闸门

NIH 的转化研究里程碑指导强调可量化的成功标准、时间线以及明确的 go/no-go 决策；UKRI 的逻辑模型则把投入、活动、输出、结果和影响沿证据链连接。OSF Projects 说明了一个科研项目还需要可组织、可协作、可保留的模块化材料，而不只是待办清单。

因此课题推进不按登录天数或主观工时计算进度：

- 建立课题时分别记录科学问题、价值、目标成果、成功标准、当前基础和现实约束；
- 默认生成五个可修改的证据闸门，每个闸门保存通过条件、最小交付、证据与决策；
- 空白闸门不能直接通过；通过当前闸门后才激活下一闸门；
- 失败和停止属于可以记录理由的科研结论，不被伪装成“进度落后”；
- 三日推进计划只负责把当前闸门变成短周期行动，不锁定长期路线。

Crossref REST API 提供无需注册的公开书目元数据查询。v2.2 使用固定 Crossref 地址按需检索，只保存题名、作者、年份、来源、DOI 等公开元数据和本人的关系判断；不自动抓取全文，也不在首页加载时发送关键词。OpenAlex 当前要求 API Key，因而不再作为默认零配置入口。

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

v2.0 的实际使用反馈表明，把闭环的每一步、论文轮播、主动回忆、闪念、奖励和备份同时放入首页，会增加扫描与选择负担。v2.0.1 因此采用渐进呈现：首页只保留山门氛围、四个核心入口和本地/联网双检索，其余动作回到职责明确的独立页面。v2.0.2 只补一条低密度工作台坞，v2.1 将它扩展为最多六个由本人固定的工作区，并在下方只显示最近保存、工作区数量、数据位置和版本；它仍不显示任务、奖励、论文轮播或可编辑表单。窄屏允许自然滚动，避免为了形式上的一屏裁掉内容。

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

## 有证据链的个人工作区

EG 实验、LAMMPS、数据集、ML、MD 和 COMSOL 是可改名的默认模板。动态工作区定义保存名称、图标、类型、排序、色调、启停、首页固定、当前目标、4–6 步流程和组件组合；科研记录仍使用结构化表与附件。这样别人的导航可以完全不同，又不需要为每个人复制一套程序代码。

MLflow 把一次机器学习运行组织为参数、指标和产物，并在模型注册表中强调版本、别名、标签与谱系；ML 工作区因此显式保留数据/代码版本、参数、指标、产物、误差与验证。LAMMPS 官方把输入脚本、数据、日志、dump、restart 等文件区分为不同运行角色；LAMMPS 与 MD 工作区据此分别保留“程序级复现”和“结构—力场—平衡—轨迹—分析”的证据链。COMSOL 的模型管理和验证案例则强调模型版本、几何材料、边界、网格与基准/实验校核，因此不会把 COMSOL 简化成普通附件夹。

所有推荐搭配都能逐项修改和一键恢复。类型变更时不会自动抹掉用户当前设置；只有用户明确点击“恢复推荐搭配”才重置流程与组件。

## 双 EXE 发行与源码开发分离

Python 官方将 Windows embeddable distribution 定位为其他应用的一部分；PyInstaller 则能把解释器和依赖一并打包，让没有安装 Python 的用户运行程序。v2.2 采用 PyInstaller one-file 作为普通用户的首要下载：GitHub Release 页面直接提供 `ResearchOS.exe` 和 `ResearchHub.exe`，减少“下载源码 ZIP、漏解压依赖、只拖出启动器”等误操作。持久数据始终位于 `%LOCALAPPDATA%`，因此 one-file 的临时展开不承担数据职责；需要迁移、U 盘模式和诊断时仍保留完整 ZIP。

程序与数据采用不同生命周期：

- 正式 EXE 默认读取 `%LOCALAPPDATA%\ResearchCultivationOS`；
- 联机中心 EXE 默认读取 `%LOCALAPPDATA%\ResearchCultivationOSHub`；
- U 盘模式通过 `portable.flag` 使用相邻 `user_data/`；
- 源码/CMD 开发继续使用仓库内数据，兼容既有目录；
- 旧版迁移使用 SQLite Backup API 复制数据库，再复制附件目录；
- GitHub Release 只包含程序、说明和校验值，不包含任何个人数据库、配置或科研文件。

GitHub 的公开/私有可见性作用于仓库，而不是单个分支。因此公开 `main` 用于稳定源码，未完成开发保存在另一个本地工作树或单独私有仓库；不能把开发分支推到同一公开仓库后再声称源码不可见。

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

Google Cloud 的重试建议强调：只重试可重试且幂等的操作，使用带抖动的指数退避，区分永久错误并设置上限；RFC 9110 定义了服务端可通过 `Retry-After` 指示等待时间。v2.0.2 起采用“本地成功与联机成功分离”的策略：

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
- https://docs.python.org/3/using/windows.html
- https://pyinstaller.org/en/stable/operating-mode.html
- https://mlflow.org/docs/latest/ml/tracking/
- https://mlflow.org/docs/latest/ml/model-registry/
- https://docs.lammps.org/Run_formats.html
- https://www.comsol.com/blogs/now-available-comsol-multiphysics-version-6-0
- https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories
- https://learn.microsoft.com/en-us/windows/apps/develop/data/store-and-retrieve-app-data
- https://grants.nih.gov/podcast-node/2278
- https://www.ninds.nih.gov/current-research/research-funded-ninds/translational-research/create-bio/create-bio-application-support-library/create-bio-examples-milestones
- https://www.ukri.org/wp-content/uploads/2023/02/ESRC-020223-Funding-Opp-Centres-LogicModelGuidance.pdf
- https://help.osf.io/article/353-welcome-to-projects
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- https://developers.openalex.org/
