# TVGun 手机光枪 — 交接文档（2026-10-03，v5.1 实测通过：在线时间标定 + 输出平滑 + 局域网自动发现）

> 本文档供更换电脑后快速恢复开发。包含：项目现状、架构、协议、数据资产、已知问题、新机器搭建步骤、命令速查。
> **实测/构建流程与防版本错配机制另见 [WORKFLOW.md](WORKFLOW.md)（必读）。**

## 1. 项目是什么

把手机固定在玩具光枪上玩"打鸭子"：PC 显示器全屏显示游戏（相当于电视），手机后置摄像头看着显示器，App 实时解算"枪口指向屏幕的哪个像素"，点手机屏幕 = 扳机。定位方案 = **Sinden 式亮边框 + 陀螺传播单应 + 逐边视觉校正**（纯软件，不改电视硬件）。

本仓库另含第一期/第二期的"隐形水印定位"仿真系统（sim/、SPEC.md、SPEC2.md、REPORT.md），与光枪真机系统相互独立，不在本文档范围。

## 2. 系统组成（v2，2026-09-25 重写核心算法）

```
PC 端（Windows）
  scripts/run_tv.py              电视端：cv2 全屏游戏（黑底+24px白边框+弹跳鸭子+分数）
                                 + 内置 HTTP 服务器（0.0.0.0:8000）+ UDP aim 监听（同端口）
  scripts/guntrack.py            【核心】追踪器 Python 参考实现（见下）
  scripts/run_track_replay.py    录制回放评测：可用率/抖动/精度/再锁定/伪失锁 MC（--v2 基线对照）
  scripts/diag_smooth.py         流畅度/手感诊断：真值锚点法感知延迟/静止与运动抖动/零偏注入
  scripts/run_record_replay.py   旧算法（extrema/linefit 四角）基线回放（留档对照）
  scripts/calib_prop.py          陀螺→相机轴向映射回归（M 矩阵标定工具）
  scripts/diag_unlock.py         失锁帧根因诊断（连通域/边拟合可视化）
  test_res/                      验证素材（见 §5）

手机端（小米 9，Android 10）
  android/                 光枪 App（纯 Java，无 gradle 手工构建链）
    build.sh               构建+安装一条龙（JDK8 javac + aapt2 + d8(JRE17) + apksigner）
    src/com/tvgun/gun/
      Tracker.java         【核心】guntrack.py 的逐语句 Java 移植（见下）
      MainActivity.java    相机双后端、Tracker 驱动、120Hz UDP aim（snapshot_ahead 预测）、
                           录制、镜头切换、服务器/预测量设置、
                           屏幕四角虚拟按键（左下=投币/开始，右下=换弹/退出；退出双击确认）
      ControlButtons.java  虚拟按键协议层（POST /coin /start /reload /exit，纯 Java 可桌面单测）
      Camera2Backend.java  camera2 枚举(含MIUI隐藏vendor id)/会话/帧回调（60fps 优先）
      OverlayView.java     准星/HUD/等级显示（FULL/PARTIAL/EDGE/GYRO/DEAD）/REC指示
      Recorder.java        视频+IMU+检测同步录制（音量下键触发）
    test/                  TrackerTest（合成场景 16 项断言）+ ReplayTest（Java/Python 回放等价）
                           + ControlButtonsTest（虚拟按键 HTTP 假服务器断言）

备用客户端
  webgun/                  浏览器版光枪（已被 APK 取代，仅留档）
```

### 追踪器 v2 算法（Tracker.java = guntrack.py，逐语句对应）

状态 = 单应 H（640x360 图像坐标 → 1920x1080 规范坐标），**准星 = H·图像中心**。

- **传播**：每个陀螺 tick 立即传播 H ← H·(K·(I+[M·(ω−bias)·dt]×)·K⁻¹)⁻¹（纯旋转精确，
  与观看距离无关）。M = [[0,1,0],[1,0,0],[0,0,-1]]（两段录制、两种镜头回归一致，
  scripts/calib_prop.py 可复算）；rot=180 时 ωx/ωy 先取反。
- **逐边测量**：每条屏幕边的预测位置（Hᵀ·边线）投影入图、按图内可见段裁剪，
  在 ±12px 自适应带内逐 bin 求亮条纹**外侧过零边**（亚像素中点插值，无包络截断偏差），
  TLS+2σ 剔除拟合直线；支撑率/残差/创新量/夹角/内侧暗度五重门控（文字屏/灯具拒绝）。
  带宽随该边"未可信测到"的时长增长（12px/s 到 24px），打破"窄带锁定错误线"的饿死螺旋。
- **校正**：4 边（FULL）= 邻边交点 → DLT → 按比例收敛（绝对复位透视漂移）；
  1-3 边（PARTIAL/EDGE）= 图像空间相似校正（平移=截断特征值 2x2 LS、旋转=夹角加权、
  尺度=平行边对间距比）。**v3 起增益自适应**（innov<1px → 0.35·g_base 平滑噪声；
  innov>12px → 满增益快速再锁定）。
