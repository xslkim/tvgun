# T10 · 第一关美术制作

状态：T10 的四站和 20 项新素材已获 A5 画廊审核通过。四站原构图分层已通过 Godot 独立合成与命中回归。正式波次接入与角色动画验证仍待完成。

[A5 画廊](gallery/index.html) · [审核表](review.yaml) · [生成记录](generation_manifest.json)

四张玩法白模均为 1776×936 灰度图，保留 60 像素边缘带和项目 HUD 矩形。白模脚本检查了目标活动区与交互灯是否越界，以及是否和前景掩体、居民保护区或常驻 HUD 矩形相交。

- [糖葫芦摊](whiteboxes/stall.png)沿用已试玩通过的灯和六只墨鸦的位置与活动包络。
- [录像厅门口](whiteboxes/video_shop.png)预留卷帘门、电视柜、招牌、两侧敌人活动区和居民救援区。
- [天桥](whiteboxes/footbridge.png)预留跨画面的桥身、桥上与桥下两条横向通道。
- [广场](whiteboxes/square.png)预留中部横向游动空间和居民保护区。

构图使用[暂定布局数据](layouts.json)。录像厅门口、天桥和广场的目标及灯位以此进入构图制作，等正式关卡和逐层素材就位后复核命中遮挡、光照、运动范围和对比度。

每站比较四张构图。16 张均通过亮度初筛，第二轮在四站的色板覆盖率最高，因此选作分层制作的构图参考。构图草稿的色板结果与最终分层合成结果分别保留。[构图筛选数据](composition_screen.json) · [选稿记录](composition_selection.json)

画廊主图用第二轮入选构图直接导出关灯 JPG，点灯 JPG 只在同一张图的灯具或招牌周围增加局部暖光。两张均保留原稿尺寸。

- 糖葫芦摊 · [原始构图](compositions/stall_02.png) · [关灯 JPG](stations/stall/composition_off.jpg) · [点灯 JPG](stations/stall/composition_on.jpg)
- 录像厅门口 · [原始构图](compositions/video_shop_02.png) · [关灯 JPG](stations/video_shop/composition_off.jpg) · [点灯 JPG](stations/video_shop/composition_on.jpg)
- 天桥 · [原始构图](compositions/footbridge_02.png) · [关灯 JPG](stations/footbridge/composition_off.jpg) · [点灯 JPG](stations/footbridge/composition_on.jpg)
- 广场 · [原始构图](compositions/square_02.png) · [关灯 JPG](stations/square/composition_off.jpg) · [点灯 JPG](stations/square/composition_on.jpg)

画廊的四个相机角位和五个转场时刻也使用入选构图。相机样张从同一幅图轻微放大取景，避免移动到边缘时露底。转场终点使用下一站的关灯构图。画廊中的相机移动用于检查画面裁切，独立纸层的视差和遮挡另行验证。

原构图已重建为四站共 31 层。按物件轮廓分割远景、店面、前景、灯具，遮挡后新露出的部分由同一纸层的邻近像素补齐。灯具、灯光和命中遮罩使用同一视差位移。四站的八个挡弹遮罩由前景纸层的二值 alpha 导出。[分层标注](composition_layers.json)

Godot 4.6.3 Compatibility 在 RTX 3090 上抓取 40 帧，包含静止关灯和点灯、相机四角叠加同向及反向呼吸。静止关灯图与统一到内容尺寸的原稿逐像素一致，点灯最大通道差为 2/255，所有抓图视口完整并通过 C03。36 个视差位置的灯具命中、透明角落避让与前景挡弹均通过。新分层的移动范围、槽位与正式波次接入仍需在关卡中复核。[引擎检查](parallax/engine_checks.json)

- 糖葫芦摊 · [Godot 关灯](parallax/frames/stall_rest.jpg) · [点灯](parallax/frames/stall_lit.jpg) · [视差](parallax/frames/stall_corner_2.jpg)
- 录像厅门口 · [Godot 关灯](parallax/frames/video_shop_rest.jpg) · [点灯](parallax/frames/video_shop_lit.jpg) · [视差](parallax/frames/video_shop_corner_2.jpg)
- 天桥 · [Godot 关灯](parallax/frames/footbridge_rest.jpg) · [点灯](parallax/frames/footbridge_lit.jpg) · [视差](parallax/frames/footbridge_corner_2.jpg)
- 广场 · [Godot 关灯](parallax/frames/square_rest.jpg) · [点灯](parallax/frames/square_lit.jpg) · [视差](parallax/frames/square_corner_2.jpg)

早期独立纸层方案的检查另存如下。24 张技术抽样帧通过 C03，八张分层关灯或点灯抽样帧的 C04 覆盖率为 95.9% 至 98.9%。

- [糖葫芦摊分层检查](stations/stall/checks.json)
- [录像厅门口分层检查](stations/video_shop/checks.json)
- [天桥分层检查](stations/footbridge/checks.json)
- [广场分层检查](stations/square/checks.json)

20 项新素材均已重检。五件道具与灯具保留了原有的明暗与材质纹理，四种纸屑恢复各自颜色。六种墨花统一为深靛墨色，重新生成了带植物装饰的环形墨花、误生成街景的垂直滴落和带装饰边的低位墨池。十张特效纹理均为 512×512 透明 PNG。

18 项独立纹理通过 C01、C03、C04，三个墨怪通过静态硬化眼包含与 C16 距离场检查。新版画廊的 81 张 JPG 均可解码。

三个墨怪修复了朱砂分离后的残留，画廊提供朱砂态和硬化态。墨身、朱砂、硬化眼和距离场分开保存。两个纸偶的步态和弹跳姿势修复了交叉腿，16 张采样姿势各有一个主要连通轮廓，144 处采样关节均有像素交叠。引擎中的关节极限和墨怪动画对位仍待验证。[素材检查数据](asset_screen.json)

内置 imagegen 共调用 88 次，全部返回图像，费用未披露。16 次构图调用选入 4 张，49 次底层、纸层和补件调用形成四站分层包，23 次独立素材与分件调用形成 20 项候选。三张新版墨花的提示词与来源记录在生成清单中。[生成清单](generation_manifest.json)

原始构图保留用户确认时的颜色。其 C04 初筛覆盖率仍为 71.8% 至 80.7%。C05 OCR 报告保留机器原始结果，复看图像未发现对应文字。C14 标定评分仍待完成。
