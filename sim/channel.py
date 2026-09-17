"""屏幕-相机信道仿真：几何 warp + 摩尔纹 + 光度/噪声链。"""
from __future__ import annotations

import numpy as np
import cv2

try:
    from .config import ChannelConfig, SCREEN_W, SCREEN_H, FOV, CAM_RES
except ImportError:  # 支持 python3 sim/channel.py 直接运行自测
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim.config import ChannelConfig, SCREEN_W, SCREEN_H, FOV, CAM_RES


def _get_rng(cfg: ChannelConfig) -> np.random.Generator:
    return cfg.rng if cfg.rng is not None else np.random.default_rng()


def _geometry(cfg: ChannelConfig, center_xy, rng: np.random.Generator, scale: float = 1.0):
    """构造屏幕源四边形 -> 相机目标四边形（含旋转/透视扰动/taa 抖动）。

    scale 用于摩尔纹超采样时把两边坐标同步放大。
    返回 (src(4,2) float32, dst(4,2) float32, 抖动后中心 (cx, cy))。
    """
    cx = float(center_xy[0]) + (rng.normal(0, cfg.taa_jitter) if cfg.taa_jitter > 0 else 0.0)
    cy = float(center_xy[1]) + (rng.normal(0, cfg.taa_jitter) if cfg.taa_jitter > 0 else 0.0)
    half = cfg.fov / 2.0
    src = np.array([
        [cx - half, cy - half], [cx + half, cy - half],
        [cx + half, cy + half], [cx - half, cy + half],
    ], dtype=np.float64)

    # 目标：cam_res 正方形四角绕中心旋转，再叠加四角透视扰动（相机像素）
    ch = cfg.cam_res / 2.0
    dst = np.array([[-ch, -ch], [ch, -ch], [ch, ch], [-ch, ch]], dtype=np.float64)
    th = np.deg2rad(cfg.rotation_deg)
    rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    dst = dst @ rot.T + ch
    if cfg.perspective_jitter > 0:
        dst += rng.uniform(-cfg.perspective_jitter, cfg.perspective_jitter, size=(4, 2))

    return (src * scale).astype(np.float32), (dst * scale).astype(np.float32), (cx, cy)


