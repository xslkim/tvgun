# 纸灯城首站可玩版

2026-11-07。任务来自 GAME01_0B_TASKS.md，当前提供 Godot 鼠标可玩首站和光枪协议联调版本。双击仓库根目录 play_paper_lantern.cmd 启动。

## 已实现

- 三轮波次约 78 秒，包含点灯软化、墨鸦净化、附墨居民救援、光与灯芯拾取、生命、6 发弹匣、两种换弹、死亡续关、结算和引擎转场。NPC 纸身是精确保护区，胸口附墨独立判定，获救后所有人物命中区失效。
- 导入 art2d 的骨架、动作和附件切换，使用相同绘制顺序做 alpha 命中，前景纸层实际像素挡枪。实现唯一主区吸附，保护区和前景之间禁止吸附。
- 白边和暗区独立于内容限亮。显示器/电视配置分别保存，支持全屏、边框调整、5 点校准与 4 个独立检查点。失败或取消校准会恢复原修正。
- 公共框架位于 framework/core/，首站波次数据和点灯、墨、救人的规则位于本游戏 levels/ 和 scripts/。本机 TCP 调试接口提供固定时钟、输入注入、状态和截图，机器人与正常输入使用相同事件入口。
- 手机 UDP 兼容旧格式，并新增带序号坐标和射击、LOST、独立 HELLO 会话及 FRAME 回传。手机收到 FRAME 后按规范坐标暗区中线取样，Python 参考同步。HTTP 路径继续使用既有格式。

## 实现选择

本机使用已验证的 Godot 4.6.3 与 Compatibility 渲染。首站非交互场景层和灯光贴图在构建时取原尺寸的 65%，按原坐标绘制，灯罩和人物保持原分辨率。站点贴图按 RGBA8 加 mip 链的保守估算约 39.34 MB。该运行分辨率需要随本次试玩复核。

输入处理参考 Godot 4.6 PacketPeerUDP，骨架变换参考 Transform2D。[UDP 文档](https://docs.godotengine.org/en/4.6/classes/class_packetpeerudp.html) · [变换文档](https://docs.godotengine.org/en/4.6/classes/class_transform2d.html)

## 验证记录

- core_tests.json 记录 39 个核心检查，覆盖多窗口坐标、保护区/遮挡/吸附、旧包时效、序号和会话、失锁暂停、校准、换弹和续关。
- engine_bot.json 记录实际 Godot 运行中的三轮通关与死亡续关，截图包括点灯、获救与结算。机器人通过本机调试 API 输入，不直接修改血量和得分。
- gpu_screen_checks.json 记录 RTX 3090 / Compatibility 的本机采样，包含启动低帧率，采样帧时间 P95 约 16.67ms，纹理计数最高约 81.87 MB。该计数含运行时分配。截图内容最大 Y′ 约 0.749，白边为 255/255/255，暗区为 0/0/0。
- udp_tests.json 记录真实本机 UDP socket 的发现、FRAME、射击去重、迟到包、失锁、回屏倒数与离屏换弹。
- frame_geometry_python.json 与 Java FrameGeometryTest 覆盖 24/48、40/24、12/72 三组白边/暗区，均测到四条边。Java TrackerTest、UdpEventsTest 和 GunProtocolTest 已运行。
- tracker_legacy_regression.json 记录旧协议历史录制的 1,746 帧回放，与修改前 Java 输出逐字节一致。既存 Python CSV 对照的等级一致率 67.87%，修改前后均低于原测试门槛，该跨语言差异保留待定位。
- APK 已通过本地构建和签名验证，实际手机安装、版本核对与录制等待硬件接入。

## 下一检查点

请先鼠标试玩一遍首站。Enter 开始，左键射击，右键或 R 换弹，5 续关，Esc 暂停，F11 全屏。反馈可包括灯和墨是否分得清、误伤是否说得通、节奏和声音是否合适。

真实光枪测试按 WORKFLOW.md 安装本次源码构建的 APK，核对 HUD 版本号并录短片确认。手机设置为 UDP、端口 9000，游戏按 G 切换输入，用 C 校准。显示器与电视各跑开局、离屏换弹、回屏重获与边框调整，并记录锁定等级、最长失锁、重获、误锁和换弹成功率。当前检测不到 adb 设备，真实硬件数据待录。

真实 0B 五项的状态均为待审核，T09–T16 批量继续等待真实验收结果。
