# TVGun 手机光枪 — 交接文档（2026-09-22）

> 本文档供更换电脑后快速恢复开发。包含：项目现状、架构、协议、数据资产、已知问题、新机器搭建步骤、命令速查。

## 1. 项目是什么

把手机固定在玩具光枪上玩"打鸭子"：PC 显示器全屏显示游戏（相当于电视），手机后置摄像头看着显示器，App 实时解算"枪口指向屏幕的哪个像素"，点手机屏幕 = 扳机。定位方案 = **Sinden 式亮边框 + 四角单应 + 陀螺仪融合**（纯软件，不改电视硬件）。

本仓库另含第一期/第二期的"隐形水印定位"仿真系统（sim/、SPEC.md、SPEC2.md、REPORT.md），与光枪真机系统相互独立，不在本文档范围。

## 2. 系统组成

```
PC 端（Windows）
  scripts/run_tv.py        电视端：cv2 全屏游戏（黑底+24px白边框+弹跳鸭子+分数）
                           + 内置 HTTP 服务器（0.0.0.0:8000）
  scripts/run_video_test.py    实拍视频离线检测验证（screen_video.mp4 用）
  scripts/run_video_imu.py     视频+仿真IMU融合验证
  scripts/run_record_replay.py 手机录制数据回放调优（基线复现/直线拟合/融合回放）
  test_res/                验证素材（见 §5）

手机端（小米 9，Android 10）
  android/                 光枪 App（纯 Java，无 gradle 手工构建链）
    build.sh               构建+安装一条龙（JBR javac + aapt2 + d8 + apksigner）
    src/com/tvgun/gun/
      MainActivity.java    相机双后端(camera2优先/legacy回退)、检测工作线程、
                           扳机、/aim上报、录制、镜头切换、服务器配置
      Camera2Backend.java  camera2 枚举(含MIUI隐藏vendor id)/会话/帧回调
      Detector.java        边框检测：双阈值连通域粗定位→640全分辨率直线拟合角点
      Fusion.java          陀螺互补滤波（200Hz外推+锁定帧校正+1s预测窗）
      OverlayView.java     准星/HUD/失锁提示/REC指示
      Recorder.java        视频+IMU+检测同步录制（音量下键触发）
    test/                  离线单元测试（41项）+ ReplayTest（Java/Python逐帧等价）

备用客户端
  webgun/                  浏览器版光枪（adb reverse 通道，已被 APK 取代，仅留档）
```

## 3. 通信协议（两端必须一致）

坐标系：**规范坐标 1920×1080**，游戏白边框四角 = (0,0)/(1920,0)/(1920,1080)/(0,1080)。检测角点取的是边框**外**缘，有约 13px 系统偏差（待校准统一处理）。

HTTP（TV 端监听 `0.0.0.0:8000`，手机经 WiFi 局域网访问 PC IP）：

| 端点 | 说明 |
|---|---|
| `POST /shot` | `{"x":f,"y":f}` → `{"hit":bool,"score":int}`，点屏幕开火 |
| `POST /aim` | `{"x":f,"y":f}` → `{"ok":true}`，~15Hz 准星上报，TV 画青色准星，0.6s 无更新消失 |
| `GET /state` | → `{"score":int,"target":{"x","y","r"}}` |

App 默认服务器 `192.168.3.19:8000`（旧电脑 IP）。**换新电脑后**：手机上**长按屏幕**弹对话框改成新 PC 的局域网 IP 即可，不用改代码；新 PC 需关闭 Windows 防火墙或放行 8000 端口。

## 4. 当前状态

### 已验证可用

- 检测：可见帧（四边完整入镜）锁定率 100%，静止抖动 0.38 屏幕px，亚像素直线拟合角点，静默错锁归零（宁可 NO LOCK 不可错锁）。
- 闭环：视频→检测→网络→TV 渲染→截屏比对，100/100 命中、中位偏差 0.76px。
- IMU 融合：轴向映射已用真机数据回归修正（rot=0: dx=−ωx, dy=+ωy）；200Hz 平滑输出；失锁 ≤1s 外推可用（中位误差 ~11px）。
- Camera2 三摄：主摄 68° / **超广角 92°** / 长焦 36°，音量上键循环切换并持久化，S=1920/rad(viewAngle) 自动重算。
- 录制：音量下键触发，640×360 灰度帧流 + ~400Hz 陀螺 + 逐帧检测输出，统一 CLOCK_MONOTONIC 时间戳。
- Java 移植与 Python 参考实现逐帧等价（锁定一致率 100%，cross 差中位 0.000px）；单元测试 41 项全过。

### 已知问题 / 待办（按优先级）

