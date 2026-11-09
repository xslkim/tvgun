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

新版原生查看器的界面和视角已由用户验证。当前交付沿用 Godot，LD17 的网页对照原型未制作。剩余验收包括 LD16 真实多轮用户批注、候选采用，以及 LD22/G4 的实体光枪和显示设备测试。

原始基准、A1a、D02/D08 和早期失败证据保留；历史索引不覆盖当前状态。没有自动推送或替用户采用候选。
