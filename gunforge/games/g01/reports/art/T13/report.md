# T13 火车站玩法白模

第三关五站已完成暂定布局。候车室以长窗、长椅和检票栏分区，站台与绿皮车厢用横向重复的车窗和行李架。灯座留出拉镜起点，工作台在砚台上方预留 640×640 的七笔字形区域。

四个战斗站共预留 8 个敌人活动区、2 个保护角色位和 4 个灯位。站台复用 T12 检票员，候车室使用路人 C。灯位涵盖站灯、信号灯、车厢顶灯三种，白模椭圆有效半径为 62.66–68.83 像素。目标区、居民和灯位与近景掩体、游玩 HUD 及安全边带的几何检查通过，字形预留区也避开了这些区域。[布局](layouts.json) · [几何检查](whitebox_checks.json)

[候车室 JPG](whiteboxes/waiting_room.jpg) · [站台 JPG](whiteboxes/platform.jpg) · [绿皮车厢 JPG](whiteboxes/green_car.jpg) · [灯座 JPG](whiteboxes/lantern_base.jpg) · [工作台 JPG](whiteboxes/workbench.jpg)

## 「忘」字七笔遮罩

已制作七张 2048×2048 遮罩，在工作台 640×640 预留区内按笔顺叠放。第 3 笔竖折盖住第 2 笔横画的 363 个显示像素。按后写笔画遮挡前笔、半径 12 开运算的口径，七笔有效半径为 40.71–75.46 像素，均达到 40 像素门槛。[原字形 JPG](forget_strokes/glyph.jpg) · [笔顺和交叉层级 JPG](forget_strokes/stroke_order.jpg) · [遮挡与命中面积记录](forget_strokes/geometry.json)

原始轮廓取自 Make Me a Hanzi `graphics.txt` 的 U+5FD8 记录，固定在 `bddc96d41bef78427ed0e034e9f7e31d71fd1b92`。该文件的上游授权为 Arphic Public License。保留单字源记录和未改写的授权文本，遮罩及 JPG 内嵌来源、改制内容与日期。[上游授权声明](https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/COPYING) · [单字源记录](forget_strokes/forget-graphics.json) · [授权文本](forget_strokes/ARPHICPL.TXT)

审核时查看编号 JPG，确认七笔的轮廓、笔顺和第 2、3 笔交叉关系，并确认授权记录。第三关站点构图可继续推进。七笔遮罩审核通过后进入 Boss 质感制作。

## 候车室构图候选

内置 imagegen 生成三版后选定第三版。左侧保留长窗和长椅，右下为检票栏，中间给路人 C 留出站位。灯箱熄灭时仍可认出深青边框与灰色玻璃，实图灯体中心落在白模灯位内，避开游玩 HUD、掩体和目标槽。分层时按实图灯体位置对齐发光层与命中遮罩。[候车室候选 JPG](compositions/waiting_room.jpg) · [白模 JPG](whiteboxes/waiting_room.jpg) · [三次提示词与检查记录](waiting_room_generation.json)

原构图的 1776×936 JPG 通过 C03 亮度检查，C04 色板覆盖率为 65.05%。

## 候车室分层与灯光

沿用原构图，将背景、后墙、地面、长窗、梁柱、灯箱、长椅、检票栏与两侧前景拆成 10 层。连续色阶修正后，分层渲染源的 C04 覆盖率为 93.04%，达到 90% 门槛。关灯 GPU 帧与分层渲染源逐像素一致，点灯只改变灯体和预定漏光区域，区域外像素完全一致。[关灯 JPG](parallax/frames/waiting_room_rest.jpg) · [点灯 JPG](parallax/frames/waiting_room_lit.jpg) · [视差极限 JPG](parallax/frames/waiting_room_corner_2.jpg)

灯体、命中遮罩和光区共用视差位移。灯体有效命中半径为 51.05 像素，完整运动范围避开 HUD 和安全边带。Godot 在静止及八个视差采样点确认灯心可命中、透明角避让、两侧前景挡弹。10 张 GPU 抓图均通过 C03，画面无露底。候车室可玩接入待推进。[分层标注](composition_layers.json) · [素材检查](parallax/art_checks.json) · [引擎记录](parallax/engine_checks.json)

