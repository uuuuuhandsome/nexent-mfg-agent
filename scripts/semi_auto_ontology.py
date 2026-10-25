# -*- coding: utf-8 -*-
"""
低资源半自动本体构建：从语料中抽取候选概念/关系，按相似度与置信度分拣。

输入：ontology/seed_ontology.json + data/ 下的手册、工单、故障码、BOM
输出：ontology/ontology_v1.json、extraction_candidates.csv、review_queue.csv、extraction_report.md

运行：python scripts/semi_auto_ontology.py
"""
import csv
import json
import os
import re
import sys
import difflib
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ONTO = os.path.join(ROOT, "ontology")

AUTO_MERGE = 0.85      # 相似度高于此：判定为同义，自动合并
REVIEW_LOW = 0.50      # 介于两者之间：进人工确认队列
CONF_AUTO = 0.80       # 抽取置信度高于此才允许自动入图


# ---------------- 相似度 ----------------
def norm(s):
    return re.sub(r"[\s\-_/（）()]", "", str(s)).lower()


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def similarity(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    ja, jb = bigrams(a), bigrams(b)
    jac = len(ja & jb) / len(ja | jb) if ja | jb else 0.0
    contain = 1.0 if (a in b or b in a) else 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    # 包含关系说明是同一概念的简写/全称，权重最高
    return max(jac, contain * 0.92, ratio)


# ---------------- 读语料 ----------------
def read_csv(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_text(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read()


# ---------------- 抽取 ----------------
INSTANCE_RE = re.compile(r"^([EH]-\d{3}|SP-\d{4}|WO-\d{4}-\d{3}|\d+(?:\.\d+)+)$")


def is_instance(raw_id):
    return bool(INSTANCE_RE.match(raw_id.split(":", 1)[-1]))


def extract():
    """返回候选列表：{kind, head, rel, tail, confidence, source, sentence}"""
    cands = []

    # 1) 故障代码表：故障 -> 部件（causedBy）、故障 -> 手册章节（references）
    for row in read_csv("fault_code_dictionary.csv"):
        code = row.get("故障代码", "").strip()
        if not code:
            continue
        name = row.get("故障名称", "").strip()
        part = row.get("关联部件", "").strip()
        sec = row.get("参考手册章节", "").strip()
        src = "fault_code_dictionary.csv"
        cands.append(dict(kind="concept", head=f"Fault:{code}", name=name, rel="",
                          tail="", confidence=0.95, source=src,
                          sentence=f"{code} {name}"))
        if part:
            cands.append(dict(kind="relation", head=f"Fault:{code}", rel="causedBy",
                              tail=f"Component:{part}", name="", confidence=0.90,
                              source=src, sentence=f"{code} {name}｜关联部件：{part}"))
        if sec:
            cands.append(dict(kind="relation", head=f"Fault:{code}", rel="references",
                              tail=f"ManualSection:{sec}", name="", confidence=0.90,
                              source=src, sentence=f"{code} {name}｜参考章节：{sec}"))

    # 2) BOM：备件 -> 适用型号（appliesTo）
    for row in read_csv("bom.csv"):
        sid = row.get("备件编号", "").strip()
        if not sid:
            continue
        sname = row.get("备件名称", "").strip()
        models = [m.strip() for m in re.split(r"[/、,，]", row.get("适用设备型号", "")) if m.strip()]
        cands.append(dict(kind="concept", head=f"SparePart:{sid}", name=sname, rel="",
                          tail="", confidence=0.95, source="bom.csv",
                          sentence=f"{sid} {sname}"))
        for m in models:
            cands.append(dict(kind="relation", head=f"SparePart:{sid}", rel="appliesTo",
                              tail=f"Model:{m}", name="", confidence=0.85,
                              source="bom.csv", sentence=f"{sid} 适用：{m}"))

    # 3) 结构说明：部件 -> 备件（usesPart）
    notes = read_text("equipment_structure_notes.txt")
    for line in notes.splitlines():
        m = re.match(r"\s*[-•]\s*(.+?)\s*->\s*(SP-\d{4})", line)
        if m:
            part, sp = m.group(1).strip(), m.group(2)
            cands.append(dict(kind="relation", head=f"Component:{part}", rel="usesPart",
                              tail=f"SparePart:{sp}", name="", confidence=0.88,
                              source="equipment_structure_notes.txt", sentence=line.strip()))

    # 4) 工单：工单 -> 处置动作（resolvedBy）、-> 备件（usesPart）
    for row in read_csv("maintenance_work_orders.csv"):
        wo = row.get("工单号", "").strip()
        if not wo:
            continue
        act = row.get("维修措施", "").strip()
        sp = row.get("更换备件", "").strip()
        if act and act != "无":
            cands.append(dict(kind="relation", head=f"WorkOrder:{wo}", rel="resolvedBy",
                              tail=f"MaintenanceAction:{act}", name="", confidence=0.80,
                              source="maintenance_work_orders.csv",
                              sentence=f"{wo} 措施：{act}"))
        if sp and sp != "无" and re.match(r"SP-\d{4}", sp):
            cands.append(dict(kind="relation", head=f"WorkOrder:{wo}", rel="usesPart",
                              tail=f"SparePart:{sp}", name="", confidence=0.85,
                              source="maintenance_work_orders.csv",
                              sentence=f"{wo} 更换：{sp}"))

    # 5) 手册：章节 -> 故障（describes），由“对应故障代码”句式抽取
    sec_pattern = re.compile(r"^(\d+(?:\.\d+){1,2})\s+(\S.*?)（对应故障代码\s*([EH]-\d{3})")
    for fname in ("maintenance_manual_cnc.txt", "maintenance_manual_hydraulic.txt",
                  "maintenance_manual_electrical.txt"):
        text = read_text(fname)
        for line in text.splitlines():
            m = sec_pattern.match(line.strip())
            if m:
                sec, title, code = m.group(1), m.group(2).strip(), m.group(3)
                cands.append(dict(kind="concept", head=f"ManualSection:{sec}", name=title,
                                  rel="", tail="", confidence=0.90, source=fname,
                                  sentence=line.strip()))
                cands.append(dict(kind="relation", head=f"ManualSection:{sec}", rel="describes",
                                  tail=f"Fault:{code}", name="", confidence=0.92,
                                  source=fname, sentence=line.strip()))

    # 6) 部件名：分别来自结构化字段（高置信）、结构说明（高置信）、手册正文（低置信）
    part_src = {}
    for row in read_csv("fault_code_dictionary.csv"):
        for p in re.split(r"[/、,，]", row.get("关联部件", "")):
            p = p.strip()
            if p:
                part_src.setdefault(p, ("fault_code_dictionary.csv", 0.90))
    for line in notes.splitlines():
        m = re.match(r"\s*[-•]\s*(.+?)\s*->\s*(SP-\d{4})", line)
        if m:
            part_src.setdefault(m.group(1).strip(), ("equipment_structure_notes.txt", 0.88))
    comp_words = ("轴承", "销", "泵", "阀", "冷却器", "密封圈", "皮囊", "滑块", "丝杠",
                  "刀套", "滤芯", "冷却单元", "蓄能器", "拉刀机构")
    for fname in ("maintenance_manual_cnc.txt", "maintenance_manual_hydraulic.txt"):
        for line in read_text(fname).splitlines():
            for w in comp_words:
                for m in re.finditer(r"[\u4e00-\u9fa5]{0,3}" + w, line):
                    name = m.group(0)
                    bad_prefix = ("更换", "判定", "确认", "检查", "拆检", "清洁",
                                  "测量", "补充", "调整", "修复", "清洗", "检测")
                    if len(name) >= 3 and len(name) <= 6 and not name.startswith(bad_prefix):
                        part_src.setdefault(name, (fname, 0.72))
    for name, (src, conf) in part_src.items():
        cands.append(dict(kind="concept", head=f"Component:{name}", name=name, rel="",
                          tail="", confidence=conf, source=src, sentence=f"部件：{name}"))

    return cands


# ---------------- 分拣 ----------------
def main():
    seed = json.load(open(os.path.join(ONTO, "seed_ontology.json"), encoding="utf-8"))
    concepts = seed["concepts"]
    existing = {}
    for c in concepts:
        for key in [c["id"], c.get("name", "")] + list(c.get("examples", [])[:2]):
            if key:
                existing[norm(key)] = c["id"]
        for al in c.get("aliases", []):
            existing[norm(al)] = c["id"]

    candidates = extract()

    # 概念候选先做归并判定
    new_concepts, review, merged, instances = [], [], [], []
    concept_map = {}   # 原始 id -> 最终 id或新 id
    for c in [x for x in candidates if x["kind"] == "concept"]:
        raw_id, name = c["head"], c["name"]
        best_sim, best_id = 0.0, None
        for known_id, cid in existing.items():
            s = similarity(name or raw_id, known_id)
            if s > best_sim:
                best_sim, best_id = s, cid
        c["similarity"] = round(best_sim, 3)
        c["matched"] = best_id or ""
        if is_instance(raw_id):
            # 故障码/备件号/工单号/章节号属于实例，不进概念相似度判定，直接入图
            c["decision"] = "instance"
            concept_map[raw_id] = raw_id
            instances.append(c)
            continue
        if best_sim >= AUTO_MERGE and c["confidence"] >= CONF_AUTO:
            c["decision"] = "auto_merge"
            concept_map[raw_id] = best_id
            merged.append(c)
        elif best_sim >= REVIEW_LOW or c["confidence"] < CONF_AUTO:
            c["decision"] = "review"
            concept_map[raw_id] = raw_id
            review.append(c)
        else:
            c["decision"] = "auto_new"
            concept_map[raw_id] = raw_id
            new_concepts.append(c)

    # 关系候选：头尾都命中才建边
    rels_new, rels_review = [], []
    rel_seen = {(r["id"] if "id" in r else "", r.get("head"), r.get("tail")) for r in seed["relations"]}
    seed_rel = {(r["head"], r["tail"]) for r in seed["relations"]}
    for c in [x for x in candidates if x["kind"] == "relation"]:
        h, t = concept_map.get(c["head"], c["head"]), concept_map.get(c["tail"], c["tail"])
        c["head_resolved"], c["tail_resolved"] = h, t
        pending = {x["head"] for x in review}
        unresolved = c["head"] in pending or c["tail"] in pending
        if c["confidence"] >= CONF_AUTO and not unresolved:
            c["decision"] = "auto_new"
            rels_new.append(c)
        else:
            c["decision"] = "review"
            rels_review.append(c)

    # ---------------- 输出 ----------------
    all_c = [x for x in candidates if x["kind"] == "concept"]
    all_r = [x for x in candidates if x["kind"] == "relation"]

    fields = ["kind", "head", "rel", "tail", "name", "confidence",
              "similarity", "matched", "decision", "source", "sentence"]
    with open(os.path.join(ONTO, "extraction_candidates.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for x in all_c + all_r:
            w.writerow(x)

    q = [x for x in all_c + all_r if x["decision"] == "review"]
    with open(os.path.join(ONTO, "review_queue.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for x in q:
            w.writerow(x)

    # 合并后的本体
    onto = json.loads(json.dumps(seed, ensure_ascii=False))
    onto["version"] = "1.0"
    for c in new_concepts:
        onto["concepts"].append({
            "id": c["head"].replace(":", "_"),
            "name": c["name"] or c["head"],
            "definition": "由半自动流水线抽取（待人工复核）",
            "examples": [c["head"].split(":")[-1]],
            "standard": "",
            "provenance": {"source": c["source"], "sentence": c["sentence"],
                           "confidence": c["confidence"], "status": "auto_new"},
        })
    existing_pairs = {(r["head"], r["tail"]) for r in onto["relations"]}
    for c in rels_new:
        key = (c["head_resolved"], c["tail_resolved"])
        if key in existing_pairs:
            continue
        existing_pairs.add(key)
        onto["relations"].append({
            "id": f"{c['rel']}_{len(onto['relations'])}",
            "head": c["head_resolved"],
            "tail": c["tail_resolved"],
            "description": c["rel"],
            "provenance": {"source": c["source"], "sentence": c["sentence"],
                           "confidence": c["confidence"], "status": "auto_new"},
        })
    json.dump(onto, open(os.path.join(ONTO, "ontology_v1.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---------------- 报告 ----------------
    total = len(all_c) + len(all_r)
    auto = total - len(q)
    lines = []
    lines.append("# 半自动本体构建 · 首次运行报告\n")
    lines.append(f"- 种子本体：{len(seed['concepts'])} 个概念 / {len(seed['relations'])} 条关系")
    lines.append(f"- 抽取候选：{total} 条（概念 {len(all_c)}，关系 {len(all_r)}）")
    lines.append(f"- 自动处理：{auto} 条（{auto/total:.1%}）")
    lines.append(f"- 人工确认队列：{len(q)} 条（{len(q)/total:.1%}）")
    lines.append(f"- 其中：实例直接入图 {len(instances)} 条｜同义自动合并 {len(merged)} 条｜新概念 {len(new_concepts)} 个")
    lines.append(f"- 新增概念：{len(new_concepts)} 个；新增关系：{len(rels_new)} 条\n")
    lines.append("## 人工确认量对比\n")
    lines.append(f"| 口径 | 条目数 | 相对全量 |")
    lines.append(f"|---|---|---|")
    lines.append(f"| 全量人工标注 | {total} | 100% |")
    lines.append(f"| 半自动 + 人工复核 | {len(q)} | {len(q)/total:.1%} |")
    lines.append(f"| 人工量下降 | — | **{1-len(q)/total:.1%}** |\n")
    lines.append("## 相似度分布\n")
    buckets = Counter()
    for x in all_c:
        s = x["similarity"]
        b = "≥0.85" if s >= 0.85 else ("0.50~0.85" if s >= 0.5 else "<0.50")
        buckets[b] += 1
    for b in ("≥0.85", "0.50~0.85", "<0.50"):
        lines.append(f"- {b}：{buckets.get(b,0)} 条")
    # 阈值敏感性：不同 AUTO_MERGE 下的自动合并条数
    free = [x for x in all_c if x["decision"] != "instance"]
    lines.append("\n## 阈值敏感性（仅统计自由文本概念）\n")
    lines.append("| 相似度阈值 | 自动合并条数 | 占比 |")
    lines.append("|---|---|---|")
    for t in (0.70, 0.80, 0.85, 0.90):
        n = sum(1 for x in free if x["similarity"] >= t and x["confidence"] >= CONF_AUTO)
        lines.append(f"| {t:.2f} | {n} / {len(free)} | {n/len(free):.1%} |")
    lines.append("")
    lines.append("\n## 待确认样例（前 15 条）\n")
    lines.append("| 类型 | 内容 | 置信度 | 相似度 | 来源 |")
    lines.append("|---|---|---|---|---|")
    for x in q[:15]:
        content = x.get("sentence") or f"{x['head']} -{x['rel']}-> {x['tail']}"
        lines.append(f"| {x['kind']} | {content[:40]} | {x['confidence']:.2f} | "
                     f"{x.get('similarity','')} | {x['source']} |")
    open(os.path.join(ONTO, "extraction_report.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
