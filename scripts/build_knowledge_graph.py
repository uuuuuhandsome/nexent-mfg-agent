# -*- coding: utf-8 -*-
"""
生成知识图谱 JSON（交付物 #4）：节点 + 边 + 溯源属性。
数据源：data/ 下的结构化表格与手册，经 ontology/ontology_v1.json 的 schema 约束。

输出：ontology/knowledge_graph.json
"""
import csv
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ONTO = os.path.join(ROOT, "ontology")

nodes = {}
edges = []
edge_seen = set()


def node(nid, ntype, name, attrs=None, prov=None):
    if nid in nodes:
        return
    nodes[nid] = {
        "id": nid,
        "type": ntype,
        "name": name,
        "attributes": attrs or {},
        "provenance": prov or {},
    }


def edge(src, rel, dst, prov=None):
    key = (src, rel, dst)
    if key in edge_seen:
        return
    edge_seen.add(key)
    edges.append({"source": src, "relation": rel, "target": dst, "provenance": prov or {}})


def read_csv(name):
    p = os.path.join(DATA, name)
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []


# ---------- 设备台账 → Equipment + Model ----------
for i, r in enumerate(read_csv("equipment_ledger.csv"), start=1):
    eid = r["设备编号"].strip()
    node(eid, "Equipment", r["设备名称"].strip(),
         {"型号": r["型号"], "产线": r["所属产线"], "投用日期": r["投用日期"],
          "关键部件": r["关键部件"], "状态": r["状态"]},
         {"document": "equipment_ledger.csv", "row": i})
    mid = r["型号"].strip()
    node(mid, "EquipmentModel", mid, {}, {"document": "equipment_ledger.csv", "row": i})
    edge(eid, "hasModel", mid, {"document": "equipment_ledger.csv", "row": i})

# ---------- 故障代码 → Fault + Component + ManualSection ----------
for i, r in enumerate(read_csv("fault_code_dictionary.csv"), start=1):
    code = r["故障代码"].strip()
    node(code, "Fault", r["故障名称"].strip(),
         {"适用设备": r["适用设备"], "可能原因": r["可能原因"], "建议处置": r["建议处置"]},
         {"document": "fault_code_dictionary.csv", "row": i})
    for part in re.split(r"[/、,，]", r.get("关联部件", "")):
        part = part.strip()
        if not part:
            continue
        node(f"CMP-{part}", "Component", part, {}, {"document": "fault_code_dictionary.csv", "row": i})
        edge(code, "causedBy", f"CMP-{part}", {"document": "fault_code_dictionary.csv", "row": i})
    sec = r.get("参考手册章节", "").strip()
    if sec:
        node(f"SEC-{sec}", "ManualSection", f"手册 {sec} 节", {"章节号": sec},
             {"document": "fault_code_dictionary.csv", "row": i})
        edge(code, "references", f"SEC-{sec}", {"document": "fault_code_dictionary.csv", "row": i})

# ---------- BOM → SparePart + appliesTo ----------
for i, r in enumerate(read_csv("bom.csv"), start=1):
    sp = r["备件编号"].strip()
    node(sp, "SparePart", r["备件名称"].strip(),
         {"适用型号": r["适用设备型号"], "总成": r["所属总成"], "规格": r["规格型号"],
          "库存": r.get("库存数量", ""), "单价": r.get("单价元", ""), "供应商": r.get("供应商", "")},
         {"document": "bom.csv", "row": i})
    for m in re.split(r"[/、,，]", r.get("适用设备型号", "")):
        m = m.strip()
        if not m:
            continue
        node(m, "EquipmentModel", m, {}, {"document": "bom.csv", "row": i})
        edge(sp, "appliesTo", m, {"document": "bom.csv", "row": i})

# ---------- 工单 → WorkOrder + MaintenanceAction ----------
for i, r in enumerate(read_csv("maintenance_work_orders.csv"), start=1):
    wo = r["工单号"].strip()
    node(wo, "WorkOrder", wo,
         {"设备": r["设备编号"], "故障代码": r["故障代码"], "现象": r["现象描述"],
          "工时": r.get("工时h"), "日期": r.get("维修日期"), "维修人": r.get("维修人")},
         {"document": "maintenance_work_orders.csv", "row": i})
    edge(wo, "hasFault", r["故障代码"].strip(), {"document": "maintenance_work_orders.csv", "row": i})
    if r["设备编号"].strip() in nodes:
        edge(wo, "belongsTo", r["设备编号"].strip(),
             {"document": "maintenance_work_orders.csv", "row": i})
    act = (r.get("维修措施") or "").strip()
    if act and act != "无":
        aid = f"ACT-{wo}"
        node(aid, "MaintenanceAction", act, {}, {"document": "maintenance_work_orders.csv", "row": i})
        edge(wo, "resolvedBy", aid, {"document": "maintenance_work_orders.csv", "row": i})
    sp = (r.get("更换备件") or "").strip()
    if sp and sp != "无":
        for one in re.split(r"[/、,，]", sp):
            one = one.strip()
            if re.match(r"SP-\d{4}", one):
                edge(wo, "usesPart", one, {"document": "maintenance_work_orders.csv", "row": i})

