# 关卡引擎当前交付

唯一任务状态源为 [execution_state.json](execution_state.json)。用户已授权全自动开发；普通实现选择和软件问题由 Agent 自行处理。

## 可以直接运行

- `start_level_player.ps1 -Package paper.station -Candidate` 启动完整首站候选。开场、巷灯教学、六波战斗、摊主救援和两种通关结尾都通过同一关卡包运行。对应的查看器使用 `start_level_review.ps1` 和同样参数。
- 根目录 `play_combat_candidate.cmd` 启动已通过用户桌面验证并迁移到通用战斗描述的《纸灯城》R2。
- 根目录 `review_combat_candidate.cmd`：同一候选的只读可视化审阅、播放、跳转、批注和版本对照。
- `play_level_prototype.cmd` / `review_levels.cmd`：保留的旧 `paper.alley`。
- PowerShell `start_level_review.ps1 -Package gallery.intro`、`orbital.convoy` 或 `orbital.siege` 打开异题材功能包。

详细操作见 [运行说明](../../../docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。启动脚本会构建并导入原生素材，已修复干净目录缺少 Godot import 缓存时旧包无法加载的问题。

## 已验证的软件

`software_acceptance.json` 涵盖编译、版本事务、快照、回放、空间几何、声音 envelope、原版 14886 次状态对照、六包实际机器人、GPU 审阅和播放器、本机 HTTP/UDP 及旧 Demo 回归。

`delivery_acceptance.json` 记录独立目录中的六包重建与 build_id 对照，以及机器人、GPU 启动、候选入口和隔离采用版启动链。首站通过实战回放、11 个关键帧的状态与几何对照、漏救援结尾和无输入失败检查。

R2 和轨道防线共用 `encounter` 战斗描述。R2 迁移的展开数据对照通过。轨道防线验证了不同画布、反应堆资源、有限弹药、干扰、拦截与失败分支。Agent 根据审阅画面将发射机出场推迟 550 毫秒，独立候选通过画面和两种结果检查。证据位于 `software_acceptance.json` 的补充索引。

## 保留边界与后续

真实用户批注仍 open；Agent 只提出新版本，未执行正式采用。自然度、紧迫感、声音喜好和手机/电视手感不能用机器人通过替代。R1 复用静态墨鸦素材做仿射动作，尚未新增骨骼/逐帧扑翼动画。工具内置模型调用未实施，当前聊天中的 Agent 按批注产出候选。

首站的一轮 Agent 自审发现，教学提示玩家试射巷灯时，首只墨鸦尚未入场。新候选只改巷灯和首波提示，保留出场、攻击、弹药和冷却。它从原生查看器第 150 帧保存的批注生成，通过全关通关和 11 个关键帧的回放验证。运行下列命令，可在批注时刻对照两个版本。

```powershell
.\gunforge\start_level_review.ps1 -Proposal .\gunforge\level_design\reviews\agent_proposals\proposal-1794220453914520000.json
```

LD17 的本机网页原型通过 Edge 验证了跳转、只读事件属性、隔离批注和同帧切版。浏览器显示 Godot 导出的帧，批注保存原生画面、命中轮廓和输入记录。第 150 帧切版时命中姿态一致，字幕随版本变化。跳到第 615 帧时，画面和命中姿态都随墨鸦入场更新。

```powershell
.\.venv\Scripts\python.exe .\gunforge\pipeline\level_design\review_web_probe.py .\gunforge\level_design\reviews\agent_proposals\proposal-1794220453914520000.json --verify --later-tick 615
```

省略 `--verify` 时，脚本会输出可在浏览器打开的本机地址，按 Ctrl+C 退出。网页单标签页展示画面和详情，后台需要 Godot 和本机桥接服务，截图编码与传输增加了等待。该次验证的已启动往返中，跳转约 0.39 至 1.53 秒，切版约 1.30 秒。原生查看器使用一个窗口，支持连续音画预览。网页原型以单帧为主，连续音画同步待验证。用户于 2026-11-09 正式选用原生 Godot 查看器。

当前验收先用鼠标，手机光枪实测延后。用户反复试玩靶场后反馈右靶等待偏久。提案 `proposal-1794231862601292700` 把右靶提前到 2.8 秒，提示音提前到 2.6 秒。Godot 桌面输入自动检查覆盖精确出靶时刻、两靶通关、重试和误射保护对象。查看器打开在第 3 秒，可对照此前的 4 秒版本。修订节奏和首站体验待玩家确认，候选采用决定仍待记录。

原始基准、A1a、D02/D08 和早期失败证据保留；历史索引不覆盖当前状态。没有自动推送或替用户采用候选。
