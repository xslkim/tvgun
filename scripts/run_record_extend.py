#!/usr/bin/env python3
"""光枪录制回放扩展：屏幕部分/完全出画时的三层坐标可用性算法验证。

数据：out/record_20260919_104442/（640x360@30fps 灰度 + 417Hz 陀螺，同一单调时钟）
前置结论（run_record_replay.py）：linefit 可见帧 100% 锁定、静止抖动 0.38px、
740/1120 帧部分/完全出画、Fusion 轴向已修正 dx=-wx, dy=+wy。

三层算法（本脚本验证目标）：
  状态：M = 规范坐标(1920x1080) -> 640x360 相机图像 的 3x3 单应；陀螺零偏 b（在线估计）
  1. 陀螺传播：每 tick M <- K·R((ω-b)·dt)·K⁻¹·M；K 由 viewAngle 得
     fx=fy=(w/2)/tan(viewAngle/2)，主点=画面中心。
     轴向（录制回归标定）：相机系 ωc = (−wy, −wx, +wz)（设备系→相机系）。
  2. 零偏在线估计：FULL 锁定且静止（0.1s 平滑 ω 的 0.5s 窗 std < STILL_STD 且
     准星速度 < STILL_SPD）时 b <- EMA(b, mean(ω), 0.1)，否则冻结。
  3. FULL 校正：四角齐 -> M <- 0.7·M + 0.3·M_cam（M[2,2] 归一）。
  4. PARTIAL 残边约束：1~3 条边可见时，M 预测各边投影，与实测拟合线（外包络 TLS，
     与 linefit 同）比较法向残差，最小二乘小步更新 H 扰动：
     横边（y=0/1080）校正 (俯仰 δθx, 垂直平移 dty)；竖边（x=0/1920）校正
     (偏航 δθy, 水平平移 dtx)。阻尼 LS + 每帧步长上限。
  5. 可用性门控：FULL（4边）/ PARTIAL（1~3边）/ GYRO_ONLY（无边, ≤T_max）/ DEAD。

评测：可用率分级、出画段末端误差（vs 重新锁定观测）、闭环误差（反向陀螺回算基准）、
静止段 gyro-only 漂移率（零偏校准前后）、T_max 扫描。

用法:
  python scripts/run_record_extend.py [--out out/record_extend] [--annotate]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_record_replay import (  # noqa: E402
    ReplayDet, load_recording, MIN_EDGE_BINS, MIN_SUPPORT, MIN_SPAN,
    MAX_EDGE_SIGMA, TRIM_ROUNDS, EDGE_BIN_W,
)

NORM_W, NORM_H = 1920.0, 1080.0
IMG_W, IMG_H = 640, 360

# ---- 传播/校正参数 ----
VIEW_ANGLE = 67.94                      # meta.txt（水平视场角，度）
FX = (IMG_W / 2) / np.tan(np.radians(VIEW_ANGLE / 2))   # ≈475
K = np.array([[FX, 0, IMG_W / 2], [0, FX, IMG_H / 2], [0, 0, 1.0]])
K_INV = np.linalg.inv(K)
GAIN_FULL = 0.6                         # FULL 校正互补增益（M 混合；0.3 滞后过大，0.9 噪声增大）
STILL_STD = 0.05                        # 静止判据：平滑 ω 0.5s 窗 std (rad/s)
STILL_SPD = 60.0                        # 静止判据：准星速度 (norm px/s)
BIAS_EMA = 0.1
T_MAX = 3.0                             # GYRO_ONLY 上限（s）
BRIGHT_MIN_FRAC = 0.85                # 包络点均值亮度 >= 0.85*hi_thr（防墙面/反光误拟合）
BAND_PARTIAL = 10.0                     # PARTIAL 边带基础半宽（px，随失约时长加宽）
BAND_PER_SEC = 2.0                      # 每失约 1s 带宽加宽
LS_DAMP = 1e-3                          # 阻尼最小二乘 λ
STEP_BETA = 0.5                         # 每帧校正步长比例
MAX_DTH = np.radians(0.5)               # 每帧旋转校正上限
MAX_DTXY = 5.0                          # 每帧平移校正上限（px）

LEVELS = {"DEAD": 0, "GYRO_ONLY": 1, "PARTIAL": 2, "FULL": 3}
PARTIAL_ENABLED = True   # False=消融实验：禁用残边校正（FULL + GYRO_ONLY）


# ================================================================ 单条边拟合

def fit_edge_line(g640, low_thr, hi_thr, p0, p1, band, centroid, bright_gate=False):
    """在 p0->p1 线段 ±band 带内取掩模像素，纵向分箱取外侧包络点
    （外侧 = 远离四边形中心，与 linefit 外边界约定一致），
    TLS + 2σ 剔除，返回齐次线 (a,b,c)（a²+b²=1）或 None。"""
    mask640 = g640 >= low_thr
    d = p1 - p0
    L = np.hypot(*d)
    if L < 40:
        return None, None
    d = d / L
    nv = np.array([-d[1], d[0]])
    if nv @ (p0 - centroid) < 0:
        nv = -nv                          # nv 指向四边形外侧
    x0 = max(int(min(p0[0], p1[0]) - band - 2), 0)
    x1 = min(int(max(p0[0], p1[0]) + band + 2), IMG_W)
    y0 = max(int(min(p0[1], p1[1]) - band - 2), 0)
    y1 = min(int(max(p0[1], p1[1]) + band + 2), IMG_H)
    if x1 <= x0 or y1 <= y0:
        return None, None
    sub = mask640[y0:y1, x0:x1]
    if not sub.any():
        return None, None
    yy, xx = np.nonzero(sub)
    xx = xx + x0
    yy = yy + y0
    perp = (xx - p0[0]) * nv[0] + (yy - p0[1]) * nv[1]
    lon = (xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]
    sel = (np.abs(perp) <= band) & (lon >= 0) & (lon <= L)
    xx, yy, perp, lon = xx[sel], yy[sel], perp[sel], lon[sel]
    n_bins = int(L / EDGE_BIN_W)
    if n_bins < MIN_EDGE_BINS:
        return None, None
    bi = np.minimum((lon / EDGE_BIN_W).astype(int), n_bins - 1)
    env, env_bins = [], []
    for b in range(n_bins):
        m = bi == b
        if not m.any():
            continue
        thr95 = np.percentile(perp[m], 95)   # 外侧（nv 方向）包络
        top = m & (perp >= thr95 - 1e-9)
        env.append((xx[top].mean(), yy[top].mean()))
        env_bins.append(b)
    support = len(env) / n_bins
    span = (env_bins[-1] - env_bins[0] + 1) / n_bins if env_bins else 0.0
    if len(env) < MIN_EDGE_BINS or not (support >= MIN_SUPPORT
                                        or (span >= MIN_SPAN and support >= 0.15)):
        return None, (len(env), support, float("nan"))
    pts = np.array(env)
    sigma = float("inf")
    normal = ctr = None
    for _ in range(TRIM_ROUNDS + 1):
        ctr = pts.mean(axis=0)
        cov = np.cov((pts - ctr).T)
        eigval, eigvec = np.linalg.eigh(cov)
        normal = eigvec[:, 0]
        res = (pts - ctr) @ normal
        sigma = float(res.std())
        if sigma < 1e-9:
            break
        inl = np.abs(res - res.mean()) <= 2 * sigma
        if inl.all():
            break
        pts = pts[inl]
        if len(pts) < MIN_EDGE_BINS:
            return None, (len(pts), support, sigma)
    if sigma > MAX_EDGE_SIGMA:
        return None, (len(pts), support, sigma)
    if bright_gate:
        env_gray = g640[pts[:, 1].astype(int), pts[:, 0].astype(int)].mean()
        if env_gray < BRIGHT_MIN_FRAC * hi_thr:
            return None, (len(pts), support, sigma)
    line = np.array([normal[0], normal[1], -normal @ ctr])
    return line, (len(pts), support, sigma)


def line_consistent(pred_p0, pred_p1, line, max_off=4.0, max_ang_deg=4.0):
    """一致性门控：拟合线与 M 预测边的平均法向偏差 <= max_off px 且方向差 <= max_ang。
    M 刚丢 FULL 时预测很准，偏差大的拟合是误拟合（墙面/文字），应拒收。"""
    d = pred_p1 - pred_p0
    L = np.hypot(*d)
    d = d / L
    nv = np.array([-d[1], d[0]])
    # 拟合线方向与预测方向夹角
    line_dir = np.array([-line[1], line[0]])
    cosang = abs(d @ line_dir)
    if cosang < np.cos(np.radians(max_ang_deg)):
        return False
    # 拟合线相对预测边的法向偏移（在中点处度量）
    mid = (pred_p0 + pred_p1) / 2
    off = abs(line[0] * mid[0] + line[1] * mid[1] + line[2])
    return off <= max_off


# ================================================================ 传播器

class Propagator:
    """M（norm->img）+ 陀螺零偏的三层状态机。"""

    def __init__(self, t_max=T_MAX):
        self.M = None
        self.bias = np.zeros(3)          # 设备系零偏
        self.level = "DEAD"
        self.t_since = 0.0               # 距上次 FULL/PARTIAL 约束（s）
        self.last_ts = None
        self.ever_locked = False
        self.t_max = t_max
        self.corners_img = None          # 当前 M 隐含的四角（640x360）
        self.vis_edges = []              # 本帧可见边索引
        self.fitted_lines = {}
        self.last_constraint_ts = None   # 最近 FULL/PARTIAL 的帧时刻

    # ---- 陀螺传播（设备系 -> 相机系：ωc=(+wy,+wx,+wz)。
    # 与 Fusion 修正映射 dx=−wx·S, dy=+wy·S 在 KRK⁻¹ 约定下数值等价（已验证）） ----
    def propagate(self, ticks):
        """ticks: (m,4) 数组 [tsNs,wx,wy,wz]，按序积分到 M。"""
        if self.M is None:
            if len(ticks):
                self.last_ts = ticks[-1, 0]
            return
        for ts, wx, wy, wz in ticks:
            if self.last_ts is None:
                self.last_ts = ts
                continue
            dt = (ts - self.last_ts) * 1e-9
            self.last_ts = ts
            if dt <= 0 or dt > 0.1:
                continue
            w = np.array([wx, wy, wz]) - self.bias
            wc = np.array([w[1], w[0], w[2]])
            th = wc * dt
            n = np.linalg.norm(th)
            if n < 1e-12:
                continue
            R = cv2.Rodrigues(th)[0]
            self.M = K @ R @ K_INV @ self.M
            self.M /= self.M[2, 2]

    # ---- 输出 ----
    def cross(self):
        if self.M is None:
            return np.array([np.nan, np.nan])
        p = np.linalg.inv(self.M) @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        return p[:2] / p[2]

    def quad_img(self):
        """规范四角 -> 图像坐标。"""
        nc = np.array([[0, 0], [NORM_W, 0], [NORM_W, NORM_H], [0, NORM_H]])
        pts = (self.M @ np.column_stack([nc, np.ones(4)]).T).T
        return pts[:, :2] / pts[:, 2:]

    # ---- FULL 校正 ----
    def correct_full(self, corners640, gain=None):
        if gain is None:
            gain = GAIN_FULL
        nc = np.array([[0, 0], [NORM_W, 0], [NORM_W, NORM_H], [0, NORM_H]], np.float32)
        M_cam = cv2.getPerspectiveTransform(nc, corners640.astype(np.float32))
        M_cam = M_cam.astype(np.float64) / M_cam[2, 2]
        if self.M is None:
            self.M = M_cam
        else:
            self.M = (1 - gain) * self.M + gain * M_cam
            self.M /= self.M[2, 2]
        self.ever_locked = True
        self.t_since = 0.0

    # ---- PARTIAL 残边约束校正 ----
    def correct_partial(self, edge_lines):
        """edge_lines: {edge_idx: (a,b,c)}，edge 0=顶(y=0) 1=右(x=1920) 2=底(y=1080)
        3=左(x=0)。横边校正 (pitch rx, dty)；竖边校正 (yaw ry, dtx)。
        残差 = M 预测的边上采样点到实测线的法向距离；阻尼 LS 每帧小步更新。"""
        params = []
        for e in edge_lines:
            for p_ in (("rx", "ty") if e in (0, 2) else ("ry", "tx")):
                if p_ not in params:
                    params.append(p_)
        r_parts = []
        dr_parts = []   # per edge: list of (param, dr)
        npts_per_edge = 17
        for e, line in edge_lines.items():
            horiz = e in (0, 2)
            if horiz:
                xs = np.linspace(0, NORM_W, npts_per_edge)
                npts = np.column_stack([xs, np.full(npts_per_edge, 0.0 if e == 0 else NORM_H)])
            else:
                ys = np.linspace(0, NORM_H, npts_per_edge)
                npts = np.column_stack([np.full(npts_per_edge, 0.0 if e == 3 else NORM_W), ys])
            q0 = self._project(npts)
            r = line[0] * q0[:, 0] + line[1] * q0[:, 1] + line[2]
            r_parts.append(r)
            drs = []
            for p_ in (("rx", "ty") if horiz else ("ry", "tx")):
                q1 = self._project_perturb(npts, p_)
                dr = (line[0] * q1[:, 0] + line[1] * q1[:, 1] + line[2]) - r
                drs.append((p_, dr / self._eps(p_)))
            dr_parts.append(drs)
        r = np.concatenate(r_parts)
        J = np.zeros((len(r), len(params)))
        row0 = 0
        for drs in dr_parts:
            for p_, dr in drs:
                J[row0:row0 + npts_per_edge, params.index(p_)] = dr
            row0 += npts_per_edge
        delta = np.linalg.solve(J.T @ J + LS_DAMP * np.eye(len(params)), J.T @ r)
        for k, p_ in enumerate(params):
            cap = MAX_DTH if p_ in ("rx", "ry") else MAX_DTXY
            delta[k] = np.clip(delta[k] * STEP_BETA, -cap, cap)
        for d, p_ in zip(delta, params):
            self.M = self._perturbed(p_, -float(d))
        self.M /= self.M[2, 2]
        return float(np.abs(r).mean())

    def _eps(self, p_):
        return 1e-4 if p_ in ("rx", "ry") else 0.5

    def _project(self, np_pts):
        q = (self.M @ np.column_stack([np_pts, np.ones(len(np_pts))]).T).T
        return q[:, :2] / q[:, 2:]

    def _project_perturb(self, np_pts, p_):
        M2 = self._perturbed(p_, self._eps(p_))
        q = (M2 @ np.column_stack([np_pts, np.ones(len(np_pts))]).T).T
        return q[:, :2] / q[:, 2:]

    def _perturbed(self, p_, eps):
        if p_ == "rx":
            R = cv2.Rodrigues(np.array([eps, 0.0, 0.0]))[0]
            M2 = K @ R @ K_INV @ self.M
        elif p_ == "ry":
            R = cv2.Rodrigues(np.array([0.0, eps, 0.0]))[0]
            M2 = K @ R @ K_INV @ self.M
        elif p_ == "tx":
            M2 = self.M.copy()
            M2[0, 2] += eps
        else:
            M2 = self.M.copy()
            M2[1, 2] += eps
        return M2 / M2[2, 2]

def calibrate_fx(frames, idx, gyro, replay_dir):
    """用相邻锁定帧传播误差标定有效焦距 FX（viewAngle 给的 475 偏小 ~30%，
    回归 S_eff≈2050/1922 norm/rad ≈ image 633-684px/rad → FX_eff≈633）。
    网格搜索 f∈[0.9,1.7]，取相邻锁定帧传播误差中位最小者。"""
    global FX, K, K_INV
    line_csv = replay_dir / "linefit_replay.csv"
    if line_csv.exists():
        new = pd.read_csv(line_csv)
    else:
        det = ReplayDet("linefit")
        recs = []
        for s in range(len(frames)):
            det.process(frames[s])
            c = det.corners
            recs.append({"locked": det.locked, "cross_x": det.cross[0],
                         "cross_y": det.cross[1], "cross_valid": det.cross_valid,
                         **{f"c{i}{a}": c[2 * i + j] for i in range(4)
                            for j, a in enumerate("xy")}})
        new = pd.DataFrame(recs)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    fts = idx["tsNs"].to_numpy()
    lk = (new["locked"] & new["cross_valid"]).to_numpy()
    corners = new[[f"c{i}{a}" for i in range(4) for a in "xy"]].to_numpy()
    nc = np.array([[0, 0], [1920, 0], [1920, 1080], [0, 1080]], np.float32)

    def err_med(fx):
        global K, K_INV
        K = np.array([[fx, 0, IMG_W / 2], [0, fx, IMG_H / 2], [0, 0, 1.0]])
        K_INV = np.linalg.inv(K)
        errs = []
        step = 3  # 抽样加速
        for i in range(1, len(new), step):
            if not (lk[i] and lk[i - 1]):
                continue
            m = (gts > fts[i - 1]) & (gts <= fts[i])
            if m.sum() < 1:
                continue
            M = cv2.getPerspectiveTransform(
                nc, (corners[i - 1].reshape(4, 2) * 2).astype(np.float32)).astype(float)
            M /= M[2, 2]
            pt = fts[i - 1]
            for j in np.nonzero(m)[0]:
                dt = (gts[j] - pt) * 1e-9
                pt = gts[j]
                if dt <= 0 or dt > 0.1:
                    continue
                wx, wy, wz = gw[j]
                R = cv2.Rodrigues(np.array([wy, wx, wz]) * dt)[0]
                M = K @ R @ K_INV @ M
                M /= M[2, 2]
            p = np.linalg.inv(M) @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
            p = p[:2] / p[2]
            errs.append(np.hypot(p[0] - new["cross_x"][i], p[1] - new["cross_y"][i]))
        return float(np.median(errs))

    best_f, best_e = 1.0, float("inf")
    for f in np.arange(0.9, 1.71, 0.05):
        e = err_med(FX * f)
        if e < best_e:
            best_f, best_e = f, e
    FX *= best_f
    K = np.array([[FX, 0, IMG_W / 2], [0, FX, IMG_H / 2], [0, 0, 1.0]])
    K_INV = np.linalg.inv(K)
    return {"fx_scale": float(best_f), "fx_eff": float(FX),
            "prop_err_median_px": best_e}


def backprop_cross(M_relock, gyro_rows):
    """从重新锁定帧的 M 出发，用陀螺反向积分回算 gap 内各帧的 cross（闭环基准）。
    gyro_rows: gap 内 (m,4) [tsNs,wx,wy,wz] 时间正序；返回 {tsNs: cross}。"""
    M = M_relock.copy()
    out = {}
    for i in range(len(gyro_rows) - 1, 0, -1):
        ts, wx, wy, wz = gyro_rows[i]
        dt = (gyro_rows[i, 0] - gyro_rows[i - 1, 0]) * 1e-9
        if dt <= 0 or dt > 0.1:
            continue
        wc = np.array([wy, wx, wz])
        th = -wc * dt                      # 反向：逆旋转
        R = cv2.Rodrigues(th)[0]
        M = K @ R @ K_INV @ M
        M /= M[2, 2]
        p = np.linalg.inv(M) @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        out[int(gyro_rows[i - 1, 0])] = p[:2] / p[2]
    return out


# ================================================================ 主状态机

def run_extended(frames, idx, gyro, t_max=T_MAX, bias_on=True):
    """逐帧三层状态机回放。返回 per-frame DataFrame。"""
    det = ReplayDet("linefit")       # 仅借用其 _coarse_parts / 几何校验
    prop = Propagator(t_max)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    gi = 0
    # 陀螺平滑（0.1s boxcar ≈ 42 样本）用于静止判定
    win = 42
    rows = []
    hist = []   # 最近帧 (tsNs, level, cross)，供零偏估计的连续性门控
    frame_ts = idx["tsNs"].to_numpy()
    prev_cross = None
    prev_ts = None
    for f in range(len(frames)):
        fts = frame_ts[f]
        # 1) 陀螺传播到本帧时刻
        j0 = gi
        while gi < len(gts) and gts[gi] <= fts:
            gi += 1
        prop.propagate(np.column_stack([gts[j0:gi], gw[j0:gi]]))

        g = frames[f]
        raw, stage, labels, best, low_thr = det._coarse_parts(g)
        level = None
        fitted = None
        # 2) FULL 尝试：粗四角 -> 4 边拟合
        if stage == 0:
            mask640 = g >= low_thr
            c640 = raw.reshape(4, 2) * 2.0
            lines = {}
            ok = True
            centroid = c640.mean(axis=0)
            for e in range(4):
                ln, _info = fit_edge_line(g, low_thr, det.last_thr,
                                          c640[e], c640[(e + 1) % 4],
                                          6.0, centroid)
                if ln is None:
                    ok = False
                    break
                lines[e] = ln
            if ok:
                corners = []
                for i in range(4):
                    p = np.cross(lines[(i - 1) % 4], lines[i])
                    corners.append(p[:2] / p[2])
                corners = np.array(corners)
                qd = corners / 2.0
                if det._geo_valid_fit(qd.reshape(8)):
                    fitted = corners
        if fitted is not None:
            prop.correct_full(fitted)
            level = "FULL"
            prop.vis_edges = [0, 1, 2, 3]
            prop.fitted_lines = lines
        elif prop.M is not None and prop.ever_locked and PARTIAL_ENABLED:
            # 3) PARTIAL：M 预测各边 -> 逐边独立拟合 + 一致性门控
            band = BAND_PARTIAL + BAND_PER_SEC * prop.t_since
            quad = prop.quad_img()
            centroid = quad.mean(axis=0)
            edge_lines = {}
            for e in range(4):
                ln, _info = fit_edge_line(g, low_thr, det.last_thr,
                                          quad[e], quad[(e + 1) % 4],
                                          band, centroid, bright_gate=True)
                if ln is not None and line_consistent(quad[e], quad[(e + 1) % 4], ln):
                    edge_lines[e] = ln
            if edge_lines:
                prop.correct_partial(edge_lines)
                level = "PARTIAL"
                prop.vis_edges = sorted(edge_lines)
                prop.fitted_lines = edge_lines
            else:
                level = "GYRO_ONLY"
                prop.vis_edges = []
                prop.fitted_lines = {}
        else:
            level = "DEAD"
            prop.vis_edges = []
            prop.fitted_lines = {}

        # 4) 零偏在线估计：仅当最近 0.5s 全部 FULL 锁定、准星窗口位移 <40px、
        #    且平滑陀螺平静时更新；b <- EMA(b, mean(ω) − ω_相机观测运动)
        hist.append((fts, level, prop.cross().copy()))
        if bias_on:
            m = (gts > fts - int(0.5e9)) & (gts <= fts)
            recent = [h for h in hist if h[0] > fts - int(0.5e9)]
            all_full = len(recent) >= 12 and all(h[1] == "FULL" for h in recent)
            if m.sum() > 100 and all_full:
                wseg = pd.DataFrame(gw[m]).rolling(win, center=True).mean().dropna()
                gyro_calm = bool((wseg.std() < STILL_STD).all())
                c_now = prop.cross()
                c_old = recent[0][2]
                dtw = max((fts - recent[0][0]) * 1e-9, 1e-6)
                if (gyro_calm and np.all(np.isfinite(c_now))
                        and np.all(np.isfinite(c_old))
                        and abs(c_now[0] - c_old[0]) < 40
                        and abs(c_now[1] - c_old[1]) < 40):
                    S_meta = 1619.31
                    dxdt = (c_now[0] - c_old[0]) / dtw
                    dydt = (c_now[1] - c_old[1]) / dtw
                    w_motion = np.array([-dxdt / S_meta, dydt / S_meta, 0.0])
                    prop.bias = (1 - BIAS_EMA) * prop.bias                         + BIAS_EMA * (gw[m].mean(axis=0) - w_motion)

        # 5) 门控：FULL/PARTIAL 刷新约束时刻；GYRO_ONLY 超时 -> DEAD
        if level in ("FULL", "PARTIAL"):
            prop.last_constraint_ts = fts
            prop.t_since = 0.0
        else:
            prop.t_since = 0.0 if prop.last_constraint_ts is None \
                else (fts - prop.last_constraint_ts) * 1e-9
        if level == "GYRO_ONLY" and prop.t_since > t_max:
            level = "DEAD"

        cr = prop.cross()
        quad = prop.quad_img() if prop.M is not None else np.full((4, 2), np.nan)
        rows.append({"seq": f, "tsNs": fts, "level": level,
                     "level_i": LEVELS[level],
                     "cross_x": cr[0], "cross_y": cr[1],
                     "n_edges": len(prop.vis_edges),
                     "vis_edges": "".join(str(e) for e in prop.vis_edges),
                     "bias_x": prop.bias[0], "bias_y": prop.bias[1],
                     "bias_z": prop.bias[2],
                     "t_since": prop.t_since,
                     **{f"q{i}{a}": quad[i, j] for i in range(4)
                        for j, a in enumerate("xy")}})
        prev_cross = cr
        prev_ts = fts
    return pd.DataFrame(rows), prop


# ================================================================ 评测

def evaluate(df, idx, gyro, detect):
    """可用率 + 出画段精度（段末误差 + 闭环基准） + 静止段漂移。"""
    res = {}
    n = len(df)
    lv = df["level"]
    res["availability"] = {k: float((lv == k).mean()) for k in LEVELS}
    res["usable_rate"] = float(lv.isin(["FULL", "PARTIAL", "GYRO_ONLY"]).mean())
    inb = df["cross_x"].between(0, NORM_W) & df["cross_y"].between(0, NORM_H)
    res["in_bounds_by_level"] = {k: float(inb[(lv == k).to_numpy()].mean())
                                 if (lv == k).any() else None for k in LEVELS}

    # 出画段（非 FULL 的极大连续段），段末传播值 vs 重新锁定相机观测
    gaps = []
    st = None
    for i, isfull in enumerate((lv == "FULL").to_numpy()):
        if not isfull and st is None:
            st = i
        if isfull and st is not None:
            gaps.append((st, i - 1, i))   # start, end, relock_idx
            st = None
    rows = []
    loop_rows = []
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    for a, b, ri in gaps:
        if ri >= n or not np.isfinite(df["cross_x"][ri]):
            continue
        dur = (df["tsNs"][b] - df["tsNs"][a]) * 1e-9
        e = float(np.hypot(df["cross_x"][b] - df["cross_x"][ri],
                           df["cross_y"][b] - df["cross_y"][ri]))
        rows.append({"gap_start": a, "gap_end": b, "dur_s": dur, "end_err": e,
                     "levels": "".join(sorted(set(df["level"][a:b + 1])))})
        # 闭环基准：从 ri 帧的 FULL 四边形重建 M，反向陀螺积分回算 gap 内各帧 cross
        # （反向基准 = 独立的第二条传播链，两者分叉程度即传播不确定性）
        # 需要 ri 帧的 M：不在 df 中存，近似用 relock 后 cross 为锚点不做全 M 回算。
        # （代价/复杂度考量，闭环基准放到 evaluate 外的专项分析；这里保留段末误差。）
    g = pd.DataFrame(rows)
    res["gaps"] = g.to_dict("records")
    if len(g):
        g["bin"] = pd.cut(g["dur_s"], [0, 0.5, 1, 2, 3, 10])
        tab = g.groupby("bin", observed=True)["end_err"].agg(
            ["size", "median", lambda s: s.quantile(.95), "max"])
        tab.columns = ["n", "median", "p95", "max"]
        res["gap_end_err_by_dur"] = {str(k): {"n": int(v["n"]),
                                              "median": float(v["median"]),
                                              "p95": float(v["p95"]),
                                              "max": float(v["max"])}
                                     for k, v in tab.iterrows()}
        # hold 基线：不传播，段内保持上次 FULL 观测
        holds = []
        for a, b, ri in gaps:
            prev_full = df["level"][:a][df["level"][:a] == "FULL"].index
            if not len(prev_full) or ri >= n:
                continue
            pf = prev_full[-1]
            e = float(np.hypot(df["cross_x"][pf] - df["cross_x"][ri],
                               df["cross_y"][pf] - df["cross_y"][ri]))
            holds.append({"dur_s": (df["tsNs"][b] - df["tsNs"][a]) * 1e-9,
                          "hold_err": e})
        if holds:
            h = pd.DataFrame(holds)
            h["bin"] = pd.cut(h["dur_s"], [0, 0.5, 1, 2, 3, 10])
            htab = h.groupby("bin", observed=True)["hold_err"].agg(["size", "median"])
            res["gap_hold_err_by_dur"] = {str(k): {"n": int(v["size"]),
                                                   "median": float(v["median"])}
                                          for k, v in htab.iterrows()}
    return res, g, gaps


def drift_test(frames, idx, gyro, bias_vec):
    """静止段（seq5-55）GYRO_ONLY 传播漂移：从 seq5 的 FULL M 出发纯传播，
    与期间 FULL 观测 cross 对比，报 px/s 漂移率。bias_vec=None 表示零偏关闭。"""
    det = ReplayDet("linefit")
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    frame_ts = idx["tsNs"].to_numpy()

    def run(bias):
        prop = Propagator()
        prop.bias = np.array(bias)
        # 初始化：seq5 的 FULL 观测（直接跑 linefit 管线到 seq5）
        d2 = ReplayDet("linefit")
        for s in range(6):
            d2.process(frames[s])
        nc = np.array([[0, 0], [NORM_W, 0], [NORM_W, NORM_H], [0, NORM_H]], np.float32)
        corners640 = (d2.corners.reshape(4, 2) * 2).astype(np.float32)
        M = cv2.getPerspectiveTransform(nc, corners640).astype(np.float64)
        prop.M = M / M[2, 2]
        prop.last_ts = None
        gi = int(np.searchsorted(gts, frame_ts[5]))
        out = []
        for f in range(6, 56):
            j0 = gi
            while gi < len(gts) and gts[gi] <= frame_ts[f]:
                gi += 1
            prop.propagate(np.column_stack([gts[j0:gi], gw[j0:gi]]))
            cr = prop.cross()
            # 对照：该帧实际 FULL 检测
            d3 = ReplayDet("linefit")
            d3.process(frames[f])
            obs = d3.cross if d3.locked else np.array([np.nan, np.nan])
            out.append({"seq": f, "px": cr[0], "py": cr[1],
                        "ox": obs[0], "oy": obs[1]})
        return pd.DataFrame(out)

    res = {}
    for tag, bias in (("bias_on", bias_vec), ("bias_off", (0, 0, 0))):
        d = run(bias)
        d["err"] = np.hypot(d["px"] - d["ox"], d["py"] - d["oy"])
        t = (d["seq"] - 5) / 30.0
        slope = np.polyfit(t, d["err"], 1)[0]
        res[tag] = {"drift_px_per_s": float(slope),
                    "err_end": float(d["err"].iloc[-1]),
                    "err_median": float(d["err"].median())}
    return res


# ================================================================ 图

def plot_availability(df, out_dir):
    t = (df["tsNs"] - df["tsNs"][0]) * 1e-9
    fig, axes = plt.subplots(3, 1, figsize=(15, 9), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1.4, 1.4]})
    colors = {"FULL": "#2ca02c", "PARTIAL": "#ff7f0e", "GYRO_ONLY": "#1f77b4",
              "DEAD": "#d62728"}
    for name, i in LEVELS.items():
        axes[0].fill_between(t, 0, 1, where=(df["level"] == name),
                             color=colors[name], alpha=0.85, step="post", label=name)
    axes[0].set_yticks([])
    axes[0].legend(ncol=4, fontsize=9)
    axes[0].set_title("availability timeline")
    axes[1].plot(t, df["cross_x"], lw=0.8, color="0.3")
    axes[1].set_ylabel("cross x (norm)")
    axes[1].grid(alpha=0.3)
    axes[2].plot(t, df["cross_y"], lw=0.8, color="0.3")
    axes[2].set_ylabel("cross y (norm)")
    axes[2].set_xlabel("t (s)")
    axes[2].grid(alpha=0.3)
    for ax in axes[1:]:
        for name, color in colors.items():
            if name == "FULL":
                continue
            ax.fill_between(t, df["cross_y"].min() - 50, df["cross_y"].max() + 50,
                            where=(df["level"] == name), color=color, alpha=0.08,
                            step="post")
    fig.tight_layout()
    fig.savefig(out_dir / "availability.png", dpi=110)
    plt.close(fig)


def plot_gap_errors(g, out_dir):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(g["dur_s"], g["end_err"], s=25, alpha=0.7)
    ax.set_xlabel("gap duration (s)")
    ax.set_ylabel("|propagated - camera| at relock (norm px)")
    ax.set_title("out-of-frame gap: end-of-gap extrapolation error")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "gap_errors.png", dpi=110)
    plt.close(fig)


def annotate_partial(frames, df, out_dir, n_samples=8):
    """PARTIAL 帧标注：预测四边形（虚线红）+ 可见边标注 + 准星。"""
    sub = df[df["level"] == "PARTIAL"]
    if not len(sub):
        return []
    pick = sub.iloc[np.linspace(0, len(sub) - 1, min(n_samples, len(sub))).astype(int)]
    out = []
    for _, row in pick.iterrows():
        s = int(row["seq"])
        img = cv2.cvtColor(frames[s], cv2.COLOR_GRAY2BGR)
        img = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_NEAREST)
        q = np.array([[row[f"q{i}x"], row[f"q{i}y"]] for i in range(4)]) * 2
        if np.all(np.isfinite(q)):
            qi = q.astype(np.int32)
            cv2.polylines(img, [qi], True, (0, 0, 255), 1, cv2.LINE_AA)
            for (px, py), nm in zip(qi, ("TL", "TR", "BR", "BL")):
                cv2.putText(img, nm, (px + 3, py + 10), cv2.FONT_HERSHEY_SIMPLEX,
                            0.45, (0, 0, 255), 1, cv2.LINE_AA)
        vis = str(row["vis_edges"])
        cx, cy = 640, 360
        cv2.line(img, (cx - 15, cy), (cx + 15, cy), (255, 255, 0), 1, cv2.LINE_AA)
        cv2.line(img, (cx, cy - 15), (cx, cy + 15), (255, 255, 0), 1, cv2.LINE_AA)
        txt = (f"seq={s} PARTIAL edges={vis} "
               f"cross=({row['cross_x']:.0f},{row['cross_y']:.0f})")
        cv2.putText(img, txt, (cx + 18, cy - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 0), 1, cv2.LINE_AA)
        path = out_dir / f"annotated_partial_{s:06d}.png"
        cv2.imwrite(str(path), img)
        out.append(path)
    return out


# ================================================================ 主流程

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rec", default=str(ROOT / "out" / "record_20260919_104442"))
    ap.add_argument("--out", default=str(ROOT / "out" / "record_extend"))
    ap.add_argument("--annotate", action="store_true", help="出 PARTIAL 示例标注帧")
    args = ap.parse_args(argv)

    rec_dir = Path(args.rec)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, idx, gyro, detect, meta = load_recording(rec_dir)
    print(f"recording: {len(frames)} frames, gyro {len(gyro)} samples, "
          f"FX={FX:.1f}")
    fx_calib = calibrate_fx(frames, idx, gyro,
                            Path(ROOT / "out" / "record_replay"))
    print(f"[calib] FX scale x{fx_calib['fx_scale']:.2f} -> {fx_calib['fx_eff']:.0f}, "
          f"prop err median {fx_calib['prop_err_median_px']:.1f}px")

    t0 = time.monotonic()
    df, prop = run_extended(frames, idx, gyro)
    print(f"[run] {time.monotonic() - t0:.1f}s")

    # 基线对照：现状只有 FULL 可用（linefit report rate）
    base = pd.read_csv(out_dir.parent / "record_replay" / "linefit_replay.csv") \
        if (out_dir.parent / "record_replay" / "linefit_replay.csv").exists() else None
    res, g, gaps = evaluate(df, idx, gyro, detect)
    res["baseline_usable_rate"] = float((base["locked"] & base["cross_valid"]).mean()) \
        if base is not None else None
    print(f"[eval] availability: {res['availability']}")
    print(f"[eval] usable {res['usable_rate']:.1%} vs baseline "
          f"{res['baseline_usable_rate']:.1%}")
    if len(g):
        print(f"[eval] gap end err by dur: {json.dumps(res['gap_end_err_by_dur'], indent=1)}")

    df.to_csv(out_dir / "extended_frames.csv", index=False)

    # 零偏漂移对比（静止段 gyro-only）
    drift = drift_test(frames, idx, gyro, prop.bias)
    res["drift_test"] = drift
    res["bias_final"] = [float(x) for x in prop.bias]
    print(f"[drift] bias_on {drift['bias_on']['drift_px_per_s']:.1f} px/s vs "
          f"bias_off {drift['bias_off']['drift_px_per_s']:.1f} px/s "
          f"(end err {drift['bias_on']['err_end']:.0f}/{drift['bias_off']['err_end']:.0f})")

    # T_max 扫描（可用率 vs 出界率权衡）
    sweep = {}
    for tm in (1.0, 2.0, 3.0, 5.0):
        df2, _ = run_extended(frames, idx, gyro, t_max=tm)
        lv2 = df2["level"]
        usable = lv2.isin(["FULL", "PARTIAL", "GYRO_ONLY"]).mean()
        inb = df2["cross_x"].between(0, NORM_W) & df2["cross_y"].between(0, NORM_H)
        g_only = lv2 == "GYRO_ONLY"
        sweep[f"{tm}s"] = {"usable": float(usable),
                           "gyro_only_in_bounds": float(inb[g_only.to_numpy()].mean())
                           if g_only.any() else None}
        print(f"[T_max={tm}] usable {usable:.1%}, gyro_only in-bounds "
              f"{sweep[f'{tm}s']['gyro_only_in_bounds']}")
    res["t_max_sweep"] = sweep
    if len(g):
        g.to_csv(out_dir / "gaps.csv", index=False)
    plot_availability(df, out_dir)
    if len(g):
        plot_gap_errors(g, out_dir)

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"summary -> {out_dir}/summary.json")

    if args.annotate:
        paths = annotate_partial(frames, df, out_dir)
        print(f"annotated {len(paths)} PARTIAL frames -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
