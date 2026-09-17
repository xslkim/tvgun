# TVGun 仿真验证项目 — 接口规范（所有实现必须严格遵守）

## 目标

软件仿真验证"屏幕坐标定位"系统：
1. 生成/获取 1920×1080 游戏画面帧；
2. 在帧上叠加人眼不可察觉的伪随机定位信号（嵌入端）；
3. 模拟"望远镜"相机拍摄屏幕局部区域（屏幕-相机信道：重采样/旋转/透视/摩尔纹/频闪/噪声/模糊/压缩）；
4. 从相机画面解码出所拍区域在屏幕上的像素坐标（解码端）；
5. 大规模评测矩阵 + 端到端 Demo。

## 目录结构

```
sim/
  __init__.py
  config.py      # 共享数据结构与常量（已存在，勿改）
  data.py        # 画面生成与下载
  embed.py       # 定位模板生成与嵌入
  channel.py     # 屏幕-相机信道仿真
  decode.py      # 坐标解码
  metrics.py     # 误差指标与汇总
scripts/
  run_demo.py    # 端到端 Demo（可视化）
  run_eval.py    # 批量评测矩阵 -> CSV + 报告
out/             # 生成的数据、结果、可视化
```

## 核心设计（已定，勿偏离）

### 嵌入信号（embed.py）
- **定位模板**：确定性随机相位带通场。用固定 seed 的 RNG 在频域生成：空间频率范围对应周期 4~24 屏幕像素的环形带通，随机相位、幅度 1，逆 FFT 取实部，归一化为零均值、std=1，shape (1080, 1920) float32。同 seed 必然逐比特可复现。
- **几何导频**：4 组正弦光栅，频率（cycles/px）：
  `(1/6, 0)`, `(0, 1/6)`, `(1/8.485, 1/8.485)`(即45°、周期6), `(1/8.485, -1/8.485)`，
  每组幅度 0.8（在模板 std=1 的同一尺度上）。导频在 FFT 幅度谱上形成可检测尖峰，供解码端估计缩放+旋转。
- **合成信号**：`signal = template + Σ pilot_gratings`，归一化使 template 部分 std=1。
- **感知加权嵌入**：亮度域嵌入。局部对比度掩模 `m = clip(0.45 + local_std/25, 0.45, 1.6)`（local_std 用 9×9 高斯窗口在 Y 通道上估计），平坦区域减小幅值保持不可见。`frame_wm = frame + strength * m * signal`（加到 Y 通道，再回 RGB），strength 默认 2.5（0~255 灰度级）。
- API:
  - `generate_template(seed: int = SEED) -> np.ndarray  # (1080,1920) float32, 零均值 std≈1`
  - `embed_signal(frame_u8: np.ndarray, strength: float = 2.5, seed: int = SEED) -> tuple[np.ndarray, EmbedState]`
  - `get_signal(state: EmbedState) -> np.ndarray  # (1080,1920) float32 含导频的完整信号`

### 信道仿真（channel.py）
模拟相机拍摄屏幕上一块 fov×fov（默认 128×128）屏幕像素的区域：
- 几何：区域中心 center_xy（屏幕像素，float）。目标相机图 cam_res×cam_res（默认 1024）。基础放大率 = cam_res/fov。叠加 rotation_deg、四角透视扰动（perspective_jitter，单位：相机像素，默认 0）、taa_jitter（中心在屏幕域的高斯抖动 std，屏幕像素）。用 cv2.getPerspectiveTransform + warpPerspective 从全帧 warp 出相机图。
- 摩尔纹（moire=True 时）：先把全帧按 moire_ss 倍超采样并模拟 RGB 竖条子像素发光结构（每屏幕像素横向分成 R/G/B 三条），再做上述 warp，最后 INTER_AREA 降到 cam_res。注意性能：只对 fov 区域周边做局部超采样渲染，不要对全帧超采样。
- 光度/噪声：exposure_gain 增益 → 频闪亮带 flicker（行向增益 `1 + flicker_amp*sin(2π(row+phase)/flicker_period)`，phase 随机）→ 高斯模糊 defocus_sigma（相机像素）→ 伽马 `out = in^(1/gamma)`（gamma≠1 时）→ 高斯噪声 noise_sigma → JPEG（jpeg_quality>0 时，cv2 编解码一次）→ 裁剪 uint8。
- API:
  - `capture(frame_wm_u8: np.ndarray, center_xy: tuple[float,float], cfg: ChannelConfig) -> np.ndarray  # (cam_res,cam_res,3) u8`
  - `sample_config(rng: np.random.Generator, level: str) -> ChannelConfig  # level ∈ {"easy","medium","hard","extreme"}`，各档位参数范围在 config.py 注释给定的边界内随机（见下）。

