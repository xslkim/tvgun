"""坐标解码:从相机拍摄画面恢复所拍区域在屏幕上的像素坐标(SPEC.md『解码』一节)。

流水线:灰度 -> FFT导频环带8重旋转对称匹配(多候选缩放+旋转) -> 相似变换校正到
屏幕像素网格 -> 相关前的谱白化(抑制规则/强纹理内容的带内能量) -> 2×2子块相位相关
迭代细化 -> 全局信号互相关定位 -> 抛物线亚像素 -> 置信度(主/次峰比)。
主候选置信度不足时按打分顺序回退尝试备选几何,由互相关响应仲裁。

第二期扩展(SPEC2.md §2/§3/§6):decode() 增加可选 imu_prior 与 lens 参数。
有可靠 IMU 先验时:角度假设从 3×k·45° 缩减为 prior.roll±3σ 小搜索(首个锁定即停)、
frame_deltas 多帧预对齐、tilt 提示初始化各向异性缩放;prior 与导频冲突(>4σ)回退
无先验路径。lens=(k1,k2) 时按 channel 的前向畸变算子构造逆映射做真去畸变。
"""
from __future__ import annotations

import math

import numpy as np
import cv2

try:
    from .config import (
        EmbedState, DecodeResult, IMUPrior, SEED,
        SCREEN_W, SCREEN_H, FOV, MARGIN, PILOT_FREQS,
    )
except ImportError:  # 允许 python3 sim/decode.py 直接运行自测
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim.config import (
        EmbedState, DecodeResult, IMUPrior, SEED,
        SCREEN_W, SCREEN_H, FOV, MARGIN, PILOT_FREQS,
    )

_PILOT_ABS = float(np.hypot(PILOT_FREQS[0][0], PILOT_FREQS[0][1]))  # 4组导频|f|相同=1/6
_HYPO = (-45.0, 0.0, 45.0)  # 导频方向集合有45°对称性,旋转估计存在k·45°歧义,逐个假设验证
OK_CONF_THRESHOLD = 1.15  # ok 判定置信度阈值。在 3200 用例评测集上扫描标定(见 REPORT.md):
                          # 该值使"错误定位被判 ok"率 0.63%、"正确定位被判 not-ok"率 3.1%,
                          # 总判定错误率最低且偏保守;SPEC 默认 1.3 会误判 ~9% 的正确定位


def _hann2d(h: int, w: int) -> np.ndarray:
    return (np.hanning(h)[:, None] * np.hanning(w)[None, :]).astype(np.float32)


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        # 等权通道和而非 luma(0.299/0.587/0.114):moire 子像素采样下每个相机像素
        # 只含部分通道的条带覆盖 cov_c(x),luma 会把嵌入 delta 调制为
        # (0.299cov_R+0.587cov_G+0.114cov_B)·delta(均值仅0.4且带条带纹),
        # 而等权和给出 (cov_R+cov_G+cov_B)·delta ≈ delta,全额保留信号;
        # 非 moire 时两者经归一化相关基本等价。
        return img.astype(np.float32).sum(axis=2)
    return img.astype(np.float32)


_UNDISTORT_CACHE: dict = {}  # (h,w,k1,k2) -> (map1,map2),去畸变映射只算一次


def _undistort(gray: np.ndarray, lens: tuple | None = None) -> np.ndarray:
    """镜头去畸变。lens=(k1,k2) 为信道施加的径向畸变系数(SPEC2 §3,已标定场景)。

    channel._apply_lens_distort 的前向算子是 obs(p)=ideal(D(p)),D(p)=K·distort(K⁻¹p)
    (借用 initUndistortRectifyMap 的方向)。去畸变需要逆映射 ideal_est(m)=obs(D⁻¹(m)):
    对每个输出像素 m,归一化得 u=K⁻¹m,用不动点迭代解径向多项式
    d·(1+k1|d|²+k2|d|⁴)=u(~12 次收敛到亚毫像素),再经 K 投回像素坐标。
    """
    if lens is None or (abs(lens[0]) < 1e-9 and abs(lens[1]) < 1e-9):
        return gray
    k1, k2 = float(lens[0]), float(lens[1])
    h, w = gray.shape
    key = (h, w, k1, k2)
    maps = _UNDISTORT_CACHE.get(key)
    if maps is None:
        f = 1.2 * w  # 与 channel._lens_intrinsic 一致:焦距 1.2*cam_res,主点居中
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        u, v = (xx - cx) / f, (yy - cy) / f
        du, dv = u.copy(), v.copy()  # 初值 d=u,迭代 d ← u/(1+k1|d|²+k2|d|⁴)
        for _ in range(12):
            r2 = du * du + dv * dv
            g = 1.0 + k1 * r2 + k2 * r2 * r2
            du, dv = u / g, v / g
        maps = ((cx + f * du).astype(np.float32), (cy + f * dv).astype(np.float32))
        _UNDISTORT_CACHE[key] = maps
    return cv2.remap(gray, maps[0], maps[1], cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


def _parabola(fm: float, f0: float, fp: float) -> float:
    """一维抛物线亚像素插值,返回相对中心点的偏移。"""
    den = fm - 2.0 * f0 + fp
    if abs(den) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (fm - fp) / den, -1.0, 1.0))


