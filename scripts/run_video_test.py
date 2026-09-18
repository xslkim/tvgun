#!/usr/bin/env python3
"""离线闭环验证：手机光枪准星坐标识别正确性。

任务 1：忠实复刻 android/src/com/tvgun/gun/Detector.java 的检测管线
  （灰度降采样到 320 宽 -> 98 分位自适应阈值 clamp [190,254] -> 双阈值滞后连通：
   低阈值=max(150, hi*0.75) 掩模上做 4 连通域，域内需 >=30 个高阈值种子像素，
   取最大保留域且 >=0.8% 画面 -> 域内 argmin/argmax(x+-y) 四极值点 + ±2px 质心细化
   -> TL/TR/BR/BL -> 几何校验（对边角差 <10°、宽高比 max/min ∈ [1.2,2.6]）
   -> 指数平滑 alpha=0.3 -> 连续 3 帧失败才失锁 -> 4 点单应
   -> 帧中心映射为规范坐标 1920x1080）。
  与 Java 版的已知差异（均不影响算法语义）：
    * 灰度来源：Java 取 NV21 Y 平面；这里用 cv2.cvtColor(BGR2GRAY)，同为 BT.601
      亮度，系数一致，差异仅在解码器色度上采样的舍入。
    * 降采样：与 Java 完全相同的隔行/列抽样（step=w//320=3，取每块左上角像素），
      而非 resize 的 area 平均。
    * 连通域：Java 手写 flood-fill（4 连通）；这里用 cv2.connectedComponentsWithStats
      (connectivity=4)，等价。
    * 单应求解：Java 手写 8x8 高斯消元（h33=1）；这里用 cv2.getPerspectiveTransform，
      数值上等价。
    * 视频无旋转，rotation=0 分支。

任务 2：逐帧 CSV / 统计 / 网格反投影标注图 / 鸭子轨迹对照 / 外角点偏差量化。

任务 3：真闭环。把每帧 cross 以约 15Hz POST 到电视端 /aim，PIL.ImageGrab 截屏，
  在截图中找青色 (RGB≈(0,255,255)) 准星质心，与 run_tv.py norm_to_px 几何算出的
  期望屏幕位置比较，阈值 40px。

用法:
  python scripts/run_video_test.py [--skip-live] [--video test_res/screen_video.mp4]
                                   [--tv http://192.168.3.19:8000] [--rate 15]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

NORM_W, NORM_H = 1920.0, 1080.0
TARGET_W = 320
ALPHA = 0.3
MIN_AREA_FRAC = 0.02   # 四边形面积占比（检测图）
MIN_BLOB_FRAC = 0.008  # 最大连通域像素占比
MIN_EDGE = 20.0
MAX_MISSES = 3
# 双阈值滞后连通（与 Detector.java 同步）：低阈值掩模做连通域，域内需 >=30 个高阈值种子
LOW_THR_RATIO = 0.75
LOW_THR_MIN = 150
MIN_SEED_HI = 30
# 四边形几何校验：对边方向角差 <10°，宽高比 max/min ∈ [1.2, 2.6]
MAX_OPP_EDGE_ANG = np.deg2rad(10)
MIN_ASPECT, MAX_ASPECT = 1.2, 2.6

# run_tv.py 几何常量（边框内边距比例 / 厚度），用于外角点偏差修正与闭环期望位置
MARGIN_RATIO = 0.04
BORDER_THICK = 24
TV_WIN_W, TV_WIN_H = 1920, 1080  # run_tv.py --size 默认值


# ---------------------------------------------------------------- 检测器复刻

class Detector:
    """Detector.java 的 Python 复刻（检测图坐标系 = 原图 // step）。"""

    def __init__(self):
        self.smooth: np.ndarray | None = None
        self.miss_count = 0
        self.locked = False
        self.last_fail = 0          # 0=ok 1=blob太小 2=无极值 3=四边形非法 4=单应失败 5=几何校验拒绝
        self.last_thr = 0
        self.last_low_thr = 0
        self.last_best_count = 0
        self.corners = np.zeros(8)  # TL,TR,BR,BL，检测图坐标
        self.cross = np.zeros(2)
        self.cross_valid = False
        self.H: np.ndarray | None = None  # 检测图 -> 规范坐标
        self.det_w = self.det_h = self.step = 0

    def _miss(self, stage: int):
        self.last_fail = stage
        self.miss_count += 1
        if self.smooth is None or self.miss_count >= MAX_MISSES:
            self.locked = False
            self.cross_valid = False
            self.smooth = None
            self.miss_count = 0

    @staticmethod
    def _refine(labels, best, dw, dh, cx, cy):
        j0, j1 = max(0, cy - 2), min(dh - 1, cy + 2)
        i0, i1 = max(0, cx - 2), min(dw - 1, cx + 2)
        win = labels[j0:j1 + 1, i0:i1 + 1]
        ys, xs = np.nonzero(win == best)
        if len(xs) == 0:
            return float(cx), float(cy)
        return float(xs.mean() + i0), float(ys.mean() + j0)

    @staticmethod
    def _valid(c, dw, dh):
        pts = c.reshape(4, 2)
        area = 0.0
        for i in range(4):
            j = (i + 1) % 4
            area += pts[i, 0] * pts[j, 1] - pts[j, 0] * pts[i, 1]
        if abs(area) / 2 < MIN_AREA_FRAC * dw * dh:
            return False
        for i in range(4):
            j = (i + 1) % 4
            if np.hypot(*(pts[j] - pts[i])) < MIN_EDGE:
                return False
        return True

    @staticmethod
    def _geo_valid(c):
        """几何校验（与 Detector.java geoValid 同步）：对边近平行 + 宽高比在包络内。"""
        tl, tr, br, bl = c.reshape(4, 2)

        def ang(p, q):
            return np.arctan2(q[1] - p[1], q[0] - p[0])

        def ang_diff(a, b):
            d = (a - b) % np.pi
            return d - np.pi if d > np.pi / 2 else (d + np.pi if d < -np.pi / 2 else d)

        if abs(ang_diff(ang(tl, tr), ang(bl, br))) > MAX_OPP_EDGE_ANG:
            return False
        if abs(ang_diff(ang(tl, bl), ang(tr, br))) > MAX_OPP_EDGE_ANG:
            return False
        w_avg = (np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2
        h_avg = (np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2
        if w_avg <= 0 or h_avg <= 0:
            return False
        aspect = max(w_avg, h_avg) / min(w_avg, h_avg)
        return MIN_ASPECT <= aspect <= MAX_ASPECT

    def process(self, frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        step = max(1, w // TARGET_W)
        g = gray[::step, ::step]  # 与 Java 相同的抽样（每块左上角）
        dh, dw = g.shape
        self.det_w, self.det_h, self.step = dw, dh, step
        n = dw * dh

        hist = np.bincount(g.ravel(), minlength=256)
        need = int(n * 0.02) + 1
        acc, thr = 0, 255
        for v in range(255, -1, -1):
            acc += int(hist[v])
            if acc >= need:
                thr = v
                break
        thr = min(max(thr, 190), 254)
        self.last_thr = thr
        low_thr = max(LOW_THR_MIN, int(thr * LOW_THR_RATIO))
        self.last_low_thr = low_thr

        # 低阈值掩模上做 4 连通域；域内须含 >= MIN_SEED_HI 个高阈值种子像素才保留
        mask = (g >= low_thr).astype(np.uint8)
        nlab, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        if nlab > 1:
            hi_counts = np.bincount(labels[g >= thr].ravel(), minlength=nlab)
            cand = [i for i in range(1, nlab) if hi_counts[i] >= MIN_SEED_HI]
            if cand:
                best = max(cand, key=lambda i: stats[i, cv2.CC_STAT_AREA])
                best_count = int(stats[best, cv2.CC_STAT_AREA])
            else:
                best, best_count = 0, 0
        else:
            best, best_count = 0, 0
        self.last_best_count = best_count
        if best_count < int(MIN_BLOB_FRAC * n):
            self._miss(1)
            return

        ys, xs = np.nonzero(labels == best)  # 行主序，与 Java k 序一致（ties 取先出现者）
        if len(xs) == 0:
            self._miss(2)
            return
        s = xs + ys
        d = xs - ys
        # TL=argmin(x+y) TR=argmax(x-y) BR=argmax(x+y) BL=argmin(x-y)
        k_tl, k_br = int(np.argmin(s)), int(np.argmax(s))
        k_tr, k_bl = int(np.argmax(d)), int(np.argmin(d))
        raw = np.array([
            *self._refine(labels, best, dw, dh, xs[k_tl], ys[k_tl]),
            *self._refine(labels, best, dw, dh, xs[k_tr], ys[k_tr]),
            *self._refine(labels, best, dw, dh, xs[k_br], ys[k_br]),
            *self._refine(labels, best, dw, dh, xs[k_bl], ys[k_bl]),
        ], dtype=np.float64)

        if not self._valid(raw, dw, dh):
            self._miss(3)
            return
        if not self._geo_valid(raw):
            self._miss(5)
            return

        self.miss_count = 0
        self.last_fail = 0
        if self.smooth is None:
            self.smooth = raw.copy()
        else:
            self.smooth += ALPHA * (raw - self.smooth)
        self.corners = self.smooth.copy()

        dst = np.array([[0, 0], [NORM_W, 0], [NORM_W, NORM_H], [0, NORM_H]], np.float32)
        H = cv2.getPerspectiveTransform(self.corners.reshape(4, 2).astype(np.float32),
                                        dst).astype(np.float64)
        if H is None:
            self._miss(4)
            return
        self.H = H
        self.locked = True
        self.cross = map_point(H, dw / 2, dh / 2)
        self.cross_valid = bool(0 <= self.cross[0] <= NORM_W and 0 <= self.cross[1] <= NORM_H)


def map_point(H, x, y):
    p = H @ np.array([x, y, 1.0])
    return p[:2] / p[2]


# ---------------------------------------------------------------- 鸭子检测

def detect_duck(frame_bgr):
    """HSV 黄色掩模 -> 最大连通域质心（原图坐标），无则 None。"""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (15, 100, 120), (40, 255, 255))
    nlab, labels, stats, cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if nlab <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < 100:
        return None
    return float(cent[i][0]), float(cent[i][1])


# ---------------------------------------------------------------- 标注图

def annotate_frame(frame, det, cross, duck_px, duck_norm, path):
    img = frame.copy()
    step = det.step
    Hinv = np.linalg.inv(det.H)

    def to_px(nx, ny):
        return map_point(Hinv, nx, ny) * step

    # 规范坐标网格反投影（每 240x135 一格）
    for gx in np.arange(0, NORM_W + 1, 240):
        pts = np.array([to_px(gx, gy) for gy in np.arange(0, NORM_H + 1, 15)], np.int32)
        cv2.polylines(img, [pts], False, (0, 255, 0), 1, cv2.LINE_AA)
    for gy in np.arange(0, NORM_H + 1, 135):
        pts = np.array([to_px(gx, gy) for gx in np.arange(0, NORM_W + 1, 20)], np.int32)
        cv2.polylines(img, [pts], False, (0, 255, 0), 1, cv2.LINE_AA)
    for nx, ny, name in ((0, 0, "(0,0)"), (NORM_W, 0, "(1920,0)"),
                         (NORM_W, NORM_H, "(1920,1080)"), (0, NORM_H, "(0,1080)")):
        px = to_px(nx, ny).astype(int)
        cv2.putText(img, name, tuple(px + [4, -4]), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (0, 255, 0), 1, cv2.LINE_AA)

    # 检测四边形（外角点）与角点标签
    q = (det.corners.reshape(4, 2) * step).astype(np.int32)
    cv2.polylines(img, [q], True, (0, 0, 255), 1, cv2.LINE_AA)
    for (x, y), name in zip(q, ("TL", "TR", "BR", "BL")):
        cv2.circle(img, (x, y), 2, (0, 0, 255), -1)
        cv2.putText(img, name, (x + 3, y + 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (0, 0, 255), 1, cv2.LINE_AA)

    # 帧中心准星 + 规范坐标标注
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(img, (cx - 12, cy), (cx + 12, cy), (255, 255, 0), 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 12), (cx, cy + 12), (255, 255, 0), 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 8, (255, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(img, f"cross=({cross[0]:.1f},{cross[1]:.1f})", (cx + 14, cy - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA)

    # 鸭子质心
    if duck_px is not None:
        cv2.circle(img, (int(duck_px[0]), int(duck_px[1])), 6, (255, 0, 255), 1, cv2.LINE_AA)
        if duck_norm is not None:
            cv2.putText(img, f"duck=({duck_norm[0]:.0f},{duck_norm[1]:.0f})",
                        (int(duck_px[0]) + 8, int(duck_px[1]) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), img)


# ---------------------------------------------------------------- 闭环（任务 3）

def tv_norm_to_px(x, y):
    """run_tv.py norm_to_px（--size 1920x1080 默认几何）。"""
    m = int(round(min(TV_WIN_W, TV_WIN_H) * MARGIN_RATIO))
    x0 = m + BORDER_THICK
    y0 = m + BORDER_THICK
    px = x0 + x / NORM_W * (TV_WIN_W - 2 * x0)
    py = y0 + y / NORM_H * (TV_WIN_H - 2 * y0)
    return px, py


def find_ring(a):
    """在截图（RGB ndarray）中找白色边框环的外包围盒 (c0, r0, c1, r1)，找不到返回 None。

    校验：宽高比 ≈ 1857/1047（1920x1080 窗口边框环，等比缩放不变）、
    环内大部分为近黑像素（游戏黑底）——避免把对话框/网页等亮块误判为游戏窗口。
    """
    white = (a[..., 0] > 240) & (a[..., 1] > 240) & (a[..., 2] > 240)
    rowsum = white.sum(axis=1)
    colsum = white.sum(axis=0)
    if rowsum.max() < 500 or colsum.max() < 300:
        return None
    rows = np.where(rowsum > 0.5 * rowsum.max())[0]
    cols = np.where(colsum > 0.5 * colsum.max())[0]
    c0, r0, c1, r1 = int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())
    w, h = c1 - c0, r1 - r0
    if w < 600 or h < 300 or not 1.55 < w / h < 2.0:
        return None
    inner = a[r0 + 60:r1 - 60, c0 + 60:c1 - 60]
    if inner.size == 0 or (inner.mean(axis=2) < 15).mean() < 0.3:
        return None
    return c0, r0, c1, r1


def ring_mapping(ring):
    """由边框环外包围盒推 窗口px -> 屏幕px 的仿射映射。

    cv2.rectangle 粗线以几何边为中心（实测：m=43, 半厚 12 -> 外边在窗口 px 31），
    环外包围盒对应窗口坐标 [m-12, w-m-1+12] x [m-12, h-m-1+12]。
    """
    c0, r0, c1, r1 = ring
    m = int(round(min(TV_WIN_W, TV_WIN_H) * MARGIN_RATIO))
    half = BORDER_THICK // 2
    wx0, wx1 = m - half, TV_WIN_W - m - 1 + half
    wy0, wy1 = m - half, TV_WIN_H - m - 1 + half
    sx = (c1 - c0) / (wx1 - wx0)
    sy = (r1 - r0) / (wy1 - wy0)
    def to_screen(wx, wy):
        return c0 + (wx - wx0) * sx, r0 + (wy - wy0) * sy
    return to_screen


def cyan_centroid(a, ring):
    """截图中青色准星中心（限制在边框环内，避免桌面图标干扰）。

    run_tv.py 会在准星右上画 cyan 坐标文字，直接求质心/行投影会被文字拉偏。
    准星 = 圆 + 过圆心的十字线（线长 4*AIM_R）。定位方法：
    1) 列投影峰值 -> 垂直线所在列 cx（垂直线每列 ~4*AIM_R px，文字列远矮）；
    2) 只在 cx ±12px 的窄带内做行投影 -> 水平线所在行 cy
       （文字从 cx + AIM_R + 6 窗口px 处才开始，进不了窄带）。
    """
    c0, r0, c1, r1 = ring
    sub = a[max(r0, 0):r1 + 1, max(c0, 0):c1 + 1]
    cyan = (sub[..., 0] < 100) & (sub[..., 1] > 180) & (sub[..., 2] > 180)
    n = int(cyan.sum())
    if n < 20:
        return None, n
    colsum = cyan.sum(axis=0)
    cols = np.where(colsum > 0.5 * colsum.max())[0]
    cx = float(cols.mean())
    cx0 = int(round(cx))
    band = cyan[:, max(0, cx0 - 12):cx0 + 13]
    rowsum = band.sum(axis=1)
    if rowsum.max() < 8:
        return None, n
    rows = np.where(rowsum > 0.5 * rowsum.max())[0]
    cy = float(rows.mean())
    return (cx + max(c0, 0), cy + max(r0, 0)), n


def http_json(url, body=None, timeout=5.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def raise_tv_window(topmost: bool = True) -> bool:
    """Windows：把名为 TVGun 的 cv2 窗口抬到前台/顶层（截屏需要它可见）。

    后台进程创建的窗口受 Windows 焦点限制，裸 SetForegroundWindow 会被拒；
    用 AttachThreadInput 挂接到当前前台线程 + Alt 键事件绕过限制，
    再 SetWindowPos(HWND_TOPMOST) 保持置顶（测试结束用 topmost=False 恢复）。
    """
    if sys.platform != "win32":
        return False
    import ctypes
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, "TVGun")
    if not hwnd:
        return False
    if topmost:
        k32 = ctypes.windll.kernel32
        fg = u.GetForegroundWindow()
        cur_tid = k32.GetCurrentThreadId()
        fg_tid = u.GetWindowThreadProcessId(fg, None)
        tgt_tid = u.GetWindowThreadProcessId(hwnd, None)
        u.AttachThreadInput(cur_tid, fg_tid, True)
        u.AttachThreadInput(cur_tid, tgt_tid, True)
        u.keybd_event(0x12, 0, 0, 0)  # Alt down
        u.ShowWindow(hwnd, 9)         # SW_RESTORE
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        u.keybd_event(0x12, 0, 2, 0)  # Alt up
        u.AttachThreadInput(cur_tid, fg_tid, False)
        u.AttachThreadInput(cur_tid, tgt_tid, False)
    u.SetWindowPos(hwnd, -1 if topmost else -2, 0, 0, 0, 0,
                   0x0001 | 0x0002 | 0x0010)  # NOSIZE|NOMOVE|NOACTIVATE
    return True


def run_live(df, out_dir, tv_url, rate, max_samples=100):
    from PIL import ImageGrab

    # 1. 确认电视端在线；不在线则本地后台启动（与 run_tv.py 默认参数一致）
    spawned = None
    try:
        http_json(f"{tv_url}/state", timeout=3.0)
        print(f"[live] TV server already running at {tv_url}")
    except Exception:
        print(f"[live] {tv_url} unreachable, spawning scripts/run_tv.py ...")
        spawned = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_tv.py"), "--port", "8000", "--seed", "42"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                http_json(f"{tv_url}/state", timeout=1.0)
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("[live] FAIL: TV server did not come up")
            return None

    # 2. 确认游戏画面可被截到（全屏边框环可见）；窗口可能被用户窗口遮挡，轮询等待
    def wait_ring(timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            a = np.array(ImageGrab.grab())
            ring = find_ring(a)
            if ring is not None:
                return a, ring
            time.sleep(0.5)
        return a, None

    a, ring = wait_ring(5.0)
    if ring is None and raise_tv_window(True):
        print("[live] raised TVGun window to topmost via win32")
        a, ring = wait_ring(10.0)
    if ring is None and spawned is not None:
        print("[live] fullscreen window not capturable, restarting with --windowed")
        spawned.terminate()
        spawned.wait(timeout=5)
        spawned = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_tv.py"), "--port", "8000",
             "--seed", "42", "--windowed"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        a = np.array(ImageGrab.grab())
        ring = find_ring(a)
    if ring is None:
        print("[live] FAIL: game border ring not visible in screen grab")
        return None
    gh, gw = a.shape[:2]
    fullscreen = ring[0] < 0.05 * gw and ring[2] > 0.95 * gw
    print(f"[live] grab {gw}x{gh}, ring outer bbox={ring}, "
          f"{'fullscreen' if fullscreen else 'windowed'} mode")
    to_screen = ring_mapping(ring)

    # 3. 以约 rate Hz 推送 cross 并截屏断言（均匀抽样 max_samples 个，缩短前台占用时间）
    rows = df[df["locked"] & df["cross_valid"]].reset_index(drop=True)
    if max_samples and len(rows) > max_samples:
        rows = rows.iloc[np.linspace(0, len(rows) - 1, max_samples).astype(int)]
    period = 1.0 / rate
    recs = []
    t_start = time.monotonic()
    prev_aim = None
    for i, row in rows.iterrows():
        t0 = time.monotonic()
        x, y = float(row["cross_x"]), float(row["cross_y"])
        try:
            http_json(f"{tv_url}/aim", {"x": x, "y": y}, timeout=2.0)
        except Exception as e:
            print(f"[live] POST /aim failed at frame {int(row['frame'])}: {e}")
            continue
        # 等至少两帧渲染周期再截屏，否则抓到的是上一个 aim 的旧帧
        time.sleep(0.05)
        # 抽样跨锁定段跳转时 aim 瞬移，截图可能仍是旧位置，单独标注
        teleport = prev_aim is not None and np.hypot(x - prev_aim[0], y - prev_aim[1]) > 100
        prev_aim = (x, y)
        a = np.array(ImageGrab.grab())
        ring = find_ring(a)
        if ring is None:
            # 游戏窗口被用户窗口盖住：重新置顶并重抓一次
            raise_tv_window(True)
            a = np.array(ImageGrab.grab())
            ring = find_ring(a)
        if ring is None:
            recs.append({"frame": int(row["frame"]), "cross_x": x, "cross_y": y,
                         "meas_sx": np.nan, "meas_sy": np.nan,
                         "exp_sx": np.nan, "exp_sy": np.nan,
                         "dev_px": np.nan, "n_cyan": 0, "hit": False,
                         "note": "ring_lost"})
            continue
        to_screen = ring_mapping(ring)
        meas, n_cyan = cyan_centroid(a, ring)
        exp = to_screen(*tv_norm_to_px(x, y))
        note = "teleport" if teleport else ""
        if meas is not None:
            dev = float(np.hypot(meas[0] - exp[0], meas[1] - exp[1]))
            recs.append({"frame": int(row["frame"]), "cross_x": x, "cross_y": y,
                         "meas_sx": meas[0], "meas_sy": meas[1],
                         "exp_sx": exp[0], "exp_sy": exp[1],
                         "dev_px": dev, "n_cyan": n_cyan, "hit": dev < 40.0,
                         "note": note})
        else:
            recs.append({"frame": int(row["frame"]), "cross_x": x, "cross_y": y,
                         "meas_sx": np.nan, "meas_sy": np.nan,
                         "exp_sx": exp[0], "exp_sy": exp[1],
                         "dev_px": np.nan, "n_cyan": n_cyan, "hit": False,
                         "note": "no_cyan"})
        dt = time.monotonic() - t0
        if dt < period:
            time.sleep(period - dt)
    raise_tv_window(False)  # 恢复非置顶，把桌面还给用户
    live_df = pd.DataFrame(recs)
    live_df.to_csv(out_dir / "live.csv", index=False)
    n_meas = int(live_df["dev_px"].notna().sum())
    n_hit = int(live_df["hit"].sum())
    n_lost = int((live_df.get("note", pd.Series(dtype=str)) == "ring_lost").sum())
    steady = live_df[live_df["dev_px"].notna() & (live_df["note"] != "teleport")]
    n_steady_hit = int(steady["hit"].sum())
    elapsed = time.monotonic() - t_start
    print(f"[live] {len(live_df)} samples in {elapsed:.1f}s "
          f"({len(live_df) / elapsed:.1f} Hz effective), "
          f"measured {n_meas}, hits(<40px) {n_hit}, "
          f"hit rate {n_hit / max(n_meas, 1):.1%}, ring lost {n_lost}, "
          f"steady-state hit rate {n_steady_hit / max(len(steady), 1):.1%} "
          f"({n_steady_hit}/{len(steady)})")
    return {"samples": int(len(live_df)), "measured": n_meas, "hits": n_hit,
            "hit_rate": n_hit / max(n_meas, 1), "ring_lost": n_lost,
            "steady_samples": int(len(steady)), "steady_hits": n_steady_hit,
            "steady_hit_rate": n_steady_hit / max(len(steady), 1),
            "steady_dev_px_median": float(steady["dev_px"].median()),
            "steady_dev_px_p95": float(steady["dev_px"].quantile(0.95)),
            "dev_px_median": float(live_df["dev_px"].median()),
            "dev_px_p95": float(live_df["dev_px"].quantile(0.95)),
            "dev_px_max": float(live_df["dev_px"].max()),
            "grab_size": [int(gw), int(gh)], "fullscreen": bool(fullscreen)}


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", default=str(ROOT / "test_res" / "screen_video.mp4"))
    p.add_argument("--out", default=str(ROOT / "out" / "video_test"))
    p.add_argument("--tv", default="http://192.168.3.19:8000")
    p.add_argument("--rate", type=float, default=15.0, help="/aim 推送频率 Hz")
    p.add_argument("--skip-live", action="store_true", help="跳过任务 3（真闭环）")
    p.add_argument("--skip-offline", action="store_true",
                   help="跳过任务 1/2，直接读已有 frames.csv 跑任务 3")
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_offline:
        df = pd.read_csv(out_dir / "frames.csv")
        live = run_live(df, out_dir, args.tv, args.rate)
        if live is not None:
            sp = out_dir / "summary.json"
            stats = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {}
            stats["live"] = live
            sp.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        return 0

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"cannot open {args.video}")
        return 1
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"video: {args.video}  {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @{fps:.1f}fps, {n_frames} frames")

    # 代表帧：首/1/4/中/3/4/尾 + 3 个固定种子随机帧；若该帧未锁定则换成最近的锁定帧
    rng = np.random.default_rng(7)
    rep_want = sorted({0, n_frames // 4, n_frames // 2, 3 * n_frames // 4, n_frames - 1}
                      | set(int(i) for i in rng.integers(0, n_frames, 3)))
    rep_store = {}

    det = Detector()
    rows = []
    idx = 0
    t0 = time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        det.process(frame)
        duck_px = detect_duck(frame)
        duck_norm = map_point(det.H, duck_px[0] / det.step, duck_px[1] / det.step) \
            if (det.locked and det.H is not None and duck_px is not None) else None
        c = det.corners * det.step  # CSV 中四角坐标以原图像素记录
        rows.append({
            "frame": idx, "locked": det.locked, "fail": det.last_fail,
            "thr": det.last_thr, "low_thr": det.last_low_thr,
            "blob_frac": det.last_best_count / (det.det_w * det.det_h),
            "cross_x": det.cross[0], "cross_y": det.cross[1],
            "cross_valid": det.cross_valid,
            "tl_x": c[0], "tl_y": c[1], "tr_x": c[2], "tr_y": c[3],
            "br_x": c[4], "br_y": c[5], "bl_x": c[6], "bl_y": c[7],
            "duck_x": duck_norm[0] if duck_norm is not None else np.nan,
            "duck_y": duck_norm[1] if duck_norm is not None else np.nan,
            "duck_px_x": duck_px[0] if duck_px is not None else np.nan,
            "duck_px_y": duck_px[1] if duck_px is not None else np.nan,
        })
        idx += 1
    cap.release()
    n = len(rows)
    print(f"processed {n} frames in {time.monotonic() - t0:.1f}s")

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "frames.csv", index=False)

    # 代表帧最终选择：wanted 若未锁定则替换为最近的锁定帧（检测确定性，第二遍重放取图）
    locked_idx = np.flatnonzero(df["locked"].to_numpy())
    rep_final = sorted({int(locked_idx[np.argmin(np.abs(locked_idx - w))]) for w in rep_want})
    cap = cv2.VideoCapture(args.video)
    det2 = Detector()
    idx = 0
    while rep_final:
        ok, frame = cap.read()
        if not ok:
            break
        det2.process(frame)
        if idx == rep_final[0] and det2.locked and det2.H is not None:
            duck_px = detect_duck(frame)
            duck_norm = map_point(det2.H, duck_px[0] / det2.step, duck_px[1] / det2.step) \
                if duck_px is not None else None
            annotate_frame(frame, det2, det2.cross, duck_px, duck_norm,
                           out_dir / f"annotated_f{idx:04d}.png")
            rep_final.pop(0)
        idx += 1
    cap.release()
    print(f"annotated frames -> {out_dir}/annotated_*.png")

    # ---- 统计
    lock_rate = float(df["locked"].mean())
    locked_df = df[df["locked"]]
    inb_rate = float(locked_df["cross_valid"].mean()) if len(locked_df) else 0.0
    consec = df["locked"] & df["locked"].shift(1, fill_value=False) \
        & (df["frame"].diff() == 1)
    disp = np.hypot(df["cross_x"].diff()[consec], df["cross_y"].diff()[consec])

    # 锁定质量代理指标：四边形对边平行度。注意真实透视下竖直边可有数度~10°的
    # 梯形汇聚（本视频近距离侧拍即如此，f0405/f0614 正确锁定时 dv≈6-10°），
    # 故评估阈值取与检测门限一致的 10°（5° 会误杀正确透视四边形）。
    # 鸭子映射回规范坐标后落在界内的比例是独立的内容级校验（鸭子始终在屏幕内）。
    q = locked_df[["tl_x", "tl_y", "tr_x", "tr_y", "br_x", "br_y", "bl_x", "bl_y"]].to_numpy()

    def edge_ang(x0, y0, x1, y1):
        return np.arctan2(y1 - y0, x1 - x0)

    ang_top = edge_ang(q[:, 0], q[:, 1], q[:, 2], q[:, 3])
    ang_bot = edge_ang(q[:, 6], q[:, 7], q[:, 4], q[:, 5])
    ang_lft = edge_ang(q[:, 0], q[:, 1], q[:, 6], q[:, 7])
    ang_rgt = edge_ang(q[:, 2], q[:, 3], q[:, 4], q[:, 5])
    d_h = np.abs((ang_top - ang_bot + np.pi / 2) % np.pi - np.pi / 2)
    d_v = np.abs((ang_lft - ang_rgt + np.pi / 2) % np.pi - np.pi / 2)
    quad_plausible = (d_h < MAX_OPP_EDGE_ANG) & (d_v < MAX_OPP_EDGE_ANG)
    quad_plausible_5deg = (d_h < np.deg2rad(5)) & (d_v < np.deg2rad(5))
    dk_lb = locked_df.dropna(subset=["duck_x"])
    duck_inb = (dk_lb["duck_x"].between(0, NORM_W) & dk_lb["duck_y"].between(0, NORM_H))
    stats = {
        "frames": n,
        "lock_rate": lock_rate,
        "in_bounds_rate_locked": inb_rate,
        "fail_counts": {int(k): int(v) for k, v in df["fail"].value_counts().items()},
        "fail_note": "0=ok 1=blob<0.8% 2=无极值 3=四边形非法 4=单应失败 5=几何校验拒绝；"
                     "失锁需连续3帧失败（hysteresis），故 locked 帧数多于 fail==0 帧数",
        "disp_median": float(disp.median()),
        "disp_p95": float(disp.quantile(0.95)),
        "disp_max": float(disp.max()),
        "cross_x_range": [float(locked_df["cross_x"].min()), float(locked_df["cross_x"].max())],
        "cross_y_range": [float(locked_df["cross_y"].min()), float(locked_df["cross_y"].max())],
        "thr_minmax": [int(df["thr"].min()), int(df["thr"].max())],
        "blob_frac_median": float(df["blob_frac"].median()),
        "quad_plausible_rate_locked": float(quad_plausible.mean()) if len(locked_df) else 0.0,
        "quad_plausible_rate_5deg": float(quad_plausible_5deg.mean()) if len(locked_df) else 0.0,
        "quad_plausible_note": "对边方向差 <10°（与检测门限一致）视为几何合理；5° 指标仅作参考——"
                               "真实透视梯形汇聚可达 ~10°，5° 会误杀正确四边形",
        "duck_in_bounds_rate_locked": float(duck_inb.mean()) if len(dk_lb) else 0.0,
    }
    print(f"lock rate {lock_rate:.1%}, in-bounds {inb_rate:.1%}, "
          f"disp median {stats['disp_median']:.2f} / P95 {stats['disp_p95']:.2f} norm-units/frame, "
          f"quad plausible {stats['quad_plausible_rate_locked']:.1%}, "
          f"duck in-bounds {stats['duck_in_bounds_rate_locked']:.1%}")

    # ---- 外角点偏差量化：检测角点是边框连通域外角点，规范系以游戏区内角点为基准，
    # 近似仿射修正：corrected = (cross + BORDER_THICK) / ((NORM + 2*BORDER_THICK)/NORM)
    scale = (NORM_W + 2 * BORDER_THICK) / NORM_W
    cx_c = (locked_df["cross_x"] + BORDER_THICK) / scale
    cy_c = (locked_df["cross_y"] + BORDER_THICK) / scale
    dx = cx_c - locked_df["cross_x"]
    dy = cy_c - locked_df["cross_y"]
    mag = np.hypot(dx, dy)
    stats["outer_corner_bias"] = {
        "correction": f"cross_corr = (cross + {BORDER_THICK}) / {scale:.5f}",
        "dx_mean": float(dx.mean()), "dy_mean": float(dy.mean()),
        "mag_mean": float(mag.mean()), "mag_median": float(mag.median()),
        "mag_max": float(mag.max()),
        "note": "规范坐标单位；x1-x0=1786 窗口px 对应 1920 规范单位 -> "
                "1 规范单位 ≈ 0.93 窗口px ≈ 1.86 屏幕px(4K 全屏 2x)",
    }
    print(f"outer-corner bias: dx mean {dx.mean():.2f}, dy mean {dy.mean():.2f}, "
          f"|delta| mean {mag.mean():.2f} norm-units")

    # ---- 轨迹对照图
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5))
    ax = axes[0]
    dk = df.dropna(subset=["duck_x"])
    sc = ax.scatter(dk["duck_x"], dk["duck_y"], c=dk["frame"], s=3, cmap="viridis",
                    label="duck")
    ax.scatter(locked_df["cross_x"], locked_df["cross_y"], s=3, c="red", label="cross")
    ax.set_xlim(0, NORM_W)
    ax.set_ylim(NORM_H, 0)
    ax.set_aspect("equal")
    ax.set_title("trajectory in normalized coords")
    ax.legend(markerscale=3)
    fig.colorbar(sc, ax=ax, label="frame")
    for k, ax in enumerate(axes[1:]):
        col = "cross_x" if k == 0 else "cross_y"
        dcol = "duck_x" if k == 0 else "duck_y"
        ax.plot(df["frame"], df[col], "r-", lw=0.8, label="cross")
        ax.plot(dk["frame"], dk[dcol], "b-", lw=0.8, alpha=0.7, label="duck")
        ax.set_xlabel("frame")
        ax.set_ylabel(col[-1])
        ax.set_title(f"{col[-1]}(t)")
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "trajectory.png", dpi=110)
    plt.close(fig)
    print(f"trajectory -> {out_dir}/trajectory.png")

    # ---- 任务 3：真闭环
    if not args.skip_live:
        live = run_live(df, out_dir, args.tv, args.rate)
        if live is not None:
            stats["live"] = live

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"summary -> {out_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
