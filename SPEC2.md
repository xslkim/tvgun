# TVGun 仿真扩展规范（第二期：IMU + 移动端 + 扩展边界条件）

本文件是 SPEC.md 的补充，SPEC.md 全部接口继续有效。原则：向后兼容（新增参数都有默认值，旧调用方式行为不变）。

## 新增/扩展模块

```
sim/imu.py            # 新增：手持运动轨迹 + IMU 噪声模型 + 先验提取
scripts/run_mobile_bench.py  # 新增：手机 SoC 算力代理基准
scripts/run_boundary.py      # 新增：边界条件专项测试套件
```

## 1. IMU 仿真（sim/imu.py）

物理设定：望远镜 = 手机，用户手持对准屏幕缓慢移动。IMU（陀螺仪+加速度计，200Hz）提供三类辅助信息给解码端。

- `HandMotion`：确定性手持运动轨迹生成器（seed 可复现）。
  - `HandMotion(seed, duration_s=2.0, speed="slow"|"fast")`
  - 轨迹 = 慢速漂移（随机方向，slow: ~30 屏幕px/s, roll ~2°/s；fast: 3 倍）+ 手震（8~12Hz 带限噪声，幅度 slow 0.3px/0.1°，fast 1.5px/0.4°）。
  - `.sample(t) -> MotionState(center_x, center_y, roll_deg, tilt_pitch_deg, tilt_yaw_deg)`，tilt 缓慢变化 ±10° 内（slow）/±25°（fast）。
- `simulate_imu(motion, rate_hz=200, seed=...) -> IMUStream`：
  - 陀螺仪：白噪声 σ=0.02°/s + 偏置随机游走（初值 ±0.5°/s）+ 量化 0.01°/s；
  - 加速度计：白噪声 σ=0.05 m/s² + 偏置 ±0.02 m/s²；
  - IMU 坐标系与相机光轴存在小安装误差（随机 ±1° 固定旋转）。
  - `IMUStream.prior_at(t) -> IMUPrior`：对内部噪声积分后的估计值（非真值），roll 误差随时间漂移（10s 内 σ≤1.5°），tilt 由重力向量估计（σ≤0.8°），并给出 `frame_deltas`（由陀螺积分得到的帧间中心位移估计，含噪声）。
- `config.IMUPrior` 数据类（见 config.py）为 decode 的输入接口。

## 2. IMU 辅助解码（sim/decode.py 扩展）

- 签名扩展：`decode(camera_frames, state, screen_wh=(SCREEN_W,SCREEN_H), fov=FOV, imu_prior: IMUPrior|None=None) -> DecodeResult`。
- 有 imu_prior 时：
  1. 几何假设搜索从 {θ̂−45°,θ̂,θ̂+45°} + 微搜索 缩减为以 prior.roll_deg 为中心 ±3·roll_std_deg 的小搜索 → 加速并减少假峰仲裁失败；
  2. tilt 提示用于初始化透视残差迭代；
  3. 多帧时先用 frame_deltas 预对齐再累加（替代首帧对齐基准），消除手持漂移导致的累加模糊；
  4. prior 与 FFT 导频估计冲突时（差 > 4·roll_std_deg）信任导频（IMU 可能丢步），回退无先验路径。
- DecodeResult.debug 增加 `"imu_used": bool`。
- 自测：构造带噪 prior（roll 偏差 +1.2°），对比有/无 prior 的解码成功率与耗时，打印。

## 3. 信道扩展（sim/channel.py）

ChannelConfig 新增字段（默认=关闭，旧行为不变）：
- `lens_k1: float = 0.0, lens_k2: float = 0.0`：径向畸变（桶形 k1<0，典型 −0.15~−0.05），在 warp 后对相机图施加；decode 端 `_undistort` 用 (cam_res 内参 + k1,k2) 去畸变——decode 需增加可选参数 `lens: tuple|None` 或从 ChannelConfig 无法得知（仿真中 decode 假设已知畸变参数=已标定；另设"未标定"测试档：k1≠0 但不传镜头参数，量化精度损失）。
- `motion_blur_px: float = 0.0`：曝光内线速度（相机px/帧），沿随机方向做线性运动模糊核。
- `rs_skew_px: float = 0.0`：卷帘快门全帧行向剪切总量（相机px），逐行水平位移线性插值。
- `shot_noise: bool = False, shot_peak: float = 50.0`：低光照泊松散粒噪声（替代/叠加高斯噪声），配合 exposure_gain<1 模拟高 ISO。
- `sample_config` 新档位（旧四档不动）：
  - `"lowlight"`：medium 基础 + shot_noise(peak 20~60) + exposure_gain 0.5~0.8 + noise_sigma 2~5；
  - `"tele"`：fov=96（更高放大倍率）+ medium 其余参数；
  - `"wide"`：fov=256（低放大倍率，摩尔纹风险区）+ medium；
  - `"distort"`：medium + lens_k1∈[−0.15,−0.05]；
  - `"motion"`：fast 手持参数 + motion_blur_px 2~8 + rotation ±20°；
  - `"rolling"`：medium + rs_skew_px 4~20。