- **采集**：失锁（或 GYRO>0.3s / 边数长期<3）时遍历至多 5 个候选亮域，
  逐个四边拟合 + 几何校验 + 中空校验（内缩 18% 四边形亮像素 ≤30%），全部通过才重建 H。
- **零偏**：双路在线学习——静止时（|校正|<2px 且 |ω|<0.06rad/s）EMA 快学；
  **v3 起游玩中连续学习**（相邻 FULL 对残余 ε=t·g_prev/(f·dt)，β=0.03，钳位 0.08）。
- **等级**：FULL(4边)/PARTIAL(2-3)/EDGE(1)/GYRO(0边≤3s)/DEAD（超 3s）。
  准星以陀螺速率（~400Hz）更新；**v3 起 aim 120Hz UDP 独立线程上报
  `snapshotAhead(now+predictMs)` 预测准星**（默认提前 90ms，补偿端到端显示延迟）。

## 3. 通信协议（两端必须一致）

坐标系：**规范坐标 1920×1080**，游戏白边框四角 = (0,0)/(1920,0)/(1920,1080)/(0,1080)。
检测角点取边框**外缘**，有 ~13px 系统偏差 + 广角镜头 ~7px 附加偏差（待两点校准统一处理）。

HTTP/UDP（TV 端监听 `0.0.0.0:8000` TCP+UDP，手机经 WiFi 局域网访问 PC IP）：

| 端点 | 说明 |
|---|---|
| `POST /shot` | `{"x":f,"y":f}` → `{"hit":bool,"score":int}`，点屏幕开火 |
| **UDP** 文本 `"x,y"` | **120Hz** 准星上报（主路径，v3 起；无连接、最新覆盖，丢包无碍） |
| **UDP :port+1** | **局域网自动发现**：手机广播 `TVGUN_DISCOVER`，PC 回 `TVGUN_HERE <port>`，手机取应答源地址为服务器（零配置） |
| `POST /coin` | `{}` → `{"ok":true}`，屏幕虚拟按键【投币】（手机→PC，街机桥接器 tvgun-bridge 提供） |
| `POST /start` | `{}` → `{"ok":true}`，屏幕虚拟按键【开始】（同上） |
| `POST /reload` | `{}` → `{"ok":true}`，屏幕虚拟按键【换弹】（同上） |
| `POST /exit` | `{}` → `{"ok":true}`，屏幕虚拟按键【退出】（同上；手机端双击确认防误触） |
| `POST /aim` | `{"x":f,"y":f}` → `{"ok":true}`（兼容路径，webgun/旧客户端用） |
| `GET /state` | → `{"score":int,"target":{"x","y","r"}}` |

准星 0.6s 无更新消失。aim 坐标 = `snapshotAhead(now, predictMs)` 的**预测值**
（默认提前 90ms，手机长按屏幕可调），射击用同一预测量，保证"指哪打哪"与显示一致。

App 默认服务器 `192.168.3.19:8000`（旧电脑 IP）只是兜底。**自动发现（2026-09-29 起）**：手机连上同一 WiFi 即广播探测，PC 应答后自动改连新 PC，无需任何手动操作（找不到 TV 时才回退到保存的地址；长按屏幕仍可手动指定/查改）。新 PC 需关闭 Windows 防火墙或**同时放行 TCP 8000、UDP 8000 与 UDP 8001**。

## 4. 当前状态（v5.1，2026-10-03 用户实测通过）

**v5/v5.1 已通过用户实机验收**：在线时间标定根治了"重启/换镜头后不稳"
与"快移到位后漂移"；残余不稳（开局采集收敛/部分可见跳变）在可接受范围。

### v5.1 补丁：PARTIAL 尺度门控 + 残余不稳定性分析

v5 实测（220120/220523 两段新录制）仍有"偶发不稳"。事件级分析（aim 流 jerk
事件分类）实锤：**顶部 jerk 事件全部集中在开局 ~15s 内，且 td on/off 完全
一致**——与 td 无关，是开局采集收敛 + 部分可见（1-3 边）漂移→回 FULL 跳变
的物理过程（innov 10-62px）。处置实验记录：

- **PARTIAL 校正全关**（gain_partial/gain_edge=0）：重锁定跳变中位 29.6→5.5px、
  jerk95 -16~-47%，但稀疏可见段可用率崩（223525：100→87.7%）——**否决**；
- **PARTIAL 增益减半/三分之一**：jerk95 降 25-47%，但 0921/223525 可用率降
  2-3%（DEAD 空洞同样是不稳）——**否决**（混沌区权衡，无干净收益）；
- **PARTIAL 尺度门控**（尺度仅 FULL 启用，sim_scale_min_edges=4）：零可测
  影响（σ 分析：2 边间距比尺度 σ≈0.7%/帧 纯噪声），保留（无害且原理正确）；
- **td 提速**（td_every 10→5）：0921 早期假峰复活（+82.8ms 摆动再现）——
  **回滚**；预热需要足够数据窗口而非扫描次数。

