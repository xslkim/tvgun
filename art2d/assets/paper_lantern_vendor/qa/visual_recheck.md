# 卖糖葫芦居民重做复核

2026-11-06 · 右向三分之四人形 NPC / 人质。复用 T05 原纸纹、服装、糖葫芦及表情附件，以同尺度设定图核对绑定。[设定与绑定](../preview/master_vs_bind.png)

远臂先于躯干绘制，近臂位于身前，领口盖住颈根。握点移到拇指内侧，按后掌、竹签、前侧拇指、袖口顺序绘制。竹签在八个动作中保持世界角度 -16°，果串朝右上方，裸签在后掌前露出。求助姿势用右手张掌，收手切回放松手，担忧头部保持同一个颈锚。

`art2d/tools/qa/check_paper_grip.py` 检查了 2,492 个烘焙姿势。在每帧握点附近，竹签同时有一段露在后掌前、一段被拇指压住。近景覆盖站立、行走、求助和挣扎。[握持复核](grip_recheck.png)

八个动作按 120 Hz 烘焙，自动 QA 为 0 错误。30 fps 逐帧贴图检查的最大穿地值为 0。核对行走支撑、收手、落地和致谢的关键帧。 [自动 QA](REPORT.md) · [关键帧](../preview/review_1.png) · [致谢](../preview/review_2.png) · [贴图地线测量](../preview/raster_metrics.json)

附墨附件在显示高度 512 的 97 帧离线检查中，最小有效半径 48.08 像素，最窄纸边 8 像素，墨溢出为 0。获救动画在 0.20 秒隐藏墨，落地后恢复轻松表情。当前抽样使用原 `blob_00`，游戏内附墨变体、碰撞及真机接入另验。 [附墨复测](ink_attachment.json)

游戏交付入口在 `../export/character.json`，与同目录图集、clips 一起使用。可用 `build.ps1 paper_lantern_vendor` 重建。附墨复测用 GunForge art Python 环境运行 `art2d/tools/qa/check_paper_rescue.py`。