档位边界（sample_config 在这些范围内均匀采样）：
| 参数 | easy | medium | hard | extreme |
|---|---|---|---|---|
| rotation_deg | ±1 | ±5 | ±15 | ±30 |
| perspective_jitter(px) | 0 | 4 | 12 | 24 |
| defocus_sigma(cam px) | 0 | 0.8 | 1.5 | 2.5 |
| moire | False | 50% | True | True |
| noise_sigma | 0 | 1.5 | 3.0 | 5.0 |
| flicker_amp | 0 | 0.03 | 0.08 | 0.15 |
| gamma | 1.0 | 0.9~1.1 | 0.8~1.25 | 0.7~1.4 |
| jpeg_quality | 0(off) | 85 | 60 | 35 |
| taa_jitter(screen px) | 0 | 0.3 | 0.8 | 1.5 |
| exposure_gain | 1.0 | 0.95~1.05 | 0.85~1.15 | 0.7~1.3 |

### 解码（decode.py）
输入相机图（或多帧 list）、EmbedState，输出区域中心的屏幕坐标。流水线：
1. 转灰度（绿色通道为主）、去镜头畸变（本仿真不模拟畸变，留接口即可）。
2. **几何同步**：对相机灰度图做 FFT，在导频预期半径附近检测峰值 → 估计缩放因子与旋转角（至少用到水平/垂直两个导频；对 ±30° 旋转与 ±15% 缩放鲁棒）。构建相似变换把相机图 warp 回"屏幕像素网格"（1 相机图 → fov×fov 屏幕像素 + margin 16px，即输出 (fov+32)²）。
3. **透视残差修正（可选迭代）**：把校正图分成 2×2 子块，各自与模板对应区域做相位相关得到 4 个残差位移 → 拟合单应细化。实现 getPerspectiveTransform + warp 后重估。最多迭代 2 次。
4. **绝对定位**：校正后的局部图与全局信号 get_signal(state) 做 FFT 互相关（cv2.matchTemplate TM_CCOEFF_NORMED 或相位相关），峰值位置给出该区域在屏幕上的坐标 → 换算为中心坐标 (x, y)。抛物线插值做亚像素。
5. 置信度 = 峰值响应 / 次峰响应（排除主峰邻域 8px）。
6. 多帧：几何同步后逐帧校正、累加平均再相关。
- API:
  - `decode(camera_frames, state: EmbedState, screen_wh=(SCREEN_W, SCREEN_H), fov=FOV) -> DecodeResult`
  - DecodeResult.x/y 为区域中心的屏幕像素坐标（float）；confidence float；ok=True/False（confidence<1.3 判 False）。

### 数据（data.py）
- 程序化生成器 `generate_frame(kind: str, seed: int) -> np.ndarray (1080,1920,3) u8 RGB`，KINDS 至少包含：
  `"sky_gradient"`（纯色+缓变，对抗性低纹理）、`"clouds"`（分形云）、`"terrain"`（值噪声地形+色带）、`"facade"`（重复窗户阵列，对抗性重复纹理）、`"urban"`（城市街景风格噪声）、`"game_scene"`（地形+天空+HUD元素合成）、`"dark_scene"`（夜景，低亮度）、`"bright_scene"`（过曝倾向）。全部确定性（seed 可复现）。
- 真实素材 `ensure_real_frames(out_dir: str, n: int = 12) -> list[str]`：从 picsum.photos（`https://picsum.photos/1920/1080?random=k`）下载 n 张，失败跳过并记录；保存到 out_dir，返回路径列表（已存在则直接复用）。
- 真值标注工具 `sample_positions(rng, n, margin=96)`：屏幕上均匀随机采样合法中心点。

### 评测（metrics.py + scripts/run_eval.py）
- metrics.py: `coord_error(true_xy, est_xy) -> float`；`summarize(df: pandas.DataFrame) -> str` 输出 markdown 表格：按 content × level 分组的 top-1 命中率（err≤1px）、err≤4px 率、中位/P95 误差、失败率（err>16 或 ok=False）、平均解码耗时。
- run_eval.py: 参数 `--levels easy,medium,hard,extreme --positions 40 --frames-per-case 1 --out out/eval`。对每个 (content × level × position) 用独立 seed 跑 embed→capture→decode，记录 true/est/error/confidence/耗时/各信道参数 到 results.csv；生成 report.md（markdown 汇总 + 失败案例可视化图存 out/eval/failures/）。内容集 = 全部 KINDS + 下载成功的真实图。支持 `--quick`（positions=8, 仅 easy+hard）。
- 多帧模式：`--frames-per-case 3` 时对同一位置连拍 3 帧（不同 flicker 相位/噪声/taa_jitter）一起送入 decode。

### Demo（scripts/run_demo.py）
单命令端到端：`python scripts/run_demo.py --kind game_scene --level medium [--x 960 --y 540] [--frames 3] --out out/demo`。
输出：终端打印真值坐标、解码坐标、误差、置信度、耗时；保存一张合成可视化 PNG（2×3 面板：原图、嵌入残差×20 放大、嵌入后画面、相机拍到的图、几何校正后的图、相关峰热力图+结论文字）。位置缺省时随机。退出码：误差≤1px 为 0。

## 实现约束
- 只用 numpy / opencv-python(-headless) / scipy / pandas / matplotlib / pillow，不引入深度学习框架（torch 已装但本项目不需要）。
- 所有随机性必须可 seed 复现。
- 每个模块文件内附 `if __name__ == "__main__":` 自测段，能独立跑通自己的核心功能。
- 不要在 config.py 之外定义共享常量；接口签名以本规范与 config.py 为准。
