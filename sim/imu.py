"""第二期扩展（SPEC2.md §1）：手持运动轨迹 + IMU 噪声仿真 + 解码先验提取。

物理设定：望远镜 = 手机，用户手持对准屏幕缓慢移动。
- HandMotion：确定性手持运动轨迹（慢漂 + 8~12Hz 带限手震），seed 可复现。
- simulate_imu：200Hz 陀螺仪/加速度计噪声模型
  （白噪声 + 偏置随机游走 + 量化 + IMU-相机安装误差）。
- IMUStream.prior_at(t)：带噪积分后的 IMUPrior（非真值）——
  roll 经互补滤波（陀螺为主、重力纠漂，漂移有界）；tilt_pitch 由重力向量估计；
  tilt_yaw 重力不可观测，仅陀螺积分，漂移较大（自测中单独给包络）；
  frame_deltas 由陀螺积分的视轴转角换算成帧间中心位移（屏幕像素，含噪声）。

几何约定（小角度手持模型）：
  相机体系 x=图像右，y=图像下，z=光轴指向屏幕；世界系 z 向上，屏幕竖直。
  roll θ 绕光轴，pitch φ 为光轴仰角，yaw ψ 绕世界竖直轴。
  重力在相机系的投影 g_b = g·(cosφ·sinθ, cosφ·cosθ, -sinφ)，
  故 θ = atan2(g_x, g_y)、φ = asin(-g_z/g) 均可由加速度计直接观测。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from .config import IMUPrior, SCREEN_W, SCREEN_H
except ImportError:  # 支持 python3 sim/imu.py 直接运行自测
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim.config import IMUPrior, SCREEN_W, SCREEN_H

G = 9.81                    # 重力加速度 m/s²
PX_PER_DEG = 40.0           # 视轴每转 1° 视场中心在屏幕上移动的像素（约 0.6m 观看距离的合理值）
GEN_FS = 240.0              # 轨迹内部生成采样率（Hz），sample() 线性插值
TREMOR_BAND = (8.0, 12.0)   # 手震频带（Hz）

# slow / fast 两档参数（fast = 3 倍速度，SPEC2 §1）
_SPEED = {
    "slow": dict(drift_px_s=30.0, roll_rate=2.0, tremor_px=0.3, tremor_deg=0.1,
                 tilt_lim=10.0, ou_lambda=0.10),
    "fast": dict(drift_px_s=90.0, roll_rate=6.0, tremor_px=1.5, tremor_deg=0.4,
                 tilt_lim=25.0, ou_lambda=0.05),
}

# 传感器噪声参数（SPEC2 §1）
GYRO_NOISE = 0.02       # 陀螺白噪声 σ（°/s）
GYRO_BIAS0 = 0.5        # 陀螺偏置初值 ±（°/s），随后随机游走
GYRO_BIAS_RW = 0.02     # 偏置随机游走强度（°/s/√s）
GYRO_QUANT = 0.01       # 陀螺量化步长（°/s）
ACCEL_NOISE = 0.05      # 加速度计白噪声 σ（m/s²）
ACCEL_BIAS = 0.02       # 加速度计偏置 ±（m/s²）
MOUNT_ERR_DEG = 1.0     # IMU-相机安装误差：±1° 固定小旋转
TAU_ROLL = 3.0          # roll 互补滤波重力纠漂时间常数（s）


@dataclass
class MotionState:
    """t 时刻的手持姿态真值。"""
    center_x: float      # 视场中心，屏幕像素
    center_y: float
    roll_deg: float      # 相机绕光轴滚转角（度）
    tilt_pitch_deg: float  # 视轴俯仰（度）
    tilt_yaw_deg: float    # 视轴偏航（度）


def _band_noise(rng: np.random.Generator, n: int, fs: float,
                f_lo: float, f_hi: float) -> np.ndarray:
    """带限白噪声：频域置带外为 0 后逆变换，输出归一化到 std=1。"""
    w = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    w[(freqs < f_lo) | (freqs > f_hi)] = 0.0
    x = np.fft.irfft(w, n)
    return x / (x.std() + 1e-12)


def _ou_process(rng: np.random.Generator, n: int, fs: float,
                rate_std: float, lam: float) -> np.ndarray:
    """均值回归（OU）角度过程：角速度为低频带限噪声，-lam*x 项把 tilt 约束在界内。"""
    dt = 1.0 / fs
    u = _band_noise(rng, n, fs, 0.05, 0.5) * rate_std  # 角速度驱动（°/s）
    x = np.zeros(n)
    a, b = 1.0 - lam * dt, dt
    for k in range(1, n):
        x[k] = a * x[k - 1] + b * u[k]
    return x


class HandMotion:
    """手持运动轨迹生成器：慢漂（随机方向）+ 8~12Hz 手震，seed 可复现。"""

    def __init__(self, seed: int, duration_s: float = 2.0, speed: str = "slow"):
        if speed not in _SPEED:
            raise ValueError(f"speed 必须是 {sorted(_SPEED)}，得到 {speed!r}")
        self.seed = int(seed)
        self.duration_s = float(duration_s)
        self.speed = speed
        p = _SPEED[speed]
        rng = np.random.default_rng(self.seed)
        n = int(round(self.duration_s * GEN_FS)) + 1
        self._t = np.arange(n) / GEN_FS

        # 慢漂：视轴俯仰/偏航 = OU 有界随机游走；俯仰再叠加随机持机姿态偏移。
        # （偏航角重力不可观测，陀螺积分只能跟踪变化量，故静态偏移只加在俯仰上，
        #   否则 tilt_yaw 先验会带一个不可估的固定偏差。）
        # 中心位移与视轴转角耦合（drift_px_s / PX_PER_DEG = 角速度；除以 1.177 使
        # 二维合成速度中位数≈标称值），使陀螺积分换算的 frame_deltas 与真值中心位移物理一致。
        rate_std = p["drift_px_s"] / PX_PER_DEG / 1.177  # 单轴角速度 σ（°/s）
        lim = p["tilt_lim"]
        yaw = _ou_process(rng, n, GEN_FS, rate_std, p["ou_lambda"])
        pitch = _ou_process(rng, n, GEN_FS, rate_std, p["ou_lambda"])
        pitch = pitch + rng.uniform(-1.0, 1.0) * min(0.5 * lim, 7.5)  # 持机俯仰偏移

        # 手震本质是视线转动：等效到偏航/俯仰角上（0.3px ↔ 0.0075°），
        # 这样陀螺可观测，frame_deltas 才能跟踪帧间手震位移
        trem_x = _band_noise(rng, n, GEN_FS, *TREMOR_BAND) * p["tremor_px"]
        trem_y = _band_noise(rng, n, GEN_FS, *TREMOR_BAND) * p["tremor_px"]
        yaw = yaw + trem_x / PX_PER_DEG
        pitch = pitch - trem_y / PX_PER_DEG
        yaw = np.clip(yaw, -lim, lim)
        pitch = np.clip(pitch, -lim, lim)

        # roll：初始角 ±5° + 近似恒速漂移（速率 ±roll_rate，带 25% 慢调制）+ 手震
        roll0 = rng.uniform(-5.0, 5.0)
        roll_rate = np.sign(rng.standard_normal()) * p["roll_rate"] * rng.uniform(0.8, 1.2)
        mod = 1.0 + 0.25 * _band_noise(rng, n, GEN_FS, 0.05, 0.3)
        roll = roll0 + roll_rate * np.cumsum(mod) / GEN_FS
        roll += _band_noise(rng, n, GEN_FS, *TREMOR_BAND) * p["tremor_deg"]

        # 中心 = 屏幕中心附近 + 视轴转角耦合位移（含手震）
        cx0 = SCREEN_W / 2 + rng.uniform(-100.0, 100.0)
        cy0 = SCREEN_H / 2 + rng.uniform(-80.0, 80.0)
        self._yaw = yaw
        self._pitch = pitch
        self._roll = roll
        self._cx = cx0 + yaw * PX_PER_DEG
        self._cy = cy0 - pitch * PX_PER_DEG

    def sample(self, t: float) -> MotionState:
        """线性插值取 t 时刻状态（t 超出 [0, duration] 时截断）。"""
        t = float(np.clip(t, 0.0, self.duration_s))
        i = np.interp
        return MotionState(
            center_x=float(i(t, self._t, self._cx)),
            center_y=float(i(t, self._t, self._cy)),
            roll_deg=float(i(t, self._t, self._roll)),
            tilt_pitch_deg=float(i(t, self._t, self._pitch)),
            tilt_yaw_deg=float(i(t, self._t, self._yaw)),
        )


def _rot_from_small_euler(rx: float, ry: float, rz: float) -> np.ndarray:
    """小角度（弧度）欧拉角 -> 旋转矩阵（安装误差用）。"""
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    return np.array([
        [cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz],
        [cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz],
        [-sy, sx * cy, cx * cy],
    ])


def _wrap_deg(x):
    return (np.asarray(x) + 180.0) % 360.0 - 180.0


class IMUStream:
    """一路带噪 IMU 数据及其积分估计结果。prior_at(t) 输出解码端先验。"""

    def __init__(self, ts, gyro, accel, roll_est, pitch_est, yaw_est, pitch_gyro):
        self.ts = ts                # 采样时刻（s）
        self.gyro = gyro            # 陀螺量测（°/s），(n,3)，IMU 系
        self.accel = accel          # 加速度计量测（m/s²），(n,3)，IMU 系
        self._roll = roll_est       # roll 互补滤波估计（°）
        self._pitch = pitch_est     # 重力估计俯仰（°）
        self._yaw = yaw_est         # 陀螺积分偏航（°，重力不可观测，会漂移）
        self._pitch_g = pitch_gyro  # 陀螺积分俯仰（°），仅供 frame_deltas 差分用

    def _est_at(self, arr, t: float) -> float:
        return float(np.interp(np.clip(t, self.ts[0], self.ts[-1]), self.ts, arr))

    def prior_at(self, t: float, fps: float = 30.0, n_frames: int = 1) -> IMUPrior:
        """t 时刻的解码先验。roll_std 随积分时间增长（封顶 1.5°）；
        n_frames>1 时给出最近 n_frames 帧（间隔 1/fps，末帧在 t）的帧间中心位移估计。"""
        roll = self._est_at(self._roll, t)
        pitch = self._est_at(self._pitch, t)
        yaw = self._est_at(self._yaw, t)
        # 不确定度模型：安装误差底噪 0.35° + 陀螺偏置漂移（互补滤波约束在 TAU_ROLL 后饱和）
        roll_std = float(min(1.5, np.hypot(0.35, GYRO_BIAS0 / np.sqrt(3) * min(t, TAU_ROLL))))
        deltas = []
        for k in range(max(0, n_frames - 1)):
            t0 = t - (n_frames - 1 - k) / fps
            t1 = t0 + 1.0 / fps
            # 由陀螺积分的视轴转角换算屏幕像素位移（含噪声/偏置）；
            # 注意必须用陀螺积分量做差分——重力估计的俯仰逐样本噪声 0.3°，
            # 帧间差分会放大成 ~15px 的伪位移
            dx = (self._est_at(self._yaw, t1) - self._est_at(self._yaw, t0)) * PX_PER_DEG
            dy = -(self._est_at(self._pitch_g, t1) - self._est_at(self._pitch_g, t0)) * PX_PER_DEG
            deltas.append((dx, dy))
        return IMUPrior(roll_deg=roll, roll_std_deg=roll_std, scale_hint=0.0,
                        tilt_pitch_deg=pitch, tilt_yaw_deg=yaw,
                        frame_deltas=deltas, available=True)


def simulate_imu(motion: HandMotion, rate_hz: int = 200, seed: int | None = None) -> IMUStream:
    """按 SPEC2 §1 噪声模型把运动真值转成带噪 IMU 流并积分出估计值。"""
    # seed 缺省时由 motion.seed 派生，保证默认也可复现
    rng = np.random.default_rng(seed if seed is not None else motion.seed * 1000003 + 7)
    dt = 1.0 / rate_hz
    n = int(round(motion.duration_s * rate_hz)) + 1
    ts = np.arange(n) * dt
    st = [motion.sample(t) for t in ts]
    roll_t = np.array([s.roll_deg for s in st])
    pitch_t = np.array([s.tilt_pitch_deg for s in st])
    yaw_t = np.array([s.tilt_yaw_deg for s in st])
    th, ph, ps = np.deg2rad(roll_t), np.deg2rad(pitch_t), np.deg2rad(yaw_t)

    # 真值角速度（相机系，°/s）：由 R = Rot_z(ψ)·B0·Rot_x(φ)·Rot_z(θ) 求得的精确关系
    d_th, d_ph, d_ps = (np.gradient(x, dt) for x in (th, ph, ps))
    w_cam = np.stack([
        d_ph * np.cos(th) - d_ps * np.sin(th) * np.cos(ph),
        -d_ph * np.sin(th) - d_ps * np.cos(th) * np.cos(ph),
        d_th - d_ps * np.sin(ph),
    ], axis=1)
    w_cam = np.rad2deg(w_cam)

    # 真值重力投影（相机系，m/s²）；手持平移加速度（<0.01 m/s²）相对噪声可忽略
    g_cam = G * np.stack([
        np.cos(ph) * np.sin(th),
        np.cos(ph) * np.cos(th),
        -np.sin(ph),
    ], axis=1)

    # IMU-相机安装误差：±1° 固定旋转
    rm = _rot_from_small_euler(*np.deg2rad(rng.uniform(-MOUNT_ERR_DEG, MOUNT_ERR_DEG, 3)))
    w_imu = w_cam @ rm.T
    a_imu = g_cam @ rm.T

    # 陀螺：白噪声 + 偏置随机游走（初值 ±0.5°/s）+ 量化 0.01°/s
    bias = rng.uniform(-GYRO_BIAS0, GYRO_BIAS0, 3)
    bias = bias + np.cumsum(rng.normal(0.0, GYRO_BIAS_RW * np.sqrt(dt), (n, 3)), axis=0)
    gyro = w_imu + bias + rng.normal(0.0, GYRO_NOISE, (n, 3))
    gyro = np.round(gyro / GYRO_QUANT) * GYRO_QUANT

    # 加速度计：白噪声 σ0.05 + 固定偏置 ±0.02
    accel = a_imu + rng.uniform(-ACCEL_BIAS, ACCEL_BIAS, 3) + rng.normal(0.0, ACCEL_NOISE, (n, 3))

    # ---- 估计（全部基于带噪量测，不用真值） ----
    roll_acc = np.degrees(np.arctan2(accel[:, 0], accel[:, 1]))          # 重力直接可观 roll
    pitch_est = np.degrees(np.arcsin(np.clip(-accel[:, 2] / np.linalg.norm(accel, axis=1), -1, 1)))
    # 由 ω_x/ω_y 精确反解俯仰/偏航角速度（小角度近似在大 roll 下会失真）：
    #   φ̇ = ω_x·cosθ − ω_y·sinθ ;  ψ̇ = (−ω_x·sinθ − ω_y·cosθ)/cosφ ;  θ̇ = ω_z + ψ̇·sinφ
    roll_est = np.empty(n)
    yaw_est = np.empty(n)
    pitch_gyro = np.empty(n)   # 俯仰陀螺积分版，供 frame_deltas 差分（重力版逐样本噪声太大）
    r = roll_acc[0]
    yg = pg = 0.0
    for k in range(n):
        if k:
            th_r, ph_r = np.deg2rad(r), np.deg2rad(pitch_est[k])
            d_ph = gyro[k, 0] * np.cos(th_r) - gyro[k, 1] * np.sin(th_r)
            d_ps = (-gyro[k, 0] * np.sin(th_r) - gyro[k, 1] * np.cos(th_r)) / np.cos(ph_r)
            # roll 互补滤波：陀螺积分为主、重力低频纠漂（误差 ~bias*TAU_ROLL，10s 内有界）
            r += (gyro[k, 2] + d_ps * np.sin(ph_r) + _wrap_deg(roll_acc[k] - r) / TAU_ROLL) * dt
            yg += d_ps * dt   # yaw 重力不可观测，仅陀螺积分，允许随时间漂移
            pg += d_ph * dt
        roll_est[k], yaw_est[k], pitch_gyro[k] = r, yg, pg

    return IMUStream(ts, gyro, accel, roll_est, pitch_est, yaw_est, pitch_gyro)


if __name__ == "__main__":
    # 1) 可复现性：同 seed 轨迹与 IMU 流逐比特一致
    m1, m2 = HandMotion(42, duration_s=3.0, speed="fast"), HandMotion(42, duration_s=3.0, speed="fast")
    s1, s2 = m1.sample(1.234), m2.sample(1.234)
    assert s1 == s2, "HandMotion 不可复现"
    p1 = simulate_imu(m1, seed=7).prior_at(1.5, n_frames=3)
    p2 = simulate_imu(HandMotion(42, duration_s=3.0, speed="fast"), seed=7).prior_at(1.5, n_frames=3)
    assert p1.roll_deg == p2.roll_deg and p1.frame_deltas == p2.frame_deltas, "simulate_imu 不可复现"
    print("[1] 可复现性 OK")

    # 2) 10s 轨迹，统计 prior_at 的 roll/tilt 估计误差包络（多 seed 聚合）
    DUR = 10.0
    errs = {"roll": [], "pitch": [], "yaw": []}
    fd_err = []
    for k in range(24):
        speed = "slow" if k % 2 == 0 else "fast"
        motion = HandMotion(seed=100 + k, duration_s=DUR, speed=speed)
        stream = simulate_imu(motion, rate_hz=200, seed=5000 + k)
        for t in np.linspace(0.2, DUR, 50):
            truth = motion.sample(t)
            prior = stream.prior_at(t, n_frames=3)
            errs["roll"].append(float(_wrap_deg(prior.roll_deg - truth.roll_deg)))
            errs["pitch"].append(prior.tilt_pitch_deg - truth.tilt_pitch_deg)
            errs["yaw"].append(float(_wrap_deg(prior.tilt_yaw_deg - truth.tilt_yaw_deg)))
        # frame_deltas 对照真值帧间位移（30fps 三帧）
        for t in np.linspace(2.0 / 30, DUR, 60):
            a, b = motion.sample(t - 1.0 / 30), motion.sample(t)
            (dx, dy), = stream.prior_at(t, n_frames=2).frame_deltas
            fd_err.append(np.hypot(dx - (b.center_x - a.center_x), dy - (b.center_y - a.center_y)))

    print(f"[2] 10s 包络统计（24 条轨迹 × 50 采样点，slow/fast 各半）")
    limits = {"roll": 1.5, "pitch": 0.8, "yaw": 3.5}  # yaw 重力不可观测，仅陀螺积分，包络放宽
    for name, label in [("roll", "roll"), ("pitch", "tilt_pitch"), ("yaw", "tilt_yaw")]:
        e = np.array(errs[name])
        print(f"    {label:11s} mean={e.mean():+.3f}°  σ={e.std():.3f}°  max|e|={np.abs(e).max():.3f}°  (限 σ≤{limits[name]}°)")
        assert e.std() <= limits[name], f"{label} 误差超出包络"
    fd = np.array(fd_err)
    print(f"    frame_deltas RMSE={np.sqrt((fd**2).mean()):.3f}px  P95={np.percentile(fd, 95):.3f}px")
    assert np.sqrt((fd**2).mean()) <= 2.0, "frame_deltas 误差过大"
    print("[3] 全部断言通过")