## 站台构图候选

内置 imagegen 三版中选定第三版。绿皮车厢与黄色腰线横贯站台，连续车窗形成横向节奏，中央月台给检票员留出站位，行李放在下方两角。实图站台钟中心落在白模标记内，右侧未点亮的竖式信号灯完整落在灯位内，避开 HUD、掩体与目标槽。车窗行比白模标记偏低，分层时按实图位置标注。[站台候选 JPG](compositions/platform.jpg) · [站台白模 JPG](whiteboxes/platform.jpg) · [提示词与检查记录](platform_generation.json)

原构图的 1776×936 JPG 通过 C03 亮度检查，C04 色板覆盖率为 79.41%。

## 站台分层与信号灯

站台拆成 9 层。色板修正集中在可见车厢，分层渲染源的 C04 覆盖率达到 93.27%。信号灯原轮廓的有效半径为 39.53 像素，灯体和命中遮罩绕同一中心放大 13% 后达到 44.55 像素。完整视差范围避开 HUD 和安全边带。[关灯 JPG](parallax/frames/platform_rest.jpg) · [点灯 JPG](parallax/frames/platform_lit.jpg)

梁柱、车厢和信号灯同步移动，行李箱按实图轮廓挡弹，边缘补图采用延展。极限位移下最外侧仍可见少量补边。Godot 的 10 张站台抓图均通过 C03，关灯帧逐像素匹配分层渲染源，点灯只改变预定光区。灯心命中、透明角避让、两侧行李挡弹和候车室回归均通过。[视差极限 JPG](parallax/frames/platform_corner_2.jpg) · [素材检查](parallax/art_checks.json) · [引擎记录](parallax/engine_checks.json)

## 绿皮车厢构图候选

内置 imagegen 三版中选定第三版。侧视构图保留连续车窗、行李架和黄色腰线，中央通道留空。两侧座椅位于下角，避开两个敌人活动区。顶灯调整为约 180×71 像素，灯体完整落在白模灯位内，保留灰蓝玻璃的熄灯状态。[绿皮车厢 JPG](compositions/green_car.jpg) · [白模 JPG](whiteboxes/green_car.jpg) · [提示词与检查记录](green_car_generation.json)

原构图的 1776×936 JPG 通过 C03，C04 色板覆盖率为 94.21%。车窗行比白模标记偏低，按实图对齐分层。

## 绿皮车厢分层与顶灯

车厢拆成 9 层。窗框、车壁、行李架和顶灯同步移动，窗外景物使用较慢的视差，两侧座椅按实图轮廓挡弹。关灯 GPU 帧与归一到 1776×936 的原构图逐像素一致，分层渲染源 C04 覆盖率为 94.22%。点灯只改变顶灯和预定漏光区域，区域外像素完全一致。[关灯 JPG](parallax/frames/green_car_rest.jpg) · [点灯 JPG](parallax/frames/green_car_lit.jpg)

顶灯有效命中半径为 59.30 像素，完整运动范围避开 HUD 和安全边带。静止和八个视差采样点的灯心命中、透明角避让和两侧座椅挡弹均通过。车厢的 10 张 GPU 抓图通过 C03，候车室和站台的 20 张复验帧逐像素匹配上一轮。[视差极限 JPG](parallax/frames/green_car_corner_2.jpg) · [素材检查](parallax/art_checks.json) · [引擎记录](parallax/engine_checks.json)

## 灯座构图候选

内置 imagegen 两版中选定第二版。弧形环梁、竖向灯骨和下方足座呈现纸灯内部。熄灭的站灯约 147×74 像素，完整落在白模灯位内。下方足座实体比白模参考框更靠下，顶部中央 `(888, 723)` 落在拉镜预留区。足座、站灯和两侧低矮遮挡均避开敌人活动区。[灯座 JPG](compositions/lantern_base.jpg) · [白模 JPG](whiteboxes/lantern_base.jpg) · [提示词与检查记录](lantern_base_generation.json)

1776×936 JPG 通过 C03，C04 色板覆盖率为 96.57%。

## 灯座分层与灯光

