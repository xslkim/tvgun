# 关卡引擎当前交付

唯一任务状态源为 [execution_state.json](execution_state.json)。用户已授权全自动开发；普通实现选择和软件问题由 Agent 自行处理。

## 可以直接运行

- 根目录 `play_combat_candidate.cmd`：最新《纸灯城》战斗候选 R1。
- 根目录 `review_combat_candidate.cmd`：同一候选的只读可视化审阅、播放、跳转、批注和版本对照。
- `play_level_prototype.cmd` / `review_levels.cmd`：保留的旧 `paper.alley`。
- PowerShell `start_level_review.ps1 -Package gallery.intro` / `orbital.convoy`：异题材功能包。

详细操作见 [运行说明](../../../docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。启动脚本会构建并导入原生素材，已修复干净目录缺少 Godot import 缓存时旧包无法加载的问题。

## 已验证的软件

`software_acceptance.json` 对应 43 项检查，涵盖编译/版本事务/快照/回放/空间几何/声音 envelope、原版 14886 次状态对照、四包实际机器人、GPU 审阅和播放器、本机 HTTP/UDP 及旧 Demo 回归。

`delivery_acceptance.json` 对应 16 项独立交付检查：独立源码目录、新 Python 3.12.10 venv、锁定依赖、重新准备审核素材和导入资源、空缓存重建四包，build_id 与原目录完全一致，再通过四包机器人、实际 GPU 启动、双击候选入口和隔离测试的采用版启动链。另有 22 个 Python 契约测试通过，确认普通入口优先选择已采用源，候选入口不修改采用指针。外部工具 Godot/uv 需按运行说明提供。

R1 是对真实用户 F01–F05 的独立玩法修改：六波 29 只怪物、连续进场/预警/扑击、可拦截墨弹、重甲弱点、可选灯火震退、居民救援、攻防效果与原型声音。20 个战斗机制断言、完整输入回放与 12 个跳转点的状态和实际几何对照通过。实际录制与批注回复见 `combat_r1_acceptance.json`。

## 保留边界与后续

真实用户批注仍 open；Agent 只提出新版本，未执行正式采用。自然度、紧迫感、声音喜好和手机/电视手感不能用机器人通过替代。R1 复用静态墨鸦素材做仿射动作，尚未新增骨骼/逐帧扑翼动画。工具内置模型调用未实施，当前聊天中的 Agent 按批注产出候选。

LD16 真实多轮用户闭环、LD17 嵌入式网页形态对照以及 LD22/G4 真实硬件尚未全部完成，不把整批任务标成 complete。原生 Godot 路线已可用，软件工作不会因没有硬件而停住；下一轮直接围绕实际试玩结果继续。

原始基准、A1a、D02/D08 和早期失败证据保留；历史索引不覆盖当前状态。没有自动推送或替用户采用候选。