def _moire_render(frame_u8: np.ndarray, cx: float, cy: float, cfg: ChannelConfig,
                  rng: np.random.Generator) -> np.ndarray:
    """局部 RGB 竖条子像素超采样渲染 -> warp -> INTER_AREA 降到 cam_res。"""
    ss = cfg.moire_ss
    half = cfg.fov / 2.0
    # 裁剪含旋转余量的局部区域，避免全帧超采样
    hc = int(np.ceil(half * np.sqrt(2.0))) + 3
    x0 = max(0, int(np.floor(cx - hc)))
    y0 = max(0, int(np.floor(cy - hc)))
    x1 = min(frame_u8.shape[1], int(np.ceil(cx + hc)))
    y1 = min(frame_u8.shape[0], int(np.ceil(cy + hc)))
    crop = frame_u8[y0:y1, x0:x1]

    up = cv2.resize(crop, None, fx=ss, fy=ss, interpolation=cv2.INTER_NEAREST).astype(np.float32)
    # 每屏幕像素横向均分 R/G/B 三条发光带。mask[j,c] = 子像素 j 与色带 c 的覆盖权重
    # （软边重叠分配，ss 不被 3 整除时每通道仍精确占 1/3，避免整数分条的通道偏色）
    j = np.arange(up.shape[1], dtype=np.float32) % ss
    lo, hi = j / ss, (j + 1) / ss
    mask = np.stack([
        np.clip(np.minimum(hi, (c + 1) / 3) - np.maximum(lo, c / 3), 0, None) * ss
        for c in range(3)
    ], axis=-1).astype(np.float32)
    up *= mask[None, :, :]

    src, dst, _ = _geometry(cfg, (cx, cy), rng, scale=float(ss))
    src = src - np.array([x0 * ss, y0 * ss], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    big = cv2.warpPerspective(up, M, (cfg.cam_res * ss, cfg.cam_res * ss),
                              flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # 子像素以通道值发光(≤255),相机 INTER_AREA 积分天然处理 1/3 占空比。
    # 不做额外的亮度补偿:若按占空比 ×3,条纹峰值会达 3×255,在后续 uint8 饱和中
    # 把条纹区(即几乎所有亮度>85的内容)的信号与内容一并削顶擦除。
    return cv2.resize(big, (cfg.cam_res, cfg.cam_res), interpolation=cv2.INTER_AREA)


def _lens_intrinsic(cam_res: int) -> np.ndarray:
    """按 cam_res 构造针孔内参：焦距取 1.2*cam_res（约 40° 视场），主点在中心。"""
    f = 1.2 * cam_res
    c = (cam_res - 1) / 2.0
    return np.array([[f, 0.0, c], [0.0, f, c], [0.0, 0.0, 1.0]], dtype=np.float64)


def _apply_lens_distort(img: np.ndarray, cfg: ChannelConfig) -> np.ndarray:
    """径向畸变（k1,k2）。

    initUndistortRectifyMap 的数学方向是：dst(i,j) = src(畸变投影点)，
    即"给定带畸变系数 dist 的观测图 -> 理想针孔图"。这正好是我们需要的
    前向算子（理想图 -> 带畸变观测图），因此直接拿来施加畸变。
    """
    K = _lens_intrinsic(cfg.cam_res)
    dist = np.array([cfg.lens_k1, cfg.lens_k2, 0.0, 0.0], dtype=np.float64)
    map1, map2 = cv2.initUndistortRectifyMap(
        K, dist, None, K, (cfg.cam_res, cfg.cam_res), cv2.CV_32FC1)
    return cv2.remap(img, map1, map2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _apply_motion_blur(img: np.ndarray, cfg: ChannelConfig, rng: np.random.Generator) -> np.ndarray:
    """随机方向线性运动模糊核（曝光内线速度 motion_blur_px 相机px/帧）。"""
    n = int(round(cfg.motion_blur_px)) + 1   # 核长（奇数化以保证居中对称）
    if n % 2 == 0:
        n += 1
    ang = rng.uniform(0.0, np.pi)            # 方向任意，[0,pi) 已覆盖直线朝向
    r = n // 2
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    on_line = np.abs(xx * np.sin(ang) - yy * np.cos(ang)) <= 0.5  # 距直线 <=0.5px
    in_seg = np.abs(xx * np.cos(ang) + yy * np.sin(ang)) <= r + 0.5
    k = (on_line & in_seg).astype(np.float32)
    k /= k.sum()
    return cv2.filter2D(img, -1, k, borderType=cv2.BORDER_REPLICATE)


def _apply_rs_skew(img: np.ndarray, cfg: ChannelConfig) -> np.ndarray:
    """卷帘快门：逐行水平剪切，全帧总量 rs_skew_px（顶行 -s/2 -> 底行 +s/2，居中无净位移）。"""
    h, w = cfg.cam_res, cfg.cam_res
    rows = np.arange(h, dtype=np.float32)
    shift = (rows / max(h - 1, 1) - 0.5) * cfg.rs_skew_px
    map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32), rows)
    map_x = map_x + shift[:, None]
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def capture(frame_wm_u8: np.ndarray, center_xy: tuple[float, float],
            cfg: ChannelConfig) -> np.ndarray:
    """模拟相机拍摄屏幕上以 center_xy 为中心的 fov×fov 区域，返回 (cam_res,cam_res,3) u8。"""
    rng = _get_rng(cfg)

    # --- 几何 + 摩尔纹 ---
    if cfg.moire:
        # taa 抖动在 _moire_render 内已消费；先算中心再渲染
        img = _moire_render(frame_wm_u8, float(center_xy[0]), float(center_xy[1]), cfg, rng)
    else:
        src, dst, _ = _geometry(cfg, center_xy, rng)
        M = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(frame_wm_u8.astype(np.float32), M,
                                  (cfg.cam_res, cfg.cam_res),
                                  flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # --- 第二期几何/时序效应：畸变 -> 运动模糊 -> 卷帘快门（默认全关，旧行为不变） ---
    if cfg.lens_k1 != 0.0 or cfg.lens_k2 != 0.0:
        img = _apply_lens_distort(img, cfg)
    if cfg.motion_blur_px > 0:
        img = _apply_motion_blur(img, cfg, rng)
    if cfg.rs_skew_px > 0:
        img = _apply_rs_skew(img, cfg)

    # --- 光度/噪声链：增益 -> 频闪亮带 -> 离焦 -> 伽马 -> 噪声 -> JPEG ---
    img = img * cfg.exposure_gain

    if cfg.flicker_amp > 0:
        phase = rng.uniform(0.0, cfg.flicker_period)
        rows = np.arange(cfg.cam_res, dtype=np.float32)
        gain = 1.0 + cfg.flicker_amp * np.sin(2.0 * np.pi * (rows + phase) / cfg.flicker_period)
        img = img * gain[:, None, None]

    if cfg.defocus_sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), cfg.defocus_sigma)

    if cfg.gamma != 1.0:
        img = np.power(np.clip(img, 0.0, 255.0) / 255.0, 1.0 / cfg.gamma) * 255.0

    if cfg.shot_noise:
        # 泊松散粒噪声：把亮度换算成光子计数（峰值 shot_peak 对应满幅 255），
        # 采样后换回来；配合 exposure_gain<1 时等效高 ISO，噪声占比更大
        img = rng.poisson(np.clip(img, 0.0, 255.0) / 255.0 * cfg.shot_peak) * (255.0 / cfg.shot_peak)
    if cfg.noise_sigma > 0:
        img = img + rng.normal(0.0, cfg.noise_sigma, size=img.shape)

    if cfg.jpeg_quality > 0:
        u8 = np.clip(img, 0, 255).astype(np.uint8)
        enc = cv2.imencode(".jpg", u8, [cv2.IMWRITE_JPEG_QUALITY, int(cfg.jpeg_quality)])[1]
        img = cv2.imdecode(enc, cv2.IMREAD_COLOR).astype(np.float32)

    return np.clip(img, 0, 255).astype(np.uint8)


