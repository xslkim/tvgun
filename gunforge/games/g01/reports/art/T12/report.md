# T12 · 旧影院

用户确认第二关五站白模和银幕影独立 Godot 原型审核通过。采用 1776×936 内容坐标，布局供正式构图与关卡脚本使用。

- 售票处，售票窗灯箱、检票员救援位、磁带墨和墨伞路线。[白模 JPG](whiteboxes/ticket_office.jpg)
- 海报长廊，沿墙壁灯、海报之间的敌人路线、两侧展架与门边遮挡。[白模 JPG](whiteboxes/poster_hall.jpg)
- 观众席，前排座椅夹出中央通道，银幕与放映窗建立纵深，路人 B 在右侧座位前。[白模 JPG](whiteboxes/auditorium.jpg)
- 放映室，工作灯、设备两侧的敌人路线和放映员救援位。[白模 JPG](whiteboxes/projection_booth.jpg)
- 银幕前，三台放映机、三个胶片盘的墨渍和银幕影核。[白模 JPG](whiteboxes/screen_stage.jpg)

八个敌人活动区、三个居民区、四处灯位和四个 Boss 命中区均避开了 60 像素边缘带、HUD、掩体和同站其他交互区。三处胶片盘墨渍的椭圆白模有效半径为 61.36 像素，影核为 63.46 像素。正式纹理落位后需重新测量实际透明度遮罩。[布局数据](layouts.json) · [几何结果](whitebox_checks.json)

## 银幕影原型

三台放映机机身不可射。打中胶片盘墨渍时，仅该盘对应的光束恢复暖色。三盘可以按任意顺序净化，三束光都恢复后才开放影核。Godot 使用共用像素判定跑通全部六种顺序，同时检查了击中机身、擦过目标矩形透明角、重复射击已净化胶片盘和提前射击影核。

[三束墨光](whiteboxes/shadow_0.jpg) · [左束恢复暖光](whiteboxes/shadow_1.jpg) · [影核开放](whiteboxes/shadow_3.jpg)

鼠标左键净化，R 重置，Esc 关闭。从仓库根目录启动，`GODOT_BIN` 指向本机 Godot 4.6.3。自动回归可在 Godot 参数中加 `--headless`，并在命令末尾加 `--probe`。

```powershell
$layout = (Resolve-Path 'gunforge/games/g01/reports/art/T12/layouts.json').Path
& $env:GODOT_BIN --path gunforge/framework --script res://tools/screen_shadow_review.gd -- $layout
```

## 构图与灯光初稿

五站各出两轮构图，第二轮改用白模和文字描述，移除了首轮从夜市参考带入的室外街景和植物。当前选用第二轮的五张室内原画，原稿、首轮对照及提示词均已归档。[JPG 画廊](gallery.html) · [生成记录](generation.json)

四个普通站点直接从原稿导出关灯图，点灯只调整灯具及其周围。程序逐像素验证光区以外与原稿相同。银幕前新增放映机、胶片盘和墨影三个独立素材，三束光使用独立遮罩。第一盘净化的像素变化局限在左侧光束和胶片盘，三盘净化后才展示朱砂影核。[灯光和命中遮罩数据](screen_shadow/art.json)

12 张离线预览 JPG 均通过 C03 亮度检查。原稿 C04 初筛有一站通过，四站在分层版本中完成了色阶修订。原画和分层版均可在画廊里对照。[构图检查](art_checks.json)

## 银幕影美术接入

Godot 审阅器已加载银幕原画、独立墨影、三台放映机与胶片盘、朱砂影核、三束光的透明贴图。机身使用实际美术 alpha，胶片墨渍和影核使用各自的二值遮罩。白模与实际素材两种输入均跑通六种净化顺序。三张 1776×936 的 Compatibility 抓图通过 C03，第一盘净化时只有对应胶片盘和左束光的像素改变，影核在第三盘后才出现。[实机检查](screen_shadow/gpu_checks.json)

[三束墨光](previews/godot_screen_0.jpg) · [左束恢复暖光](previews/godot_screen_1.jpg) · [影核开放](previews/godot_screen_3.jpg)

沿用上面的 Godot 启动命令，把布局路径换成 `gunforge/games/g01/reports/art/T12/screen_shadow/art.json` 即可打开美术版。

## 纸居民与墨怪

放映员、检票员和路人 B 各拆为 10 个纸偶部件。24 张采样姿势各有一个主要连通轮廓，216 处采样关节均保持交叠。角色配置保留救援与保护规则。

磁带墨的录像带外壳和散落磁带不计入主伤害区。墨伞撑伞时只有伞面无效区，收伞后可打墨身，朱砂是附加弱点。两个可射态的有效半径在当前候选显示尺寸下分别为 49.09 和 59.58 像素，均通过距离场往返检查。Godot 可玩候选已覆盖撑伞、连续收伞和收伞完成三种状态。[角色与墨怪 JPG](actors/index.html) · [几何结果](actors/checks.json) · [六张内置 imagegen 源图与提示词](actor_generation.json)

## 独立分层与灯具

五站共拆成 40 层，包含地面、墙面、银幕、帘幕、设备、灯具与前景掩体。四站使用连续色阶调整，五站分层版 C04 覆盖率为 91.6% 至 99.7%。原画和原画 JPG 保留。分层版静止画面与其渲染源逐像素一致。极限位移下细栏杆仍能看到轻微补边痕迹。[分层标注](composition_layers.json) · [色板和灯具检查](parallax/art_checks.json)

