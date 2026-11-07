# 录像厅老板重做复核

2026-11-06 · 右向三分之四人形 NPC / 人质。用老板自己的夹克领口、袖口和录像带盒标注，复用 T05 原画与担忧表情。 [设定与绑定](../preview/master_vs_bind.png)

近远臂采用固定的三分之四绘制顺序。握点设在靠手一侧的盒子上角，按后掌、录像带盒、前侧拇指、袖口顺序绘制。盒角从掌前露出，拇指盖住接触处，盒身随腕部在手下方垂挂。近侧右手切换放松和求助手掌。

`art2d/tools/qa/check_paper_grip.py` 检查了 2,492 个烘焙姿势。每帧盒角同时与后掌和前侧拇指形成遮挡。近景覆盖站立、行走、求助和挣扎。[握持复核](../../paper_lantern_vendor/qa/grip_recheck.png)

八个动作按 120 Hz 烘焙，自动 QA 为 0 错误。30 fps 逐帧贴图检查的最大穿地值为 0。 [自动 QA](REPORT.md) · [关键帧](../preview/review_1.png) · [致谢](../preview/review_2.png) · [贴图地线测量](../preview/raster_metrics.json)

附墨附件在显示高度 300 的 97 帧离线检查中，最小有效半径 43.63 像素，最窄纸边 7.62 像素，墨溢出为 0。获救动画在 0.20 秒隐藏墨，落地后恢复轻松表情。当前抽样使用原 `blob_00`，游戏内附墨变体、碰撞及真机接入另验。 [附墨复测](ink_attachment.json)

游戏交付入口在 `../export/character.json`，与同目录图集、clips 一起使用。可用 `build.ps1 paper_lantern_video` 重建。附墨复测用 GunForge art Python 环境运行 `art2d/tools/qa/check_paper_rescue.py`。
