# TVGun 开发与实测流程（防版本错配指南）

> 目标读者：在多台电脑 + 手机之间协作的开发者（当前主力）。
> 2026-09-25 事故复盘：实测机构建失败，手机上残留旧 App，导致"新版不流畅/不准确"的
> 错误结论。本文档的流程和机制保证这种事不再发生。

## 1. 版本识别机制（已内建，先知道怎么查）

APK 构建时 `build.sh` 会把 `git describe --always --dirty --tags` 嵌入 App
（生成 `out/gen/.../Version.java`，不入库）。运行中有**三个地方**能看到当前版本：

| 位置 | 查法 | 期望输出 |
|---|---|---|
| **HUD 左下角** | 打开 App 直接看屏幕（灰色小字） | 如 `3407e3e` 或 `3407e3e-dirty` |
| **logcat** | `adb shell "logcat -d -s tvgun:I"` 找 `tvgun version` | `tvgun version 3407e3e` |
| **录制 meta.txt** | 录制目录的 `meta.txt` 里 `appVersion=` 行 | `appVersion=3407e3e` |

**规则：任何测试开始前，先看 HUD 左下角的版本号，确认等于预期 commit。**
**规则：任何录制数据回传时，meta.txt 的 appVersion 必须与预期一致，否则数据作废重录。**

辅助判别（当没有版本戳的老数据）：看 `detect.csv` 的 `failStage` 列——
出现 6/7 的是旧管线（Detector+Fusion 错误码）；v2 追踪器只写等级 0..4
（0=DEAD 1=GYRO 2=EDGE 3=PARTIAL 4=FULL），且 fusedX/Y 与 detCrossX/Y 恒等、blobFrac 恒为 0。

## 2. 标准实测流程（每次实测按顺序走）

1. **同步代码**：`git pull`，确认 `git log --oneline -1` 是要测的 commit。
2. **安装 APK**（二选一）：
   - 自行构建：`cd android && bash build.sh install`（机器无关，自动探测 JDK/SDK；
     失败时用 `JAVAC=/JAVA11=/ANDROID_SDK=` 环境变量指定）；
   - 预编译：`adb install -r android/tvgun.apk`（先确认 APK 与 HEAD 一致，见 §4）。
3. **核对版本**：打开 App，看 HUD 左下角版本号 == 预期 commit。
   **构建失败不会让手机上的旧 App 消失**——装完必须看版本号，不看等于没装。
4. **冒烟录制**：音量下键录 5~10 秒，拉回看 `meta.txt` 的 `appVersion=` 与
   `detect.csv` schema（failStage 只有 0..4）。通过才开始正式测试。
5. **回传数据**：整个录制目录 push 到 `test_res/`（frames.bin 走 LFS），
   附一句 HUD 版本截图或 logcat `tvgun version` 行。

## 3. 构建环境约定

- `android/build.sh` 自动探测：javac（任意 JDK）→ Java 11+（d8/apksigner 需要）→
  Android SDK（最新 platform 与 build-tools）。探测顺序：Android Studio JBR →
  已知安装路径 → PATH。
- 探测失败时的环境变量覆盖：`JAVAC=<javac路径>`、`JAVA11=<java11+路径>`、
  `ANDROID_SDK=<sdk根目录>`。
- 各机器已验证配置：
  - 开发机（D:\tvgun）：JDK8 javac + JRE17（D:\Tools）+ android-35/build-tools 36.0.0；
  - 实测机：Android Studio JBR + 本机 SDK。

## 4. 预编译 APK 更新规则

- `android/tvgun.apk` 入库是为了**免构建直装**，必须与源码保持一致：
  - 只在核心代码（src/ 或追踪算法参数）变更后才重新构建并 `git add -f android/tvgun.apk`；
  - commit message 里写明 APK 对应的 commit；
  - 拉代码后安装 APK 前，先 `git log --oneline -1 -- android/tvgun.apk`，
    若该 commit 落后于 HEAD 且期间有 src/ 变更，必须自行 `bash build.sh install` 重装。
- `android/tvgun.apk.idsig`、`android/out/`、`android/debug.keystore` 一律不入库。

## 5. 数据可信度检查清单（分析数据前先做）

1. `meta.txt` 有 `appVersion=` 且与目标 commit 一致；
2. `detect.csv` 的 `failStage` 只有 0..4（不是 6/7）；
3. `frames.bin` 尺寸 = 帧数 × 230400；
4. 时钟统一：`gyro.csv` 与 `frames_idx.csv` 的 tsNs 在同一 CLOCK_MONOTONIC 上
   （`meta.txt` 的 clock 行有说明；camera2 的 `camera2TsOffsetNs` 应 < 0.5s）。

不满足任何一条：数据作废，按 §2 重录。

## 6. 常见坑

- **构建成功 ≠ 安装成功**：`build.sh` 不带 `install` 参数只编译不安装。
- **install 成功 ≠ 版本正确**：装完不看 HUD 版本号 = 没装。
- **git pull 成功 ≠ LFS 成功**：网络不通时 frames.bin 只会是 3 行指针文件，
  `git lfs pull` 或换网络后再拉；分析前先看文件大小对不对（§5.3）。
- **服务器地址**：换电脑后手机上**长按屏幕**改 PC 局域网 IP；PC 防火墙放行 TCP 8000。
- **Windows 行尾**：本仓库 .gitattributes 未统一行尾，跨机器 diff 出 CRLF 差异属正常。