1. **部分/完全出画时不可用（核心待办）**：当前要求四条边全部入镜。数据实测 66% 使用时间存在缺边。方案已设计未实现：
   - 陀螺单应传播（H ← K·RΔ·K⁻¹·H，纯旋转可完全由陀螺推出）+ 静止零偏自校准；
   - 残边约束校正（可见横边钉俯仰+垂直，竖边钉偏航+水平，简化 VIO）；
   - 可用性分级 FULL/PARTIAL/GYRO_ONLY/DEAD（T_max≈3s）。
   开发素材：`test_res/record_20260921_230150`（主摄）与 `record_wide_20260921_235354`（超广角）含全部失效场景。
2. **超广角畸变未评估**：92° 镜头桶形畸变会让边框变弯，fitEdges 的 σ 校验可能误杀；先用广角录制数据评估，必要时加畸变模型或只用画面中心区域。
3. **超广角预览未目验**：camera2 预览 Surface 曾修过黑屏 bug（setFixedSize），亮画面下未人工确认过一次。
4. **camera2 暗光 fps≈28**（fpsRange 是软约束，legacy 是硬锁 30）；可试 TEMPLATE_RECORD。
5. **两点校准未做**：枪管与手机光轴的安装偏差 + 边框外角点偏差，计划用"瞄两个已知角开两枪"自动解算补偿。
6. **有效 S 随观看距离变化**：陀螺积分不含平移视差（物理边界），失锁外推在近距离会欠走 ~25%。
7. vendor id 候选表（20/21/60-63/100/120）是小米 9 实测值，换手机需重新探测。

## 5. 数据资产（test_res/）

| 路径 | 内容 |
|---|---|
| `screen_video.mp4` | 最早的实拍视频 960×540×22s（锁定率验证用） |
| `record_20260921_230150/` | 主摄 68°，58.2s：静止/瞄四角/侧边出画/上下出画/近距离/快甩/完全出画 |
| `record_wide_20260921_235354/` | 超广角 92°，53s，同套动作 |

录制目录格式：`meta.txt`（相机/时钟参数）、`frames.bin`（640×360 uint8 灰度拼接）、`frames_idx.csv`（seq,tsNs）、`gyro.csv`（tsNs,wx,wy,wz）、`detect.csv`（逐帧检测+融合输出）、`full_*.jpg`（每秒1张参考）。

注意：`frames.bin` 使仓库已近 700MB。如需瘦身：`git filter-repo` 或迁移 Git LFS。

## 6. 新电脑搭建

1. 克隆仓库。
2. **Python**：装 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)，然后：
   ```bash
   uv venv .venv && uv pip install -r requirements.txt
   uv pip uninstall opencv-python-headless && uv pip install opencv-python   # TV窗口需要GUI版
   ```
3. **Android 构建链**（构建 APK 才需要）：安装 Android Studio（自带 JBR 与 SDK）。`android/build.sh` 顶部路径需指向新机器的：
   - JBR：`C:\Program Files\Android\Android Studio\jbr\bin`
   - SDK platform：`platforms\android-37.0\android.jar`，build-tools `36.0.0`
   - adb：`Sdk\platform-tools\adb.exe`
4. **手机**：小米 9 开 USB 调试，插线授权（`adb devices` 显示 `device`）。App 已装在手机上，换电脑不用重装；如需重装 `cd android && bash build.sh install`。
5. **网络**：手机与新 PC 同一局域网；新 PC 关防火墙或放行 TCP 8000；查新 PC 局域网 IP（`ipconfig`），手机上**长按屏幕**把服务器改成新 IP。
6. 启动电视端验证：`.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42`，手机 App 对屏应出 LOCK + TV 出青色准星。

## 7. 命令速查

```bash
# 电视端
.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42   # --selftest 自检
# 构建安装 App
cd android && bash build.sh install
# 手机操作（ADB 替换为本机路径）
adb shell am start -n com.tvgun.gun/.MainActivity     # 启动
adb shell input keyevent KEYCODE_VOLUME_UP            # 切镜头
adb shell input keyevent KEYCODE_VOLUME_DOWN          # 开始/停止录制
adb shell "logcat -d -s tvgun:I"                      # 看日志
MSYS_NO_PATHCONV=1 adb pull /storage/emulated/0/Android/data/com.tvgun.gun/files/record/<目录> D:\tvgun\test_res\xxx
# 回放验证
.venv/Scripts/python.exe scripts/run_record_replay.py --baseline   # 旧算法对照
.venv/Scripts/python.exe scripts/run_record_replay.py --annotate 8 # 出标注帧
# 单元测试（android/test/ 下，JBR javac 直编译 Detector/Fusion + 测试类）
```

## 8. git 历史

```
c4aaecc Camera2迁移接入超广角/长焦
118b441 超广角采集数据 53s
fd03a31 直线拟合角点+融合轴向修复（静默错锁归零）
7159af4 主摄采集数据 58.2s（全场景）
c7972d0 手机光枪真机系统初版（APK+TV+验证）
bc0c621 屏幕坐标定位仿真验证系统（第一、二期）
```
