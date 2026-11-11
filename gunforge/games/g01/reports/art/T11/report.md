# T11 · 墨舞龙

2026-11-10，T10 画廊验收通过后制作。用户明确确认首审通过，覆盖三态与分节绑定。

从左到右是尚未开放、当前可射、已净化。三态共用同一张纸身和两个铜扣轴心。墨团、暖光和可射遮罩独立，净化时墨团渐隐，露出原来被盖住的纸鳞。

[三态同框 JPG](sample/three_states.jpg) · [五秒净化短片](sample/purification.mp4)

- [起始 JPG](sample/start.jpg)，尾侧先开放。
- [尾侧净化 JPG](sample/tail_purified.jpg)，中段开放。
- [中段净化 JPG](sample/body_purified.jpg)，头侧开放。
- [三节净化 JPG](sample/all_purified.jpg)，纸龙恢复暖色。

短片使用广场入选构图。75 帧均按铜扣位置串接，任一时刻最多开放一节，开放顺序为尾侧、中段、头侧。三段均使用同一龙节验证绑定。出图一次，使用内置 imagegen 从 T09 已审核净化龙节提取透明纸身，墨团从 T09 可射态提取。源图、提示词和哈希随样片保存。[绑定与状态数据](sample/sample.json) · [生成记录](sample/source.json)

## 整龙候选

整龙已组装为龙头上颚、可动下颚、八节龙身、龙尾和独立朱砂核。八节沿用已审核的纸鳞和铜扣，每节单独调整尺寸、色调和墨团轮廓，保存锁定态、可射态和净化态所需图层。龙嘴仅在八节全部净化后开放。

[广场游动 JPG](full/swim.jpg) · [命中区 JPG](full/hit_zone.jpg) · [龙嘴开放 JPG](full/mouth.jpg) · [净化完成 JPG](full/purified.jpg) · [游动与命中区短片](full/swim_hit_zones.mp4)

- 90 个游动姿势中，最小可见命中区有效半径为 42.67 像素。龙嘴测量扣除了上颚和下颚的遮挡。各目标的运动范围避开 60 像素边缘带和 HUD 保留区。
- 可射墨团与自身背板的亮度差为 36.1% 至 37.9%，朱砂核与口腔背板为 29.7%。此处计算使用实际承托目标的纸层。
- Godot 用共用的逐像素判定跑通从尾到头的八节净化。锁定节和已净化节无法命中，最后才开放龙嘴。120 帧关节偏差小于 0.001 像素。
- 头部组件和尾部各用一次内置 imagegen，均以 T09 整龙和三节样片纸身为参考。生成提示词和源图已归档。[生成记录](full/generation.json) · [整龙配置](boss.json) · [离线测量](full/checks.json)

用户确认本轮审核通过，T11 第二次审核完成，覆盖整龙游动及命中反馈。

## 第一关广场可玩候选

正常播放器入口从广场的两个墨怪开始。清场后墨舞龙入场，依次开放尾侧到头侧八节。八节全净化后，龙嘴里的朱砂核开放，上下颚仍按可见轮廓挡弹。摆头预警后会喷墨，若未及时击破朱砂核会扣一枚灯芯。净化朱砂核后进入过关结算。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.plaza -Candidate
```

无界面与 RTX 3090 自动通关均为 13 发，覆盖一次喷墨命中和下一次喷墨被打断。回归还覆盖旧帧射击与下一节隔离、龙颚挡弹及检查点重播。正常启动、HTTP/UDP 回环、糖葫芦摊与旧影院软件回归通过。7 张 1776×936 游戏抓图通过 C03。[验证记录](gameplay/verification.json)

[广场前置波次](gameplay/plaza_wave.jpg) · [墨舞龙入场](gameplay/dragon_entry.jpg) · [龙嘴朱砂核](gameplay/dragon_mouth.jpg) · [喷墨](gameplay/dragon_breath.jpg) · [净化完成](gameplay/dragon_cleansed.jpg)

实体光枪可用此入口单独复验。按 G 切换手机光枪模式，清除广场的两个墨怪，从龙尾最亮的墨团一路净化到龙头，再在摆头时击中龙嘴红核。第一关站点串接待做，下一步先把录像厅门口做成可玩站点。

## Godot 审阅器

从仓库根目录启动，鼠标左键净化，R 重置，Esc 关闭。可在参数末尾加 `--probe` 并用 `--headless` 跑回归。审阅器也可载入[原型配置](boss_draft.json)。

```powershell
$boss = (Resolve-Path 'gunforge/games/g01/reports/art/T11/boss.json').Path
& $env:GODOT_BIN --path gunforge/framework --script res://tools/ink_dragon_review.gd -- $boss
```
