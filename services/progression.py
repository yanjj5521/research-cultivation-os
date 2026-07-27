from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RealmStage:
    key: str
    threshold: int
    name: str
    description: str


# Stable keys keep personalized names attached to the same stage when a later
# version inserts a new realm between two existing stages.
REALM_STAGES: tuple[RealmStage, ...] = (
    RealmStage("mortal", 0, "凡人", "开始留下第一份可验证的科研痕迹"),
    RealmStage("body_early", 40, "炼体初境", "建立作息、文件与最小交付习惯"),
    RealmStage("body_middle", 90, "炼体中境", "能够连续完成短时学习行动"),
    RealmStage("body_late", 160, "炼体后境", "开始把输入转成笔记、图表或代码"),
    RealmStage("body_complete", 240, "炼体圆满", "形成稳定的每日交付节奏"),
    RealmStage("qi_1", 350, "炼气一层", "掌握本领域最基础的概念与单位"),
    RealmStage("qi_3", 480, "炼气三层", "能复述关键机制并指出适用边界"),
    RealmStage("qi_6", 650, "炼气六层", "能读懂常见图表与实验步骤"),
    RealmStage("qi_9", 860, "炼气九层", "能独立完成一个基础案例"),
    RealmStage("qi_complete", 1120, "炼气圆满", "基础知识、工具和交付开始互相连接"),
    RealmStage("foundation_early", 1450, "筑基初期", "建立自己的知识库与记录规范"),
    RealmStage("foundation_middle", 1850, "筑基中期", "能从文献中提取可验证的证据"),
    RealmStage("foundation_late", 2350, "筑基后期", "能把问题拆成变量、机制与观测量"),
    RealmStage("foundation_complete", 2950, "筑基圆满", "形成可持续迭代的科研工作流"),
    RealmStage("core_early", 3650, "金丹初期", "拥有首批可复用的数据、SOP与案例"),
    RealmStage("core_middle", 4450, "金丹中期", "能设计对照并识别主要限制步骤"),
    RealmStage("core_late", 5350, "金丹后期", "能将加工、结构、输运与性能串联"),
    RealmStage("core_complete", 6350, "金丹圆满", "形成一条证据闭环的研究叙事"),
    RealmStage("nascent_early", 7500, "元婴初期", "能独立推进一个边界清晰的问题"),
    RealmStage("nascent_middle", 8800, "元婴中期", "能协调实验、模拟或数据分析支线"),
    RealmStage("nascent_late", 10250, "元婴后期", "能判断哪些结果值得继续投入"),
    RealmStage("nascent_complete", 11850, "元婴圆满", "形成稳定的研究判断与复盘能力"),
    RealmStage("spirit_early", 13600, "化神初期", "能把复杂机制讲清并接受证据检验"),
    RealmStage("spirit_middle", 15500, "化神中期", "能将知识资产转化为论文图与方法"),
    RealmStage("spirit_late", 17600, "化神后期", "能提出具有区分度的科学问题"),
    RealmStage("spirit_complete", 19900, "化神圆满", "形成鲜明且可复用的学术表达体系"),
    RealmStage("void", 22400, "炼虚境", "能够搭建团队可复现的科研基础设施"),
    RealmStage("fusion", 25200, "合体境", "知识、数据、方法与协作高度协同"),
    RealmStage("mahayana", 28300, "大乘境", "能够定义问题并引导研究方向"),
    RealmStage("tribulation", 31700, "渡劫境", "以连续挑战检验知识体系的真实强度"),
    RealmStage("true_immortal", 35500, "真仙境", "形成可持续创造、验证与传承的科研体系"),
)


LEGACY_REALM_KEYS: tuple[str, ...] = (
    "mortal",
    "qi_1",
    "qi_6",
    "qi_complete",
    "foundation_early",
    "foundation_complete",
    "core_early",
    "core_complete",
    "nascent_complete",
    "spirit_complete",
    "void",
    "fusion",
    "mahayana",
    "tribulation",
)


def default_realm_labels() -> dict[str, str]:
    return {stage.key: stage.name for stage in REALM_STAGES}


def normalize_realm_labels(value: Any) -> dict[str, str]:
    labels = default_realm_labels()
    if isinstance(value, dict):
        for stage in REALM_STAGES:
            candidate = str(value.get(stage.key, "")).strip()[:30]
            if candidate:
                labels[stage.key] = candidate
        return labels
    if isinstance(value, list):
        keys = LEGACY_REALM_KEYS if len(value) == len(LEGACY_REALM_KEYS) else tuple(
            stage.key for stage in REALM_STAGES
        )
        for index, candidate in enumerate(value):
            if index >= len(keys):
                break
            text = str(candidate).strip()[:30]
            if text:
                labels[keys[index]] = text
    return labels


DAILY_XP_BANDS: tuple[tuple[int, int, str], ...] = (
    (20, 6, "微行动"),
    (45, 10, "标准行动"),
    (75, 16, "专注行动"),
    (120, 22, "深度行动"),
    (10_000, 30, "长时行动"),
)


def fixed_daily_xp(duration_minutes: int) -> int:
    minutes = max(5, min(int(duration_minutes or 30), 240))
    for upper, xp, _ in DAILY_XP_BANDS:
        if minutes <= upper:
            return xp
    return DAILY_XP_BANDS[-1][1]


CULTIVATION_TASK_XP = {1: 25, 2: 50, 3: 90}
CULTIVATION_DIFFICULTY_LABELS = {1: "小成", 2: "进阶", 3: "突破"}


def fixed_cultivation_xp(difficulty: int) -> int:
    return CULTIVATION_TASK_XP.get(max(1, min(int(difficulty or 1), 3)), 25)
