# 《纸灯城》PC 鼠标试玩调整

构建 `e5eb6e545f829848831215e2eff261add50f1d508e91c18688482830d941288c`。

- 三关弹匣由 12 发增至 18 发。最后一发照常结算，打空后自动回光，0.35 秒补满。按 R 仍可提前换弹。
- 巷口的灯和覆墨画在墨鸦后方。命中范围重叠时优先命中前方的墨鸦，墨鸦移开后可用同一位置点灯。
- 巷口扑击鸦从亮红圈到起扑由 0.72 秒增至 1.65 秒，起扑到造成伤害由 0.28 秒增至 0.52 秒。糖葫芦摊与火车站的墨鸦也延长了预警，分别为 2.4 秒和 2 秒。糖葫芦摊在伤害发生前打掉墨鸦可以取消伤害。

Godot 桌面输入回归向正式播放器发送鼠标点击，验证 18 发、自动换弹与 R 换弹，使用同一个重叠像素先打墨鸦再点灯，并验证在预警 1.5 秒后和起扑后打断。图形版与无界面版的三关均通过 15 站、109 条输入回放、失败重试、58 秒自然片尾和四段跳过。26 项关卡管线测试通过。[回归记录](checks.json) · [隔离包清单](candidate_manifest.json)

## 试玩

在仓库根目录打开 Windows PowerShell。按 Enter 开始，左键射击，R 提前换弹。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_cast -Candidate -SkipOpening
```

本机已经打包，可直接启动相同构建。

```powershell
$stage = 'D:\gunforge_cache\t16_cast_mouse_balance_verified'
$godot = 'D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe'
& $godot --path "$stage/gunforge/framework" --script res://tools/level_player.gd -- "--build=$stage/level.json" "--assets=$stage" --isolated-settings
```

复测先在巷口把光弹打空一次，确认补满后左键可继续射击。墨鸦飞到灯前时瞄准墨身。第一只墨鸦亮红圈时稍等再射，观察是否来得及打断。能继续打到后面时，记下是否又因换弹来不及而失去灯芯。手机光枪和电视验收安排在发布阶段。