海报长廊和观众席的壁灯按原位置放大了可见灯体，命中遮罩跟随可见轮廓。四灯在 1776×936 内容坐标下的有效半径为 49.47 至 97.36 像素，完整视差运动范围避开 HUD 和边缘带。灯体、命中遮罩、发光层和漏光层共用位移。银幕前的放映机继续使用独立的胶片盘机制。

Godot 4.6.3 Compatibility 抓取 49 张静止、点灯和视差极限图，均通过 C03 且没有露底。45 个采样位置通过实际掩体像素的挡弹检查，包含四个灯位的 36 次中心命中及透明角避让。[Godot 分层 JPG](gallery.html) · [引擎结果](parallax/engine_checks.json)

## 五站可玩候选

五站已接入正常播放器，按售票处、海报长廊、观众席、放映室、银幕前推进。前四站的灯每次亮 7.5 秒，磁带墨巡游进入暖光区时软化，离开暖光区或灯灭时恢复硬化。墨伞撑开时挡弹，收伞后可打墨身。三名居民的纸身均受保护，胸口墨团单独判定。银幕前未净化的放映机会扫光并刷出磁带墨，清掉对应胶片盘可阻止本次刷怪或清除该束光生成的敌人，三盘净化后开放影核。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.cinema -Candidate
```

Enter 开始，左键射击，R 换弹，G 切换手机光枪模式。自动通关用 27 发光弹救出三名居民并清除影核，覆盖灯具墨遮、渐变、闪烁与重新点亮，以及撑伞保护、纸身保护、扫光刷怪和提前净化跳过扫光。20 张 1776×936 实际关卡抓图通过 C03。正常入口和本机 HTTP/UDP 回环通过，糖葫芦摊原关卡回归通过。[候选验证](gameplay/verification.json)

[点灯后在光外](gameplay/ticket_lit_outside.jpg) · [入光后软化](gameplay/ticket_lit.jpg) · [墨光扫过](gameplay/screen_sweep.jpg) · [磁带墨出现](gameplay/screen_spawn.jpg) · [影核开放](gameplay/screen_core.jpg)

五站已接入轻幅视差。灯体、灯光和命中遮罩使用同一位移，前景按移动后的可见轮廓挡弹。灯光叠加在移动的分层上，切站前保留灯体。三名居民使用现有纸偶运行时，墨团跟随胸口移动，净化后进入获救和道谢动画。带居民的站点在净化完成后停留 1.3 秒再切站。[挣扎](gameplay/resident_struggle.jpg) · [获救](gameplay/resident_rescued.jpg) · [道谢](gameplay/resident_thanks.jpg)

灯光判定取磁带墨中心在漏光遮罩中的值，再乘以当前灯光亮度，以 0.3 为软化阈值。漏光遮罩按每盏灯的峰值归一化，与可见光同位移。7.5 秒亮灯周期的开头和结尾各有 0.3 秒渐变，画面和命中判定共用同一亮度。前四站自动回归的连续软化窗口分别为 95、84、117、86 帧（60 Hz）。排队射击按已显示帧判定，同一帧到期并重新点灯时，新一轮渐亮正常启动。[渐亮 JPG](gameplay/ticket_fade_in.jpg) · [渐暗 JPG](gameplay/ticket_fade_out.jpg)

四盏灯复用 T08 的三款灯墨，贴图裁在各自灯罩内。射灯后墨沿灯罩下缘退去，亮灯末段两次局部闪烁，墨随渐暗向上回爬。灯墨只参与渲染，灯具仍沿用原有命中区。GPU 取样确认墨在渐亮时集中于灯罩下部，满亮时完全退去。[墨遮灯 JPG](gameplay/ticket_off.jpg) · [退墨 JPG](gameplay/ticket_fade_in.jpg) · [将熄闪烁 JPG](gameplay/ticket_lamp_flicker.jpg) · [墨回爬 JPG](gameplay/ticket_ink_returned.jpg)

墨伞入场后撑伞 2.4 秒，随后用 0.6 秒连续收伞。伞面命中区随画面一同收拢，逐渐显露的墨身在收伞完成前保持不可伤害。四站回归均确认第 36 帧才开放墨身和朱砂，绑定旧伞面快照的射击不会伤害新墨身。[撑伞](gameplay/umbrella_open.jpg) · [收伞中](gameplay/umbrella_folding.jpg) · [收伞完成](gameplay/umbrella_closed.jpg)

## 人工验收

- 实体光枪在显示器和电视各测一次售票处。用上面的命令启动，按 G 切换手机光枪模式。射左上灯箱，等灯墨退去、末段闪烁和回爬后再射一次。最后在磁带墨显示「软化 · 射击」时命中，核对瞄准与反馈。
- A5 用任一设备通关一次。确认墨伞收完后才可伤害、只射胸口墨团可救人、银幕前每盘净化只改变对应光束，三盘清完才开放影核。

2026-11-11 用户确认旧影院 A5 与显示器、电视的实体光枪复验通过。旧影院接在 T11 墨舞龙之后，十站同会话通关通过软件回归。[两关候选与 JPG](gameplay/lantern_city/report.md)