## 4. 动态场景（run_eval / channel 协作）

游戏画面逐帧变化是重要遗漏：多帧连拍时**内容在变、嵌入模板不变**。实现方式：评测端对视频序列的每一帧单独 embed_signal（同 seed → 同模板），逐帧 capture 后一起送 decode。data.py 新增：
- `generate_sequence(kind, seed, n_frames, fps=30) -> list[np.ndarray]`：程序化动画（game_scene/terrain/clouds 的时序版：视差滚动 + 云漂移 + HUD 数值变化），seed 可复现，相邻帧内容位移 1~6px。
- 真实视频帧（可选，下载失败优雅跳过）：`ensure_real_video_frames(out_dir, n=60)`，从 https://test-videos.co.uk 或类似稳定源拉一个短 mp4 抽帧 resize 到 1080p。
- data.py 新增内容类型（静态）：`"foliage"`（枝叶）、`"water"`（水面波纹）、`"text_ui"`（菜单/聊天文字界面）、`"map"`（俯视小地图风格）、`"crowd"`（密集人群剪影）、`"static_noise"`（雪花噪声）。

## 5. 边界条件专项套件（scripts/run_boundary.py）

固定内容集（≥4 种代表性内容）× 专项变量扫描，输出 out/boundary/report.md：
1. **屏幕边缘**：中心点距边缘 [8, 16, 32, 64]px（视场部分出屏，BORDER_REPLICATE 区域无信号），量化可用性边界；
2. **放大倍率**：fov ∈ {96, 128, 192, 256} × cam_res ∈ {512, 768, 1024} 网格；
3. **镜头畸变**：k1 ∈ {0, −0.05, −0.1, −0.15} × {已标定, 未标定}；
4. **低光照**：exposure_gain ∈ {0.3, 0.5, 0.8} × shot_peak ∈ {20, 50, 100}；
5. **运动**：motion_blur_px ∈ {0,2,4,8} × rs_skew_px ∈ {0,5,10,20}；
6. **动态场景**：generate_sequence 连拍 3 帧（内容位移 1~6px/帧）× {有IMU, 无IMU}；
7. **IMU 消融**：hard/extreme/motion 三档 × {无先验, IMU先验} 对比命中率与耗时。

## 6. 移动端基准（scripts/run_mobile_bench.py）

- 固定 `cv2.setNumThreads(1)` 模拟手机单核；报告 decode 耗时随 cam_res {512, 768, 1024}、单/三帧、有/无 IMU 的变化表（中位/P95 ms）。
- 优化目标：三帧 + IMU + cam_res 768 下中位 < 150ms（手机大核约桌面单核 1/2~1/3 性能，对应手机端 <300~450ms；若达不到，给出可行的裁剪：减小 FFT 尺寸、缩小相关搜索窗（有 prior 时只搜 ±32px）、降低迭代次数）。
- decode.py 可增加内部优化（不改变输出语义）：有 prior 时限制相关搜索范围、FFT 尺寸取 2 的幂附近快速尺寸等。

## 7. 评测扩展（run_eval.py / metrics.py）

- `--levels` 接受新档位名；新增 `--imu`（配合 HandMotion 轨迹驱动连续位置+先验注入，替代独立随机位置）与 `--dynamic`（序列帧模式）开关。
- metrics.summarize 增加分组列 `imu` 与 `dynamic`（存在时）。
- 最终报告写入 REPORT.md 新增章节（保留第一期数字不动，追加"第二期：IMU + 移动端 + 边界条件"）。

## 实现约束（同第一期）

- numpy/opencv/scipy/pandas/matplotlib，无深度学习框架；全部随机可 seed 复现。
- config.py 只允许"新增字段/数据类"，不得修改既有字段语义。
- 每个新模块/扩展附 __main__ 自测并实际跑通。