v5.1 最终 13 段回归（td off→on）：可用率持平或更好（0926 98.4→99.4%），
jerk p95 十段改善或持平（235405 9.0→7.8、004842 10.0→8.3、220120 13.6→11.4、
220523 9.9→7.9），静止抖动持平。ReplayTest 全过。
**已知残余**：开局 ~5-15s（采集收敛+部分可见）与长 PARTIAL 段回 FULL 时的
跳变属物理过程；根治方向是陀螺尺度/轴对准在线标定（待办 5 的 3x3 矩阵，
可复用 td 的曲线积累框架）。

### v5：相机↔IMU 时间戳偏移的在线标定（根治"重启后不稳/快移漂移"）

用户 v4.1 实测仍不稳，并提出关键假设：手机重启后相机与 IMU 之间的延时
变化。离线扫描全部 11 段录制（scripts/diag_ts_offset.py，陀螺积分角 vs
视觉角位移的 δ 网格相关）**证实假设**：各会话最优偏移从 **-42ms 到 +36ms**
互不一致（两段大样本录制差 58ms；重启、换镜头都会变）。快速甩动时 30ms
错位在 5 rad/s 下 = 70~100px 视觉/IMU 失配，是"快移到位后漂移/不稳"的
主根因——**任何固定参数都永远调不准**（Kalibr/VINS-Mono 在线 td 估计的
标准做法）。方案（Tracker.java = guntrack.py 同步，全自动、无需用户标定
动作、天然支持任意手机/镜头）：

- **观测**：边测量帧对的实测边线（带内新拟合的纯图像量，1 边帧也贡献该
  法向 1D 约束） vs 陀螺累积积分（独立 _gcum 环）经 Rodrigues 精确旋转
  T(δ)=K·R(∫ω)·K⁻¹ 变换的预测边线，法向残差；每个 δ 拟合尺度 k
  （吸收焦距误差/平移视差/卷帘快门幅度差——无 k 时实测可发散到搜索边界）。
- **估计**：δ∈±100ms 网格（步长 4ms）残差曲线**跨扫描 EMA 积累**（真 δ
  恒定，积累后最小值变锐，与离线全局扫描同构）；只用 |om|≥1.5px 的有效
  运动约束（边线噪声 ~0.5px）。
- **加固**（每一层都是实测抓出的问题）：预热 ≥8 次扫描才应用（0921 早期
  曾摆到 +82.8ms 假最小值）；扫描按有效约束数加权（<30 降权）；与当前 δ̂
  不一致的扫描降权 0.06；首次应用需 argmin 连续 2 次一致（±8ms）；滞回
  切换需显著更优（-0.03）；抛物线亚网格细化（~1-2ms）；目标更新死区 2ms；
  **δ̂ 应用限速 0.5ms/帧**（突变让积分窗口端点跳动、输出瞬间跳 ω·Δ，
  实测 jerk p95 恶化 30%+）。
- **验证**（scripts/diag_td.py 三件套）：自洽——11 段在线 δ̂ 与 4 个离线
  收敛参考全部吻合（±15ms 内）；注入恢复——陀螺时间戳人为平移
  ±20~60ms，24 点中 22 点 ≤10ms、最坏 11.8ms（困难浅曲线段，无系统性
  方向偏置）；指标回归——11 段可用率全持平，jerk p95 八段改善
  （223451 7.7→6.1、223638 8.3→6.7、004842 9.6→8.7、094620 12.2→11.5），
  lag/jerk 其余无系统性劣化。ReplayTest 全过（relock P95 140.7→23.7px）。
- **回放工具链配套**：diag_smooth.replay/run_track_replay/ReplayTest 的
  process 前瞻喂入 +150ms（真机管道延迟——因果喂入下 δ̂>0 每帧漏积 δ̂
  的旋转，td-on 被冤枉）；snapshot_ahead 外推余量按最后一个 ≤tgt 的
  tick 计算（队列含前瞻样本时余量不被压零）；回放陀螺 cast 到 float32
  （与 Java float 一致）。已知边界：困难段（浅曲线）δ̂ 残差 ±12ms；
  0926 段 lag p95 与 0925_235405 段 jerk p95 各有小幅劣化（混沌敏感）。

### v4.1 补丁：急停到位后的"漂移"修复

用户 v4 实测：静止/慢瞄的"飘"已解决，但**快速移动到位后准星仍漂移**。
停点事件时间线分析（scripts/diag_settle_dump.py）实锤：到位后追踪器内部
（raw 流）误差仅 3-8px，而显示流（aim）与 raw 的差高达 ~240px·ω 的
前冲尾巴——**ω_EMA 有 τ=30ms 滞后，急停瞬间仍按残速 ~0.5-2 rad/s 外推
几十 px，再花 ~0.3s 衰减回来**。修复 = **减速感知外推缩放**：外推量 ×
min(1, |ω_ema|/ω_peak)，ω_peak 为 |ω_raw| 峰值保持（瞬时抬升、τ=150ms
衰减）。匀速段比值≈1 满预测不受影响；减速段比值骤降，外推立即收。
闭环指标（diag_settle.py，甩动到位事件 |aim-raw| 中位）：到位时刻
11.6-15.7px → **3.5-8.6px**，+100ms 收敛到 ~2px。全量 10 段回归
（diag_v4_sweep --variant 0 12）：静止抖动/jerk/感知延迟与 v4 持平或更好
（lag p95 回到 v3 水平），无任何回归。

