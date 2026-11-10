# T11 · 墨舞龙三节样片

2026-11-10，T10 画廊验收通过后制作。当前为美术任务规定的首个审核点，审核三态与分节绑定。

从左到右是尚未开放、当前可射、已净化。三态共用同一张纸身和两个铜扣轴心。墨团、暖光和可射遮罩独立，净化时墨团渐隐，露出原来被盖住的纸鳞。

[三态同框 JPG](sample/three_states.jpg) · [五秒净化短片](sample/purification.mp4)

- [起始 JPG](sample/start.jpg)，尾侧先开放。
- [尾侧净化 JPG](sample/tail_purified.jpg)，中段开放。
- [中段净化 JPG](sample/body_purified.jpg)，头侧开放。
- [三节净化 JPG](sample/all_purified.jpg)，纸龙恢复暖色。

短片使用广场入选构图。75 帧均按铜扣位置串接，任一时刻最多开放一节，开放顺序为尾侧、中段、头侧。三段均使用同一龙节验证绑定。出图一次，使用内置 imagegen 从 T09 已审核净化龙节提取透明纸身，墨团从 T09 可射态提取。源图、提示词和哈希随样片保存。[绑定与状态数据](sample/sample.json) · [生成记录](sample/source.json)

首审通过后制作整条龙的头部上颚与下颚、尾部、八节身段和独立龙嘴朱砂核。

## Godot 八节原型

已用样片纸身跑通八节铜扣串接。每次只开放一节，按尾到头依次净化，全部净化后才开放临时龙嘴核。无窗口回归用共用的逐像素命中判定验证了八节顺序、锁定态不可射、重复命中无效，以及嘴核最后开放。120 帧的最大关节偏差小于 0.001 像素。[原型配置](boss_draft.json)

从仓库根目录启动，鼠标左键净化，R 重置，Esc 关闭。可在参数末尾加 `--probe` 并用 `--headless` 跑同一原型的回归。

```powershell
$draft = (Resolve-Path 'gunforge/games/g01/reports/art/T11/boss_draft.json').Path
& $env:GODOT_BIN --path gunforge/framework --script res://tools/ink_dragon_review.gd -- $draft
```

原型使用八份相同的样片身段与临时嘴核。正式头尾与八节变体、光枪所需的最小命中区、正式关卡接入均在首审后的制作范围。