# ---------- 质检 → Inspection ----------
for i, r in enumerate(read_csv("quality_inspection.csv"), start=1):
    qc = r["质检单号"].strip()
    node(qc, "Inspection", qc,
         {"批次": r["批次号"], "检测项": r["检测项"], "标准值": r["标准值"],
          "实测值": r["实测值"], "判定": r["判定"], "日期": r["检测日期"]},
         {"document": "quality_inspection.csv", "row": i})
    eq = r["设备编号"].strip()
    if eq in nodes:
        edge(eq, "inspectedBy", qc, {"document": "quality_inspection.csv", "row": i})

# ---------- 结构说明 → Component usesPart SparePart ----------
notes = os.path.join(DATA, "equipment_structure_notes.txt")
if os.path.exists(notes):
    for i, line in enumerate(open(notes, encoding="utf-8"), start=1):
        m = re.match(r"\s*[-•]\s*(.+?)\s*->\s*(SP-\d{4})", line)
        if m:
            part, sp = m.group(1).strip(), m.group(2)
            node(f"CMP-{part}", "Component", part, {},
                 {"document": "equipment_structure_notes.txt", "line": i})
            edge(f"CMP-{part}", "usesPart", sp,
                 {"document": "equipment_structure_notes.txt", "line": i})

# ---------- 组装 ----------
schema = json.load(open(os.path.join(ONTO, "ontology_v1.json"), encoding="utf-8"))

# 本体演化：补齐「故障→处置」链路所需的概念与关系（C 阶段扩展，带溯源）
EXT = {
    "concept": {"id": "MaintenanceAction", "name": "处置动作",
                "definition": "工单中实际采取的维修措施",
                "examples": ["更换主轴轴承并重新预紧"],
                "standard": "企业维修作业规范",
                "provenance": {"source": "ontology 扩展（C）", "status": "schema_extension",
                               "reason": "原种子本体缺失处置动作，导致故障无法连到备件"}},
    "relation": {"id": "resolvedBy", "head": "WorkOrder", "tail": "MaintenanceAction",
                 "description": "工单采取的处置动作",
                 "provenance": {"source": "ontology 扩展（C）", "status": "schema_extension"}},
}
changed = False
if EXT["concept"]["id"] not in {c["id"] for c in schema["concepts"]}:
    schema["concepts"].append(EXT["concept"])
    changed = True
if EXT["relation"]["id"] not in {r["id"] for r in schema["relations"]}:
    schema["relations"].append(EXT["relation"])
    changed = True
if changed:
    json.dump(schema, open(os.path.join(ONTO, "ontology_v1.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("ontology_v1.json 已扩展：+MaintenanceAction / +resolvedBy")
type_count = Counter(n["type"] for n in nodes.values())
rel_count = Counter(e["relation"] for e in edges)

kg = {
    "meta": {
        "name": "设备运维知识图谱",
        "version": "1.0",
        "schema_version": schema.get("version"),
        "schema_concepts": len(schema["concepts"]),
        "schema_relations": len(schema["relations"]),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": dict(type_count),
        "relation_types": dict(rel_count),
        "provenance_rule": "每个节点与边均记录来源文档与行号/章节，支持逐条回溯",
    },
    "nodes": sorted(nodes.values(), key=lambda x: (x["type"], x["id"])),
    "edges": sorted(edges, key=lambda x: (x["source"], x["relation"], x["target"])),
}

out = os.path.join(ONTO, "knowledge_graph.json")
json.dump(kg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"节点 {len(nodes)}｜边 {len(edges)}")
print("节点类型：", dict(type_count))
print("关系类型：", dict(rel_count))
schema_rels = {r["id"] for r in schema["relations"]}
unknown = sorted(set(rel_count) - schema_rels)
schema_types = {c["id"] for c in schema["concepts"]}
unknown_types = sorted(set(type_count) - schema_types)
print("schema 未定义的关系：", unknown or "无")
print("schema 未定义的类型：", unknown_types or "无")
print("输出：", out, os.path.getsize(out), "bytes")
