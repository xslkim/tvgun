# 关卡引擎当前交付

唯一任务状态源为 [execution_state.json](execution_state.json)。用户已授权全自动开发；普通实现选择和软件问题由 Agent 自行处理。

## 可以直接运行

- 根目录 `play_combat_candidate.cmd` 启动已通过用户桌面验证并迁移到通用战斗描述的《纸灯城》R2。
- 根目录 `review_combat_candidate.cmd`：同一候选的只读可视化审阅、播放、跳转、批注和版本对照。
- `play_level_prototype.cmd` / `review_levels.cmd`：保留的旧 `paper.alley`。
- PowerShell `start_level_review.ps1 -Package gallery.intro`、`orbital.convoy` 或 `orbital.siege` 打开异题材功能包。

详细操作见 [运行说明](../../../docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。启动脚本会构建并导入原生素材，已修复干净目录缺少 Godot import 缓存时旧包无法加载的问题。

## 已验证的软件

`software_acceptance.json` 对应 50 项检查，涵盖编译、版本事务、快照、回放、空间几何、声音 envelope、原版 14886 次状态对照、五包实际机器人、GPU 审阅和播放器、本机 HTTP/UDP 及旧 Demo 回归。

`delivery_acceptance.json` 对应 19 项独立交付检查。五个关卡包从空缓存重建后得到相同 build_id，并通过机器人、GPU 启动、候选入口和隔离采用版启动链。25 个 Python 契约测试覆盖来源映射、非法攻击窗口、版本隔离和修改命中时刻时关键帧的同步。

R2 和轨道防线共用 `encounter` 战斗描述。R2 迁移的展开数据对照通过。轨道防线验证了不同画布、反应堆资源、有限弹药、干扰、拦截与失败分支。Agent 根据审阅画面将发射机出场推迟 550 毫秒，独立候选通过画面和两种结果检查。证据位于 `software_acceptance.json` 的补充索引。

## 保留边界与后续

真实用户批注仍 open；Agent 只提出新版本，未执行正式采用。自然度、紧迫感、声音喜好和手机/电视手感不能用机器人通过替代。R1 复用静态墨鸦素材做仿射动作，尚未新增骨骼/逐帧扑翼动画。工具内置模型调用未实施，当前聊天中的 Agent 按批注产出候选。

LD16 真实多轮用户闭环、LD17 嵌入式网页形态对照以及 LD22/G4 真实硬件尚未全部完成，不把整批任务标成 complete。原生 Godot 路线已可用，软件工作不会因没有硬件而停住；下一轮直接围绕实际试玩结果继续。

原始基准、A1a、D02/D08 和早期失败证据保留；历史索引不覆盖当前状态。没有自动推送或替用户采用候选。