灯座拆成 9 层。纸面、灯骨、环梁、地面和站灯同步移动，足座和两侧遮挡使用较快视差。拉镜起点 `(888, 723)` 落在足座实体内。关灯 GPU 帧逐像素匹配归一后的原构图。点灯只改变站灯和预定漏光区域，区域外像素完全一致。分层渲染源的 C04 色板覆盖率为 96.56%。[关灯 JPG](parallax/frames/lantern_base_rest.jpg) · [点灯 JPG](parallax/frames/lantern_base_lit.jpg)

站灯有效命中半径为 54.00 像素。静止和八个视差采样点的灯心命中、透明角避让及两侧挡弹均通过。四站的 40 张 Godot GPU 抓图通过 C03 和画面覆盖检查，前三站的 30 张抓图逐像素匹配上一轮。下一步准备工作台实图构图。[视差极限 JPG](parallax/frames/lantern_base_corner_2.jpg) · [素材检查](parallax/art_checks.json) · [引擎记录](parallax/engine_checks.json)

## 工作台构图候选

内置 imagegen 生成工作台背景。纸灯位于左下，砚台居中放在桌面，笔架和卷纸靠右。中央 640×640 的字形区域只保留青绿墙面。按已有七笔遮罩做静态对比检查，墨黑和底图的各笔画亮度中位差为 0.5078–0.5460。Boss 最终质感和 C06 留待签核后验证。[工作台 JPG](compositions/workbench.jpg) · [白模 JPG](whiteboxes/workbench.jpg)

为通过色板检查，对木质道具和桌面的暖色中间调做连续色阶修正。1776×936 JPG 通过 C03，C04 色板覆盖率为 92.55%。OCR 返回低置信度结果，检查画面未见文字。下一步拆分墙面、桌面、纸灯、砚台和两侧道具，并验证视差及拉镜落点。[原图、提示词和检查记录](workbench_generation.json)

## 工作台分层与镜头锚点

工作台拆成 6 层。墙面使用较慢的视差，桌面、纸灯、砚台、笔架和卷纸同步移动。静止 GPU 帧逐像素匹配调色后的构图，渲染源 C04 色板覆盖率为 92.62%。[静止 JPG](parallax/frames/workbench_rest.jpg) · [视差极限 JPG](parallax/frames/workbench_corner_2.jpg)

拉镜锚点在左侧纸灯底座 `(281, 827)`，墨池锚点在砚台中心 `(888, 806)`。静止和八个视差采样点中，两个锚点均留在各自的可见轮廓内。字形预留区跟随砚台移动，完整运动范围避开桌面、道具、游玩 HUD 和安全边带。五站共 49 张 Godot GPU 抓图通过 C03 和画面覆盖检查，前四站的 40 张抓图逐像素匹配上一轮。下一步接入候车室可玩候选。实际拉镜演出与 Boss 接入待验证。[工作台素材包](parallax/workbench/station.json) · [素材检查](parallax/art_checks.json) · [引擎记录](parallax/engine_checks.json)

## 候车室可玩候选

`paper.waiting_room` 已接入候车室分层、墨鸦、墨伞和路人 C。路人 C 沿用 T09 设定，拆成 10 个纸偶部件，8 个离线姿态的关节连接通过。可玩流程验证了纸居民保护区、胸口墨团和获救姿态。极限动作的 C10 人工复核留到 A5。[待机 JPG](actors/passerby_c/idle.jpg) · [获救 JPG](gameplay/waiting_room/waiting_room_rescue.jpg) · [分件检查](actors/passerby_c/checks.json)

站灯每次消耗一发，照亮 6 秒后可再点。墨鸦在灯暗时仍会预警和扑击，进入光区后才变软。撑开的伞面无效，收伞过程挡弹，收完后露出可射的墨身。Godot 软件回归通过最后一发点灯后换弹、成功通关、无操作失败和重试。成功流程在 8 发内完成，保留 5 条灯芯并救出路人。7 张 GPU 抓图通过 C03。T12 旧影院的五站回归也通过。[关灯 JPG](gameplay/waiting_room/waiting_room_off.jpg) · [点灯 JPG](gameplay/waiting_room/waiting_room_lit.jpg) · [墨鸦攻击 JPG](gameplay/waiting_room/crow_attack.jpg) · [墨伞收伞 JPG](gameplay/waiting_room/umbrella_folding.jpg) · [软件验收记录](gameplay/waiting_room/software_checks.json)

