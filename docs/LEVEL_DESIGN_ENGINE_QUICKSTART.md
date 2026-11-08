# 关卡原型与可视化工具

这是已能运行的开发原型。三包使用同一编译、运行会话、事件调度、命中、回放和审阅入口。正式关卡采用、真实用户批注及手机/电视验收分别记录，不由自动测试代替。

## 最新战斗候选 R1

双击根目录 **play_combat_candidate.cmd** 试玩，或 **review_combat_candidate.cmd** 打开只读审阅工具。两者自动准备素材、编译和导入 Godot 资源，不需要先打开编辑器。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.assault -Candidate
.\gunforge\start_level_review.ps1 -Package paper.assault -Candidate
```

候选有六波 29 只敌人、近身扑击、可拦截墨弹、重甲/朱印弱点与居民救援。怪物始终能射击；射击灯获得 1.5 秒震退支援，冷却 6 秒，飞出的墨弹仍需拦截。R 换弹，Enter 开始或重试。声音默认开启。六波完整守住约 82 秒，忽视敌人攻击会提前失败。

本轮采用已经确认的素材和风格，动作使用位移、旋转、缩放与命中回弹；尚未新增墨鸦逐帧或骨骼扑翼动画。合成的纸墨声音是可替换的原型音效。自然度、声音喜好及光枪手感需要实际试玩继续迭代。

旧 `paper.alley` 仍通过下述旧入口打开，候选不会自动采用。实际用户的五条批注保持 open，Agent 只提出解决版本。

普通 `-Package` 启动会优先读取该包已明确采用的源版本；未采用时使用默认样例。`-Candidate` 强制预览当前生成的默认候选，`-Build` 则打开指定构建。采用记录不会被重建脚本覆盖。软件版本更新后会从不可变源重新编译；审阅器只有在构建 ID 与采用记录一致时才显示“已采用构建”。

## 打开《纸灯城》可视化工具

在项目根目录双击 **review_levels.cmd**。它会先准备已有素材、编译《纸灯城》巷口，再打开 Godot 审阅窗口。

也可以在 PowerShell 中运行：

```powershell
cd D:\tvgun
.\gunforge\start_level_review.ps1 -Package paper.alley
```

如果系统执行策略拦截 `.ps1`，用根目录 `.cmd`，或：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\gunforge\start_level_review.ps1 -Package paper.alley
```

- 打开后暂停在开头；点“从头播放”观看关卡。
- “播放 / 暂停”“前进一帧”和下方滑块控制时间。
- 播放时点击画面射击；暂停时点击对象查看只读信息。
- “Alpha 命中轮廓”显示来自实际图像 alpha、裁剪与透明度的轮廓。判定仍使用同一命中模块；轮廓不是包围盒替代。
- 右侧“事件”“关卡树”“依赖图”查看触发、属性和依赖。选择事件后，下方显示设计与 source map；动态条件未发生时不编造绝对发生时间。
- “最近输入判定”查看已消费输入、原始姿态绑定和结果。
- 填写批注后保存，会同时保存该版本的玩家画面、Alpha 图和输入记录。批注位于 `gunforge/level_design/reviews/comments/`，大文件放外部缓存。
- “打开构建”可切换候选；“查看版本差异”与“切换上一版本”用于对照。设计数据只读，修改通过 Agent 补丁生成新候选。
- “保存回放”“打开回放”处理同一 build_id 的输入记录；A/B 标记可循环播放。
- 旧关卡及白模声音默认关闭，战斗候选 R1 默认开启；按钮控制实际 WAV cue。跳转不会补播已经过去的一次性声音，持续声音按记录的偏移恢复。
- “采用当前候选”是可选的用户操作：需要理由、警告确认及当前采用版本校验。预览和保存批注都不会自动采用。

《纸灯城》默认目标时长 78 秒；保留旧版浮点秒时钟的实际完成点为 78.1 秒，审阅范围包含完整结束。涉及续关的录制可继续扩展时间范围。

## 直接玩原型

双击根目录 **play_level_prototype.cmd**，或：

```powershell
.\gunforge\start_level_player.ps1 -Package paper.alley
```

按 Enter 开始/重试/恢复，鼠标点击射击，R 换弹，Esc 暂停，G 切换光枪输入，Q 退出。手机仍使用已有 UDP 9000 / 发现 8001 或 HTTP 8080 协议。播放入口持续接收网络恢复消息，暂停原因彼此独立。

新入口读取旧 Demo 已保存的校准/显示设置。目前首次校准和调整边框仍使用原 Demo 的设置界面；需要新校准时先运行 **play_paper_lantern.cmd**。真实手机与电视的手感尚待实测。

## 验证其他题材

```powershell
.\gunforge\start_level_review.ps1 -Package gallery.intro
.\gunforge\start_level_review.ps1 -Package orbital.convoy
.\gunforge\start_level_player.ps1 -Package gallery.intro
```

靶场有移动目标、保护对象、区域进入、弹药和成功/失败；科幻白模有护盾窗口、双发目标、可拦截投射物、船体与任务分支。它们是功能白模，不是新美术提案。

## 打开 Agent 自审候选

示例索引在 `gunforge/level_design/reviews/agent_example_runs.json`。其中 `examples.gallery.compiled` 和 `examples.protection.compiled` 是实际候选构建路径：

```powershell
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\build_examples.py
$examples = Get-Content -Raw -Encoding UTF8 .\gunforge\level_design\reviews\agent_example_runs.json | ConvertFrom-Json
.\gunforge\start_level_review.ps1 -Build $examples.examples.gallery.compiled
```

靶场候选把目标 B 晚出两秒并向中央移动，同时保持预警提前量与入区行程；科幻候选推迟并放慢第二发投射物。它们来自 Agent 查看实际画面后的自审，保留了原版和约束，**不是用户批注或用户已采用**。

## 环境与检查

需要项目 `.venv/Scripts/python.exe`、Godot 4.6.3 Compatibility 和已有已审核素材。可用 `GODOT_BIN` 指定 Godot，`GUNFORGE_LEVEL_CACHE` 指定缓存；默认缓存为项目同级 `gunforge_cache/level_design/`，不要求固定 D 盘。

开发依赖版本记录于 `gunforge/pipeline/level_design/requirements.lock`。当前环境使用 uv，可重装关卡模块依赖：

```powershell
uv pip install --python .venv/Scripts/python.exe -r .\gunforge\pipeline\level_design\requirements.lock
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\verify_software.py
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\verify_delivery.py
```

检查会新建独立证据目录；入口索引为 `gunforge/level_design/reviews/software_acceptance.json`。它涵盖源哈希、编译内容校验、回放、快照/跳转、三包机器人、真实 GPU 界面及回环 HTTP/UDP。手机追踪、电视延迟、真实试听和用户评价不在其通过结论中。

`verify_delivery.py` 需要 uv；它复制必要源码与已审核素材，在独立目录创建新 Python 3.12.10 环境、按锁文件装依赖、使用空缓存重建四个包，核对 build_id，再执行机器人与实际 GPU 启动。结果见 `delivery_acceptance.json`。Godot 4.6.3 必须另行提供，可设置 `GODOT_BIN`。

如果报“版本/资源改变”，先重新运行相应启动脚本构建，或从不可变源重新编译；不要手改缓存中的 `level.json`。关闭占用同一端口的旧游戏再启动新的播放入口。可视化审阅本身不占用手机网络端口。
