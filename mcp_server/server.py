#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""plant-structure MCP Server（SSE 传输）

Nexent「设备运维认知智能体」—— B 的交付物 #6：MCP server。

为什么要这一层：Nexent 自带的 knowledge_base_search 是向量检索，擅长
"意思相近"的召回，但对**精确编号 / 数值 / 限值 / 跨表关联**不可靠。
这层工具把设备台账、故障代码字典、备件 BOM、手册限值做成结构化查询，
返回「值 + 出处（文件 + 章节）」，让 Agent 能据此做多跳推理并逐条溯源。

数据与 nexent 侧 4 个知识库同源（设备知识库数据包）：
  设备台账 → equipment_ledger.csv
  故障代码 → fault_code_dictionary.csv
  备件 BOM → bom.csv
  限值     → maintenance_manual_*.txt

启动：
    python server.py                  # 默认监听 0.0.0.0:8931
    set MCP_PORT=8932 && python server.py

Nexent 中注册的 MCP 地址（容器内访问宿主机，不能用 127.0.0.1）：
    http://host.docker.internal:8931/sse
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 依赖已随仓库内置在 vendor/ 下，无需 pip install
VENDOR = HERE / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))

from mcp.server.fastmcp import FastMCP  # noqa: E402

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8931"))

mcp = FastMCP(
    "plant-structure",
    instructions=(
        "设备运维结构化查询服务。当问题涉及精确编号（设备编号、故障代码、备件编号）、"
        "精确数值与限值（振动、温升、压力、间隙、力矩），或需要给出「文件 + 章节」级引用时调用；"
        "泛化描述（原理、步骤叙述、故障现象解释）仍走知识库检索。"
    ),
    host=HOST,
    port=PORT,
    sse_path="/sse",
    message_path="/messages/",
)

_D = json.loads((HERE / "data" / "plant.json").read_text(encoding="utf-8"))
EQUIP = _D["equipment"]
FAULTS = _D["fault_codes"]
SECTIONS = _D["sections"]
PARTS = _D["spare_parts"]
LIMITS = _D["thresholds"]

# 型号前缀 -> 设备类别（对应故障代码字典的「适用设备」）
SCOPE_BY_PREFIX = {"VMC": "CNC", "HMC": "CNC", "HPU": "HYD", "CU": "CLG", "EC": "ELE"}


def _norm(text: str) -> str:
    s = (text or "").lower().replace("×", "x").replace("（", "(").replace("）", ")")
    for ch in " -_/.,、":
        s = s.replace(ch, "")
    return s


def _hit(keyword: str, *fields) -> bool:
    kw = _norm(keyword)
    if not kw:
        return False
    blob = _norm(" ".join(str(f) for f in fields if f is not None))
    return kw in blob


def _scope_of_model(model: str) -> str:
    for pre, scope in SCOPE_BY_PREFIX.items():
        if model.upper().startswith(pre):
            return scope
    return ""


def _cite_section(sec: str) -> dict:
    info = SECTIONS.get(sec)
    if not info:
        return {"章节": sec, "出处": f"章节 {sec}"}
    return {"章节": sec, "章节标题": info["title"], "出处": f"《{info['file']}》{info['title']}"}


@mcp.tool()
def ping() -> str:
    """连通性自检。返回 pong 与服务器当前时间，用于确认 MCP 已接通。"""
    return f"pong | plant-structure MCP | {time.strftime('%Y-%m-%d %H:%M:%S')}"


@mcp.tool()
def list_equipment() -> list[dict]:
    """列出在册设备台账（设备编号、名称、型号、产线、投用日期、关键部件、状态）。

    当用户问「有哪些设备」「某条产线有哪些设备」「某台设备是什么型号」时先调用它，
    拿到设备编号后再用 get_equipment 查详情。
    """
    return [
        {
            "设备编号": e["id"], "设备名称": e["name"], "型号": e["model"],
            "所属产线": e["line"], "投用日期": e["since"],
            "关键部件": e["parts"], "状态": e["status"],
            "出处": "《equipment_ledger.csv》",
        }
        for e in EQUIP
    ]


@mcp.tool()
def get_equipment(keyword: str) -> dict:
    """按设备编号 / 名称 / 型号 / 产线 查询设备详情，并带出关联备件与适用故障代码。

    适用：需要确认某台设备的型号、关键部件、所属产线，或想从设备反查
    「该型号能用哪些备件」「这台设备可能报哪些故障代码」。
    例：keyword="CNC-01" / "VMC850" / "液压站" / "机加二线"。

    Args:
        keyword: 设备编号（CNC-01）、设备名称（立式加工中心）、型号（VMC850）、或产线名。
    """
    rows = [e for e in EQUIP if _hit(keyword, e["id"], e["name"], e["model"], e["line"], e["parts"])]
    if not rows:
        return {"查询": keyword, "命中": 0,
                "提示": "未匹配到设备，可调用 list_equipment 查看全部设备编号与型号。"}

    out = []
    for e in rows:
        scope = _scope_of_model(e["model"])
        parts = [p for p in PARTS if _norm(e["model"]) in _norm(p["models"])]
        codes = [f for f in FAULTS if f["scope"] == scope]
        out.append({
            "设备编号": e["id"], "设备名称": e["name"], "型号": e["model"],
            "所属产线": e["line"], "投用日期": e["since"], "关键部件": e["parts"],
            "状态": e["status"],
            "适用故障代码": [{"代码": c["code"], "名称": c["name"]} for c in codes],
            "该型号可用备件": [
                {"备件编号": p["code"], "名称": p["name"], "规格": p["spec"],
                 "库存": p["stock"], "单价元": p["price"]}
                for p in parts
            ],
            "出处": "《equipment_ledger.csv》《fault_code_dictionary.csv》《bom.csv》",
        })
    return {"查询": keyword, "命中": len(out), "结果": out}