候选可用下列命令启动。显示器和电视光枪实测留到第三关集中验收。下一步接入站台的信号灯、检票员和战斗。

2026-11-11 用户确认候车室候选验收通过，确认对应构建 `7d1b286b8e8f8a28588c1b3e52766624c6e116b9f19f89e0a0b8f6049ade2265`。第三关整体 A5 与设备实测按里程碑集中记录。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.waiting_room -Candidate
```

## 站台可玩候选

`paper.platform` 接入信号灯、两侧行李遮挡和 T12 检票员。左侧墨鸦在月台巡飞，可直接净化。右侧墨伞的活动位比白模向右 105 像素、向上 42 像素，使露出的墨身进入右侧信号灯的实际光区。撑伞时命中无效，收伞过程挡弹，收完后点亮信号灯可净化。信号灯一次照亮 6 秒，收伞后的实测可射时间为 323 帧，约 5.38 秒。[关灯 JPG](gameplay/platform/platform_folded_dark.jpg) · [点灯 JPG](gameplay/platform/platform_lit.jpg)

Godot 验证了两类敌人的暗场预警、出手和伤害、信号灯重新点亮、两侧行李挡弹、检票员保护区及胸口墨团救援。成功流程用 10 发覆盖命中和误射分支，保留 5 条灯芯并救出检票员。无操作失败及重试通过，8 张 GPU 抓图通过 C03。候车室复跑通过，用户验收对应的候车室关卡源一致。[墨伞攻击 JPG](gameplay/platform/platform_umbrella_attack.jpg) · [获救 JPG](gameplay/platform/platform_rescued.jpg) · [软件验收记录](gameplay/platform/software_checks.json)

站台的 A5 与显示器、电视光枪实测留到第三关集中验收。下一步接入绿皮车厢。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.platform -Candidate
```

## 绿皮车厢可玩候选

`paper.green_car` 接入车厢顶灯、两侧座椅、墨鸦和墨伞。墨鸦从左侧座椅后飞出，座椅遮住的部位会挡弹。点亮顶灯后，墨鸦飞进光区才软化，飞出光区时再次硬化。实测连续可射 231 帧，约 3.85 秒。右侧墨伞收完伞即可净化，暗场中的墨鸦仍有攻击预警和扑击效果。[入场 JPG](gameplay/green_car/green_car_entry.jpg) · [光区外 JPG](gameplay/green_car/green_car_outside_spill.jpg) · [进入光区 JPG](gameplay/green_car/green_car_lit.jpg)

Godot 验证了两侧座椅挡弹、顶灯到期与重新点亮、收伞命中权限、暗场扑击、成功通关和失败重试。包含挡弹与无效命中的测试流程共 7 发，通关时保留 5 条灯芯。7 张 GPU 抓图通过 C03，候车室和站台也通过复跑。[扑击 JPG](gameplay/green_car/green_car_crow_attack.jpg) · [收伞 JPG](gameplay/green_car/green_car_folding.jpg) · [软件验收记录](gameplay/green_car/software_checks.json)

绿皮车厢的 A5 与显示器、电视光枪实测留到第三关集中验收。下一步接入灯座战斗。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.green_car -Candidate
```

## 灯座可玩候选

`paper.lantern_base` 接入中央站灯和两侧前景遮挡。右侧墨鸦巡飞进入光区，左侧墨伞活动位向右移 125 像素、向上移 52 像素，让露出的墨身落入同一盏灯的光区。点亮一次即可完成两侧净化，实测共同可射 134 帧，约 2.23 秒。关灯时两类敌人仍会预警和出手。两侧挡弹、收伞、复点、无伤通关和失败重试均通过。[关灯 JPG](gameplay/lantern_base/lantern_base_folded_dark.jpg) · [点灯 JPG](gameplay/lantern_base/lantern_base_lit.jpg) · [墨伞攻击 JPG](gameplay/lantern_base/lantern_base_umbrella_attack.jpg)

清空战斗后锁定射击输入，静止坐标 `(888, 723)` 的拉镜起点随视差移动，仍落在足座轮廓内。7 张 Godot GPU 抓图通过 C03，候车室、站台和绿皮车厢均通过复跑。下一步接入从灯座拉出到工作台的演出。灯座的 A5 与显示器、电视光枪实测留到第三关集中验收。[通关后 JPG](gameplay/lantern_base/lantern_base_handoff.jpg) · [软件验收记录](gameplay/lantern_base/software_checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.lantern_base -Candidate
```

