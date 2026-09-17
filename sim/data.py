"""画面生成与下载：程序化场景生成器、真实素材下载、真值位置采样。"""
from __future__ import annotations

import os
import urllib.request

import cv2
import numpy as np

from .config import SCREEN_W, SCREEN_H

W, H = SCREEN_W, SCREEN_H

KINDS = [
    "sky_gradient",
    "clouds",
    "terrain",
    "facade",
    "urban",
    "game_scene",
    "dark_scene",
    "bright_scene",
    # ---- 第二期新增（SPEC2.md §4）----
    "foliage",
    "water",
    "text_ui",
    "map",
    "crowd",
    "static_noise",
]

# 支持时序动画的内容类型（generate_sequence）
SEQ_KINDS = ["game_scene", "terrain", "clouds"]

PICSUM_URL = "https://picsum.photos/1920/1080?random={k}"


# ---------------------------------------------------------------- 工具

def _fbm(rng: np.random.Generator, octaves: int = 5, base_cells: int = 4,
         persistence: float = 0.5, size: tuple[int, int] | None = None) -> np.ndarray:
    """分形值噪声：逐倍频程生成低频随机栅格并三次插值上采样后加权叠加。

    size=(h, w) 可生成非全屏尺寸（供时序大画布用），默认 (H, W) 行为不变。
    """
    h, w = size if size is not None else (H, W)
    acc = np.zeros((h, w), np.float32)
    amp, total, cells = 1.0, 0.0, base_cells
    for _ in range(octaves):
        gh = max(2, int(cells * h / w) + 1)
        small = rng.random((gh, cells + 1), dtype=np.float32)
        up = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        acc += amp * up
        total += amp
        amp *= persistence
        cells *= 2
    return acc / total


def _to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img, 0, 255).astype(np.uint8)


def _lerp_rgb(a, b, t: np.ndarray) -> np.ndarray:
    """按标量场 t 在两颜色间插值，t shape (H,W) 或 (H,W,1)。"""
    if t.ndim == 2:
        t = t[..., None]
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    return a + (b - a) * t


# ---------------------------------------------------------------- 生成器

def _sky_gradient(rng) -> np.ndarray:
    # 近乎纯色的缓变天空：垂直渐变 + 极轻微水平/噪声扰动
    top = np.array([rng.uniform(120, 200), rng.uniform(150, 210), rng.uniform(200, 255)])
    bot = top * rng.uniform(0.75, 0.95) + rng.uniform(0, 20, 3)
    t = (np.arange(H, dtype=np.float32) / (H - 1)) ** rng.uniform(0.8, 1.4)
    img = _lerp_rgb(top, bot, t[:, None].repeat(W, axis=1))
    sway = 2.0 * np.sin(2 * np.pi * np.arange(W, dtype=np.float32) / W * rng.uniform(1, 3))
    img += sway[None, :, None] * rng.uniform(0.3, 0.8)
    img += rng.normal(0, 0.4, (H, W, 1))  # 残留微噪声，避免完全恒定
    return _to_u8(img)


def _clouds(rng) -> np.ndarray:
    # 分形云：fbm 标量场阈值化，蓝天->白云过渡
    n = _fbm(rng, octaves=6, base_cells=3)
    n = (n - n.min()) / (np.ptp(n) + 1e-6)
    t = np.clip((n - 0.35) / 0.45, 0, 1) ** 0.8
    img = _lerp_rgb((105, 160, 235), (245, 248, 252), t)
    shade = _fbm(rng, octaves=4, base_cells=6)
    img *= (0.85 + 0.3 * shade)[..., None]
    return _to_u8(img)


def _terrain(rng) -> np.ndarray:
    # 值噪声高度场 + 按高度分色带（水/沙/草/岩/雪）
    h = _fbm(rng, octaves=6, base_cells=5)
    h = (h - h.min()) / (np.ptp(h) + 1e-6)
    bands = [(0.30, (30, 80, 160)), (0.38, (200, 190, 140)),
             (0.62, (70, 140, 70)), (0.82, (110, 100, 95)),
             (1.01, (235, 240, 245))]
    img = np.zeros((H, W, 3), np.float32)
    prev, color = 0.0, bands[0][1]
    for hi, c in bands:
        mask = (h >= prev) & (h < hi)
        img[mask] = color
        prev, color = hi, c
    # 带内亮度随高度微调，增加纹理
    img *= (0.8 + 0.4 * h)[..., None]
    img += rng.normal(0, 1.5, (H, W, 1))
    return _to_u8(img)