### v4：从"能用"到"商用手感"——输出级融合反转

用户实测反馈 v3"准星非常飘不稳定"。用 3 段新录制（含实测当时数据）闭环诊断
（diag_smooth 新增 **aim 流**指标 = 真机显示/射击路径 snapshot_ahead(90ms)）实锤
根因——**不是视觉管线，是输出路径把两种噪声直接放进 120Hz 显示流**：

1. **30Hz 视觉校正阶跃**：FULL innov 中位 5.7-6.7px × 自适应增益 → 每帧 2-4px
   的离散拽动直接出现在输出里（jerk p50 贡献）；
2. **ω_EMA 外推噪声**：snapshot_ahead 用 τ=15ms 的角速度 EMA 线性外推 90ms，
   陀螺噪声 0.014-0.023 rad/s 经 EMA（σ÷3.7）×0.09s×1425px/rad ≈ 每 tick
   ±0.6-0.9px 高频震颤，predictMs 越大越飘。

**架构结论（回应"IMU 为主、视觉为辅"）**：纯 IMU 光枪无界漂移，视觉是唯一绝对
基准不能丢；正解是**输出级融合反转**——陀螺拥有输出的全部相对运动（纯旋转
传播数学上精确、天然丝滑），视觉只做绝对纠偏，其阶跃/噪声在输出端被吸收。
v4 两个改动（只作用于 snapshot_ahead 显示/射击路径；内部 H、process 帧率
输出、回放等价语义全部不变）：

1. **one-euro 输出滤波**（商用体感外设标准方案，VR 手柄同款）：2D 单 cutoff，
   cutoff = 1.5Hz + 0.02·|速度|。静止/慢瞄 → 重滤波藏阶跃与震颤；快速运动 →
   近乎直通不糊（运动中阶跃本身不可见）。β 实测选 0.02：0.08 对 2px 阶跃
   截止冲到 ~20Hz 近乎直通，否决。备选 offset（误差状态分离）模式留在
   guntrack.py（out_mode="offset"），实测略逊于 one-euro，未移植 Java。
2. **阻尼外推 + ω_EMA τ 加倍**：外推 θ=ω·τ_d(1-e^(-t/τ_d))（τ_d=80ms）替代
   线性外推——回甩过冲与外推噪声封顶 ω·τ_d；EMA τ 15→30ms 噪声 ÷1.6。
   代价：持续匀速运动欠预测（lag p95 +~10-25px，中位不变），实测权衡值得。

### v4 离线指标（全部 9 段录制 v3→v4，aim 流中位）

| 指标 | v3 | v4 |
|---|---|---|
| 可用率（9 段） | 98.4-100% | 完全一致（内部路径未动） |
| aim 流静止抖动 | 0.37px（干净段 0.41/0.18） | **0.11px**（干净段 **0.08/0.05**） |
| aim 流 jerk p50 / p95 | 2.82 / 15.3px | **1.60 / 9.9px** |
| 感知延迟 lag100 中位 / p95 | 33.2 / 145px | 35.7 / 154px（+2.5/+9，可忽略） |
| ReplayTest（主摄） | 全过 | 全过（内部路径不变） |

### v3 融合核（存档：输出预测+自适应增益+连续零偏+UDP+60fps）

用户实测反馈"检测基本正常，但流畅度/稳定性/真实手感差距大"。先换技术路线的
评估结论：**视觉管线（Sinden 亮边框+逐边亚像素拟合）不是瓶颈**——瓶颈在融合律、
端到端延迟和传输抖动。ArUco/纯陀螺等替代路线同样受 30Hz 帧率与角点噪声约束，
不能解决这三个根因，故保留架构、重写融合核 v3（Tracker.java = guntrack.py 同步）：

1. **输出预测（手感主修）**：aim/射击统一用 `snapshotAhead(now, predictMs)`——
   陀螺队列积分到 now 后，再用 ω 短时 EMA（τ=15ms）匀速外推 predictMs 毫秒
   （限 250ms/0.5rad），补偿曝光→处理→传输→渲染的端到端延迟。默认 90ms，
   手机长按屏幕可调（拖尾调大、回甩调小）。真值锚点法（FULL DLT 未平滑准星
   做真值插值）离线验证：**感知延迟 P95 降低 1.8-2.4 倍**（如广角 100ms 档
   67.3→37.2px，主摄 69.9→29.1px）。快速往返甩动时恒速外推物理受限（加速度快），
   此时 pred≈cur，不更差。
