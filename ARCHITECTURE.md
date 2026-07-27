# 问道科研 v1.2 架构

## 1. 设计目标

v1.2 优先解决五件事：

1. 计划可以随科研状态随时变化；
2. 每次学习必须留下可检查交付；
3. 复盘只能基于本人交付的受控关键文本；
4. 游戏系统必须映射真实科研能力，不另造一套空转数据；
5. 版本升级不能破坏科研资料和个性化。

旧版 `research_tracks` 与 `research_plan_items` 继续保留在数据库中，只作为兼容数据，不再出现在主导航。`/foundation` 会转到近期计划，避免升级时直接删除用户旧数据。

## 2. 本地优先与轻量联机

```text
个人节点（每人一份）
├─ FastAPI + Jinja2
├─ research_os.db
├─ uploads / deliveries / simulations
├─ 近期计划、复盘、炼丹
└─ 离线同步队列
          │
          └── HTTPS/API ── 轻量同行会
                           ├─ 身份与公开主页
                           ├─ 轻量资产
                           ├─ 个性化
                           ├─ 资料链接卡
                           └─ 版本包
```

论文、实验数据、图片、代码和交付附件不进入轻量中心。中心数据库只能由中心 FastAPI 进程访问，成员不能共享打开同一个 SQLite 文件。

## 3. 近期计划

`services/prompt_builder.py` 从下列信息生成计划提示词：

- 当前目标；
- 尚未完成的近期任务；
- 最近交付及其关键文本；
- 最近一句状态记录。

大模型输出采用宽松 Markdown 协议：

```text
# 计划名
> 说明
## Day 1 | 主题
- [重点] 任务 | 45min | 20XP | 交付：...
```

`services/plan_import.py` 解析后写入 `study_plans` 和 `daily_missions`。启用新计划时，旧计划只归档，不删除。

## 4. 交付与复盘来源

### 4.1 交付

`mission_deliveries` 保存任务交付元数据，附件保存在：

```text
storage/deliveries/<storage_key>/
```

如果填写复盘关键文本，系统同时写入：

```text
复盘关键文本.txt
```

### 4.2 统一复盘来源

`review_sources` 是每日任务与特殊任务的共同索引：

| 字段 | 作用 |
|---|---|
| `source_type` | `mission_delivery` 或 `special_task` |
| `source_id` | 原始交付 ID |
| `source_text` | 受控关键文本 |
| `storage_key` | 可追溯交付目录 |
| `source_date` | 延迟复盘日期索引 |

AI 不会自动读取整个科研库。只有用户主动写入交付目录的关键文本才能进入自动题库。

## 5. 出题与开放题评分

### 5.1 出题

`services/review_engine.py` 要求模型返回固定结构：

```json
{
  "questions": [
    {
      "question": "...",
      "evidence": "...",
      "rubric": ["...", "..."],
      "kind": "recall"
    }
  ]
}
```

问题、证据与评分点一起写入 `review_sessions`。用户答题前不显示证据。

### 5.2 评分

开放答案不采用字符串相等和单一正确答案。评分输出为：

- `score`：0–100 的形成性分数；
- `level`：掌握、部分掌握、需要复习；
- `feedback`：缺失要素与下一步；
- `evidence_quote`：依据的交付证据；
- `confidence`：模型判断置信度。

之后用户必须选择“掌握 / 模糊 / 忘了”。`next_due` 由本人判断决定，而不是让模型成为最终裁判。

外部模型失败时，系统使用低置信度离线初判，并明确显示回退原因。

## 6. AI 提供器与安全边界

`services/ai_provider.py` 支持：

- 离线规则；
- Ollama `/api/generate`；
- OpenAI Responses API 或同结构兼容接口。

模型输出必须符合 JSON Schema。来自交付的文本被明确视为“不可信数据而非指令”，降低文档提示注入风险。

API 密钥只读取环境变量：

```text
OPENAI_API_KEY
RESEARCH_OS_AI_KEY
```

密钥不进入 `settings`、备份 JSON、个性化包或 Git 仓库。

## 7. 灵草、炼丹与挑战

### 7.1 特殊任务

`special_tasks` 保存：

- 可检查任务；
- 难度 1–5；
- 最小交付；
- 交付说明；
- 复盘关键文本；
- 对应灵草奖励。

### 7.2 灵草

`herb_inventory` 以难度映射五级灵草。完成任务才增加库存。

### 7.3 丹药

丹药复用 `inventory_items`，`item_type='pill'`。渡劫丹会在开启五问雷劫时消耗；题目仍来自 `review_sources`。

游戏资产不能兑换真实权益，不能替代科研评价。

## 8. 个性化与跨版本迁移

个性化 v2 包包含：

- 个人主页；
- 主题与主页短句；
- 网站名称；
- 14 个境界名称；
- 导航名称；
- 复盘弹窗开关。

不包含：

- 科研附件；
- 数据库；
- API 密钥；
- 联机 Token。

导入同时兼容 `research-cultivation-personalization-v1` 与 `v2`。

## 9. 数据安全

- SQLite：WAL、外键、忙等待；
- 自动快照：Python `sqlite3.Connection.backup()`；
- 完整备份：数据库与 `storage/` 一起打包；
- 安全升级：校验 ZIP 路径、安装到新目录、迁移数据、保留旧目录；
- 公开仓库：忽略数据库、附件、`.env`、Token、密钥与生成包。

## 10. 后续扩展边界

建议下一阶段优先做：

1. 将本人自评真正用于到期题抽样；
2. 增加交付关键文本的人工编辑与版本记录；
3. 为 AI 调用增加可见的费用上限和调用日志；
4. 增加数据库迁移测试与浏览器端端到端测试。

暂不建议：

- 自动扫描全部私人文件；
- 自建大型向量数据库；
- 将科研原始数据同步到轻量中心；
- 让模型评分直接决定高风险学术或实验决策。
