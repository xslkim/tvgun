# TVGun / GunForge / 纸灯城

长期目标是可由 AI Agent 设计和制作光枪游戏的引擎；短期先完成《纸灯城》。美术方向已确认，第一个可玩 Demo 已完成。

## 当前入口

- 完整首站候选「夜市巷口」串起开场、巷灯教学、六波战斗、摊主救援和结算。启动方式见 [运行说明](docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。
- 第二站白模「糖葫芦摊」可独立试玩，先点灯，再净化硬化墨鸦。启动方式见 [运行说明](docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。
- 战斗候选 R2 可用 [play_combat_candidate.cmd](play_combat_candidate.cmd) 试玩，也可用 [review_combat_candidate.cmd](review_combat_candidate.cmd) 审阅和批注。
- [工具运行说明](docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md) / [本轮战斗改动](docs/PAPER_LANTERN_COMBAT_REVISION_01.md) / [B 站与街机战斗复查](docs/ARCADE_LIGHTGUN_COMBAT_FEEDBACK_RESEARCH.md)。
- 启动首站：双击 `play_paper_lantern.cmd`；操作和构建见 [运行说明](gunforge/framework/README.md)。
- Demo：夜市巷口、三轮约 78 秒，点灯、净墨救人、换弹、失败续关和结算。
- 当前开发：[通用关卡设计引擎方案 v0.3](docs/LEVEL_DESIGN_ENGINE_PLAN.md)，以《纸灯城》首个落地、异题材白模验证泛化；已获全自动执行授权。
- [关卡引擎开发任务 v0.2](docs/LEVEL_DESIGN_ENGINE_TASKS.md)：LD00–LD23 的依赖、交付、验收和阶段决策点；当前进度以 [执行状态](gunforge/level_design/reviews/execution_state.json) 为准；[阶段报告](gunforge/level_design/reviews/PROGRESS.md)。
- [街机光枪机制调研](docs/ARCADE_LIGHTGUN_LEVEL_RESEARCH.md)：公开机制、来源和通用能力提炼；[方案 review](docs/REVIEW_LEVEL_DESIGN_ENGINE_PLAN.md) 及 [v0.2 复审](docs/REVIEW_LEVEL_DESIGN_ENGINE_PLAN_v0.2.md) 的处理结果见方案第 13、14 节。
- 本机验证与待验项目：[0B 报告](gunforge/games/g01/reports/0B/report.md) 和 [任务状态](docs/GAME01_0B_TASKS.md)。自动检查与真实手机/显示器/电视验收分开记录。

## 文档职责

- [游戏设定](docs/GAME01_PAPER_LANTERN_CITY.md)：世界观、人物身份、玩法与三关内容提案。
- [美术定稿](gunforge/games/g01/bible/style.md)：已经确认的方向与后续反馈；同目录 JSON/YAML 契约记录具体约束。
- [美术制作方案](docs/ART_PLAN_PAPER_LANTERN_CITY.md) / [任务表](docs/ART_TASKS_PAPER_LANTERN_CITY.md)：制作方法与历史验收依据。
- [GunForge 总体方案](docs/GUNFORGE_PLAN.md)：早期总体规划；其中未落地的模块、版本和供应商信息不能当作当前事实。
- [手机协议与追踪](HANDOVER.md) / [实测流程](WORKFLOW.md)：硬件输入及录制；游戏端最新 HTTP/UDP 行为还需结合 framework/core 代码。
- [开场 CG](gunforge/games/g01/cinematics/opening_original/README.md)：独立媒体交付，尚未接入正式过场播放器。
- [本轮清理记录](docs/PROJECT_CLEANUP_2026-11-08.md)：删除项、保留原因与验证。

## 代码职责

- `android/`、`scripts/guntrack.py`：手机光枪输入及 Python 追踪参考实现。
- `gunforge/framework/`：Godot 公共运行基础。
- `gunforge/games/g01/`：本作关卡、规则、素材与证据。
- `gunforge/pipeline/`：资产构建、制作与自动检查。
- `art2d/`：2D 分件、骨架、动画和导出工具；本作仍依赖它。

`reports/` 是历史验证证据，不能按其中旧的 pending 状态覆盖后来的审核记录。带版本号的美术脚本存在继承关系，不能按文件名批量删除。`docs/FPSGAME_TVGUN_PLAN.md` 是另一项 3D 游戏接入研究，不是《纸灯城》的实现依据。
