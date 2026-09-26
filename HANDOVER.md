# TVGun 手机光枪 — 交接文档（2026-09-25，追踪器 v2 重写版）

> 本文档供更换电脑后快速恢复开发。包含：项目现状、架构、协议、数据资产、已知问题、新机器搭建步骤、命令速查。
> **实测/构建流程与防版本错配机制另见 [WORKFLOW.md](WORKFLOW.md)（必读）。**

## 1. 项目是什么

把手机固定在玩具光枪上玩"打鸭子"：PC 显示器全屏显示游戏（相当于电视），手机后置摄像头看着显示器，App 实时解算"枪口指向屏幕的哪个像素"，点手机屏幕 = 扳机。定位方案 = **Sinden 式亮边框 + 陀螺传播单应 + 逐边视觉校正**（纯软件，不改电视硬件）。

本仓库另含第一期/第二期的"隐形水印定位"仿真系统（sim/、SPEC.md、SPEC2.md、REPORT.md），与光枪真机系统相互独立，不在本文档范围。

## 2. 系统组成（v2，2026-09-25 重写核心算法）

```
PC 端（Windows）
  scripts/run_tv.py              电视端：cv2 全屏游戏（黑底+24px白边框+弹跳鸭子+分数）
                                 + 内置 HTTP 服务器（0.0.0.0:8000）
  scripts/guntrack.py            【核心】追踪器 Python 参考实现（见下）
  scripts/run_track_replay.py    录制回放评测：可用率/抖动/精度/再锁定/伪失锁 MC
  scripts/run_record_replay.py   旧算法（extrema/linefit 四角）基线回放（留档对照）
  scripts/calib_prop.py          陀螺→相机轴向映射回归（M 矩阵标定工具）
  scripts/diag_unlock.py         失锁帧根因诊断（连通域/边拟合可视化）
  test_res/                      验证素材（见 §5）

手机端（小米 9，Android 10）
  android/                 光枪 App（纯 Java，无 gradle 手工构建链）
    build.sh               构建+安装一条龙（JDK8 javac + aapt2 + d8(JRE17) + apksigner）
    src/com/tvgun/gun/
      Tracker.java         【核心】guntrack.py 的逐语句 Java 移植（见下）
      MainActivity.java    相机双后端、Tracker 驱动、60Hz aim 发送、录制、镜头切换
      Camera2Backend.java  camera2 枚举(含MIUI隐藏vendor id)/会话/帧回调
      OverlayView.java     准星/HUD/等级显示（FULL/PARTIAL/EDGE/GYRO/DEAD）/REC指示
      Recorder.java        视频+IMU+检测同步录制（音量下键触发）
    test/                  TrackerTest（合成场景 16 项断言）+ ReplayTest（Java/Python 回放等价）

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
- **校正**：4 边（FULL）= 邻边交点 → DLT → 按 0.6 增益收敛（绝对复位透视漂移）；
  1-3 边（PARTIAL/EDGE）= 图像空间相似校正（平移=截断特征值 2x2 LS、旋转=夹角加权、
  尺度=平行边对间距比）；全部 slew 限幅 60px/帧防可视跳变。
- **采集**：失锁（或 GYRO>0.3s / 边数长期<3）时遍历至多 5 个候选亮域，
  逐个四边拟合 + 几何校验 + 中空校验（内缩 18% 四边形亮像素 ≤30%），全部通过才重建 H。
- **零偏**：视觉确认不动（|校正|<2px）且 |ω|<0.06rad/s 时 EMA 在线学习陀螺零偏。
- **等级**：FULL(4边)/PARTIAL(2-3)/EDGE(1)/GYRO(0边≤3s)/DEAD（超 3s）。
  准星以陀螺速率（~400Hz）更新，aim 上报 60Hz 独立线程（不绑相机帧）。

## 3. 通信协议（两端必须一致）

坐标系：**规范坐标 1920×1080**，游戏白边框四角 = (0,0)/(1920,0)/(1920,1080)/(0,1080)。
检测角点取边框**外缘**，有 ~13px 系统偏差 + 广角镜头 ~7px 附加偏差（待两点校准统一处理）。

HTTP（TV 端监听 `0.0.0.0:8000`，手机经 WiFi 局域网访问 PC IP）：

| 端点 | 说明 |
|---|---|
| `POST /shot` | `{"x":f,"y":f}` → `{"hit":bool,"score":int}`，点屏幕开火 |
| `POST /aim` | `{"x":f,"y":f}` → `{"ok":true}`，**60Hz** 准星上报，TV 画青色准星，0.6s 无更新消失 |
| `GET /state` | → `{"score":int,"target":{"x","y","r"}}` |

App 默认服务器 `192.168.3.19:8000`（旧电脑 IP）。**换新电脑后**：手机上**长按屏幕**弹对话框改成新 PC 的局域网 IP 即可，不用改代码；新 PC 需关闭 Windows 防火墙或放行 8000 端口。

## 4. 当前状态（v2 实测指标）

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
5. **GYRO 长窗漂移**：伪失锁 2s 窗末中位误差 ~110px（零偏随机游走主导）；>1s 的完全出画
   属物理边界，回屏时由采集/逐边校正收敛（slew 限幅，可视上不跳变）。
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
5. **网络**：手机与新 PC 同一局域网；新 PC 关防火墙或放行 TCP 8000；查新 PC 局域网 IP（`ipconfig`），手机上**长按屏幕**把服务器改成新 IP。
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
# 旧基线对照
.venv/Scripts/python.exe scripts/run_record_replay.py --rec test_res/record_20260921_230150
# 陀螺轴向映射回归
.venv/Scripts/python.exe scripts/calib_prop.py --rec test_res/record_20260921_230150
# Java 单元测试 + 回放等价（JDK8 javac 直编译）
JDK="/c/Program Files/Android/jdk/jdk-8.0.302.8-hotspot/jdk8u302-b08"
"$JDK/bin/javac.exe" -encoding UTF-8 -d /tmp/jcls android/src/com/tvgun/gun/Tracker.java android/test/*.java
"$JDK/bin/java.exe" -cp /tmp/jcls TrackerTest
"$JDK/bin/java.exe" -cp /tmp/jcls ReplayTest [recDir refCsv]   # 默认主摄录制
"$JDK/bin/java.exe" -cp /tmp/jcls ReplayTest D:/tvgun/test_res/record_wide_20260921_235354 D:/tvgun/out/track_record_wide_20260921_235354/track_replay.csv
```

## 8. git 历史

```
（v2）追踪器重写：H 传播 + 逐边校正 + 采集多候选 + 60Hz aim
c4aaecc Camera2迁移接入超广角/长焦
118b441 超广角采集数据 53s
fd03a31 直线拟合角点+融合轴向修复（静默错锁归零）
7159af4 主摄采集数据 58.2s（全场景）
c7972d0 手机光枪真机系统初版（APK+TV+验证）
bc0c621 屏幕坐标定位仿真验证系统（第一、二期）
```
