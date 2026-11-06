---
name: 2d-skeletal-character
description: 为游戏制作横版 2D 骨骼角色，从原创设定或透明拆件图完成切件、绑定、动作、质检与图集导出。
---

# 2D 骨骼角色生产

在 `art2d` 目录执行。环境与交付入口见 [README](../../README.md)。

1. **确定需求。** 记录游戏视角、角色尺度、识别特征、所需动作和接地方式。选 [同形模板](../../pipeline/rig/templates/README.md) 起步，以游戏给定的设定为准。 [需求卡](templates/character_card.md) · [美术规范](../../docs/spec/ART_SPEC.md)
2. **保存来源。** 用 [提示词模板](references/prompt_library.md) 生成或取得设定与拆件。保存 `assets/<id>/concept/raw.png` 和 `manifest.json`，记录原始 Prompt、来源、参数、参考输入与授权。未提供的模型版本或 seed 写明不可用。
3. **切件与绑定。** 写 `concept/layout.json` 和 `concept/rig_layout.json`。裁框用原图像素，锚点用裁后比例。按设定图确定近远肢、关节位置和附件顺序。为动作中露出的隐藏面补齐贴图。 [人形切件样例](../../assets/courier/concept/layout.json) · [绑定规范](../../docs/spec/RIG_SPEC.md)
4. **从 idle 验证，再构建所需动作。** 运行 `./skills/2d-skeletal-character/scripts/build.ps1 <id> -Clips idle`，对照 `preview/master_vs_bind.png`。修好比例、遮挡和接缝后，重新运行并传入所需动作。动作参数由角色配置和 [曲线实现](../../pipeline/anim/clips.mjs) 提供。 [动画规范](../../docs/spec/ANIM_SPEC.md)
5. **验收并交付。** 查看 `qa/REPORT.md`、动作 GIF、关键帧和极限姿势。确认自动 QA 无错误，设定轮廓、配件、遮挡和脚底接触经人工或目视复核。交付整个 `export/`，并保留原图和生产配置。 [验收清单](references/checklists.md) · [故障排查](references/troubleshooting.md)

PowerShell 命令从已有原图执行切件、构建、QA 和渲染。省略 `-Clips` 会构建当前原型的全部模板动作。需要骨架 GIF 或洋葱皮时运行 `node tools/qa/render.mjs <id> idle --debug`。
