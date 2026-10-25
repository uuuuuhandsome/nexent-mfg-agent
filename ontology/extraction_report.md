# 半自动本体构建 · 首次运行报告

- 种子本体：40 个概念 / 37 条关系
- 抽取候选：210 条（概念 75，关系 135）
- 自动处理：177 条（84.3%）
- 人工确认队列：33 条（15.7%）
- 其中：实例直接入图 38 条｜同义自动合并 4 条｜新概念 6 个
- 新增概念：6 个；新增关系：129 条

## 人工确认量对比

| 口径 | 条目数 | 相对全量 |
|---|---|---|
| 全量人工标注 | 210 | 100% |
| 半自动 + 人工复核 | 33 | 15.7% |
| 人工量下降 | — | **84.3%** |

## 相似度分布

- ≥0.85：17 条
- 0.50~0.85：15 条
- <0.50：43 条

## 阈值敏感性（仅统计自由文本概念）

| 相似度阈值 | 自动合并条数 | 占比 |
|---|---|---|
| 0.70 | 4 / 37 | 10.8% |
| 0.80 | 4 / 37 | 10.8% |
| 0.85 | 4 / 37 | 10.8% |
| 0.90 | 4 / 37 | 10.8% |


## 待确认样例（前 15 条）

| 类型 | 内容 | 置信度 | 相似度 | 来源 |
|---|---|---|---|---|
| concept | 部件：导轨滑块 | 0.90 | 0.571 | fault_code_dictionary.csv |
| concept | 部件：冷却泵 | 0.90 | 0.667 | fault_code_dictionary.csv |
| concept | 部件：冷却器 | 0.90 | 0.667 | fault_code_dictionary.csv |
| concept | 部件：刀套 | 0.88 | 0.5 | equipment_structure_notes.txt |
| concept | 部件：接触球轴承 | 0.72 | 0.5 | maintenance_manual_cnc.txt |
| concept | 部件：拉刀机构 | 0.72 | 0.333 | maintenance_manual_cnc.txt |
| concept | 部件：换主轴轴承 | 0.72 | 0.92 | maintenance_manual_cnc.txt |
| concept | 部件：机更换轴承 | 0.72 | 0.5 | maintenance_manual_cnc.txt |
| concept | 部件：轨润滑泵 | 0.72 | 0.571 | maintenance_manual_cnc.txt |
| concept | 部件：换导轨滑块 | 0.72 | 0.5 | maintenance_manual_cnc.txt |
| concept | 部件：或滚珠丝杠 | 0.72 | 0.0 | maintenance_manual_cnc.txt |
| concept | 部件：换刀时刀套 | 0.72 | 0.286 | maintenance_manual_cnc.txt |
| concept | 部件：定位销 | 0.72 | 0.167 | maintenance_manual_cnc.txt |
| concept | 部件：换定位销 | 0.72 | 0.154 | maintenance_manual_cnc.txt |
| concept | 部件：时更换刀套 | 0.72 | 0.286 | maintenance_manual_cnc.txt |