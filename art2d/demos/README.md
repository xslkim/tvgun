# Clockwork Bestiary · Demo

从项目目录启动，无需安装 npm 包。

```powershell
node demos/viewer/serve.mjs
```

打开 [本地检视台](http://127.0.0.1:4173/)。命令可接受自定义端口，例如 `node demos/viewer/serve.mjs 4180`。选择角色和动作，使用暂停、前后逐帧、倍速、骨骼、网格和移动补偿。人形可切剑、锤或空手，组合按钮播放移动 → 攻击 → 移动。

| 角色 | 原型和动作数 | 源与证据 |
| --- | --- | --- |
| 黄铜信使 | 人形 14 | [源卡](../assets/courier/concept/CARD.md) · [导出](../assets/courier/export/character.json) · [走路](../assets/courier/preview/walk.gif) · [QA](../assets/courier/qa/REPORT.md) |
| 铜脊猎犬 | 四足 8 | [源卡](../assets/hound/concept/CARD.md) · [导出](../assets/hound/export/character.json) · [扑咬](../assets/hound/preview/attack_heavy.gif) · [QA](../assets/hound/qa/REPORT.md) |
| 灯翼蛾 | 飞行 7 | [源卡](../assets/moth/concept/CARD.md) · [导出](../assets/moth/export/character.json) · [飞行](../assets/moth/preview/fly.gif) · [QA](../assets/moth/qa/REPORT.md) |
| 黑曜甲虫 | 多足 7 | [源卡](../assets/scarab/concept/CARD.md) · [导出](../assets/scarab/export/character.json) · [疾行](../assets/scarab/preview/run.gif) · [QA](../assets/scarab/qa/REPORT.md) |
| 潮汐史莱姆 | 软体 11 | [源卡](../assets/jelly/concept/CARD.md) · [导出](../assets/jelly/export/character.json) · [蠕动](../assets/jelly/preview/walk.gif) · [QA](../assets/jelly/qa/REPORT.md) |
| 余烬布丁 | Skill 验证样例 11 | [源卡](../assets/ember/concept/CARD.md) · [导出](../assets/ember/export/character.json) · [待机](../assets/ember/preview/idle.gif) · [QA](../assets/ember/qa/REPORT.md) |

`assets/<id>/concept` 存生成原图、Prompt、裁切与绑定布局。各角色的 `export` 是可搬移的一包图集、骨架及动作 JSON。每个动作的基础 GIF 和关键帧在 `preview`。播放器可切换骨架，离线调试图可用 `node tools/qa/render.mjs <id> idle --debug` 生成。一键重建步骤见 [Skill](../skills/2d-skeletal-character/SKILL.md)。

[Edge 无头验证日志](viewer/RESULTS.txt) · [播放器截图](viewer/verified.png)