2. **自适应校正增益（one-euro 式）**：g_eff = g_base·(GAIN_MIN+(1-GAIN_MIN)·
   ramp(innov_pre))，innov<1px → 0.35·g_base 平滑噪声，innov>12px → 满增益快速
   再锁定。GAIN_MIN=0.35 是实测权衡点（0.15 太小：视差/积分误差积累成慢摆动；
   运动因子 gain/(1+k|ω|) 实测否决：运动时校正多为真实误差，少信反而积累）。
   效果：平滑运动段 MA7 抖动 1.83→**1.09px**，静止 FULL 抖动 0.36→0.23-0.32px。
3. **连续零偏估计（dyn bias）**：静止学习只在不动时工作，游玩中零偏漂移
   （实测 ~0.01-0.02 rad/s）会在 GYRO 段放大（2s→20-30px）。v3 在 FULL 帧用
   校正前残余分解 ε=t·g_prev/(f·dt) 缓慢并入（β=0.03，钳位 0.08）：
   轴向映射由数值实验钉死（+t_y→+ε_x、-t_x→+ε_y、-θ→+ε_z；预测四边形漂移
   方向与旋转光流相反）；仅相邻 FULL 对（GYRO/非 FULL 校正/采集融合插入都
   破坏 d/g 关系）；陀螺注入测试闭环验证收敛正确（学到的 Δbias≈注入量 70-140%）。
   备选方案存档：两帧精确式 d=(1-g)t_prev−t_now（d≈0.2px/帧 淹没在噪声里）、
   稳态门 |Δt|<1px（过严，几乎不更新）——均实测否决，勿复活。
4. **传输去抖**：aim 从 HTTP POST（每次新 TCP 连接，WiFi 握手 5-30ms 尖峰直接
   卡准星）改 **UDP 120Hz**（同端口 8000，无连接、最新覆盖）；射击/状态仍走
   HTTP（要应答）。PC 端 run_tv.py 加 UDP 监听，游戏循环改为 60Hz 帧 pacing
   （原 waitKey(16) 实际只有 40-50fps）。
5. **相机 60fps 优先**：camera2 AE 档位优先 [60,60]——视觉更新率/曝光上限减半
   （运动中边框更锐利、卷帘快门剪切减半）；处理跟不上时 mailbox 自然丢帧退化
   为 ~30fps（每帧都是最新的，无积压），宽镜头不支持时自动回落 30。

### v3 离线指标（5 段录制回放，真值锚点法）

| 指标 | v2 基线 | v3 终版 |
|---|---|---|
| 可用率（5 段） | 97.8-100% | 98.4-100% |
| 静止 FULL 抖动（2 段干净录制） | 0.36 / 0.40px | **0.32 / 0.23px** |
| 平滑运动段 MA7 抖动（广角） | 1.83px | **1.09px** |
| 感知延迟 P95（100ms 档，广角/主摄） | 88.3 / 63.4px | **37.2 / 29.1px**（预测开） |
| 跟踪器内禀滞后 τ（锚点法） | 8-17ms | 8-17ms |
| 伪失锁 0.5s 窗末误差（广角，dyn on/off） | 33.3 / 36.6px | **25.6px** |
| ReplayTest（5 段） | 全过 | 全过（grade 一致 83-100%，co-FULL 差 ≤1.2px，抖动完全持平） |

### v3 自审查备忘（改动区）

- `snapshot_ahead`：队尾后外推用 ω_EMA−bias，限角 0.5rad/限时 250ms；H 为
  None/DEAD 时回退当前 cross；不动基准、不消费队列（与 snapshot 同惰性语义）。
- `dec4`（动态零偏用残余分解）必须在 `_apply_correction` **之前**算
  （校正后残余被增益削减，簿记会错）。
- `meas_cross`/`innov_pre` 每帧重置；采集 DLT 成功也记 `meas_cross`（真值锚点）。
- 诊断共识：**GYRO 段静止抖动跨版本不可比**——同一角速度噪声经斜视角透视
  放大倍数不同，反馈链混沌使各版本落点不同；公平对比只看 FULL 段（jit_full）。
- record_20260926_114948（主摄重运动）锚点仅 6 个，感知延迟指标不可判——
  该形态（屏幕长期不全）的预测收益需真机验证。

### 2026-09-26 主摄实测复盘（record_20260926_114948，部分采集版）

惰性传播版实测仍差（真机 DEAD 26%/GYRO 43%）。离线复锤归因链与修复：

1. **采集要求 4 边是死结**：屏幕部分入镜时 GYRO>3s → DEAD → 全采集必失败 → 永久 DEAD。
   新增**部分采集**：粗四边形+拟合边重建——相邻双边角点用交点（真值），单边角点投影
   到拟合线（裁切只影响垂直方向），再满增益相似校正 + 一致性校验（<4px/<3°）；
   GYRO 状态下直接用拟合边校正现有 H（绝不用被裁切的粗四边形初始化有 H 的状态）。
   事故案例：seq154 错四边形初始化 → cross (7445,-10676) 假锁，由"无 H 时禁止用粗
   四边形+相邻/双轴边数要求+一致性校验"三关杜绝。
