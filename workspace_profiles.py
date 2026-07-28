from __future__ import annotations

import json
from typing import Any


WORKSPACE_MODULES = {
    "knowledge": ("通用知识专题", "收录论文、笔记、代码和附件"),
    "experiments": ("实验台账", "使用结构化实验批次表"),
    "simulations": ("LAMMPS / 模拟案例", "归档输入、日志、轨迹和复现命令"),
    "datasets": ("数据集", "保存来源、字段、单位、许可和版本"),
    "ml": ("ML 建模", "组织数据边界、运行、指标、产物和模型卡"),
    "md": ("MD 模拟", "管理结构、力场、平衡、生产、轨迹和分析"),
    "comsol": ("COMSOL 多物理场", "管理物理假设、边界、网格、求解和验证"),
}

WORKSPACE_TOOLS = {
    "papers": ("论文资料", "藏", "收录并检索本工作区的文献、笔记与代码"),
    "notes": ("方法/结论笔记", "记", "记录假设、判断边界、异常和下一步"),
    "uploads": ("文件与附件", "收", "上传原始文件、图片、脚本或模型包"),
    "tasks": ("修炼任务", "始", "把当前工作区的问题拆成可交付动作"),
    "experiments": ("实验批次", "验", "配比、制样、电化学与力学结构化台账"),
    "simulations": ("模拟案例", "算", "输入、版本、日志、轨迹和复现命令"),
    "datasets": ("数据档案", "数", "来源、许可、字段单位、版本和质量边界"),
    "folders": ("项目文件夹", "夹", "按原目录保存一组相关科研文件"),
    "focus": ("专注闭关", "静", "带着当前工作区名称进入专注计时"),
}

WORKSPACE_ACCENTS = {
    "clay": "陶土",
    "sage": "青松",
    "ink": "墨色",
    "amber": "琥珀",
}

WORKSPACE_PROFILES = {
    "knowledge": {
        "kicker": "Knowledge Workspace",
        "objective": "围绕一个科学问题形成可检索、可引用、可复盘的证据链。",
        "workflow": ("提出问题", "收集证据", "比较边界", "形成判断"),
        "tools": ("papers", "notes", "uploads", "tasks"),
        "evidence": "问题、来源、关键证据、反例与当前结论",
    },
    "experiments": {
        "kicker": "Experimental Workspace",
        "objective": "把变量、样品、测试条件和结论放在同一条可追溯实验链中。",
        "workflow": ("假设与变量", "样品与过程", "测试与质控", "结论与复验"),
        "tools": ("experiments", "uploads", "notes", "datasets", "tasks"),
        "evidence": "样品编号、配方与过程、原始曲线、异常、重复性和结论边界",
    },
    "simulations": {
        "kicker": "LAMMPS Workspace",
        "objective": "让每个模拟案例都能由输入、版本、命令和输出重新运行。",
        "workflow": ("结构与势函数", "输入与版本", "运行与日志", "校验与固化"),
        "tools": ("simulations", "uploads", "notes", "datasets", "tasks"),
        "evidence": "input/data、势函数来源、LAMMPS 版本、运行命令、log/dump/restart 和 PASS 标准",
    },
    "datasets": {
        "kicker": "Dataset Workspace",
        "objective": "让每份数据在建模前先说清来源、许可、单位、版本和适用边界。",
        "workflow": ("来源与许可", "字段与单位", "清洗与版本", "质检与拆分"),
        "tools": ("datasets", "uploads", "notes", "tasks"),
        "evidence": "来源、采集/筛选规则、数据字典、缺失异常、版本和训练验证拆分",
    },
    "ml": {
        "kicker": "Machine Learning Workspace",
        "objective": "把数据谱系、特征、运行参数、指标和实验验证连成可复现模型卡。",
        "workflow": ("数据边界", "特征管线", "运行与指标", "验证与模型卡"),
        "tools": ("datasets", "notes", "uploads", "tasks", "folders"),
        "evidence": "数据版本与拆分、代码版本、参数、指标、产物、误差分析和外部验证",
    },
    "md": {
        "kicker": "Molecular Dynamics Workspace",
        "objective": "把结构、力场、平衡、生产和分析固化为可重复的分子模拟案例。",
        "workflow": ("结构与力场", "最小化/平衡", "生产与轨迹", "分析与复现"),
        "tools": ("simulations", "datasets", "uploads", "notes", "tasks"),
        "evidence": "初始结构、力场与电荷、系综、时间步长、平衡判据、轨迹和分析脚本",
    },
    "comsol": {
        "kicker": "COMSOL Multiphysics Workspace",
        "objective": "让模型从物理问题到网格、求解和实验校核都有显式证据。",
        "workflow": ("物理与假设", "几何材料/边界", "网格与求解", "验证与校核"),
        "tools": ("uploads", "notes", "datasets", "tasks", "folders"),
        "evidence": "方程与假设、材料来源、边界条件、网格无关性、求解器、基准与实验校核",
    },
}

DEFAULT_WORKSPACES = (
    {
        "workspace_key": "eg-lab",
        "name": "EG 实验",
        "icon": "验",
        "module": "experiments",
        "description": "配比、成型、电化学与力学实验台账",
        "accent": "clay",
        "sort_order": 10,
    },
    {
        "workspace_key": "lammps-lab",
        "name": "LAMMPS",
        "icon": "算",
        "module": "simulations",
        "description": "可复现模拟案例、日志与轨迹归档",
        "accent": "ink",
        "sort_order": 20,
    },
    {
        "workspace_key": "dataset-lab",
        "name": "数据集",
        "icon": "数",
        "module": "datasets",
        "description": "实验表格、机器学习数据与变量说明",
        "accent": "sage",
        "sort_order": 30,
    },
    {
        "workspace_key": "ml-lab",
        "name": "ML",
        "icon": "智",
        "module": "ml",
        "description": "数据、特征、训练、验证与模型卡归档",
        "accent": "sage",
        "sort_order": 40,
    },
    {
        "workspace_key": "md-lab",
        "name": "MD",
        "icon": "动",
        "module": "md",
        "description": "结构、力场、轨迹、分析与可复现案例",
        "accent": "ink",
        "sort_order": 50,
    },
    {
        "workspace_key": "comsol-lab",
        "name": "COMSOL",
        "icon": "场",
        "module": "comsol",
        "description": "几何、材料、网格、求解器与多物理场验证",
        "accent": "amber",
        "sort_order": 60,
    },
)


def profile_for(module: str) -> dict[str, Any]:
    return WORKSPACE_PROFILES.get(module, WORKSPACE_PROFILES["knowledge"])


def normalize_workflow(value: Any, module: str) -> list[str]:
    raw: Any = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            raw = value.splitlines()
    if not isinstance(raw, (list, tuple)):
        raw = []
    cleaned = [str(item).strip()[:24] for item in raw if str(item).strip()]
    return cleaned[:6] or list(profile_for(module)["workflow"])


def normalize_toolset(value: Any, module: str) -> list[str]:
    raw: Any = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            raw = [part.strip() for part in value.split(",")]
    if not isinstance(raw, (list, tuple)):
        raw = []
    cleaned: list[str] = []
    for item in raw:
        key = str(item).strip()
        if key in WORKSPACE_TOOLS and key not in cleaned:
            cleaned.append(key)
    return cleaned[:7] or list(profile_for(module)["tools"])
