# 2D 角色美术生产

面向游戏开发 Agent。输入角色设定、游戏视角和所需动作，输出可预览、可校验的拆件、骨架、图集和动画。

1. 按 [生产 Skill](skills/2d-skeletal-character/SKILL.md) 制作角色。样例的画风、比例与动作全集供参考，制作范围由游戏需求决定。
2. 从已有原图和配置构建。需要 Node 24、uv 和 Python 3.12，Pillow 由脚本加载。
3. 比对同尺度设定图与绑定图，检查近远遮挡、关键配件和动作接地。结合自动 QA 验收。 [黄铜信使示例](assets/courier/qa/visual_recheck.md)

```powershell
./skills/2d-skeletal-character/scripts/build.ps1 courier
node demos/viewer/serve.mjs
```

打开 [本地播放器](http://127.0.0.1:4173/)。用 `-Clips idle,walk,attack_light` 指定试制或交付动作；每次构建重写该角色的动作索引。Git 克隆后用 `git lfs pull` 获取原图和 GIF。

纸灯城人物可从 [卖糖葫芦居民](http://127.0.0.1:4173/demos/viewer/?character=paper_lantern_vendor) 和 [录像厅老板](http://127.0.0.1:4173/demos/viewer/?character=paper_lantern_video) 直接进入。角色 ID 为 `paper_lantern_vendor`、`paper_lantern_video`，通过相同的 `build.ps1 <id>` 从各自 `concept/` 构建八个 NPC 动作。原 T05 分件已随各自 `raw.png` 归档；仅重新导入旧源图时才需要缓存和 `tools/import_paper_residents.py`。

## 交给游戏

交付整个 `assets/<id>/export/`，从 `character.json` 读取图集、骨架和动作。Canvas 播放器是实测接入示例。游戏引擎适配、碰撞、事件效果及跨动作足锁由游戏侧负责。 [数据合同](docs/spec/ANIM_SPEC.md#游戏接入) · [授权](docs/RIGHTS.md)

[美术规范](docs/spec/ART_SPEC.md) · [绑定规范](docs/spec/RIG_SPEC.md) · [示例资源](demos/README.md) · [验收记录](docs/FINAL_REPORT.md)