2. **slew 限幅拖累收敛**（60→250px 时仍把正确采集拖到几十帧才收敛，期间 FULL 误差
   中位 95px）：限幅全部停用，防假跳变改由几何/中空/暗度/一致性门控负责。
3. **采集融合门从准星距改为四角最大位移**（形状不同但中心恰好重合时旧门会漏判，
   错误状态挂着 FULL 标签不纠正）。

效果（同数据回放）：可用率 97.8%（DEAD 15 帧）、FULL 中位 6.9px、EDGE 21px、
GYRO 27px（重运动+近距离平移视差的物理边界）；再锁定校正中位 11.8px；
Java/Python 等价 grade 一致 96.4%、co-FULL 准星差 0.07px。**主摄 68° 在实测距离下
可用性已达标；超广角仍是大空间/大动作推荐镜头。**

### 2026-09-25 深夜实测复盘（record_20260925_235405 / record_wide_20260925_235333）

**根因（已修复）：陀螺-视觉时间错配。** 旧实现里 worker 处理一帧时，陀螺已积分到
"处理时刻"（曝光之后 ~0.1-0.2s），预测位置相对帧内容超前 = 角速度 × 延迟；用户运动
中位 0.55 rad/s（P90 1.1），超前量 10-30 img px，超出边带（12-24px）→ 逐边测量饿死
→ GYRO 占比 53-66%、FULL 仅 0.8-6.6%，输出大量漂移。用录制数据做 +延迟 扫描复现：
+208ms 时等级分布与真机逐帧一致率从 20% 升到 62%，分布 [0,306,122,147,45] ≈ 真机
[0,329,131,119,41]，实锤。

**修复：惰性传播（lazy propagation）。** 陀螺 tick 只入队不积分；`processGray(frameTs)`
先把 H 从基准重积分到帧曝光时刻再做视觉；`snapshot(nowNs)` 从基准重积分到 now 输出
准星（60Hz aim 不受影响）。Python/Java 同步实现，行为等价（见 §Java/Python 回放等价）。

**残余时间偏移标定（δ 扫描，2026-09-26）**：用户问是否要专门标定相机-IMU 事件 gap。
用新录制对帧时间戳偏移 δ∈[-100,+100]ms 扫描：校正量中位数随 δ 单调改善到 ~+33ms
（6.5→4.9px），≈ 曝光起点→曝光中心（exposure/2）+ 卷帘快门均值的理论值；与陀螺轴
映射 M（calib_prop.py，逐帧锁定对回归）是相互独立的两个标定，M 已在 v2 固定。
**结论：不需要额外的手机端标定流程**，改为原理性补偿：camera2 帧时间戳 =
image.getTimestamp() + SENSOR_EXPOSURE_TIME/2（CaptureCallback 读真实曝光时间，
未知时回退 16.5ms）。δ 扫描显示残余 ±25ms 内指标平坦，无需逐机微调。

修复后（同两段录制回放）：可用率 95-100%，GYRO 1-2%（原 53-66%），FULL 14-18%；
真机预期行为 = 回放行为（回放与真机输入完全相同）。

### 2026-09-25 真机实测复盘（record_wide_20260925_214838）

**结论：当时手机上跑的是旧 APK（Detector+Fusion），不是 v2。** detect.csv 为旧管线特征
（failStage∈{0,6,7} 旧错误码、blobFrac 全量非零、detCross≠fused 全行）。根因：v2 初版
build.sh 写死了开发机路径，实测机构建失败 → 手机仍是旧 App。已修复：build.sh 机器无关化
（自动探测 JDK/SDK，`JAVAC=/JAVA11=/ANDROID_SDK=` 可覆盖），并把**预编译 APK 直接入库**
（`android/tvgun.apk`，`adb install -r` 即可，无需构建）。

旧管线实测行为（15.1s/422 帧，即用户感到"不流畅不准确"的内容）：
- 锁定率仅 64.5%，34.4% 帧处于外推/无锁；|fused-det| 中位 73px（P90 163px，max 464px）；
- 全链路误差（渲染准星 vs 图像中心实测）：静止时 (-1.6,+5.8)px，运动中 −63px，
  失锁外推时 −364px（跟随延迟+外推冻结主导）；
- aim 上报 ≤15Hz 绑相机帧。

v2 追踪器在该环境的稀疏验证（17 张 full jpg 帧 + gyro 回放）：
- seq0/28/402 正常采集 FULL，准星与旧 det 差 2.5px（seq0）；采集拒绝场景全部是合理的
  屏幕出画（边框被图像边缘裁切，旧管线在这些帧靠极值角点"静默错锁"）；
- 该环境采集链路与陀螺传播工作正常，无灯具/文字屏错锁。

### 实验室回放指标（惰性传播修复后）

修复前后对比（同数据回放）：