# 档位边界表（与 SPEC.md 一致；单值参数视为上界，在 [0, 上界] 均匀采样）
_LEVEL_TABLE = {
    "easy":    dict(rot=1.0,  pj=0.0,  df=0.0, moire_p=0.0, noise=0.0, fl=0.0,  gamma=(1.0, 1.0),  jpeg=(0, 0),    taa=0.0, gain=(1.0, 1.0)),
    "medium":  dict(rot=5.0,  pj=4.0,  df=0.8, moire_p=0.5, noise=1.5, fl=0.03, gamma=(0.9, 1.1),  jpeg=(85, 100), taa=0.3, gain=(0.95, 1.05)),
    "hard":    dict(rot=15.0, pj=12.0, df=1.5, moire_p=1.0, noise=3.0, fl=0.08, gamma=(0.8, 1.25), jpeg=(60, 85),  taa=0.8, gain=(0.85, 1.15)),
    "extreme": dict(rot=30.0, pj=24.0, df=2.5, moire_p=1.0, noise=5.0, fl=0.15, gamma=(0.7, 1.4),  jpeg=(35, 60),  taa=1.5, gain=(0.7, 1.3)),
}


# 第二期新档位（SPEC2.md §3）：均在 medium 基础上叠加专项参数
_LEVEL_TABLE_V2 = ("lowlight", "tele", "wide", "distort", "motion", "rolling")


def _sample_config_v2(rng: np.random.Generator, level: str) -> ChannelConfig:
    """第二期档位：复用旧 medium 采样逻辑作基底，再覆盖专项参数。"""
    cfg = sample_config(rng, "medium")
    if level == "lowlight":     # 低光照：泊松散粒 + 欠曝 + 高斯噪声
        cfg.shot_noise = True
        cfg.shot_peak = float(rng.uniform(20.0, 60.0))
        cfg.exposure_gain = float(rng.uniform(0.5, 0.8))
        cfg.noise_sigma = float(rng.uniform(2.0, 5.0))
    elif level == "tele":       # 高放大倍率
        cfg.fov = 96
    elif level == "wide":       # 低放大倍率（摩尔纹风险区）
        cfg.fov = 256
    elif level == "distort":    # 桶形径向畸变
        cfg.lens_k1 = float(rng.uniform(-0.15, -0.05))
    elif level == "motion":     # 快速手持：运动模糊 + 大旋转
        cfg.motion_blur_px = float(rng.uniform(2.0, 8.0))
        cfg.rotation_deg = float(rng.uniform(-20.0, 20.0))
    elif level == "rolling":    # 卷帘快门剪切
        cfg.rs_skew_px = float(rng.uniform(4.0, 20.0))
    return cfg


