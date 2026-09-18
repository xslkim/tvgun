#!/usr/bin/env python3
"""视频 + 仿真 IMU 融合算法验证（手机光枪）。

在 scripts/run_video_test.py（复刻手机端检测管线）基础上验证融合算法规格
（与手机 App 端严格一致）：
  状态 p = 准星规范坐标 (x,y)
  陀螺 tick（200Hz）：p += (ω_h·dt·S, ω_v·dt·S)，S = 像素/弧度系数
  相机帧且 locked && crossValid：p ← 0.7·p + 0.3·p_camera（互补校正）
  失锁 ≤1s：继续陀螺外推，predicted=true；>1s 冻结，predicted=false
  重新锁定时校正并清 predicted

真值与测量模型（关键建模选择，在此注明）：
  * 手持运动是低频的，检测管线输出 cross 含 ~6 规范单位的逐帧抖动噪声。
    若直接把原始 cross 线性插值当真值，陀螺真值将携带全部检测噪声，
    融合评估失去意义（校正残差恒为 0）。故：
      真值轨迹 cross_true = 锁定帧 cross 的 5 帧滑动平均（去检测噪声）后线性插值；
      相机测量 p_camera = 原始 cross（含噪声，与真机一致）。
  * S 标定：采用 sim/imu.py 的项目标定值 PX_PER_DEG=40 px/°（0.6m 观看距离），
    规范坐标 1920 宽等同屏幕像素，故 S = 40·180/π ≈ 2291.8 规范单位/rad。
    规格中"cross 位移/四边形旋转角回归"的路线在本视频上退化（见报告：
    准星位移来自 yaw/pitch 平移，与四边形 roll 角不相关），故同时给出
    Δcross vs 四边形中心位移 的回归作为比例性交叉验证。
  * 陀螺噪声模型复用 sim/imu.py 的常量与结构（白噪声 σ=0.02°/s +
    偏置随机游走初值 ±0.5°/s、强度 0.02°/s/√s + 量化 0.01°/s）；
    HandMotion 接口是自主轨迹生成器，不适配"重放视频真值"，故噪声模型
    按同等参数自行实现（常量直接从 sim.imu 导入）。

三配置：A) 相机-only；B) 融合（失锁即冻结）；C) 融合 + 失锁外推（≤1s）。
真实视频的失锁段很短（≤0.5s），为考核 ≤1s/>1s 外推逻辑，另注入 25 段
0.3~2.5s 的合成遮蔽窗口（seed 固定）评估 C 的重新锁定误差。

任务 4：60Hz 把 C 的融合准星 POST 到电视端 /aim，截屏抽查。

用法:
  python scripts/run_video_imu.py [--skip-live] [--video ...] [--out ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from run_video_test import (  # noqa: E402
    Detector, NORM_W, NORM_H, cyan_centroid, detect_duck, find_ring,
    http_json, map_point, raise_tv_window, ring_mapping, tv_norm_to_px,
)
from sim.imu import (  # noqa: E402
    GYRO_BIAS0, GYRO_BIAS_RW, GYRO_NOISE, GYRO_QUANT, PX_PER_DEG,
)

FPS = 30.0
IMU_HZ = 200
S_PX_PER_RAD = PX_PER_DEG * 180.0 / np.pi   # ≈ 2291.8 规范单位/rad
CORRECT_GAIN = 0.3                          # 互补校正增益（规格）
EXTRAP_TIMEOUT = 1.0                        # 失锁外推上限（s）

# 合成遮蔽 Monte Carlo：每次运行注入单个独立遮蔽窗口，统计重新锁定误差
N_MC = 60
MC_DUR = (0.2, 2.2)       # 遮蔽时长范围（覆盖 <1s 外推与 >1s 冻结两档）
MC_RANGE = (2.0, 19.0)
MC_SEED = 1000


# ------------------------------------------------------------ 任务 1：视频运动真值

def run_pipeline(video: str) -> pd.DataFrame:
    """检测管线跑全视频，逐帧输出 cross 与四边形几何量。"""
    import cv2
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    det = Detector()
    rows = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        det.process(frame)
        q = det.corners.reshape(4, 2)  # TL,TR,BR,BL 检测图坐标
        ctr = q.mean(axis=0)
        roll = float(np.degrees(np.arctan2(q[1, 1] - q[0, 1], q[1, 0] - q[0, 0])))
        scale = float((np.hypot(*(q[1] - q[0])) + np.hypot(*(q[2] - q[3]))) / 2)
        rows.append({"frame": idx, "t": idx / FPS,
                     "locked": det.locked, "cross_valid": det.cross_valid,
                     "cross_x": det.cross[0], "cross_y": det.cross[1],
                     "quad_cx": ctr[0], "quad_cy": ctr[1],
                     "quad_roll_deg": roll, "quad_w": scale})
        idx += 1
    cap.release()
    return pd.DataFrame(rows)


def build_truth(df: pd.DataFrame, smooth_win: int = 5):
    """真值 = 锁定帧 cross 滑动平均后的线性插值；测量 = 原始 cross。"""
    v = df["locked"] & df["cross_valid"]
    t = df["t"].to_numpy()
    meas_x = df["cross_x"].to_numpy()
    meas_y = df["cross_y"].to_numpy()
    ker = np.ones(smooth_win) / smooth_win
    sx = np.convolve(meas_x[v], ker, mode="same")
    sy = np.convolve(meas_y[v], ker, mode="same")
    # 滑动平均边缘用原始值回填，避免端点塌陷
    k = smooth_win // 2
    sx[:k], sx[-k:] = meas_x[v][:k], meas_x[v][-k:]
    sy[:k], sy[-k:] = meas_y[v][:k], meas_y[v][-k:]
    tv = t[v]
    truth_x = np.interp(t, tv, sx)
    truth_y = np.interp(t, tv, sy)
    return meas_x, meas_y, truth_x, truth_y, v.to_numpy()


def calibrate_S(df: pd.DataFrame) -> dict:
    """S 标定的两种路线对比（报告用）。"""
    v = (df["locked"] & df["cross_valid"]).to_numpy()
    dtheta = np.diff(np.deg2rad(df["quad_roll_deg"].to_numpy()[v]))
    dcx = np.diff(df["cross_x"].to_numpy()[v])
    dcy = np.diff(df["cross_y"].to_numpy()[v])
    dqx = np.diff(df["quad_cx"].to_numpy()[v])
    dqy = np.diff(np.asarray(df["quad_cy"].to_numpy()[v]))

    def reg(dx, dy):
        m = np.abs(dx) > 1e-9
        if m.sum() < 3:
            return float("nan"), float("nan")
        slope = float((dx[m] * dy[m]).sum() / (dx[m] ** 2).sum())
        ss_res = float(((dy[m] - slope * dx[m]) ** 2).sum())
        ss_tot = float(((dy[m] - dy[m].mean()) ** 2).sum())
        return slope, 1.0 - ss_res / max(ss_tot, 1e-12)

    out = {}
    out["roll_route_slope_x"], out["roll_route_r2_x"] = reg(dtheta, dcx)
    out["roll_route_slope_y"], out["roll_route_r2_y"] = reg(dtheta, dcy)
    out["center_route_kx"], out["center_route_r2_x"] = reg(dqx, dcx)
    out["center_route_ky"], out["center_route_r2_y"] = reg(dqy, dcy)
    out["norm_per_det_px_geom"] = float(NORM_W / df["quad_w"][v].mean())
    out["S_px_per_rad"] = S_PX_PER_RAD
    out["S_note"] = ("采用 sim/imu.py PX_PER_DEG=40 -> S=40*180/pi≈2291.8 规范单位/rad；"
                     "roll 回归路线退化（准星位移来自 yaw/pitch 平移而非 roll），"
                     "中心位移回归 k≈NORM_W/quad_w 验证比例性")
    return out


# ------------------------------------------------------------ 任务 2：仿真 IMU 流

def synth_gyro(t: np.ndarray, truth_x: np.ndarray, truth_y: np.ndarray,
               seed: int = 42, bias_scale: float = 1.0):
    """由真值轨迹合成 200Hz 陀螺流（deg/s），噪声模型同 sim/imu.py。

    返回 (gyro_h, gyro_v)，单位 deg/s，对应准星水平/竖直角速度。
    """
    rng = np.random.default_rng(seed)
    n = len(t)
    dt = 1.0 / IMU_HZ
    # 真值角速度：准星速度（规范单位/s）/ PX_PER_DEG -> deg/s
    vx = np.gradient(np.interp(t, t[0] + np.arange(len(truth_x)) / FPS, truth_x), dt)
    vy = np.gradient(np.interp(t, t[0] + np.arange(len(truth_y)) / FPS, truth_y), dt)
    w_true = np.stack([vx, vy], axis=1) / PX_PER_DEG  # deg/s

    bias = rng.uniform(-GYRO_BIAS0, GYRO_BIAS0, 2) * bias_scale
    bias = bias + np.cumsum(rng.normal(0.0, GYRO_BIAS_RW * np.sqrt(dt), (n, 2)), axis=0)
    gyro = w_true + bias + rng.normal(0.0, GYRO_NOISE, (n, 2))
    gyro = np.round(gyro / GYRO_QUANT) * GYRO_QUANT
    return gyro[:, 0], gyro[:, 1], bias.copy()


# ------------------------------------------------------------ 任务 3：融合仿真

def run_fusion(df, gyro_h, gyro_v, meas_mask, allow_extrapolate):
    """200Hz tick 级融合仿真。

    meas_mask: 每帧是否有相机测量（locked&&valid 且未被合成遮蔽）。
    allow_extrapolate: False=配置B（失锁即冻结），True=配置C（外推≤1s）。
    返回 (tick 级输出 DataFrame 所需数组, relock 误差列表)。
    """
    t_frame = df["t"].to_numpy()
    meas_x = df["cross_x"].to_numpy()
    meas_y = df["cross_y"].to_numpy()
    n_frames = len(df)
    duration = t_frame[-1]
    n_ticks = int(round(duration * IMU_HZ)) + 1
    dt = 1.0 / IMU_HZ
    # 帧 f 的测量在第一个 >= t_f 的 tick 生效（模拟 30fps 到达）
    frame_tick = np.minimum(np.ceil(t_frame * IMU_HZ).astype(int), n_ticks - 1)

    p = None
    last_meas_t = -1e9
    frozen = True
    predicted = False
    relock_errs = []   # (err, was_predicted, t) —— 外推中校正 / 冻结后校正分开统计
    out = np.full((n_ticks, 2), np.nan)
    pred_flag = np.zeros(n_ticks, dtype=bool)
    fi = 0
    for k in range(n_ticks):
        t = k * dt
        if p is not None and not frozen:
            p = p + np.array([gyro_h[k], gyro_v[k]]) * dt * PX_PER_DEG
        while fi < n_frames and frame_tick[fi] == k:
            if meas_mask[fi]:
                m = np.array([meas_x[fi], meas_y[fi]])
                if p is not None and t - last_meas_t > 1.5 / FPS:
                    # 经历了至少一次失锁后的重新锁定：记录外推/冻结残差
                    relock_errs.append((float(np.hypot(*(p - m))), predicted, t))
                p = m if p is None else (1 - CORRECT_GAIN) * p + CORRECT_GAIN * m
                last_meas_t = t
                frozen = False
                predicted = False
            else:
                # 该帧无测量：按配置决定是否外推/冻结
                if p is not None:
                    gap = t - last_meas_t
                    if allow_extrapolate and gap <= EXTRAP_TIMEOUT:
                        predicted = True
                    elif allow_extrapolate and gap > EXTRAP_TIMEOUT:
                        frozen = True
                        predicted = False
                    else:
                        frozen = True  # 配置 B：失锁即冻结
            fi += 1
        if p is not None:
            out[k] = p
            pred_flag[k] = predicted
    return out, pred_flag, relock_errs


def frame_outputs(tick_out, df):
    """在相机帧时刻采样 tick 级输出。"""
    idx = np.minimum(np.ceil(df["t"].to_numpy() * IMU_HZ).astype(int), len(tick_out) - 1)
    return tick_out[idx]


def jitter_stats(vals):
    d = np.linalg.norm(np.diff(vals, axis=0), axis=1)
    return {"median": float(np.median(d)), "p95": float(np.percentile(d, 95)),
            "max": float(d.max())}


# ------------------------------------------------------------ 图

def plot_traj(df, truth_x, truth_y, p_a, p_b, p_c, out_dir):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    t = df["t"]
    for ax, meas, tru, a, b, c, name in (
            (axes[0], df["cross_x"], truth_x, p_a[:, 0], p_b[:, 0], p_c[:, 0], "x"),
            (axes[1], df["cross_y"], truth_y, p_a[:, 1], p_b[:, 1], p_c[:, 1], "y")):
        ax.plot(t, meas, ".", color="0.7", ms=2, label="camera meas (raw cross)")
        ax.plot(t, tru, "g-", lw=1.2, label="truth (smoothed)")
        ax.plot(t, a, "r-", lw=0.8, drawstyle="steps-post", label="A camera-only")
        ax.plot(t, b, "b-", lw=0.8, alpha=0.8, label="B fusion")
        ax.plot(t, c, "m-", lw=0.8, alpha=0.6, label="C fusion+extrap")
        ax.set_ylabel(f"{name} (norm)")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)
    axes[1].set_xlabel("t (s)")
    fig.suptitle("trajectory: A vs B vs C")
    fig.tight_layout()
    fig.savefig(out_dir / "traj_compare.png", dpi=110)
    plt.close(fig)


def plot_loss_zoom(df, truth_x, truth_y, demo_windows, demo_ticks, out_dir):
    """3 个代表性遮蔽窗口的放大图：0.5s 纯外推 / 1.0s 临界 / 2.0s 冻结。"""
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    for ax, (b0, b1), (tick_out, rl) in zip(axes, demo_windows, demo_ticks):
        n_ticks = len(tick_out)
        m = (df["t"] >= b0 - 0.4) & (df["t"] <= b1 + 0.4)
        k0, k1 = max(int((b0 - 0.4) * IMU_HZ), 0), min(int((b1 + 0.4) * IMU_HZ), n_ticks - 1)
        tk = np.arange(k0, k1 + 1) / IMU_HZ
        ax.plot(df["t"][m], truth_x[m], "g-", lw=1.5, label="truth x")
        avail = df["locked"] & df["cross_valid"]
        show = m & avail & ~((df["t"] >= b0) & (df["t"] <= b1))
        ax.plot(df["t"][show], df["cross_x"][show], "k.", ms=5, label="camera meas")
        ax.plot(tk, tick_out[k0:k1 + 1, 0], "m-", lw=1.2, label="C output x")
        ax.axvspan(b0, b1, color="red", alpha=0.12, label="blackout")
        if b1 - b0 > EXTRAP_TIMEOUT:
            ax.axvline(b0 + EXTRAP_TIMEOUT, color="orange", ls="--", lw=1,
                       label="freeze@1s")
        for err, was_pred, rt in rl:
            if abs(rt - b1) > 0.15:
                continue  # 只标注注入遮蔽对应的重新锁定（附近有真实失锁时会混入）
            ax.annotate(f"relock err={err:.1f}\n({'extrapolating' if was_pred else 'frozen'})",
                        xy=(rt, float(np.interp(rt, df['t'], truth_x))),
                        xytext=(rt - 0.55, float(np.interp(rt, df['t'], truth_x)) + 15),
                        arrowprops=dict(arrowstyle="->", color="red"), color="red",
                        fontsize=9)
        ax.set_title(f"blackout {b0:.2f}s~{b1:.2f}s ({b1 - b0:.1f}s)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "loss_zoom.png", dpi=110)
    plt.close(fig)


def plot_err_hist(err_real, err_mc, err_mc_b3, mc_df, out_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
    bins = np.linspace(0, max(max(err_mc or [1]), max(err_mc_b3 or [1])) * 1.05, 30)
    if err_mc:
        ax1.hist(err_mc, bins=bins, alpha=0.6,
                 label=f"C MC bias x1 (n={len(err_mc)})")
    if err_mc_b3:
        ax1.hist(err_mc_b3, bins=bins, alpha=0.6,
                 label=f"C MC bias x3 (n={len(err_mc_b3)})")
    if err_real:
        for e in err_real:
            ax1.axvline(e, color="k", ls=":", lw=1)
        ax1.plot([], [], "k:", label=f"real unlock relocks (n={len(err_real)})")
    ax1.set_xlabel("|p_pred - p_camera| at relock (norm units)")
    ax1.set_ylabel("count")
    ax1.set_title("relock error, extrapolating (blackout <=1s)")
    ax1.legend()
    ax1.grid(alpha=0.3)
    # 误差 vs 遮蔽时长散点（外推档近似 bias·dur 线性增长，冻结档饱和）
    for bs, color in ((1.0, "tab:blue"), (3.0, "tab:red")):
        sub = mc_df[mc_df["bias_scale"] == bs]
        ax2.scatter(sub["dur"], sub["err"], s=14, alpha=0.6, color=color,
                    label=f"bias x{int(bs)}")
    ax2.axvline(EXTRAP_TIMEOUT, color="orange", ls="--", lw=1, label="freeze@1s")
    ax2.set_xlabel("blackout duration (s)")
    ax2.set_ylabel("relock err (norm units)")
    ax2.set_title("relock error vs blackout duration")
    ax2.legend()
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "relock_err_hist.png", dpi=110)
    plt.close(fig)


# ------------------------------------------------------------ 任务 4：60Hz 上电视

def live_replay(df, tick_out_c, tv_url, out_dir, dur_s=10.0, t_start=3.0):
    """以 60Hz 回放 C 融合准星 POST /aim；再以 15Hz 回放 A（相机-only 阶梯）对照。
    截屏找青色准星，比较相邻截屏位移分布。"""
    from PIL import ImageGrab

    try:
        http_json(f"{tv_url}/state", timeout=3.0)
    except Exception as e:
        print(f"[live] TV unreachable: {e}")
        return None
    raise_tv_window(True)
    time.sleep(0.5)
    a = np.array(ImageGrab.grab())
    ring = find_ring(a)
    if ring is None:
        print("[live] game window not visible")
        raise_tv_window(False)
        return None
    to_screen = ring_mapping(ring)

    def replay(get_pos, rate_hz, tag):
        """get_pos(t)->(x,y)|None；真实时间同步回放（落后即跳到当前时刻），
        截屏期望位置用最近一次实际 POST 的准星值（截图拍到的就是它）。"""
        obs = []
        t0 = time.monotonic()
        last_post = -1.0
        last_pos = None
        next_grab = 0.5
        while True:
            now = time.monotonic() - t0
            if now > dur_s:
                break
            tl = t_start + now
            if now - last_post >= 1.0 / rate_hz:
                pos = get_pos(tl)
                if pos is not None and np.all(np.isfinite(pos)):
                    try:
                        http_json(f"{tv_url}/aim",
                                  {"x": float(pos[0]), "y": float(pos[1])}, timeout=2.0)
                        last_pos = (float(pos[0]), float(pos[1]))
                    except Exception:
                        pass
                    last_post = now
            if now >= next_grab:
                a = np.array(ImageGrab.grab())
                ring = find_ring(a)
                if ring is not None and last_pos is not None:
                    ts_map = ring_mapping(ring)
                    meas, n_cyan = cyan_centroid(a, ring)
                    if meas is not None:
                        exp = ts_map(*tv_norm_to_px(*last_pos))
                        dev = float(np.hypot(meas[0] - exp[0], meas[1] - exp[1]))
                        obs.append({"config": tag, "t": now, "sx": meas[0], "sy": meas[1],
                                    "dev_px": dev})
                next_grab = now + 0.35
            else:
                # 混合睡眠+自旋，保证 60Hz 上报精度（Windows sleep 粒度 ~15ms）
                target = min(last_post + 1.0 / rate_hz, next_grab)
                rem = target - now
                if rem > 0.004:
                    time.sleep(rem - 0.002)
        return obs

    n_ticks = len(tick_out_c)

    def pos_c(tl):
        k = int(round(tl * IMU_HZ))
        if 0 <= k < n_ticks and np.all(np.isfinite(tick_out_c[k])):
            return tick_out_c[k]
        return None

    # A 配置：30fps 阶梯（取整到帧），以 15Hz 上报
    meas_x = df["cross_x"].to_numpy()
    meas_y = df["cross_y"].to_numpy()
    t_frame = df["t"].to_numpy()
    valid = (df["locked"] & df["cross_valid"]).to_numpy()

    def pos_a(tl):
        f = int(tl * FPS)
        f = min(f, len(df) - 1)
        while f > 0 and not valid[f]:
            f -= 1
        if valid[f]:
            return np.array([meas_x[f], meas_y[f]])
        return None

    print("[live] replay C @60Hz ...")
    obs_c = replay(pos_c, 60.0, "C@60Hz")
    time.sleep(1.0)
    print("[live] replay A @15Hz (camera-only staircase) ...")
    obs_a = replay(pos_a, 15.0, "A@15Hz")
    raise_tv_window(False)

    obs = pd.DataFrame(obs_c + obs_a)
    obs.to_csv(out_dir / "live_imu.csv", index=False)
    res = {}
    for tag in ("C@60Hz", "A@15Hz"):
        o = obs[obs["config"] == tag]
        if len(o) >= 2:
            d = np.linalg.norm(np.diff(o[["sx", "sy"]].to_numpy(), axis=0), axis=1)
            dtg = np.diff(o["t"].to_numpy())
            rate = d / np.maximum(dtg, 1e-6)  # px/s，按截屏间隔归一
            res[tag] = {"grabs": int(len(o)),
                        "dev_px_median": float(o["dev_px"].median()),
                        "dev_px_max": float(o["dev_px"].max()),
                        "step_median": float(np.median(d)),
                        "step_p95": float(np.percentile(d, 95)),
                        "step_max": float(d.max()),
                        "step_cv": float(d.std() / max(d.mean(), 1e-9)),
                        "speed_px_s_median": float(np.median(rate)),
                        "speed_px_s_cv": float(rate.std() / max(rate.mean(), 1e-9))}
        else:
            res[tag] = {"grabs": int(len(o))}
    print(f"[live] {json.dumps(res, indent=1)}")
    return res


# ------------------------------------------------------------ 主流程

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", default=str(ROOT / "test_res" / "screen_video.mp4"))
    p.add_argument("--out", default=str(ROOT / "out" / "video_imu"))
    p.add_argument("--tv", default="http://192.168.3.19:8000")
    p.add_argument("--skip-live", action="store_true")
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 任务 1
    t0 = time.monotonic()
    df = run_pipeline(args.video)
    print(f"pipeline: {len(df)} frames in {time.monotonic() - t0:.1f}s, "
          f"lock rate {df['locked'].mean():.1%}")
    meas_x, meas_y, truth_x, truth_y, valid = build_truth(df)
    df["truth_x"], df["truth_y"] = truth_x, truth_y
    s_calib = calibrate_S(df)
    print(f"S calib: roll-route R2 x={s_calib['roll_route_r2_x']:.3f} y={s_calib['roll_route_r2_y']:.3f}; "
          f"center-route kx={s_calib['center_route_kx']:.2f} ky={s_calib['center_route_ky']:.2f} "
          f"(geom {s_calib['norm_per_det_px_geom']:.2f}) R2 x={s_calib['center_route_r2_x']:.3f} "
          f"y={s_calib['center_route_r2_y']:.3f}; S={s_calib['S_px_per_rad']:.1f} norm/rad")

    # ---- 任务 2
    duration = df["t"].iloc[-1]
    n_ticks = int(round(duration * IMU_HZ)) + 1
    ts = np.arange(n_ticks) / IMU_HZ
    gyro_h, gyro_v, bias = synth_gyro(ts, truth_x, truth_y, seed=42)
    gyro_h_b3, gyro_v_b3, _ = synth_gyro(ts, truth_x, truth_y, seed=42, bias_scale=3.0)

    # ---- 任务 3
    df["meas_avail"] = valid  # 真实可用性

    # A：相机-only（帧时刻输出 = 测量，阶梯）
    p_a = np.stack([meas_x, meas_y], axis=1)
    p_a[~valid] = np.nan

    tick_b, _, _ = run_fusion(df, gyro_h, gyro_v, valid, allow_extrapolate=False)
    tick_c, pred_c, relock_real = run_fusion(df, gyro_h, gyro_v, valid,
                                             allow_extrapolate=True)

    # 合成遮蔽 Monte Carlo：每轮独立窗口 + 独立陀螺噪声实现，bias×3 成对重跑
    mc = []  # (dur, bias_scale, err, was_predicted)
    for r in range(N_MC):
        rng = np.random.default_rng(MC_SEED + r)
        b0 = rng.uniform(*MC_RANGE)
        dur = rng.uniform(*MC_DUR)
        mask = valid & ~((df["t"] >= b0) & (df["t"] <= b0 + dur)).to_numpy()
        gh, gv, _ = synth_gyro(ts, truth_x, truth_y, seed=5000 + r)
        gh3, gv3, _ = synth_gyro(ts, truth_x, truth_y, seed=5000 + r, bias_scale=3.0)
        for bs, g1, g2 in ((1.0, gh, gv), (3.0, gh3, gv3)):
            _, _, rl = run_fusion(df, g1, g2, mask, allow_extrapolate=True)
            for err, was_pred, rt in rl:
                if b0 + dur - 0.05 <= rt <= b0 + dur + 0.2:  # 只保留注入遮蔽对应的重新锁定
                    mc.append({"dur": dur, "bias_scale": bs, "err": err,
                               "predicted": was_pred})
    mc_df = pd.DataFrame(mc)
    mc_df.to_csv(out_dir / "mc_relock.csv", index=False)

    # 放大图用：3 个代表性遮蔽窗口（0.5s 外推 / 1.0s 临界 / 2.0s 冻结）
    demo_windows = [(5.0, 5.5), (9.0, 10.0), (13.0, 15.0)]
    demo_ticks = []
    for b0, b1 in demo_windows:
        mask = valid & ~((df["t"] >= b0) & (df["t"] <= b1)).to_numpy()
        tout, _, rl = run_fusion(df, gyro_h, gyro_v, mask, allow_extrapolate=True)
        demo_ticks.append((tout, rl))

    p_b = frame_outputs(tick_b, df)
    p_c = frame_outputs(tick_c, df)

    df["p_a_x"], df["p_a_y"] = p_a[:, 0], p_a[:, 1]
    df["p_b_x"], df["p_b_y"] = p_b[:, 0], p_b[:, 1]
    df["p_c_x"], df["p_c_y"] = p_c[:, 0], p_c[:, 1]
    df["predicted_c"] = frame_outputs(pred_c.astype(float), df).astype(bool)
    df.to_csv(out_dir / "imu_frames.csv", index=False)

    # 指标
    jit_a = jitter_stats(p_a[valid])
    jit_b = jitter_stats(p_b[valid])
    # 检测噪声量级估计（测量 - 平滑真值），用于解释 A vs B 抖动对比
    noise = np.stack([meas_x - truth_x, meas_y - truth_y], axis=1)[valid]
    noise_std = float(noise.std())
    noise_med = float(np.median(np.linalg.norm(noise, axis=1)))
    # 200Hz 平滑度：tick 级相邻步长（A 上采样到 200Hz 为阶梯：96% tick 步长为 0，
    # 每 6~7 tick 跳一次完整帧间位移；用帧级步长 jit_a 对照 B/C 的 tick 步长）
    tb = tick_b[np.all(np.isfinite(tick_b), axis=1)]
    tc = tick_c[np.all(np.isfinite(tick_c), axis=1)]
    step_b = jitter_stats(tb)
    step_c = jitter_stats(tc)

    def err_stats(e):
        if not e:
            return {}
        return {"n": len(e), "median": float(np.median(e)),
                "p95": float(np.percentile(e, 95)), "max": float(np.max(e))}

    def split_errs(rl):
        """relock 列表 (err, was_predicted, t) -> (外推中校正, 冻结后校正)。"""
        return ([e for e, pr, _ in rl if pr], [e for e, pr, _ in rl if not pr])

    real_ext, real_frz = split_errs(relock_real)
    mc_ext = mc_df[mc_df["predicted"] & (mc_df["bias_scale"] == 1.0)]["err"]
    mc_frz = mc_df[~mc_df["predicted"] & (mc_df["bias_scale"] == 1.0)]["err"]
    mc_ext_b3 = mc_df[mc_df["predicted"] & (mc_df["bias_scale"] == 3.0)]["err"]
    mc_frz_b3 = mc_df[~mc_df["predicted"] & (mc_df["bias_scale"] == 3.0)]["err"]

    metrics = {
        "S_calibration": s_calib,
        "jitter_A_camera_only": jit_a,
        "jitter_B_fusion": jit_b,
        "detector_noise_norm_units": {"std": noise_std, "median_abs": noise_med},
        "jitter_note": "30Hz 抖动 A≈B 为预期：cross 逐帧位移由真实手持运动主导，"
                       "检测噪声占比小；融合收益体现在 200Hz tick 步长与失锁桥接",
        "tick_step_A_equiv_frame_step": jit_a,
        "tick_step_B_200Hz": step_b,
        "tick_step_C_200Hz": step_c,
        "relock_err_C_real_extrapolating": err_stats(real_ext),
        "relock_err_C_real_frozen": err_stats(real_frz),
        "relock_err_C_mc_extrapolating": err_stats(list(mc_ext)),
        "relock_err_C_mc_frozen": err_stats(list(mc_frz)),
        "relock_err_C_mc_bias_x3_extrapolating": err_stats(list(mc_ext_b3)),
        "relock_err_C_mc_bias_x3_frozen": err_stats(list(mc_frz_b3)),
        "bias_x3_degradation_median_ratio_extrapolating":
            float(np.median(mc_ext_b3) / np.median(mc_ext)) if len(mc_ext) and len(mc_ext_b3) else None,
        "monte_carlo": {"n_windows": N_MC, "dur_range": MC_DUR, "seed": MC_SEED},
        "gyro_noise": {"white_deg_s": GYRO_NOISE, "bias0_deg_s": GYRO_BIAS0,
                       "bias_rw": GYRO_BIAS_RW, "quant_deg_s": GYRO_QUANT,
                       "bias0_abs_deg_s": [float(abs(bias[0, 0])), float(abs(bias[0, 1]))]},
    }
    print(f"jitter A median/p95: {jit_a['median']:.2f}/{jit_a['p95']:.2f} | "
          f"B {jit_b['median']:.2f}/{jit_b['p95']:.2f} norm units; "
          f"detector noise std {noise_std:.2f}")
    print(f"relock MC extrapolating: {err_stats(list(mc_ext))}")
    print(f"relock MC frozen>1s: {err_stats(list(mc_frz))}")
    print(f"relock MC bias x3 extrapolating: {err_stats(list(mc_ext_b3))}")
    print(f"relock MC bias x3 frozen>1s: {err_stats(list(mc_frz_b3))}")

    # ---- 图
    plot_traj(df, truth_x, truth_y, p_a, p_b, p_c, out_dir)
    plot_loss_zoom(df, truth_x, truth_y, demo_windows, demo_ticks, out_dir)
    plot_err_hist(real_ext, list(mc_ext), list(mc_ext_b3), mc_df, out_dir)

    # ---- 任务 4
    if not args.skip_live:
        live = live_replay(df, tick_c, args.tv, out_dir)
        if live is not None:
            metrics["live"] = live

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"summary -> {out_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
