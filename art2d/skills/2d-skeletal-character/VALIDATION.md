# Skill 复现记录 · 余烬布丁

2026-11-06，使用此前未制作的紫色软体角色。项目根目录运行，无额外模型账号。根据 Skill 的需求卡和软体 Prompt 生成新的透明工作板，保存 [清单](../../assets/ember/concept/manifest.json)。复制软体模板，替换 ID、工作尺寸、独立阀门的位置和尺寸，裁后人工标两处锚点。

- 快速流程按步骤切件、构建 idle、跑数值 QA、渲染并检查 [主参考对比](../../assets/ember/preview/master_vs_bind.png) 和 [待机](../../assets/ember/preview/idle.gif)。产出两件独立 PNG、四骨和网格。
- 完整流程用 PowerShell 包装命令构建软体矩阵 11 段。最终 [自动 QA](../../assets/ember/qa/REPORT.md) 为 0 错误，复检 [前七段](../../assets/ember/preview/review_1.png) 与 [余下四段](../../assets/ember/preview/review_2.png)。额外测试新的网格面积门槛后修正压扁权重，再导出并重渲。
- 预览器实际选中验证角色、载入 idle。验证样例在清单标注 `validation: true`，与五个主 Demo 独立统计。[浏览器日志](../../demos/viewer/RESULTS.txt)
- 验证中补写了软体模板的必保控制骨、验证样例计数方式及 UTF-8 无 BOM。Windows 的结构校验器用 Python `-X utf8` 运行，校验 [通过](VALIDATOR.txt)。