| 指标 | 修复前真机（时间错配） | 修复后（惰性传播） |
|---|---|---|
| 广角新录制 GYRO 占比 | 53.1% | **1.0%** |
| 广角新录制可用率 | 46.9%（locked） | **100%** |
| 输出平滑度（帧间二阶差分均值） | 84.9px（P95 436） | **17.0px（P95 50）** |
| 广角新录制 FULL 精度（vs linefit 参考） | — | 中位 3.3px（运动模糊尾部 P90 36） |
| 主摄新录制 GYRO 占比 | 66.0% | 55.7%（**几何主导**：68° FOV 装不下，见待办 8） |
| 旧主摄录制 可用率/静止抖动 | — | 100% / 0.36px |
| 旧广角录制 可用率/静止抖动 | — | 98.0% / 0.49px |
| Java/Python 回放等价（3 段） | — | grade 一致 80-99%，co-FULL 准星差 0.38-0.59px，抖动完全持平 |
| Java 耗时 | — | 1.4ms/帧（桌面 JVM） |

### 已知问题 / 待办（按优先级）

1. **两点校准未做**：枪管-手机光轴安装偏差 + 边框外缘 13px 偏差 + 广角 +6.9px 系统偏差，
   计划用"瞄两个已知角开两枪"自动解算补偿。校准前打鸭子有固定偏差（不影响流畅性，影响准度）。
2. **超广角畸变已评估无需处理**：92° 镜头下边框直线拟合 σ 中位 0.29px（上限 2px），不弯。
3. **超广角预览未目验**：camera2 预览 Surface 曾修过黑屏 bug（setFixedSize），亮画面下未人工确认过一次。
4. **camera2 暗光 fps≈28**（fpsRange 是软约束，legacy 是硬锁 30）；可试 TEMPLATE_RECORD。
5. **GYRO 长窗漂移**：伪失锁 2s 窗末中位误差 ~110px——**主因是陀螺尺度/轴对准
   误差**（1-2% × 总转角），零偏只占小头（v3 连续零偏已把 0.5s 窗误差 33→26px）；
   进一步要在线标定 3x3 陀螺标定矩阵（自由度多、噪声大，未做）。>1s 完全出画
   属物理边界，回屏由采集/逐边校正收敛。
10. **v3 预测旋钮 predictMs**（默认 90ms）按显示器延迟调节：电视（游戏模式）
    90-130ms、电竞显示器 50-70ms；HUD 不显示当前值，长按屏幕对话框可查改。
6. vendor id 候选表（20/21/60-63/100/120）是小米 9 实测值，换手机需重新探测。
7. **EDGE 级精度有限**：单边约束只钉 2 个自由度（横边钉垂直，竖边钉水平），另一方向靠陀螺。
   大角度长时间只有单边可见时该方向会漂——属设计内行为（≥2 边即恢复全约束）。
8. **主摄 68° FOV 在实测距离下几何受限**：实测距离下屏幕常部分出画。
   部分采集（粗四边形+拟合边重建+一致性校验）已解决"部分入镜不能定位"问题，
   五段录制回放可用率 97.8-100%。余量：超广角仍是大空间/大动作推荐镜头。
9. **record_20260925_235405（主摄重运动）的 Java/Python 回放混沌**：等级一致率
   68.6%（门 75%），但可用帧数逐帧相同、强对角混淆——反馈链在小数级差异上的
   混沌放大（该录制 GYRO 占比 ~50%，收敛锚点少），非移植缺陷；其余四段
   85.9-99.6% 一致。行为级指标（可用率/抖动/再锁定）全部对齐。


## 5. 数据资产（test_res/）

| 路径 | 内容 |
|---|---|
| `screen_video.mp4` | 最早的实拍视频 960×540×22s（锁定率验证用） |
| `record_20260921_230150/` | 主摄 68°，58.2s：静止/瞄四角/侧边出画/上下出画/近距离/快甩/完全出画 |
| `record_wide_20260921_235354/` | 超广角 92°，53s，同套动作 |
| `record_wide_20260925_214838/` | 超广角 92°（c2:21），~15s/422帧，**旧APK录制（作废，见 §4 复盘）** |
| `record_wide_20260925_235333/` | 超广角 92°（c2:21），620帧，新版 v2（appVersion=3407e3e-dirty） |
| `record_20260925_235405/` | 主摄 68°（c2:0），506帧，新版 v2（appVersion=3407e3e-dirty） |
| `record_20260926_114948/` | 主摄 68°（c2:0），686帧，惰性传播+曝光中点补偿版（appVersion=25d8a50-dirty） |
| `record_20261002_094620/` | 超广角 92°（c2:21），459帧，v4.1 重启后会话（v5 根因确认的触发数据） |
| `record_20261002_220120/` | 超广角 92°，539帧，**v5 实测**（locked 89.8%） |
| `record_20261002_220523/` | 超广角 92°，406帧，**v5 实测**（locked 100%） |