def sample_config(rng: np.random.Generator, level: str) -> ChannelConfig:
    """按档位边界表均匀采样一组信道参数。"""
    if level in _LEVEL_TABLE_V2:
        return _sample_config_v2(rng, level)
    if level not in _LEVEL_TABLE:
        raise ValueError(f"unknown level: {level!r}, expect one of {list(_LEVEL_TABLE) + list(_LEVEL_TABLE_V2)}")
    p = _LEVEL_TABLE[level]
    return ChannelConfig(
        rotation_deg=float(rng.uniform(-p["rot"], p["rot"])),
        perspective_jitter=float(rng.uniform(0.0, p["pj"])),
        defocus_sigma=float(rng.uniform(0.0, p["df"])),
        moire=bool(rng.random() < p["moire_p"]),
        noise_sigma=float(rng.uniform(0.0, p["noise"])),
        flicker_amp=float(rng.uniform(0.0, p["fl"])),
        gamma=float(rng.uniform(*p["gamma"])),
        jpeg_quality=0 if p["jpeg"] == (0, 0) else int(rng.uniform(*p["jpeg"])),
        taa_jitter=float(rng.uniform(0.0, p["taa"])),
        exposure_gain=float(rng.uniform(*p["gain"])),
        rng=rng,
    )


if __name__ == "__main__":
    import os
    import time

    os.makedirs("out", exist_ok=True)
    rng = np.random.default_rng(42)

    # 渐变测试图：水平 R 渐变 + 垂直 G 渐变 + 棋盘细纹理
    yy, xx = np.mgrid[0:SCREEN_H, 0:SCREEN_W]
    frame = np.stack([
        xx / SCREEN_W * 255,
        yy / SCREEN_H * 255,
        ((xx // 4 + yy // 4) % 2) * 80 + 40,
    ], axis=-1).astype(np.uint8)

    tiles = []
    for level in ["easy", "medium", "hard", "extreme"]:
        cfg = sample_config(rng, level)
        t0 = time.perf_counter()
        img = capture(frame, (960.0, 540.0), cfg)
        dt = time.perf_counter() - t0
        assert img.shape == (cfg.cam_res, cfg.cam_res, 3), f"bad shape {img.shape}"
        assert img.dtype == np.uint8
        print(f"[{level:7s}] shape={img.shape} mean={img.mean():6.2f} std={img.std():6.2f} "
              f"moire={cfg.moire} rot={cfg.rotation_deg:+5.2f} jpeg={cfg.jpeg_quality} "
              f"time={dt * 1000:.0f}ms")
        tiles.append(cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA))

    collage = np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])
    cv2.imwrite("out/channel_test.png", cv2.cvtColor(collage, cv2.COLOR_RGB2BGR))
    print("saved out/channel_test.png", collage.shape)

    # ---- 第二期新档位：各 capture 一张，2x3 拼贴 ----
    tiles2 = []
    for level in _LEVEL_TABLE_V2:
        cfg = sample_config(rng, level)
        t0 = time.perf_counter()
        img = capture(frame, (960.0, 540.0), cfg)
        dt = time.perf_counter() - t0
        assert img.shape == (cfg.cam_res, cfg.cam_res, 3), f"bad shape {img.shape}"
        assert img.dtype == np.uint8
        print(f"[{level:7s}] shape={img.shape} mean={img.mean():6.2f} std={img.std():6.2f} "
              f"k1={cfg.lens_k1:+.3f} blur={cfg.motion_blur_px:4.2f} skew={cfg.rs_skew_px:5.2f} "
              f"shot={cfg.shot_noise} peak={cfg.shot_peak:4.1f} gain={cfg.exposure_gain:.2f} "
              f"fov={cfg.fov} time={dt * 1000:.0f}ms")
        tiles2.append(cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA))

    collage2 = np.vstack([np.hstack(tiles2[:3]), np.hstack(tiles2[3:])])
    cv2.imwrite("out/channel_test2.png", cv2.cvtColor(collage2, cv2.COLOR_RGB2BGR))
    print("saved out/channel_test2.png", collage2.shape)
