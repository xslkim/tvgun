# 第一关夜市可玩候选

巷口、糖葫芦摊、录像厅门口、天桥、广场按顺序运行于同一个游戏会话。各站从现有独立候选的源版本组装，糖葫芦摊沿用其独立候选底图。灯芯、弹药、印记和救援数随玩家切站，弹匣容量统一为 12 发。切站间隔为 0.6 秒，旧场景和目标随下一站入场清除。击破墨舞龙的朱砂核后统一结算。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.night_market -Candidate
```

Godot 无界面与 RTX 3090 回归均在同一会话中通关，用 64 发、换弹 5 次、救出 2 人，结算时余 4 枚灯芯。测试核对了四次切站的资源状态，验证了旧帧射击隔离和糖葫芦摊的独立波次计数。正式入口、开场播放与跳过、HTTP/UDP 回环均通过，5 个已有候选回归通过。7 张 1776×936 JPG 通过 C03。[构建与验证记录](verification.json)

[巷口](station_1_alley.jpg) · [糖葫芦摊](station_2_stall.jpg) · [录像厅门口](station_3_video_shop.jpg) · [天桥](station_4_footbridge.jpg) · [墨舞龙](station_5_dragon.jpg) · [通关](night_market_clear.jpg)

实体光枪可按 G 切换手机模式。显示器和电视各跑一次时，重点核对切站后准星对位、弹药与灯芯，以及广场尾节和龙嘴的命中。第一关实体复验待记录。[夜市和旧影院两关候选](../../../T12/gameplay/lantern_city/report.md)