录制目录格式：`meta.txt`（相机/时钟参数）、`frames.bin`（640×360 uint8 灰度拼接）、`frames_idx.csv`（seq,tsNs）、`gyro.csv`（tsNs,wx,wy,wz）、`detect.csv`（逐帧检测+融合输出；v2 起 failStage 列存 grade）、`full_*.jpg`（每秒1张参考）。

注意：`frames.bin` 走 Git LFS，仓库已近 700MB。

## 6. 新电脑搭建（本机已验证）

1. 克隆仓库（需 git-lfs 拉取 frames.bin）。
2. **Python**：装 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)，然后：
   ```bash
   uv venv .venv && uv pip install -r requirements.txt
   uv pip uninstall opencv-python-headless && uv pip install opencv-python   # TV窗口需要GUI版
   ```
3. **Android 构建链**（仅自行构建 APK 才需要；也可直接用仓库里的预编译 `android/tvgun.apk`）：
   `android/build.sh` 自动探测 JDK（javac 任意版本）+ Java 11+（d8/apksigner 用）+
   Android SDK（最新 platform 与 build-tools）；探测失败时用环境变量覆盖：
   `JAVAC=<javac路径> JAVA11=<java11+路径> ANDROID_SDK=<sdk根目录> bash build.sh install`。
4. **手机**：小米 9 开 USB 调试，插线授权（`adb devices` 显示 `device`）。
   安装：`cd android && bash build.sh install`，或直接 `adb install -r android/tvgun.apk`。
5. **网络**：手机与新 PC 同一局域网；新 PC 关防火墙或放行 **TCP 8000 + UDP 8000**；查新 PC 局域网 IP（`ipconfig`），手机上**长按屏幕**把服务器改成新 IP。
6. 启动电视端验证：`.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42`，手机 App 对屏应出 FULL/PARTIAL + TV 出青色准星。

## 7. 命令速查

```bash
# 电视端
.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42   # --selftest 自检
# 构建安装 App
cd android && bash build.sh install
# 手机操作
adb shell am start -n com.tvgun.gun/.MainActivity     # 启动
adb shell input keyevent KEYCODE_VOLUME_UP            # 切镜头
adb shell input keyevent KEYCODE_VOLUME_DOWN          # 开始/停止录制
adb shell "logcat -d -s tvgun:I"                      # 看日志
MSYS_NO_PATHCONV=1 adb pull /storage/emulated/0/Android/data/com.tvgun.gun/files/record/<目录> D:\tvgun\test_res\xxx
# 追踪器回放评测（Python 参考实现）
.venv/Scripts/python.exe scripts/run_track_replay.py --rec test_res/record_20260921_230150
.venv/Scripts/python.exe scripts/run_track_replay.py --rec test_res/record_wide_20260921_235354
# 流畅度/手感诊断（真值锚点法；--v3 0 跑 v2 基线；--inject 做零偏注入验证）
.venv/Scripts/python.exe scripts/diag_smooth.py --v3 1 --save out/diag_v3.json
.venv/Scripts/python.exe scripts/diag_smooth.py --rec test_res/x --v3 1 --no-still-bias --inject 0.012,-0.008,0.006
# 旧基线对照
.venv/Scripts/python.exe scripts/run_record_replay.py --rec test_res/record_20260921_230150
# 陀螺轴向映射回归
.venv/Scripts/python.exe scripts/calib_prop.py --rec test_res/record_20260921_230150
# Java 单元测试 + 回放等价（JDK8 javac 直编译）
JDK="/c/Program Files/Android/jdk/jdk-8.0.302.8-hotspot/jdk8u302-b08"
"$JDK/bin/javac.exe" -encoding UTF-8 -d /tmp/jcls android/src/com/tvgun/gun/Tracker.java android/src/com/tvgun/gun/ControlButtons.java android/test/*.java
"$JDK/bin/java.exe" -cp /tmp/jcls TrackerTest
"$JDK/bin/java.exe" -cp /tmp/jcls ControlButtonsTest   # 虚拟按键协议层（内置假 HTTP 服务器）
"$JDK/bin/java.exe" -cp /tmp/jcls ReplayTest [recDir refCsv]   # 默认主摄录制
"$JDK/bin/java.exe" -cp /tmp/jcls ReplayTest D:/tvgun/test_res/record_wide_20260921_235354 D:/tvgun/out/track_record_wide_20260921_235354/track_replay.csv
```

## 8. git 历史

```
屏幕虚拟按键：投币/开始/换弹/退出四角悬浮按钮（ControlButtons 协议层 + ControlButtonsTest，退出双击确认）
（v2）追踪器重写：H 传播 + 逐边校正 + 采集多候选 + 60Hz aim
c4aaecc Camera2迁移接入超广角/长焦
118b441 超广角采集数据 53s
fd03a31 直线拟合角点+融合轴向修复（静默错锁归零）
7159af4 主摄采集数据 58.2s（全场景）
c7972d0 手机光枪真机系统初版（APK+TV+验证）
bc0c621 屏幕坐标定位仿真验证系统（第一、二期）
```
