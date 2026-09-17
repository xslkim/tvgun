"""共享数据结构与常量。所有模块的统一接口定义，勿随意修改。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

SEED = 20260916
SCREEN_W, SCREEN_H = 1920, 1080
FOV = 128          # 望远镜视场覆盖的屏幕像素边长
CAM_RES = 1024     # 相机输出分辨率（边长）
MARGIN = 16        # 解码校正时的边界余量（屏幕像素）

# 几何导频频率（cycles/px），与 SPEC.md 一致
PILOT_FREQS = [
    (1.0 / 6.0, 0.0),
    (0.0, 1.0 / 6.0),
    (1.0 / 8.485, 1.0 / 8.485),
    (1.0 / 8.485, -1.0 / 8.485),
]
PILOT_AMP = 0.8


@dataclass
class EmbedState:
    """嵌入端状态：解码端凭此重建信号。"""
    seed: int
    strength: float
    template: np.ndarray = field(repr=False)  # (H,W) float32, 含导频的完整信号
    screen_wh: tuple[int, int] = (SCREEN_W, SCREEN_H)


@dataclass
class ChannelConfig:
    """屏幕-相机信道参数。默认值 = 理想信道。"""
    rotation_deg: float = 0.0
    perspective_jitter: float = 0.0   # 四角扰动幅度，相机像素
    defocus_sigma: float = 0.0        # 高斯模糊 std，相机像素
    moire: bool = False               # 是否模拟 RGB 子像素发光结构
    moire_ss: int = 4                 # 摩尔纹仿真的超采样倍率
    noise_sigma: float = 0.0          # 加性高斯噪声（0~255）
    flicker_amp: float = 0.0          # 频闪亮带行增益幅度
    flicker_period: float = 32.0      # 亮带周期，相机像素
    gamma: float = 1.0
    jpeg_quality: int = 0             # 0 = 不压缩
    taa_jitter: float = 0.0           # 中心抖动 std，屏幕像素
    exposure_gain: float = 1.0
    cam_res: int = CAM_RES
    fov: int = FOV
    rng: Any = field(default=None, repr=False)  # 可选 np.random.Generator，用于相位等随机量
    # ---- 第二期扩展（SPEC2.md），默认关闭、旧行为不变 ----
    lens_k1: float = 0.0            # 径向畸变系数（桶形为负）
    lens_k2: float = 0.0
    motion_blur_px: float = 0.0     # 曝光内线速度总量，相机像素
    rs_skew_px: float = 0.0         # 卷帘快门全帧行向剪切总量，相机像素
    shot_noise: bool = False        # 低光照泊松散粒噪声
    shot_peak: float = 50.0         # 泊松噪声峰值（越小噪声越大）


@dataclass
class IMUPrior:
    """手机 IMU 提供给解码端的辅助先验（SPEC2.md §1）。available=False 等价于无先验。"""
    roll_deg: float = 0.0          # 相机相对屏幕的滚转角估计（含噪声/漂移）
    roll_std_deg: float = 1.5      # roll 估计的不确定度
    scale_hint: float = 0.0        # 0=无提示；否则为放大率提示（cam_res/fov 尺度）
    tilt_pitch_deg: float = 0.0    # 视线相对屏幕法线的俯仰/偏航估计（透视提示）
    tilt_yaw_deg: float = 0.0
    frame_deltas: list = field(default_factory=list)  # 多帧间中心位移估计 [(dx,dy), ...] 屏幕像素
    available: bool = True


@dataclass
class DecodeResult:
    x: float = 0.0            # 区域中心屏幕像素坐标
    y: float = 0.0
    confidence: float = 0.0   # 主峰/次峰响应比
    ok: bool = False          # confidence >= 1.3
    n_frames: int = 1
    debug: dict = field(default_factory=dict, repr=False)  # 可视化中间结果