## 拉出纸灯到工作台

`paper.lantern_pullback` 在灯座战斗通关后锁定射击，先推近内部足座，再以足座为共同焦点叠化到纸灯外侧，约 2.53 秒拉回工作台全景。镜头使用两张已通过色板检查的场景渲染源，落地后由工作台六层接管。首版的小数坐标触发了加载器的校验失败，改用整像素偏移和可精确表示的倍率后，构建通过校验并从正式启动入口打开。[灯座特写 JPG](gameplay/lantern_pullback/pullback_inside_rim.jpg) · [纸灯近景 JPG](gameplay/lantern_pullback/pullback_paper_lantern.jpg) · [工作台落地 JPG](gameplay/lantern_pullback/pullback_workbench.jpg)

Godot 验证了失败时不触发过场、过场禁射、两处足座锚点对齐、镜头插值的完整画面覆盖、抵达工作台及重试。两次切换的可见纹理均已缓存，7 张 GPU 抓图均完全不透明并通过 C03。下一步串联四个战斗站与工作台落地。工作台 Boss 接入待「忘」字遮罩签核。[软件验收记录](gameplay/lantern_pullback/software_checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.lantern_pullback -Candidate
```

## 火车站连续候选

`paper.train_station` 串联候车室、站台、绿皮车厢和灯座，战斗清空后拉出纸灯并抵达工作台。灯芯、光弹、分数和救援人数在五次切换中延续。Godot 验证了站台失败后重试、用最后一发点灯后换弹、上一站的旧瞄准帧无法激活灯、过场禁射，以及 16 条输入回放重现整段流程。测试路线用 14 发，抵达工作台时有 4 条灯芯、10 发光弹、2 人获救和 1000 分。[软件验收记录](gameplay/train_station/software_checks.json)

五次切换时可见纹理均已缓存，五站 GPU 抓图通过 C03。前两关使用原验收构建复跑十站通过。[候车室 JPG](gameplay/train_station/waiting_room.jpg) · [站台 JPG](gameplay/train_station/platform.jpg) · [绿皮车厢 JPG](gameplay/train_station/green_car.jpg) · [灯座 JPG](gameplay/train_station/lantern_base.jpg) · [工作台 JPG](gameplay/train_station/workbench.jpg)

灯光预载前，站台首次点亮信号灯时有一帧耗时 30.05 ms，其中纹理上传耗时 27.58 ms。引擎现在随墨遮层预载并保留绑定的灯光纹理，点灯时直接使用缓存。[调整前的帧时记录](gameplay/train_station/performance.json)

同一 RTX 3090 上复测两轮，共 3280 帧。四站八次首次点灯均无纹理上传，站台信号灯帧为 1.84–1.91 ms。五处切换帧为 1.32–2.94 ms，两轮最慢帧为 5.01 ms。C15 预算通过，单站常驻峰值 39.70 MiB，含预载峰值 61.35 MiB。五站抓图与调整前逐像素一致。用新引擎重新构建前两关已验收的关卡源，十站通关、两条失败重试路径及纹理回收均通过。下一步整理 A5 画廊和验收入口。[灯光预载复测](gameplay/train_station/light_preload.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.train_station -Candidate
```

## A5 预审画廊

画廊集中展示四站同构图的关灯与点灯、工作台落地、拉镜足座对齐，以及路人 C、检票员和墨怪的游玩画面。Chrome 在桌面和手机宽度均加载了 14 张原尺寸 JPG，检查了 53 条链接和站点导航。遮罩 JPG、单字源记录和授权原文的哈希与几何记录一致。[打开预审画廊](gallery.html)

当前可先签核「忘」字轮廓、1–7 笔顺及第 3 笔盖住第 2 笔的层级，并确认来源和授权记录。整关 A5 与显示器、电视光枪实测留到 Boss 接入后。下一轮用引擎抓图核查四站 C06 可读性。[编号 JPG](forget_strokes/stroke_order.jpg) · [授权原文](forget_strokes/ARPHICPL.TXT)

## 四站 C06 可读性筛查

在 Godot 中固定姿态、视差和灯光，对四站共 21 个状态抓取成对画面。普通态使用可命中墨身遮罩，比较目标与同一帧移除目标后的底图。8 个样本中，灯座两例的亮度中位差分别为 0.379 和 0.328，达到 0.20 门槛。候车室、站台和绿皮车厢的六例为 0.063–0.179，待改善。[可射与硬化态 1/8 JPG](gameplay/readability/targets_1_8.jpg)

硬化态当前复用调暗的朱砂印记。5 个样本的印记亮度中位差为 0.053–0.114，正式的眼部指标仍待独立表现接入后验证。8 个预警在 1/8 缩略图均保留可见差异，最终轮廓和预警可读性留待 A5。下一轮制作独立的对比度改进候选，从候车室开始复测。[预警 1/8 JPG](gameplay/readability/warnings_1_8.jpg) · [引擎样本与数值记录](gameplay/readability/checks.json)

## 候车室对比度试样

在同一构图内调整后墙和窗玻璃色阶，让原有墨身轮廓落在较亮的蓝纸背景上。同帧、同命中遮罩比较中，墨鸦的亮度中位差由 0.063 升至 0.336，墨伞由 0.082 升至 0.256。包括四个补充时刻在内，六个普通态样本均达到 0.20 门槛，最低为 0.214。[墨鸦原版 JPG](variants/waiting_room_contrast/comparison/crow_before.jpg) · [墨鸦试样 JPG](variants/waiting_room_contrast/comparison/crow_after.jpg) · [墨伞原版 JPG](variants/waiting_room_contrast/comparison/umbrella_before.jpg) · [墨伞试样 JPG](variants/waiting_room_contrast/comparison/umbrella_after.jpg)

试样的 C04 色板覆盖率为 92.17%。10 张视差抓图通过 C03 与完整覆盖检查，点灯变化限制在预定光区。候车室完整玩法回归通过，包括暗场预警、最后一发点灯、换弹、救援和失败重试。独立候选的后墙与玻璃色调待美术复核，硬化态提示仍待完善。[极限视差 JPG](variants/waiting_room_contrast/parallax/frames/waiting_room_corner_2.jpg) · [试样验收记录](variants/waiting_room_contrast/comparison/checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.waiting_room_contrast -Candidate
```

## 站台对比度试样

沿原车窗轮廓提亮玻璃和邻近车壁。同帧、同命中遮罩比较中，墨鸦的亮度中位差由 0.158 升至 0.319，墨伞由 0.179 升至 0.304。六个可射样本均达到 0.20 门槛，最低为 0.225，出现在墨鸦扑击画面。[墨鸦原版 JPG](variants/platform_contrast/comparison/crow_before.jpg) · [墨鸦试样 JPG](variants/platform_contrast/comparison/crow_after.jpg) · [墨伞原版 JPG](variants/platform_contrast/comparison/umbrella_before.jpg) · [墨伞试样 JPG](variants/platform_contrast/comparison/umbrella_after.jpg)

C04 色板覆盖率为 90.57%，9 张玩法样本和 10 张视差抓图均通过 C03。信号灯命中遮罩、软化区域和行李挡弹遮罩与原版一致。新旧构建均通过失败重试、信号灯到期和重新点亮、挡弹与救援回归，收伞后的可射窗口为 323 帧。车窗色调和缩略图辨识度待美术复核，硬化态提示仍待完善。[极限视差 JPG](variants/platform_contrast/parallax/frames/platform_corner_2.jpg) · [试样验收记录](variants/platform_contrast/comparison/checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.platform_contrast -Candidate
```

## 绿皮车厢对比度试样

沿四扇车窗的原有开口提亮窗外景物，保留原有的建筑、山线和车厢构图。同帧、同命中遮罩比较中，墨鸦的亮度中位差由 0.096 升至 0.331，墨伞由 0.065 升至 0.294。六个可射样本均达到 0.20 门槛，最低为 0.219。[墨鸦原版 JPG](variants/green_car_contrast/comparison/crow_before.jpg) · [墨鸦试样 JPG](variants/green_car_contrast/comparison/crow_after.jpg) · [墨伞原版 JPG](variants/green_car_contrast/comparison/umbrella_before.jpg) · [墨伞试样 JPG](variants/green_car_contrast/comparison/umbrella_after.jpg)

C04 色板覆盖率为 94.32%，9 张玩法样本和 10 张视差抓图均通过 C03。顶灯命中与软化遮罩、座椅挡弹遮罩和各层边界与原版一致。两版均通过座椅挡弹、顶灯到期和重新点亮、墨鸦进出光区、墨伞收伞及失败重试，墨鸦连续可射窗口为 231 帧。窗外色调和缩略图辨识度待美术复核。下一轮核查可复用的硬化眼资产与四站接入方式。[极限视差 JPG](variants/green_car_contrast/parallax/frames/green_car_corner_2.jpg) · [试样验收记录](variants/green_car_contrast/comparison/checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.green_car_contrast -Candidate
```

## 四站硬化眼试样

四个战斗站的五个硬化目标接入成对的暖纸色细眼。墨鸦沿用 A2e 认可的眼形、位置和材质，墨伞试样将同形眼纹对齐收伞后的墨身中心。进入光区软化后恢复原有朱砂印记。五个固定姿态中，10 只眼的亮度中位差为 0.530–0.595，单眼长度为 18–22 像素，达到 C06 的 0.30 和 16 像素门槛。命中眼部仍判为无效，八个普通态样本的命中遮罩和对比度与原版一致。[五处原版与试样 JPG](variants/hardened_eyes/comparison/eyes_before_after.jpg) · [候车室整帧 JPG](variants/hardened_eyes/comparison/waiting_room_crow_after.jpg) · [站台整帧 JPG](variants/hardened_eyes/comparison/platform_umbrella_after.jpg)

21 张玩法样本通过 C03。四站通关、五次切换、失败重试及 16 条输入回放通过，四次首次点灯的纹理上传均为零。RTX 3090 的 1640 帧回放中最慢一帧为 9.16 ms。前两关十站通关及通用运行时回归通过。墨伞眼形和 1/8 缩略图辨识度留待 A5。下一轮将三站普通态对比度试样与硬化眼合到同一个预审构建。[软件验收记录](variants/hardened_eyes/comparison/checks.json)

```powershell
.\gunforge\start_level_player.ps1 -Package paper.train_station_hardened -Candidate
```

候车室开场先看墨鸦胸口的双眼，再射亮顶灯。墨鸦飞入光区时，双眼应切换为朱砂印记。

## 可读性合并候选

`paper.train_station_readability` 把候车室、站台、绿皮车厢的普通态对比度试样与四站硬化眼接到同一条路线。20 个普通态样本的最小亮度中位差为 0.214，五个硬化姿态的 10 只眼均为 18–22 像素，亮度中位差最低为 0.529。33 张样本通过 C03，八个预警在 1/8 缩略图保留可见差异。八个同姿态普通态样本的命中遮罩与原版逐像素一致。[普通态同姿态 JPG](variants/combined_readability/normal_before_after.jpg) · [硬化眼同姿态 JPG](variants/combined_readability/hardened_before_after.jpg) · [1/8 缩略图与数值](gallery.html#combined-readability)

Windows Godot 4.6.3 验证四站点灯、挡弹、失败重试、跨站资源和 16 条输入回放。两轮连续回放共渲染 3286 帧，四站首次点灯均为零纹理上传，五次切换可见纹理均已缓存。RTX 3080 Ti 两轮最慢一帧 8.38 ms，含预载的场景与角色纹理峰值为 61.39 MiB。[软件与预载记录](variants/combined_readability/software_checks.json)

场景色调、墨伞眼形和缩略图辨识度留待美术预审。整关 A5 和显示器、电视上的手机光枪实测在工作台 Boss 接入后进行。[「忘」字七笔遮罩](forget_strokes/stroke_order.jpg)

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.train_station_readability -Candidate
```

## 工作台「忘」字 Boss 候选

用户已确认火车站可读性合并候选验证通过。`paper.train_station_boss` 沿用四站合并版，在拉镜结束后让七笔墨字上浮。当前一笔有脉动的朱砂描边和落笔光点。误射只擦伤未轮到的笔画并触发灰色反馈，重复误射不会提前打散该笔。第 3 笔在交叉处覆盖第 2 笔。每散一笔留下淡灰残迹，并改变下一轮墨潮的节奏、宽度和落点。第 7 笔净化后结算。[第一笔 JPG](gameplay/workbench_boss/forget_first_stroke.jpg) · [误射 JPG](gameplay/workbench_boss/forget_wrong_stroke.jpg) · [最终残迹 JPG](gameplay/workbench_boss/forget_final_residue.jpg)

Windows Godot 从候车室回归到结算，覆盖工作台落地时的纹理预载、上浮禁射、顺序命中、交叉遮挡、Boss 失败重试，以及 26 条输入回放。验证路线最终为 4 条灯芯、0 发光弹、2 人获救和 1700 分，四张 GPU 抓帧通过 C03。[Boss 软件验证记录](gameplay/workbench_boss/software_checks.json)

下一步将第三关接到夜市和旧影院连续包。Boss 美术与实体光枪仍待第三关整关验收。[七笔遮罩和来源记录](gallery.html#strokes)

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.train_station_boss -Candidate
```

## 三关连续候选

`paper.lantern_city_campaign` 复用夜市、旧影院和火车站候选，两个章节转场各停留 1.5 秒。净化银幕影后，保留银幕画面和三台恢复暖光的放映机，显示第三关提示，再进入候车室。进入下一关时保留灯芯、光弹、获救人数和印记，且拒绝上一关已提交的旧瞄准帧。[夜市转旧影院 JPG](gameplay/campaign/cinema_transition.jpg) · [旧影院转火车站 JPG](gameplay/campaign/train_station_transition.jpg) · [候车室接续 JPG](gameplay/campaign/station_11_waiting_room.jpg)

Windows Godot 在无界面和 GPU 两种运行中均依序通过 15 站，结算为 4 条灯芯、2 发光弹、7 人获救和 8900 分。114 条输入回放复现通关状态和事件轨迹。故意在工作台失败后，重试回到巷口并恢复初始资源。四张代表抓帧通过 C03。[工作台结算 JPG](gameplay/campaign/campaign_clear.jpg) · [三关软件回归](gameplay/campaign/software_checks.json)

下一步接入工作台结局过场。第三关的 A5 和实体光枪验收仍待完成。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_campaign -Candidate
```

## 工作台片尾初版

三关候选第七笔净化后，收起战斗 HUD 和墨痕，在工作台上逐渐点亮纸灯，播放点灯声，随后出现字幕「灯亮着，就还在。」片尾从点灯开始到总结算共 10.8 秒，可按 Enter、Esc 或光枪开始键跳过。当前是工作台短版，正式旁白和灯城回望仍待制作。[点灯前 JPG](gameplay/ending/ending_unlit.jpg) · [点灯后与字幕 JPG](gameplay/ending/ending_quote.jpg) · [总结算 JPG](gameplay/ending/campaign_clear.jpg)

Windows 无界面和 GPU 回归均通过 15 站、114 条输入回放和完整片尾。片尾期间射击和换弹无效。跳过后一帧到达同一结算并保留灯芯、光弹、获救人数和分数。另在播放器中验证了 Enter、Esc、设备开始事件及结算后重试。工作台失败仍可从夜市巷口重试，独立第三关 Boss 也通过了重编后的回归。三张片尾抓帧通过 C03。实体光枪待实测。[片尾软件回归](gameplay/ending/software_checks.json)

试玩沿用三关候选入口。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_campaign -Candidate
```
