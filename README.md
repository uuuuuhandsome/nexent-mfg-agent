# 基于 Nexent 的先进制造异常诊断智能体

## 解决什么问题
数控机床报警后，一线人员需要在日志、维修手册、安全标准之间反复翻找，
平均耗时 40 分钟，且常因遗漏安全规程导致二次事故。

## 做了什么
一个能跨文档推理、并给出可溯源维修方案的智能体（基于华为 ModelEngine Nexent）。

## 技术栈
Nexent / ModelEngine · deepseek-v4-pro · Qwen3-VL-32B · bge-m3 · MCP

## 目录结构
- `docs/` 方案与答辩材料
- `data/` 样例数据
- `mcp_servers/` 自研 MCP 工具
- `skills/` 技能模板与提示词
- `eval/` 评测集

## 怎么跑
（待补）

## License
MIT