@mcp.tool()
def get_fault_code(code_or_name: str) -> dict:
    """按故障代码或故障名称查询标准处置，并给出对应手册章节的精确出处。

    这是跨表定位的关键一步：故障代码字典里的「参考手册章节」可以直接跳到维修手册，
    再配合 get_spare_part 确认更换件库存，即可完成「代码 → 章节 → 备件」的多跳链路。
    例：code_or_name="E-101" / "H-201" / "主轴异响" / "油缸爬行"。

    Args:
        code_or_name: 故障代码（E-101、H-201）或故障名称（主轴异响、液压压力不足）。
    """
    rows = [f for f in FAULTS if _hit(code_or_name, f["code"], f["name"], f["cause"], f["part"])]
    if not rows:
        return {"查询": code_or_name, "命中": 0,
                "提示": "未匹配到故障代码。可用代码范围：E-101~E-108（CNC）、H-201~H-205（HYD）。"}
    out = []
    for f in rows:
        rec = {
            "故障代码": f["code"], "故障名称": f["name"], "适用设备类别": f["scope"],
            "可能原因": f["cause"], "关联部件": f["part"], "建议处置": f["action"],
        }
        rec.update(_cite_section(f["section"]))
        rec["相关备件"] = [
            {"备件编号": p["code"], "名称": p["name"], "规格": p["spec"],
             "库存": p["stock"], "单价元": p["price"]}
            for p in PARTS
            if _norm(f["part"]) in _norm(p["name"]) or _norm(p["name"]) in _norm(f["part"])
        ]
        out.append(rec)
    return {"查询": code_or_name, "命中": len(out), "结果": out}


@mcp.tool()
def get_spare_part(keyword: str) -> dict:
    """按备件编号 / 名称 / 规格 / 所属总成查询备件库存与价格（来自 BOM）。

    适用：「某个备件库存还有多少」「这个型号的设备该用哪个规格的轴承」
    「换件成本多少」。返回库存数量与单价，可直接支撑「够不够换」的判断。
    例：keyword="SP-1001" / "主轴轴承" / "7014C" / "液压站"。

    Args:
        keyword: 备件编号、名称、规格型号或所属总成。
    """
    rows = [p for p in PARTS if _hit(keyword, p["code"], p["name"], p["models"],
                                     p["assembly"], p["spec"], p["vendor"])]
    if not rows:
        return {"查询": keyword, "命中": 0, "提示": "未匹配到备件，可用编号形如 SP-1001。"}
    return {
        "查询": keyword, "命中": len(rows),
        "结果": [
            {"备件编号": p["code"], "备件名称": p["name"], "适用设备型号": p["models"],
             "所属总成": p["assembly"], "规格型号": p["spec"], "库存数量": p["stock"],
             "单价元": p["price"], "供应商": p["vendor"], "出处": "《bom.csv》"}
            for p in rows
        ],
    }


@mcp.tool()
def get_threshold(keyword: str) -> dict:
    """按监测项查询维修手册里的精确限值（报警线 / 停机线 / 允差 / 力矩 / 牌号）。

    适用：「振动多大算超标」「温升报警值是多少」「间隙允差」「预紧力矩多少」
    这类必须给准数的判断，避免向量检索把 2.8 和 4.5 混为一谈。
    例：keyword="振动" / "温升" / "压力" / "间隙" / "力矩" / "油温" / "清洁度"。

    Args:
        keyword: 监测项关键词，如 振动、温升、压力、间隙、力矩、油温、清洁度、牌号。
    """
    rows = [t for t in LIMITS if _hit(keyword, t["item"], t["note"], t["section"])]
    if not rows:
        rows = LIMITS  # 没命中就把全部限值给出，避免空返回
        note = "未精确匹配，返回全部限值供选择。"
    else:
        note = "限值随设备类别区分，判定时必须指明适用对象。"
    out = []
    for t in rows:
        rec = {"监测项": t["item"], "限值": f"{t['value']} {t['unit']}".strip(),
               "说明": t["note"]}
        rec.update(_cite_section(t["section"]))
        out.append(rec)
    return {"查询": keyword, "说明": note, "命中": len(out), "结果": out}


if __name__ == "__main__":
    print(f"[plant-structure] listening on http://{HOST}:{PORT}/sse", flush=True)
    print(f"[plant-structure] register in Nexent: http://host.docker.internal:{PORT}/sse", flush=True)
    mcp.run(transport="sse")