def _pilot_score_map(mag: np.ndarray, fov: int):
    """导频环带的8重旋转对称打分图 S(r,θ) 及坐标网格。

    导频在半径 r0=fov·|f| 处产生8个间隔45°的峰。规则内容(facade窗格等)的谐波峰
    不具备同半径8重对称性;各向同性纹理环对S只贡献角度向平坦基底,按半径减去
    角度向中值后消除。log 域求和使缺峰惩罚强于单峰奖励。
    """
    h, w = mag.shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r0 = fov * _PILOT_ABS
    n_r, n_t = 97, 1440
    radii = np.linspace(r0 / 1.25, r0 * 1.25, n_r)
    tstep = 360.0 / n_t
    thetas = np.deg2rad(np.arange(n_t, dtype=np.float64) * tstep)
    yy = cy + radii[:, None] * np.sin(thetas)[None, :]
    xx = cx + radii[:, None] * np.cos(thetas)[None, :]
    polar = cv2.remap(mag, xx.astype(np.float32), yy.astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    norm = np.median(polar, axis=1, keepdims=True) + 1e-9
    pn = np.log(polar / norm + 0.3)
    S = sum(np.roll(pn, -k * (n_t // 8), axis=1) for k in range(8))
    S = S - np.median(S, axis=1, keepdims=True)
    return S, radii, tstep, r0


def _refine_pilots(mag: np.ndarray, r_est: float, th_est: float, r0: float):
    """8个导频峰逐个局部抛物线亚像素细化,中位数拟合 scale/theta,抵抗个别污染峰。"""
    h, w = mag.shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    lm = np.log(mag + 1e-12)
    rs, angs = [], []
    for k in range(8):
        a = np.deg2rad(th_est + k * 45.0)
        py, px = cy + r_est * np.sin(a), cx + r_est * np.cos(a)
        iy, ix = int(round(py)), int(round(px))
        y0, y1 = max(0, iy - 3), min(h, iy + 4)
        x0, x1 = max(0, ix - 3), min(w, ix + 4)
        nb = mag[y0:y1, x0:x1]
        if nb.size == 0:
            continue
        jy, jx = np.unravel_index(int(np.argmax(nb)), nb.shape)
        gy, gx = y0 + jy, x0 + jx
        if 0 < gy < h - 1 and 0 < gx < w - 1:
            dy = _parabola(lm[gy - 1, gx], lm[gy, gx], lm[gy + 1, gx])
            dx = _parabola(lm[gy, gx - 1], lm[gy, gx], lm[gy, gx + 1])
            ry, rx = gy + dy - cy, gx + dx - cx
            rs.append(float(np.hypot(rx, ry)))
            ang = np.rad2deg(np.arctan2(ry, rx)) - k * 45.0
            # 折叠到 th_est 附近(-22.5,22.5]
            ang = (ang - th_est + 22.5) % 45.0 - 22.5 + th_est
            angs.append(float(ang))
    if len(rs) >= 6:
        return r0 / float(np.median(rs)), float(np.median(angs)), len(rs)
    return r0 / r_est, th_est, len(rs)


def _geometry_candidates(gray: np.ndarray, fov: int, k: int = 4):
    """几何同步:返回 top-k (scale, theta, score) 候选,theta 折叠到[-22.5,22.5)。

    强纹理真实照片可能在环带内形成比导频更亮的伪候选,故保留多个局部极大,
    由上层用互相关响应逐一验证。
    """
    h, w = gray.shape
    win = _hann2d(h, w)
    g = (gray - gray.mean()) * win
    # FFT 尺寸取 cv2 最优(2/3/5 平滑):导频峰的 FFT bin 半径=f·fov 与尺寸无关,
    # 零填充只加密谱采样,不影响 _pilot_score_map 的坐标解释
    ph, pw = cv2.getOptimalDFTSize(h), cv2.getOptimalDFTSize(w)
    if (ph, pw) != (h, w):
        gp = np.zeros((ph, pw), np.float32)
        gp[:h, :w] = g
        g = gp
    F = np.fft.fftshift(np.fft.fft2(g))
    mag = np.abs(F)
    S, radii, tstep, r0 = _pilot_score_map(mag, fov)
    n_r, n_t = S.shape

    Sm = S.copy()
    cands = []
    for _ in range(k * 3):  # 多提取,细化去重后保留前 k 个
        ir, it = np.unravel_index(int(np.argmax(Sm)), Sm.shape)
        score = float(Sm[ir, it])
        dr = _parabola(float(S[ir - 1, it]), float(S[ir, it]), float(S[ir + 1, it])) \
            if 0 < ir < n_r - 1 else 0.0
        dt = _parabola(float(S[ir, (it - 1) % n_t]), float(S[ir, it]),
                       float(S[ir, (it + 1) % n_t]))
        r_est = float(radii[ir] + dr * (radii[1] - radii[0]))
        th_est = float((it + dt) * tstep)
        scale, theta, n_pk = _refine_pilots(mag, r_est, th_est, r0)
        theta = (theta + 22.5) % 45.0 - 22.5
        # 与已有候选近似相同(细化收敛到同一物理峰)则跳过
        if all(abs(scale - s) > 0.02 or abs(theta - t) > 0.5 for s, t, _, _ in cands):
            cands.append((scale, theta, score, n_pk))
            if len(cands) >= k:
                break
        # 抑制该候选的局部矩形邻域(径向±4 bin, 角度±3°),找下一个局部极大
        r_lo, r_hi = max(0, ir - 4), min(n_r, ir + 5)
        cols = (np.arange(it - 12, it + 13) % n_t)
        Sm[np.ix_(np.arange(r_lo, r_hi), cols)] = -np.inf
        if not np.isfinite(Sm).any():
            break
    return cands


def _estimate_geometry(gray: np.ndarray, fov: int):
    """主候选几何估计(等价于 _geometry_candidates 的 top-1),保留诊断用接口。"""
    s, th, score, n_pk = _geometry_candidates(gray, fov, k=1)[0]
    return s, th, {"n_pilot_peaks": n_pk, "score": score}


def _warp_to_grid(gray: np.ndarray, scale: float, theta_deg: float, fov: int, out: int,
                  offset: tuple[float, float] = (0.0, 0.0),
                  aniso: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """相似变换把相机图warp回屏幕像素网格(out=out见方,中心对齐)。

    offset: 输出网格中心的额外平移(屏幕像素,IMU frame_deltas 预对齐用),
            平移量随 k·R 一同进入采样,即 dst(p)=src(cc+kR(p-oc-offset))。
    aniso:  水平/垂直缩放因子,tilt 提示的透视缩短 cos(yaw)/cos(pitch)。
    """
    cam = gray.shape[0]
    k = cam / fov * scale  # 相机像素/屏幕像素
    kx, ky = k * aniso[0], k * aniso[1]
    th = np.deg2rad(theta_deg)
    co, si = np.cos(th), np.sin(th)
    oc, cc = (out - 1) / 2.0, (cam - 1) / 2.0
    ox, oy = oc + offset[0], oc + offset[1]
    M = np.array([[co * kx, -si * ky, cc - co * kx * ox + si * ky * oy],
                  [si * kx, co * ky, cc - si * kx * ox - co * ky * oy]], np.float32)
    return cv2.warpAffine(gray, M, (out, out),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def _accumulate(infos, ds: float, dtheta: float, hypo: float, fov: int, out: int,
                pre: list | None = None, aniso: tuple[float, float] = (1.0, 1.0)):
    """多帧:逐帧按自身几何估计(+全局修正+hypo假设)校正,相位相关对齐后累加平均。

    pre: 各帧的 IMU 预对齐位移(屏幕像素,首帧为(0,0));先按预对齐量平移采样中心,
         相位相关只需估计残余噪声位移,消除手持漂移导致的累加模糊。
    返回(平均图, 平均残余位移): 对齐以首帧(预对齐后)为基准,由调用方据此修正坐标。
    """
    ref, acc, win = None, None, _hann2d(out, out)
    shifts = [(0.0, 0.0)]
    for fi, (gray, s0, th0) in enumerate(infos):
        off = pre[fi] if pre is not None else (0.0, 0.0)
        img = _warp_to_grid(gray, s0 / (1.0 - ds), th0 + dtheta + hypo, fov, out, off, aniso)
        if ref is None:
            ref, acc = img, img.astype(np.float64)
            continue
        (sx, sy), _ = cv2.phaseCorrelate(ref, img, win)  # ref(p)=img(p+s),img相对ref偏移了s
        if abs(sx) < 6 and abs(sy) < 6:  # taa_jitter/IMU残差等帧间抖动,亚像素对齐
            M = np.float32([[1, 0, sx], [0, 1, sy]])  # dst(p)=src(p+s)即可对齐到ref
            img = cv2.warpAffine(img, M, (out, out), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                 borderMode=cv2.BORDER_REPLICATE)
            shifts.append((sx, sy))
        else:
            shifts.append((0.0, 0.0))
        acc += img
    mean_shift = (float(np.mean([s[0] for s in shifts])), float(np.mean([s[1] for s in shifts])))
    return (acc / len(infos)).astype(np.float32), mean_shift


def _bandpass(img: np.ndarray) -> np.ndarray:
    """屏幕网格上的环形带通(周期4~24px,平滑过渡带),压制画面内容低频、提升相关信噪比。"""
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    r = np.hypot(fx, fy)
    lo, hi = 1.0 / 24.0, 1.0 / 4.0

    def smoothstep(e0, e1, x):
        t = np.clip((x - e0) / (e1 - e0), 0, 1)
        return t * t * (3 - 2 * t)

    mask = smoothstep(lo * 0.7, lo, r) * (1.0 - smoothstep(hi, hi * 1.3, r))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * mask)).astype(np.float32)


def _bandpass_mask(h: int, w: int, p_lo: float = 24.0, p_hi: float = 4.0) -> np.ndarray:
    """环形带通频域掩模(周期 p_lo~p_hi 像素,平滑过渡带)。"""
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    r = np.hypot(fx, fy)
    lo, hi = 1.0 / p_lo, 1.0 / p_hi

    def smoothstep(e0, e1, x):
        t = np.clip((x - e0) / (e1 - e0), 0, 1)
        return t * t * (3 - 2 * t)

    return (smoothstep(lo * 0.7, lo, r) * (1.0 - smoothstep(hi, hi * 1.3, r))).astype(np.float32)


def _whiten_bandpass(img: np.ndarray, p_lo: float = 24.0, p_hi: float = 4.0) -> np.ndarray:
    """带通 + 谱白化:带内按 1/(|F|+eps·中值) 逐 bin 归一。

    规则/强纹理内容(facade 窗格谐波、terrain 色带边缘)在带内少数 bin 上能量远超
    嵌入信号,白化把这些 bin 压回单位幅度,等效于对内容做匹配滤波抑制;
    eps 防止纯噪 bin 被无限放大。
    """
    mask = _bandpass_mask(*img.shape, p_lo=p_lo, p_hi=p_hi)
    F = np.fft.fft2(img - float(img.mean()))
    mag = np.abs(F)
    med = float(np.median(mag[mask > 0.5])) + 1e-9
    W = mask / (mag + 0.1 * med)
    return np.real(np.fft.ifft2(F * W)).astype(np.float32)


def _correlate(templ: np.ndarray, img: np.ndarray) -> np.ndarray:
    return cv2.matchTemplate(templ, _whiten_bandpass(img), cv2.TM_CCOEFF_NORMED)


# ------------------------------------------------ 几何候选仲裁
# 强纹理真实照片可能让导频打分图的 top-1 几何候选出错。回退时对备选候选逐一做
# 全分辨率求解,按 arb = peak·(1+mresp) 仲裁:mresp 为相关峰处 2×2 子块与模板的
# 相位相关平均响应,几何错误时子块无法相位锁定(mresp≈0.1 以下),几何正确时
# 即使相关峰被内容压制,子块仍能锁在信号上(mresp 明显更高)。


def _block_stats(acc: np.ndarray, templ: np.ndarray, px: int, py: int, out: int):
    """相关峰处 2×2 子块与模板窗口的相位相关统计:(锁定块数, 平均 resp)。"""
    B = out // 2
    win = _hann2d(B, B)
    accb = _bandpass(acc)
    nlock, resps = 0, []
    for i in (0, 1):
        for j in (0, 1):
            blk = np.ascontiguousarray(accb[i * B:(i + 1) * B, j * B:(j + 1) * B])
            tw = np.ascontiguousarray(templ[py + i * B:py + (i + 1) * B,
                                          px + j * B:px + (j + 1) * B])
            if tw.shape != (B, B) or float(tw.std()) < 1e-3:
                continue
            (sx, sy), resp = cv2.phaseCorrelate(blk, tw, win)
            resps.append(float(resp))
            if resp >= 0.1 and abs(sx) <= 3 and abs(sy) <= 3:
                nlock += 1
    return nlock, (float(np.mean(resps)) if resps else 0.0)


def _block_residuals(acc: np.ndarray, templ: np.ndarray, x0: int, y0: int, out: int):
    """2×2子块与模板对应窗口做相位相关,由4个残差位移估计残余缩放/旋转。"""
    B = out // 2
    win = _hann2d(B, B)
    bs, ds = [], []
    for i in (0, 1):
        for j in (0, 1):
            blk = np.ascontiguousarray(acc[i * B:(i + 1) * B, j * B:(j + 1) * B])
            tw = np.ascontiguousarray(templ[y0 + i * B:y0 + (i + 1) * B, x0 + j * B:x0 + (j + 1) * B])
            # phaseCorrelate会改写非连续输入视图,必须传连续副本
            if float(tw.std()) < 1e-3:
                return None
            (sx, sy), resp = cv2.phaseCorrelate(blk, tw, win)  # blk(p)=tw(p+s)
            if resp < 0.1 or abs(sx) > 3 or abs(sy) > 3:
                return None
            bs.append(((j - 0.5) * B, (i - 0.5) * B))
            ds.append((-sx, -sy))  # 残差位移模型blk(p)=tw(p-d) -> d=-s
    bs, ds = np.array(bs), np.array(ds)
    den = float((bs ** 2).sum())
    eps = float((bs * ds).sum() / den)                    # d≈eps·p: 残余缩放
    delta = float((bs[:, 0] * ds[:, 1] - bs[:, 1] * ds[:, 0]).sum() / den)  # d≈delta·J·p: 残余旋转
    return eps, -float(np.rad2deg(delta))  # 内容旋正δ说明θ估计偏大δ,取负修正


def _conf_of(corr: np.ndarray) -> float:
    """主峰/次峰响应比(排除主峰 8px 邻域)。"""
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    tmp = corr.copy()
    tmp[max(0, py - 8):py + 9, max(0, px - 8):px + 9] = -1.0
    second = float(tmp.max())
    peak = float(corr.max())
    return peak / second if second > 1e-9 else float("inf")


def _solve(infos, templ: np.ndarray, fov: int, out: int, hypos=_HYPO,
           pre: list | None = None, aniso: tuple[float, float] = (1.0, 1.0),
           micro: bool = True, early_break: bool = False):
    """对给定逐帧几何估计,跑角度假设 + 几何微搜索 + 透视残差迭代细化。

    hypos: 角度假设列表(无先验时为 3 个 k·45°;有 IMU prior 时为 roll±3σ 小网格)。
    early_break: prior 路径专用,某个假设置信度与子块锁定都已达标时立即停搜,
                 省去剩余假设的全分辨率互相关(主要耗时项)。
    """
    # 1. 逐个角度假设校正累加并互相关;无先验时取响应最强者,有先验时锁定即停
    best = None  # (peak, hypo, acc, corr, mean_shift)
    for hypo in hypos:
        acc, ms = _accumulate(infos, 0.0, 0.0, hypo, fov, out, pre, aniso)
        corr = _correlate(templ, acc)
        peak = float(corr.max())
        if best is None or peak > best[0]:
            best = (peak, hypo, acc, corr, ms)
        if early_break:
            py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
            if _conf_of(corr) >= _CONF_SURE and _block_stats(acc, templ, px, py, out)[0] >= 3:
                best = (peak, hypo, acc, corr, ms)
                break
    peak, hypo, acc, corr, ms = best

    # 2. 几何微搜索:初始峰无法锁定子块时(导频 theta 被内容拉偏 ~1° 的情形),
    #    对每个 45° 假设在 dth 小网格上找更强相关峰作为细化起点;仅低置信时触发
    ds = dth = 0.0
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    if micro and _block_stats(acc, templ, px, py, out)[0] == 0 and _conf_of(corr) < 1.5:
        for hy2 in hypos:
            for dth_g in (-1.2, -0.6, 0.6, 1.2):
                acc2, ms2 = _accumulate(infos, 0.0, dth_g, hy2, fov, out, pre, aniso)
                corr2 = _correlate(templ, acc2)
                if float(corr2.max()) > peak * 1.05:
                    peak, acc, corr, hypo, dth, ds, ms = \
                        float(corr2.max()), acc2, corr2, hy2, dth_g, 0.0, ms2

    # 3. 透视残差迭代细化(最多2次,仅在接受能改善相关峰时生效)
    for _ in range(2):
        py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
        res = _block_residuals(_bandpass(acc), templ, px, py, out)
        if res is None:
            break
        eps, dd = res
        if abs(dd) < 1e-3 and abs(eps) < 1e-4:
            break
        ds_comb = 1.0 - (1.0 - ds) / (1.0 - eps)  # 缩放修正为乘性,合成到ds
        acc2, ms2 = _accumulate(infos, ds_comb, dth + dd, hypo, fov, out, pre, aniso)
        corr2 = _correlate(templ, acc2)
        if float(corr2.max()) > peak + 1e-4:
            peak, acc, corr, ds, dth, ms = float(corr2.max()), acc2, corr2, ds_comb, dth + dd, ms2
        else:
            break

    # 3. 峰值定位+抛物线亚像素插值;多帧时换算到各帧平均中心(c_mean=c_0-mean_shift)
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    dx = _parabola(corr[py, px - 1], corr[py, px], corr[py, px + 1]) if 0 < px < corr.shape[1] - 1 else 0.0
    dy = _parabola(corr[py - 1, px], corr[py, px], corr[py + 1, px]) if 0 < py < corr.shape[0] - 1 else 0.0
    x = px + out / 2.0 + dx - ms[0]
    y = py + out / 2.0 + dy - ms[1]

    # 4. 置信度=主峰/次峰(排除主峰8px邻域)
    conf = _conf_of(corr)

    s_est, th_est = infos[0][1] / (1.0 - ds), infos[0][2] + dth + hypo
    nlock, mresp = _block_stats(acc, templ, px, py, out)
    return dict(x=x, y=y, peak=peak, confidence=conf, acc=acc, corr=corr,
                hypo=hypo, ds=ds, dth=dth, scale=s_est, theta=th_est,
                nlock=nlock, mresp=mresp, arb=peak * (1.0 + mresp))


_CONF_SURE = 2.0    # 置信度≥该值且子块锁定良好时跳过备选几何回退(标定见 REPORT)
_MRESP_SURE = 0.15  # 子块平均相位响应≥该值视为几何可信
_N_CAND_FALLBACK = 20   # 回退时提取的几何候选数(真值的局部极大排名可达 ~20)
_MAX_FALLBACK_SOLVES = 12  # 回退全分辨率求解上限(候选经去重后通常 ~7 个)


def decode(camera_frames, state: EmbedState,
           screen_wh: tuple[int, int] = (SCREEN_W, SCREEN_H), fov: int = FOV,
           imu_prior: IMUPrior | None = None, lens: tuple | None = None) -> DecodeResult:
    """解码所拍区域中心的屏幕坐标。

    imu_prior(SPEC2 §2): 提供时以 prior.roll_deg 为中心做 ±3σ 角度小搜索
    (替代 3×k·45° 假设 + 微搜索),多帧先用 frame_deltas 预对齐,tilt 作为
    各向异性缩放初值;prior 与导频估计冲突(>4σ)或 prior 路径无法锁定时
    回退无先验完整搜索。lens=(k1,k2): 已标定径向畸变系数,先做去畸变。
    """
    frames = [camera_frames] if isinstance(camera_frames, np.ndarray) else list(camera_frames)
    out = fov + 2 * MARGIN
    templ = np.array(state.template, dtype=np.float32)  # 显式拷贝,绝不影响EmbedState

    # 1. 逐帧灰度(+去畸变) + 主候选几何(强纹理内容可能使 top-1 候选错误,备选见步骤3)
    grays = [_undistort(_to_gray(f), lens) for f in frames]
    cand0 = _geometry_candidates(grays[0], fov, k=1)
    frame_prim = [cand0[0]] + [_geometry_candidates(g, fov, k=1)[0] for g in grays[1:]]
    s0, th0, _, n_pk = cand0[0]

    def _infos_for(sb, thb):
        infos = [(grays[0], sb, thb)]
        for gi, g in enumerate(grays[1:], start=1):
            sj, thj = frame_prim[gi][0], frame_prim[gi][1]
            infos.append((g, sj * sb / cand0[0][0], thj - cand0[0][1] + thb))
        return infos

    def _pre_deltas():
        # frame_deltas 为帧间中心位移估计(屏幕px),累加得各帧相对首帧的预对齐量
        if not (imu_prior and imu_prior.available) or len(frames) < 2 \
                or not imu_prior.frame_deltas:
            return None
        pre, cx, cy = [(0.0, 0.0)], 0.0, 0.0
        for dx, dy in imu_prior.frame_deltas[:len(frames) - 1]:
            cx, cy = cx + float(dx), cy + float(dy)
            pre.append((cx, cy))
        while len(pre) < len(frames):
            pre.append(pre[-1])
        return pre

    def _full_solve():
        # 无先验完整路径:3×k·45°假设 + 微搜索,必要时回退备选几何仲裁(旧行为)
        b = _solve(_infos_for(s0, th0), templ, fov, out)
        if b["confidence"] < _CONF_SURE or b["mresp"] < _MRESP_SURE:
            cands = _geometry_candidates(grays[0], fov, k=_N_CAND_FALLBACK)
            for sc, thc, _, _ in cands[1:_MAX_FALLBACK_SOLVES]:
                alt = _solve(_infos_for(sc, thc), templ, fov, out)
                if alt["arb"] > b["arb"]:
                    b = alt
        return b

    # 2. IMU prior 路径:冲突检测 -> roll±3σ 小搜索(锁定即停);失败回退完整路径
    best, imu_used = None, False
    if imu_prior is not None and imu_prior.available:
        roll = float(imu_prior.roll_deg)
        rstd = max(float(imu_prior.roll_std_deg), 1e-3)
        # 导频有 45° 折叠歧义,取离 prior 最近的等价角比对;差>4σ 判 IMU 丢步
        th_near = th0 + 45.0 * round((roll - th0) / 45.0)
        if abs(th_near - roll) <= 4.0 * rstd:
            aniso = (math.cos(math.radians(float(imu_prior.tilt_yaw_deg))),
                     math.cos(math.radians(float(imu_prior.tilt_pitch_deg))))
            grid = sorted((float(g) for g in np.linspace(-3.0 * rstd, 3.0 * rstd, 5)),
                          key=abs)  # 中心优先,通常第一个假设即锁定
            best = _solve(_infos_for(s0, roll), templ, fov, out, hypos=grid,
                          pre=_pre_deltas(), aniso=aniso, micro=False, early_break=True)
            if best["confidence"] >= _CONF_SURE and best["mresp"] >= _MRESP_SURE:
                imu_used = True
            else:
                full = _full_solve()  # prior 未锁定,与无先验路径仲裁取优
                # 45° 假分支否决: prior 与导频折叠角一致(已过冲突检测),而 full 路径
                # 的仲裁赢家可能落在 k·45° 歧义分支上(绝对 theta 与 prior roll 相差
                # ~45°)。此类赢家与 IMU+导频双重证据矛盾,采纳它曾产生 846px 且
                # conf≈1.17>阈值的假阳性(facade/extreme);此时保留 prior 路径结果
                # (通常低置信 -> not-ok,失败转为如实上报)。prior roll 本身的 45° 级
                # 丢步已由折叠冲突检测覆盖不了,但那是 ~30σ 事件,忽略。
                th_f = float(full["theta"])
                if abs(th_f - roll) > 4.0 * rstd and full["arb"] > best["arb"]:
                    imu_used = True  # 否决 full 赢家,保留 prior 路径结果
                elif full["arb"] > best["arb"]:
                    best = full
                else:
                    imu_used = True
        # 冲突时 best=None,直接走完整路径
    if best is None:
        best = _full_solve()

    return DecodeResult(
        x=best["x"], y=best["y"], confidence=best["confidence"],
        ok=best["confidence"] >= OK_CONF_THRESHOLD, n_frames=len(frames),
        debug={
            "corrected": best["acc"],      # 几何校正+多帧累加后的屏幕网格图
            "corr": best["corr"].copy(),   # 相关热力图
            "theta_deg": best["theta"],    # 估计的旋转角
            "scale": best["scale"],        # 估计的缩放倍率(相对cam_res/fov)
            "hypothesis_deg": best["hypo"],
            "n_pilot_peaks": n_pk,
            "peak": best["peak"],          # 白化相关主峰响应
            "mresp": best["mresp"],        # 峰处 2×2 子块相位相关平均响应
            "nlock": best["nlock"],        # 锁定的子块数(0~4)
            "imu_used": imu_used,          # 最终结果是否来自 IMU prior 路径
        },
    )


if __name__ == "__main__":
    """自测:不依赖embed/channel等未实现模块,自行构造SPEC定义的信号与简化信道。"""
    import time

    # 1) 按SPEC生成全局信号:周期4~24px环形带通随机相位模板 + 4组导频光栅
    H, W = SCREEN_H, SCREEN_W
    rng = np.random.default_rng(SEED)
    fy = np.fft.fftfreq(H)[:, None]
    fx = np.fft.fftfreq(W)[None, :]
    band = (np.hypot(fx, fy) >= 1 / 24) & (np.hypot(fx, fy) <= 1 / 4)
    Fspec = np.zeros((H, W), np.complex128)
    Fspec[band] = np.exp(1j * rng.uniform(0, 2 * np.pi, int(band.sum())))
    t = np.real(np.fft.ifft2(Fspec))
    t = (t - t.mean()) / t.std()
    yy, xx = np.mgrid[0:H, 0:W]
    sig = t.copy()
    for pfx, pfy in PILOT_FREQS:
        sig = sig + 0.8 * np.cos(2 * np.pi * (pfx * xx + pfy * yy))
    sig = sig.astype(np.float32)
    state = EmbedState(seed=SEED, strength=2.5, template=sig)

    # 2) 模拟游戏画面:低频内容 + 不可见信号
    content = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 8)
    content = 128 + content / content.std() * 35
    frame = np.clip(content + state.strength * sig, 0, 255).astype(np.uint8)
    frame = np.stack([frame] * 3, -1)

    # 3) 简化信道:warpPerspective模拟放大/旋转/缩放+噪声
    def sim_capture(center, rot_deg, zoom, noise_sigma, cam_res=1024, jitter=(0.0, 0.0)):
        k = cam_res / FOV * zoom  # 相机像素/屏幕像素
        th = np.deg2rad(rot_deg)
        cc = (cam_res - 1) / 2.0
        co, si = np.cos(th) * k, np.sin(th) * k
        cxp, cyp = center[0] + jitter[0], center[1] + jitter[1]
        # src->dst: q = cc + k·R(th)·(p-c)
        M = np.array([[co, -si, cc - co * cxp + si * cyp],
                      [si, co, cc - si * cxp - co * cyp],
                      [0, 0, 1]], np.float64)
        cam = cv2.warpPerspective(frame, M, (cam_res, cam_res), flags=cv2.INTER_LINEAR)
        if noise_sigma > 0:
            cam = np.clip(cam.astype(np.float32) + rng.normal(0, noise_sigma, cam.shape), 0, 255)
        return cam.astype(np.uint8)

    cases = [
        ("基础: 放大8倍+旋转7°+噪声2", (713.4, 402.6), 7.0, 1.00, 2.0, 1),
        ("缩放+12%+旋转-25°+噪声3+3帧", (1200.7, 300.2), -25.0, 1.12, 3.0, 3),
        ("边界: 缩放-15%+旋转30°", (500.0, 800.0), 30.0, 0.85, 2.0, 1),
    ]
    all_ok = True
    for name, center, rot, zoom, noise, nfrm in cases:
        cams = [sim_capture(center, rot, zoom, noise,
                            jitter=(rng.normal(0, 0.5), rng.normal(0, 0.5)) if nfrm > 1 else (0, 0))
                for _ in range(nfrm)]
        t0 = time.time()
        res = decode(cams, state)
        dt = time.time() - t0
        err = float(np.hypot(res.x - center[0], res.y - center[1]))
        print(f"[{name}] 真值=({center[0]:.1f},{center[1]:.1f}) "
              f"解码=({res.x:.2f},{res.y:.2f}) 误差={err:.3f}px "
              f"置信度={res.confidence:.2f} ok={res.ok} "
              f"θ={res.debug['theta_deg']:.2f}° s={res.debug['scale']:.3f} "
              f"导频峰={res.debug['n_pilot_peaks']} 耗时={dt:.2f}s")
        if err >= 1.0 or not res.ok:
            all_ok = False
    print("自测(第一期回归)", "全部通过(误差<1px)" if all_ok else "存在失败用例!")

    # ================= 第二期:IMU 辅助 + 镜头去畸变 + 移动端基准 =================

    # 4) 去畸变:与 channel._apply_lens_distort 相同的前向算子(借用 undistort 映射方向)
    def sim_lens_distort(img, k1, k2, cam_res):
        f = 1.2 * cam_res
        c = (cam_res - 1) / 2.0
        K = np.array([[f, 0, c], [0, f, c], [0, 0, 1]], np.float64)
        dist = np.array([k1, k2, 0, 0], np.float64)
        m1, m2 = cv2.initUndistortRectifyMap(K, dist, None, K, (cam_res, cam_res), cv2.CV_32FC1)
        return cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # 4a) 逆映射精度:理想图 -> 畸变 -> 去畸变,内部区域应近似还原
    #     (探针用平滑图:白噪声经两次双线性插值必然衰减,不能用于往返校验)
    probe = cv2.GaussianBlur(rng.normal(0, 1, (512, 512)).astype(np.float32), (0, 0), 4)
    rt = _undistort(sim_lens_distort(probe, -0.1, 0.02, 512), (-0.1, 0.02))
    rt_err = float(np.abs(rt - probe)[32:-32, 32:-32].max())
    print(f"[去畸变逆映射] k1=-0.1,k2=0.02 平滑图往返最大误差={rt_err:.4f} (内容std=1)")
    if rt_err > 0.05:
        all_ok = False

    # 4b) 端到端:桶形畸变 k1=-0.1,已标定(lens 传入)vs 未标定
    K1, K2 = -0.1, 0.02
    cam_d = sim_lens_distort(sim_capture((960.3, 540.7), 5.0, 1.0, 2.0), K1, K2, 1024)
    r_cal = decode(cam_d, state, lens=(K1, K2))
    r_unc = decode(cam_d, state)  # 未标定:不传 lens
    e_cal = float(np.hypot(r_cal.x - 960.3, r_cal.y - 540.7))
    e_unc = float(np.hypot(r_unc.x - 960.3, r_unc.y - 540.7))
    print(f"[畸变端到端] 已标定 误差={e_cal:.3f}px conf={r_cal.confidence:.2f} | "
          f"未标定 误差={e_unc:.3f}px conf={r_unc.confidence:.2f}")
    if e_cal >= 1.0 or not r_cal.ok:
        all_ok = False

    # 5) 带噪 prior(roll 偏差 +1.2°) Monte Carlo:有/无先验的成功率与耗时
    N = 20
    rows = {"imu": [], "plain": []}
    n_ok = {"imu": 0, "plain": 0}
    for i in range(N):
        c = (float(rng.uniform(150, 1770)), float(rng.uniform(150, 930)))
        rot = float(rng.uniform(-20, 20))
        zoom = float(rng.uniform(0.9, 1.1))
        cam = sim_capture(c, rot, zoom, 2.5)
        prior = IMUPrior(roll_deg=rot + 1.2 + float(rng.normal(0, 0.8)),
                         roll_std_deg=1.5)
        for tag, kw in (("imu", dict(imu_prior=prior)), ("plain", {})):
            t0 = time.perf_counter()
            r = decode(cam, state, **kw)
            rows[tag].append((time.perf_counter() - t0) * 1e3)
            if np.hypot(r.x - c[0], r.y - c[1]) < 1.0 and r.ok:
                n_ok[tag] += 1
    for tag in ("imu", "plain"):
        print(f"[prior对比/{tag}] 成功率={n_ok[tag]}/{N} "
              f"耗时中位={np.median(rows[tag]):.0f}ms P95={np.percentile(rows[tag], 95):.0f}ms")
    if n_ok["imu"] < N * 0.95 or n_ok["plain"] < N * 0.95:
        all_ok = False

    # 5b) 冲突回退:prior roll 偏离 +30°(>4σ),应信任导频回退无先验路径且仍解码正确
    cam = sim_capture((800.0, 450.0), 6.0, 1.0, 2.5)
    r_cf = decode(cam, state, imu_prior=IMUPrior(roll_deg=36.0, roll_std_deg=1.5))
    e_cf = float(np.hypot(r_cf.x - 800.0, r_cf.y - 450.0))
    print(f"[prior冲突回退] prior=36° 真值=6° -> 误差={e_cf:.3f}px "
          f"imu_used={r_cf.debug['imu_used']} ok={r_cf.ok}")
    if e_cf >= 1.0 or r_cf.debug["imu_used"]:
        all_ok = False

    # 6) 多帧手持漂移 + frame_deltas 预对齐:3帧,帧间漂移~2px,真值=首帧中心
    drift = [(0.0, 0.0), (2.1, -0.8), (4.0, -1.9)]
    deltas = [(drift[j][0] - drift[j - 1][0] + float(rng.normal(0, 0.2)),
               drift[j][1] - drift[j - 1][1] + float(rng.normal(0, 0.2)))
              for j in (1, 2)]
    cams = [sim_capture((700.0, 500.0), -12.0, 1.05, 2.5, jitter=drift[j]) for j in range(3)]
    prior = IMUPrior(roll_deg=-12.0 + 1.2, roll_std_deg=1.5, frame_deltas=deltas)
    r_d = decode(cams, state, imu_prior=prior)
    r_d0 = decode(cams, state)
    e_d = float(np.hypot(r_d.x - 700.0, r_d.y - 500.0))
    e_d0 = float(np.hypot(r_d0.x - 700.0, r_d0.y - 500.0))
    print(f"[多帧预对齐] 有deltas 误差={e_d:.3f}px imu_used={r_d.debug['imu_used']} | "
          f"无先验 误差={e_d0:.3f}px (漂移4px,无先验以平均中心为基准,误差天然偏大)")
    if e_d >= 1.0 or not r_d.debug["imu_used"]:
        all_ok = False

    # 7) 移动端基准(SPEC2 §6):单线程 cam_res=768 三帧+IMU,目标中位<150ms
    cv2.setNumThreads(1)
    cams768 = [sim_capture((900.0, 500.0), 8.0, 1.0, 2.0, cam_res=768,
                           jitter=(0.3 * j, -0.2 * j)) for j in range(3)]
    prior768 = IMUPrior(roll_deg=9.2, roll_std_deg=1.5,
                        frame_deltas=[(0.3, -0.2), (0.3, -0.2)])
    ts_imu, ts_plain = [], []
    for _ in range(5):
        t0 = time.perf_counter(); r_m = decode(cams768, state, imu_prior=prior768)
        ts_imu.append((time.perf_counter() - t0) * 1e3)
        t0 = time.perf_counter(); decode(cams768, state)
        ts_plain.append((time.perf_counter() - t0) * 1e3)
    cv2.setNumThreads(-1)
    e_m = float(np.hypot(r_m.x - 900.0, r_m.y - 500.0))
    med_imu, med_plain = float(np.median(ts_imu)), float(np.median(ts_plain))
    print(f"[移动端基准] 768×3帧 单线程: 有IMU 中位={med_imu:.0f}ms "
          f"(目标<150ms) 误差={e_m:.3f}px | 无先验 中位={med_plain:.0f}ms")
    if e_m >= 1.0:
        all_ok = False

    print("自测(第二期)", "全部通过" if all_ok else "存在失败用例!")