def _facade(rng) -> np.ndarray:
    # 规则窗户网格：对抗性重复纹理
    base = np.array([rng.uniform(150, 210), rng.uniform(140, 190), rng.uniform(120, 170)])
    img = np.full((H, W, 3), base, np.float32)
    img += rng.normal(0, 1.0, (H, W, 1))
    win_w, win_h = 64, 84
    step_x, step_y = 120, 140
    off_x, off_y = 40, 30
    lit = rng.random(((H - off_y) // step_y + 1, (W - off_x) // step_x + 1))
    for r, y0 in enumerate(range(off_y, H - win_h, step_y)):
        for c, x0 in enumerate(range(off_x, W - win_w, step_x)):
            if lit[r, c] < 0.25:  # 部分窗亮灯
                col = (240, 220, 160)
            else:
                v = rng.uniform(35, 60)
                col = (v, v + 8, v + 18)
            cv2.rectangle(img, (x0, y0), (x0 + win_w, y0 + win_h), col, -1)
            cv2.rectangle(img, (x0, y0), (x0 + win_w, y0 + win_h),
                          tuple(base * 0.6), 3)
    # 楼层分隔线
    for y in range(off_y - 12, H, step_y):
        cv2.line(img, (0, y), (W, y), tuple(base * 0.8), 2)
    return _to_u8(img)


def _urban(rng) -> np.ndarray:
    # 城市街景：天空 + 楼群剪影（带窗点噪声）+ 路面
    horizon = int(H * rng.uniform(0.55, 0.7))
    img = _lerp_rgb((200, 170, 150), (120, 130, 150),
                    (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1))
    x = 0
    while x < W:  # 沿水平方向排列随机宽度/高度的楼体
        bw = int(rng.integers(120, 320))
        bh = int(rng.integers(int(H * 0.15), int(H * 0.45)))
        tone = rng.uniform(45, 95)
        col = (tone, tone + rng.uniform(-8, 8), tone + rng.uniform(-5, 15))
        y0 = horizon - bh
        cv2.rectangle(img, (x, y0), (min(x + bw, W), horizon), col, -1)
        # 窗点：楼体内随机亮/暗小格
        wx = rng.integers(x + 6, max(x + 7, min(x + bw, W) - 10),
                          size=int(bw * bh / 900))
        wy = rng.integers(y0 + 6, horizon - 10, size=wx.size)
        val = rng.uniform(0, 255, wx.size)
        img[wy, wx] = np.stack([val, val * 0.95, val * 0.8], 1)
        x += bw + int(rng.integers(0, 30))
    cv2.rectangle(img, (0, horizon), (W, H), (70, 70, 75), -1)  # 路面
    img += rng.normal(0, 3.0, (H, W, 1))  # 街景颗粒噪声
    return _to_u8(img)


def _game_scene(rng) -> np.ndarray:
    # 游戏画面：天空 + 远山地形 + HUD 元素
    img = _sky_gradient(rng).astype(np.float32)
    cloud = _fbm(rng, octaves=5, base_cells=3)
    t = np.clip((cloud - 0.45) / 0.4, 0, 1) * 0.6
    img = img * (1 - t[..., None]) + np.array((245, 248, 252)) * t[..., None]
    ground = _fbm(rng, octaves=5, base_cells=8)
    # 取一行并 1D 平滑，得到每列地平线高度
    g1d = cv2.GaussianBlur(ground[H // 2][None, :], (1, 61), 0).ravel()
    g1d = (g1d - g1d.mean()) / (np.ptp(g1d) + 1e-6)
    gy = (H * 0.62 + g1d * H * 0.25).astype(np.int32)
    for y in range(H):
        m = gy < y
        if not m.any():
            continue
        img[y, m, 0] = 70 + 40 * g1d[m]
        img[y, m, 1] = 115 + 45 * g1d[m]
        img[y, m, 2] = 55
    # HUD：血条、准星、右下角弹药框
    cv2.rectangle(img, (40, 40), (400, 80), (20, 20, 20), -1)
    cv2.rectangle(img, (46, 46), (46 + int(348 * rng.uniform(0.3, 1.0)), 74),
                  (60, 200, 80), -1)
    cx, cy = W // 2, H // 2
    cv2.drawMarker(img, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 41, 2)
    cv2.rectangle(img, (W - 300, H - 110), (W - 40, H - 40), (25, 25, 30), -1)
    cv2.putText(img, f"AMMO {int(rng.integers(0, 120)):03d}", (W - 280, H - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 230, 230), 2)
    return _to_u8(img)


def _dark_scene(rng) -> np.ndarray:
    # 夜景：低亮度渐变 + 星点 + 微光地面
    t = (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1)
    img = _lerp_rgb((8, 10, 22), (18, 22, 38), t)
    n_stars = int(rng.integers(200, 400))
    sx = rng.integers(0, W, n_stars)
    sy = rng.integers(0, int(H * 0.7), n_stars)
    img[sy, sx] = rng.uniform(120, 255, (n_stars, 1)) * np.array([1.0, 1.0, 0.95])
    glow = _fbm(rng, octaves=3, base_cells=2)
    img += (glow * 12)[..., None]  # 大范围微弱环境光
    img += rng.normal(0, 1.0, (H, W, 1))
    return _to_u8(np.clip(img, 0, 90))  # 压上限保持暗场


def _bright_scene(rng) -> np.ndarray:
    # 过曝倾向：高亮基底 + 缓变 + 太阳耀斑
    t = (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1)
    img = _lerp_rgb((250, 248, 240), (225, 235, 248), t)
    sun_x, sun_y = rng.uniform(W * 0.2, W * 0.8), rng.uniform(H * 0.1, H * 0.4)
    yy, xx = np.mgrid[0:H, 0:W]
    r2 = (xx - sun_x) ** 2 + (yy - sun_y) ** 2
    img += (255 * np.exp(-r2 / (2 * rng.uniform(120, 220) ** 2)))[..., None]
    img += rng.normal(0, 1.5, (H, W, 1))
    return _to_u8(np.clip(img, 190, 255))  # 抬下限保持亮场


def _foliage(rng) -> np.ndarray:
    # 枝叶：深绿背景 + 枝干线条 + 大量随机朝向椭圆叶片
    img = _lerp_rgb((30, 60, 35), (60, 110, 60),
                    (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1))
    for _ in range(int(rng.integers(6, 12))):  # 枝干
        x0, y0 = rng.uniform(0, W), rng.uniform(0, H)
        ang, ln = rng.uniform(0, 2 * np.pi), rng.uniform(200, 700)
        cv2.line(img, (int(x0), int(y0)),
                 (int(x0 + ln * np.cos(ang)), int(y0 + ln * np.sin(ang))),
                 (50, 40, 30), int(rng.integers(3, 9)))
    for _ in range(int(rng.integers(600, 1000))):  # 叶片
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        a = rng.uniform(8, 26)
        g = rng.uniform(90, 200)
        col = (g * rng.uniform(0.3, 0.6), g, g * rng.uniform(0.25, 0.5))
        cv2.ellipse(img, (int(cx), int(cy)), (int(a), int(a * rng.uniform(0.35, 0.6))),
                    rng.uniform(0, 180), 0, 360, col, -1)
    img += rng.normal(0, 1.5, (H, W, 1))
    return _to_u8(img)


def _water(rng) -> np.ndarray:
    # 水面波纹：蓝色渐变底 + 多组不同方向/波长的正弦行波调制亮度 + 高光闪点
    yy, xx = np.mgrid[0:H, 0:W]
    xx, yy = xx.astype(np.float32), yy.astype(np.float32)
    img = _lerp_rgb((20, 60, 120), (40, 120, 180), (yy / H)[..., None])
    warp = _fbm(rng, 4, 6) * 0.15  # 相位扰动，让波纹自然弯曲
    bright = np.zeros((H, W), np.float32)
    for _ in range(int(rng.integers(4, 7))):
        kx, ky = rng.uniform(-1, 1, 2)
        norm = np.hypot(kx, ky) + 1e-6
        lam = rng.uniform(40, 160)
        bright += np.sin(2 * np.pi * (kx * xx + ky * yy) / (lam * norm)
                         + rng.uniform(0, 2 * np.pi) + warp)
    img += (bright / max(abs(bright).max(), 1e-6) * 18)[..., None]
    glint = _fbm(rng, 5, 8)  # 阈值化高光闪点
    img += (np.clip((glint - 0.62) / 0.1, 0, 1) * 140)[..., None]
    return _to_u8(img)


def _text_ui(rng) -> np.ndarray:
    # 菜单/聊天文字界面：暗色底 + 顶部标题栏 + 菜单列表（含选中项）+ 聊天框
    t = (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1)
    img = _lerp_rgb((30, 34, 44), (22, 26, 34), t)
    img += (_fbm(rng, 4, 6) * 18)[..., None]  # 背景微纹理
    letters = np.array(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))

    def word(n: int) -> str:
        return "".join(rng.choice(letters, size=int(n)))

    cv2.rectangle(img, (0, 0), (W, 100), (15, 17, 22), -1)
    cv2.putText(img, "MAIN MENU", (60, 68), cv2.FONT_HERSHEY_SIMPLEX,
                1.6, (240, 240, 245), 3)
    sel = int(rng.integers(0, 6))
    for i in range(6):  # 左侧菜单条目
        y0 = 200 + i * 90
        if i == sel:
            cv2.rectangle(img, (50, y0 - 52), (700, y0 + 20), (70, 120, 200), -1)
        cv2.putText(img, word(rng.integers(4, 10)), (80, y0),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                    (245, 245, 245) if i == sel else (170, 175, 185), 2)
    # 底部聊天框：多行彩色玩家消息 + 输入行光标
    cv2.rectangle(img, (50, H - 360), (1000, H - 60), (12, 14, 18), -1)
    cv2.rectangle(img, (50, H - 360), (1000, H - 60), (80, 85, 95), 2)
    palette = [(120, 200, 255), (255, 200, 120), (160, 255, 160), (255, 160, 200)]
    for i in range(5):
        name = f"{word(3)}{int(rng.integers(10, 99))}"
        msg = " ".join(word(rng.integers(2, 8)) for _ in range(int(rng.integers(3, 7))))
        cv2.putText(img, f"{name}: {msg}", (70, H - 318 + i * 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    palette[int(rng.integers(0, len(palette)))], 2)
    cv2.putText(img, "> " + word(6) + "|", (70, H - 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (230, 230, 230), 2)
    # 右侧滚动条
    cv2.rectangle(img, (W - 70, 180), (W - 50, H - 400), (60, 64, 72), -1)
    th0 = int(rng.integers(200, H - 600))
    cv2.rectangle(img, (W - 68, th0), (W - 52, th0 + 120), (150, 155, 165), -1)
    return _to_u8(img)


def _map(rng) -> np.ndarray:
    # 俯视小地图：地形色底 + 水域 + 道路折线网 + 网格 + 地标 + 玩家三角 + 指北针
    h = _fbm(rng, 5, 5)
    h = (h - h.min()) / (np.ptp(h) + 1e-6)
    img = _lerp_rgb((90, 140, 80), (190, 180, 130), h)  # 低海拔绿 -> 高海拔棕
    img[h < 0.28] = (60, 110, 190)  # 水域
    for _ in range(int(rng.integers(4, 8))):  # 道路：随机游走折线
        pts = [(rng.uniform(0, W), rng.uniform(0, H))]
        ang = rng.uniform(0, 2 * np.pi)
        for _ in range(int(rng.integers(4, 9))):
            ang += rng.normal(0, 0.5)
            px, py = pts[-1]
            ln = rng.uniform(120, 320)
            pts.append((px + ln * np.cos(ang), py + ln * np.sin(ang)))
        cv2.polylines(img, [np.array(pts, np.int32)], False,
                      (200, 190, 160), int(rng.integers(4, 9)))
    overlay = img.copy()  # 半透明网格线
    for gx in range(0, W, 160):
        cv2.line(overlay, (gx, 0), (gx, H), (255, 255, 255), 1)
    for gy in range(0, H, 160):
        cv2.line(overlay, (0, gy), (W, gy), (255, 255, 255), 1)
    img = cv2.addWeighted(img, 0.85, overlay, 0.15, 0)
    for _ in range(int(rng.integers(10, 20))):  # 地标：蓝圈 / 黄方块
        mx, my = int(rng.uniform(60, W - 60)), int(rng.uniform(60, H - 60))
        if rng.random() < 0.5:
            cv2.circle(img, (mx, my), 14, (80, 140, 240), 3)
        else:
            cv2.rectangle(img, (mx - 12, my - 12), (mx + 12, my + 12),
                          (240, 210, 80), 3)
    px, py = int(rng.uniform(W * 0.3, W * 0.7)), int(rng.uniform(H * 0.3, H * 0.7))
    tri = np.array([(px, py - 22), (px - 16, py + 16), (px + 16, py + 16)], np.int32)
    cv2.fillPoly(img, [tri], (240, 60, 60))  # 玩家位置红三角
    cv2.rectangle(img, (8, 8), (W - 8, H - 8), (230, 230, 230), 6)
    cv2.arrowedLine(img, (W - 90, 130), (W - 90, 60), (240, 240, 240), 4, tipLength=0.35)
    cv2.putText(img, "N", (W - 104, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (240, 240, 240), 3)
    return _to_u8(img)


def _crowd(rng) -> np.ndarray:
    # 密集人群剪影：暖色舞台光背景 + 由远及近多排人形剪影（近大远小透视）
    t = (np.arange(H, dtype=np.float32) / H)[:, None].repeat(W, 1)
    img = _lerp_rgb((235, 200, 150), (180, 120, 90), t)
    img *= (0.85 + 0.3 * _fbm(rng, 3, 2))[..., None]
    y = H * 0.32
    while y < H + 80:
        ph = 30 + 130 * (y - H * 0.3) / (H * 0.7)  # 人高随排数（透视）增大
        x = rng.uniform(-20, 20)
        gap = ph * rng.uniform(0.55, 0.8)
        while x < W + 20:
            tone = rng.uniform(15, 60)
            col = (tone, tone * rng.uniform(0.8, 1.0), tone * rng.uniform(0.9, 1.2))
            # 躯干椭圆 + 头部圆
            cv2.ellipse(img, (int(x), int(y - 0.4 * ph)),
                        (int(0.30 * ph), int(0.42 * ph)), 0, 0, 360, col, -1)
            cv2.circle(img, (int(x), int(y - 0.82 * ph)), max(2, int(0.15 * ph)), col, -1)
            x += gap * rng.uniform(0.85, 1.25)
        y += ph * 0.5
    img += rng.normal(0, 2.0, (H, W, 1))
    return _to_u8(img)


def _static_noise(rng) -> np.ndarray:
    # 电视雪花：逐像素均匀噪声 + 少量彩色噪点 + 水平撕裂亮带
    img = rng.uniform(0, 255, (H, W, 1)).astype(np.float32).repeat(3, axis=2)
    img += rng.normal(0, 10, (H, W, 3))
    for _ in range(int(rng.integers(3, 8))):
        y0 = int(rng.integers(0, H - 4))
        img[y0:y0 + int(rng.integers(1, 4))] += rng.uniform(30, 80)
    return _to_u8(img)


_GENERATORS = {
    "sky_gradient": _sky_gradient,
    "clouds": _clouds,
    "terrain": _terrain,
    "facade": _facade,
    "urban": _urban,
    "game_scene": _game_scene,
    "dark_scene": _dark_scene,
    "bright_scene": _bright_scene,
    "foliage": _foliage,
    "water": _water,
    "text_ui": _text_ui,
    "map": _map,
    "crowd": _crowd,
    "static_noise": _static_noise,
}


# ---------------------------------------------------------------- 公开 API

def generate_frame(kind: str, seed: int) -> np.ndarray:
    """生成 (1080,1920,3) uint8 RGB 画面，同 (kind, seed) 逐比特可复现。"""
    if kind not in _GENERATORS:
        raise ValueError(f"未知 kind: {kind!r}, 可选: {KINDS}")
    rng = np.random.default_rng(seed)
    frame = _GENERATORS[kind](rng)
    assert frame.shape == (H, W, 3) and frame.dtype == np.uint8
    return frame


def ensure_real_frames(out_dir: str, n: int = 12) -> list[str]:
    """从 picsum.photos 下载 n 张 1920×1080 真实图；失败跳过，已存在复用。

    n 支持到 24（第二期扩量），picsum 按 random 参数返回不同图。
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for k in range(n):
        path = os.path.join(out_dir, f"real_{k:02d}.jpg")
        if not os.path.exists(path):
            try:
                req = urllib.request.Request(
                    PICSUM_URL.format(k=k), headers={"User-Agent": "tvgun-sim"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                buf = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img is None or img.shape[0] < 100:
                    raise ValueError("下载内容不是有效图像")
                with open(path, "wb") as f:
                    f.write(data)
            except Exception as e:  # 网络失败跳过并记录
                print(f"[data] 下载 real_{k:02d} 失败，跳过: {e}")
                continue
        paths.append(path)
    return paths


# ---------------------------------------------------------------- 时序动画（第二期）

def _seq_steps(rng: np.random.Generator, n_frames: int) -> np.ndarray:
    """逐帧位移增量 (n_frames-1, 2) int：方向缓慢转向，相邻帧步长保证 1~6px。"""
    steps = np.zeros((max(n_frames - 1, 0), 2), np.int32)
    ang = rng.uniform(0, 2 * np.pi)
    for i in range(steps.shape[0]):
        ang += rng.normal(0, 0.35)  # 运动方向缓变，模拟连续镜头
        for _ in range(100):
            mag = rng.uniform(1.0, 6.0)
            dx, dy = int(round(mag * np.cos(ang))), int(round(mag * np.sin(ang)))
            if 1.0 <= np.hypot(dx, dy) <= 6.0:
                break
        else:
            dx, dy = 2, 0
        steps[i] = (dx, dy)
    return steps


def _seq_offsets(rng: np.random.Generator, n_frames: int) -> np.ndarray:
    """累计位移轨迹 (n_frames, 2) int，平移到非负（作为大画布裁剪原点）。"""
    off = np.vstack([np.zeros((1, 2), np.int32),
                     np.cumsum(_seq_steps(rng, n_frames), axis=0)])
    return off - off.min(axis=0)


def _canvas_size(off: np.ndarray, extra: float = 1.0, mg: int = 8) -> tuple[int, int]:
    """按最大位移 span 计算大画布尺寸 (cw, ch)，extra 为视差层速度倍率上限。"""
    span = off.max(axis=0) if len(off) else np.zeros(2, np.int32)
    cw = W + int(np.ceil(span[0] * extra)) + 2 * mg
    ch = H + int(np.ceil(span[1] * extra)) + 2 * mg
    return cw, ch


def _seq_clouds(seed: int, n_frames: int, fps: float) -> list[np.ndarray]:
    # 云漂移：天空底 0.2 倍缓漂 + 远/近两层分形云 0.5/1.0 倍漂移，形成视差
    rng = np.random.default_rng(seed)
    off = _seq_offsets(rng, n_frames)
    cw, ch = _canvas_size(off)
    p = rng.uniform(0.9, 1.3)
    t = (np.arange(ch, dtype=np.float32) / (ch - 1)) ** p
    sky = _lerp_rgb((115, 165, 235), (195, 215, 242), t[:, None].repeat(cw, 1))
    far = _fbm(rng, 5, 3, size=(ch, cw))
    near = _fbm(rng, 6, 4, size=(ch, cw))
    near2 = _fbm(rng, 6, 4, size=(ch, cw))   # 形变目标场：云随时间缓慢演化
    fine = _fbm(rng, 4, 48, size=(ch, cw))   # 高频边缘细节，使小位移可测
    frames = []
    for i in range(n_frames):
        sx, sy = np.round(off[i] * 0.2).astype(int) + 8
        fx, fy = np.round(off[i] * 0.5).astype(int) + 8
        nx, ny = off[i] + 8
        img = sky[sy:sy + H, sx:sx + W].copy()
        tf = np.clip((far[fy:fy + H, fx:fx + W] - 0.40) / 0.45, 0, 1) ** 0.9 * 0.5
        img = img * (1 - tf[..., None]) + np.array((238, 244, 250)) * tf[..., None]
        a = min(0.5, 0.06 * i)  # 云形变权重随时间增长
        nf = (1 - a) * near[ny:ny + H, nx:nx + W] + a * near2[ny:ny + H, nx:nx + W]
        nf = nf + 0.25 * (fine[ny:ny + H, nx:nx + W] - 0.5)
        tn = np.clip((nf - 0.38) / 0.42, 0, 1) ** 0.8
        img = img * (1 - tn[..., None]) + np.array((250, 251, 253)) * tn[..., None]
        frames.append(_to_u8(img))
    return frames


def _seq_terrain(seed: int, n_frames: int, fps: float) -> list[np.ndarray]:
    # 地形滚动：整幅大画布 1.0 倍平移 + 云影层 1.5 倍漂移（视差）
    rng = np.random.default_rng(seed)
    off = _seq_offsets(rng, n_frames)
    cw, ch = _canvas_size(off)
    h = _fbm(rng, 6, 5, size=(ch, cw))
    h = (h - h.min()) / (np.ptp(h) + 1e-6)
    bands = [(0.30, (30, 80, 160)), (0.38, (200, 190, 140)),
             (0.62, (70, 140, 70)), (0.82, (110, 100, 95)),
             (1.01, (235, 240, 245))]
    img_big = np.zeros((ch, cw, 3), np.float32)
    prev = 0.0
    for hi, c in bands:
        img_big[(h >= prev) & (h < hi)] = c
        prev = hi
    img_big *= (0.8 + 0.4 * h)[..., None]
    # 高频地表细节，使小位移在内容上可见可测
    img_big *= (0.82 + 0.36 * _fbm(rng, 4, 96, size=(ch, cw)))[..., None]
    scw, sch = _canvas_size(off, extra=1.5)
    shadow = _fbm(rng, 4, 4, size=(sch, scw))
    frames = []
    for i in range(n_frames):
        img = img_big[8 + off[i, 1]:8 + off[i, 1] + H,
                      8 + off[i, 0]:8 + off[i, 0] + W].copy()
        sx, sy = np.round(off[i] * 1.5).astype(int) + 8
        dark = np.clip((shadow[sy:sy + H, sx:sx + W] - 0.55) / 0.2, 0, 1) * 0.35
        img *= (1 - dark)[..., None]
        frames.append(_to_u8(img))
    return frames


def _seq_game_scene(seed: int, n_frames: int, fps: float) -> list[np.ndarray]:
    # 游戏场景：天空固定 + 云层 0.5 倍视差 + 远山地面 1.0 倍滚动 + HUD 数值逐帧变化
    rng = np.random.default_rng(seed)
    off = _seq_offsets(rng, n_frames)
    cw, ch = _canvas_size(off)
    top = np.array([rng.uniform(120, 200), rng.uniform(150, 210), rng.uniform(200, 255)])
    bot = top * rng.uniform(0.75, 0.95)
    tcol = (np.arange(H, dtype=np.float32) / (H - 1))[:, None].repeat(W, 1)
    sky = _lerp_rgb(top, bot, tcol)
    sun_x, sun_y = rng.uniform(W * 0.2, W * 0.8), rng.uniform(H * 0.08, H * 0.3)
    yy, xx = np.mgrid[0:H, 0:W]
    sky += (200 * np.exp(-((xx - sun_x) ** 2 + (yy - sun_y) ** 2)
                         / (2 * rng.uniform(100, 180) ** 2)))[..., None]
    cloud = _fbm(rng, 5, 3, size=(ch, cw))
    # 远山 1D 剖面（宽度覆盖大画布），地面逐帧按剖面重建
    ground = _fbm(rng, 5, 8, size=(64, cw))
    g1d = cv2.GaussianBlur(ground[32][None, :], (1, 61), 0).ravel()
    g1d = (g1d - g1d.mean()) / (np.ptp(g1d) + 1e-6)
    gy0 = H * 0.62 + g1d * H * 0.25
    # 地表纹理（随地面同步滚动）：低频起伏 + 高频细颗粒，保证 1~6px 位移可见可测
    detail = 0.55 * _fbm(rng, 5, 24, size=(ch, cw)) \
        + 0.45 * _fbm(rng, 4, 128, size=(ch, cw))
    hp = rng.uniform(0.5, 1.0)          # HUD 初值
    hp_rate = rng.uniform(0.002, 0.01)
    ammo0 = int(rng.integers(60, 240))
    ys = np.arange(H, dtype=np.float32)[:, None]
    frames = []
    for i in range(n_frames):
        ox, oy = off[i]
        cx, cy = np.round(off[i] * 0.5).astype(int) + 8
        img = sky.copy()
        tc = np.clip((cloud[cy:cy + H, cx:cx + W] - 0.45) / 0.4, 0, 1) * 0.6
        img = img * (1 - tc[..., None]) + np.array((245, 248, 252)) * tc[..., None]
        # 地面：水平随 ox 取剖面、垂直随 oy 平移，叠加同步滚动的地表纹理
        gy = gy0[8 + ox:8 + ox + W] + oy
        shade = g1d[8 + ox:8 + ox + W]
        ground_col = np.stack([70 + 40 * shade, 115 + 45 * shade,
                               np.full_like(shade, 55)], axis=1)
        below = (ys > gy[None, :])[..., None]
        img = np.where(below, np.broadcast_to(ground_col, (H, W, 3)), img)
        tex = (0.65 + 0.7 * detail[8 + oy:8 + oy + H, 8 + ox:8 + ox + W])[..., None]
        img = np.where(below, img * tex, img)
        # HUD：固定于屏幕，血条/弹药/计时逐帧变化
        el = i / fps
        cv2.rectangle(img, (40, 40), (400, 80), (20, 20, 20), -1)
        cv2.rectangle(img, (46, 46), (46 + int(348 * max(0.05, hp - hp_rate * i)), 74),
                      (60, 200, 80), -1)
        cv2.drawMarker(img, (W // 2, H // 2), (255, 255, 255), cv2.MARKER_CROSS, 41, 2)
        cv2.rectangle(img, (W - 300, H - 110), (W - 40, H - 40), (25, 25, 30), -1)
        cv2.putText(img, f"AMMO {max(0, ammo0 - 3 * i):03d}", (W - 280, H - 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 230, 230), 2)
        cv2.putText(img, f"{int(el // 60):02d}:{el % 60:04.1f}", (W // 2 - 70, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        frames.append(_to_u8(img))
    return frames


_SEQ_GENERATORS = {
    "game_scene": _seq_game_scene,
    "terrain": _seq_terrain,
    "clouds": _seq_clouds,
}


def generate_sequence(kind: str, seed: int, n_frames: int, fps: float = 30) -> list[np.ndarray]:
    """生成 n_frames 帧时序动画（SEQ_KINDS），相邻帧内容位移 1~6px，seed 可复现。"""
    if kind not in _SEQ_GENERATORS:
        raise ValueError(f"kind {kind!r} 不支持时序生成, 可选: {SEQ_KINDS}")
    if n_frames < 1:
        raise ValueError(f"n_frames 必须 >= 1, 收到 {n_frames}")
    frames = _SEQ_GENERATORS[kind](seed, n_frames, fps)
    for f in frames:
        assert f.shape == (H, W, 3) and f.dtype == np.uint8
    return frames


# ---------------------------------------------------------------- 真实视频帧（第二期）

VIDEO_URLS = [
    "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4",
    "https://test-videos.co.uk/vids/jellyfish/mp4/h264/720/Jellyfish_720_10s_1MB.mp4",
    "https://test-videos.co.uk/vids/sintel/mp4/h264/720/Sintel_720_10s_1MB.mp4",
]


def ensure_real_video_frames(out_dir: str, n: int = 60) -> list[str]:
    """从稳定源下载短 mp4，均匀抽 n 帧 resize 到 1920×1080 存 jpg。

    下载/解码失败优雅跳过，返回已下载部分（可能为空列表）；已存在则复用。
    """
    os.makedirs(out_dir, exist_ok=True)
    want = [os.path.join(out_dir, f"vid_{k:03d}.jpg") for k in range(n)]
    if all(os.path.exists(p) for p in want):
        return want
    src = os.path.join(out_dir, "video_src.mp4")
    if not os.path.exists(src):
        for url in VIDEO_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tvgun-sim"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                if len(data) < 10_000:
                    raise ValueError(f"内容过小({len(data)}B)，非有效视频")
                with open(src, "wb") as f:
                    f.write(data)
                break
            except Exception as e:  # 网络失败换下一个源
                print(f"[data] 视频下载失败 {url}: {e}")
        if not os.path.exists(src):
            print("[data] 全部视频源不可用，跳过")
            return [p for p in want if os.path.exists(p)]
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print("[data] 视频文件无法解码，跳过")
        return [p for p in want if os.path.exists(p)]
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total // n) if total > 0 else 1
    got, fi = [], 0
    ok, frame = cap.read()
    while ok and len(got) < n:
        if fi % step == 0:
            img = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)
            path = want[len(got)]
            cv2.imwrite(path, img)
            got.append(path)
        fi += 1
        ok, frame = cap.read()
    cap.release()
    if len(got) < n:
        print(f"[data] 视频可用帧不足，仅抽取 {len(got)}/{n} 帧")
    return got


def sample_positions(rng: np.random.Generator, n: int, margin: int = 96) -> np.ndarray:
    """均匀采样 n 个合法区域中心点，返回 (n,2) float，列序 (x, y)。"""
    xs = rng.uniform(margin, SCREEN_W - margin, n)
    ys = rng.uniform(margin, SCREEN_H - margin, n)
    return np.stack([xs, ys], axis=1)


# ---------------------------------------------------------------- 自测

if __name__ == "__main__":
    out_dir = os.path.join("out", "data")
    os.makedirs(out_dir, exist_ok=True)

    NEW_KINDS = ["foliage", "water", "text_ui", "map", "crowd", "static_noise"]

    def _tile(img: np.ndarray, label: str) -> np.ndarray:
        t = cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA)
        cv2.putText(t, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 0, 0), 3)
        cv2.putText(t, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (255, 255, 255), 1)
        return t

    def _collage(tiles: list[np.ndarray], cols: int) -> np.ndarray:
        rows = -(-len(tiles) // cols)
        tiles = tiles + [np.zeros_like(tiles[0])] * (rows * cols - len(tiles))
        return np.vstack([np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows)])

    # ---- 静态内容：全部 KINDS（含第二期新增 6 种）----
    tiles = []
    print(f"{'kind':<14} {'min':>4} {'max':>4} {'mean':>8} {'std':>8}")
    for kind in KINDS:
        f1 = generate_frame(kind, seed=123)
        f2 = generate_frame(kind, seed=123)
        f3 = generate_frame(kind, seed=456)
        assert f1.shape == (H, W, 3) and f1.dtype == np.uint8
        assert 0 <= f1.min() and f1.max() <= 255
        assert np.array_equal(f1, f2), f"{kind} 同 seed 不可复现"
        assert not np.array_equal(f1, f3), f"{kind} 换 seed 无变化"
        print(f"{kind:<14} {f1.min():>4} {f1.max():>4} "
              f"{f1.mean():>8.2f} {f1.std():>8.2f}")
        tiles.append(_tile(f1, kind))

    collage = _collage(tiles, 4)
    path = os.path.join(out_dir, "preview.png")
    cv2.imwrite(path, cv2.cvtColor(collage, cv2.COLOR_RGB2BGR))
    print(f"拼贴图已保存: {path} {collage.shape}")

    # ---- 第二期：时序序列（5 帧，位移与内容变化验证）----
    tiles2 = [_tile(generate_frame(k, 123), k) for k in NEW_KINDS]
    for kind in SEQ_KINDS:
        seq = generate_sequence(kind, seed=7, n_frames=5)
        seq_rep = generate_sequence(kind, seed=7, n_frames=5)
        assert all(np.array_equal(a, b) for a, b in zip(seq, seq_rep)), \
            f"{kind} 序列同 seed 不可复现"
        seq_alt = generate_sequence(kind, seed=8, n_frames=5)
        assert not np.array_equal(seq[0], seq_alt[0]), f"{kind} 序列换 seed 无变化"
        print(f"[{kind}] 5 帧序列:")
        for i in range(1, len(seq)):
            assert not np.array_equal(seq[i - 1], seq[i]), f"{kind} 相邻帧无变化"
            d16 = seq[i].astype(np.int16) - seq[i - 1].astype(np.int16)
            diff = float(np.abs(d16).mean())
            # 模板区域（128×128 网格块）内容变化取最大
            gmax = max(float(np.abs(d16[gy:gy + 128, gx:gx + 128]).mean())
                       for gy in range(0, H - 127, 128)
                       for gx in range(0, W - 127, 128))
            # 相位相关测下半画面位移（避开 game_scene 固定 HUD；加窗抑制边缘效应）
            a = cv2.cvtColor(seq[i - 1][H // 2:], cv2.COLOR_RGB2GRAY).astype(np.float32)
            b = cv2.cvtColor(seq[i][H // 2:], cv2.COLOR_RGB2GRAY).astype(np.float32)
            win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
            (dx, dy), _ = cv2.phaseCorrelate(a, b, win)
            mag = float(np.hypot(dx, dy))
            assert diff > 0.1, f"{kind} 相邻帧全帧变化过小: {diff}"
            assert gmax > 1.0, f"{kind} 模板区域内容无变化: {gmax}"
            assert 0.3 <= mag <= 8.0, f"{kind} 相邻帧位移越界: {mag}"
            print(f"  帧{i - 1}->{i}: 全帧均差={diff:6.2f} 最大块差={gmax:6.2f} "
                  f"位移=({dx:+5.1f},{dy:+5.1f}) |{mag:.2f}px|")
        tiles2 += [_tile(f, f"{kind}#{i}") for i, f in enumerate(seq)]
        tiles2.append(np.zeros_like(tiles2[0]))  # 凑齐 6 列

    collage2 = _collage(tiles2, 6)
    path2 = os.path.join(out_dir, "preview2.png")
    cv2.imwrite(path2, cv2.cvtColor(collage2, cv2.COLOR_RGB2BGR))
    print(f"第二期拼贴图已保存: {path2} {collage2.shape}")

    # ---- 真实素材下载（网络失败优雅跳过，不作为硬性断言）----
    real = ensure_real_frames(out_dir, n=24)
    print(f"ensure_real_frames(n=24): {len(real)}/24 张可用")
    vid = ensure_real_video_frames(os.path.join(out_dir, "video"), n=5)
    print(f"ensure_real_video_frames(n=5): {len(vid)}/5 帧可用")

    rng = np.random.default_rng(0)
    pos = sample_positions(rng, 1000)
    assert pos.shape == (1000, 2)
    assert pos[:, 0].min() >= 96 and pos[:, 0].max() <= W - 96
    assert pos[:, 1].min() >= 96 and pos[:, 1].max() <= H - 96
    print(f"sample_positions: 1000 点 x∈[{pos[:,0].min():.1f},{pos[:,0].max():.1f}] "
          f"y∈[{pos[:,1].min():.1f},{pos[:,1].max():.1f}]")
    print("自测全部通过")
