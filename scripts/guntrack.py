#!/usr/bin/env python3
"""TVGun 光枪追踪器 v2 —— Python 参考实现（与 Java 移植版逐语句对应）。

核心改动（相对 Detector.java + Fusion.java 的旧管线）：
  1. 状态为单应 H（640x360 图像坐标 -> 1920x1080 规范坐标），而非四角+准星；
  2. 帧间由陀螺传播 H：p_new = K·R·K⁻¹·p_old，H ← H·(K·R·K⁻¹)⁻¹，
     R = I+[M·∫(ω-bias)dt]×，M 为两段录制回归出的设备轴→相机轴映射（rot=0）；
  3. 每帧对"预测可见"的每条屏幕边独立做亮边带直线拟合（不依赖完整闭环四边形）：
     每 bin 取亮条纹外侧过零边（亚像素），TLS+2σ 剔除得边线；内侧暗度校验
     拒绝文字屏/灯具假边。校正分两路：
       - 4 边（FULL）：角点=邻边交点 → DLT 解 H_meas → 按比例收敛（绝对复位）；
       - 1-3 边（PARTIAL/EDGE）：图像空间相似校正——平移 t 由 n_eᵀt=o_e 截断
         特征值 2x2 解（平行边对时截掉病态方向）、旋转=夹角加权均值、尺度=
         平行边对间距变化；全部 slew 限幅防可视跳变。
     4 边=FULL，2-3 边=PARTIAL，1 边=EDGE，0 边且视觉丢失<T_MAX=GYRO，否则 DEAD；
  4. 采集（失锁重建）遍历多个候选亮域逐个做四边拟合 + 内部暗度/环形中空校验，
     拒绝灯具/文字屏等干扰（广角录制中旧算法的主要失败源）；
  5. 静止时在线估计陀螺零偏（视觉确认不动 + |ω| 小）。

坐标约定：
  - 图像坐标：640x360，x 右 y 下，主点 (320,180)，焦距 f = 320/tan(fovH/2)；
  - 规范坐标：1920x1080，边框外缘四角 = (0,0)/(1920,0)/(1920,1080)/(0,1080)（沿用旧约定）；
  - 屏幕边线：top L=(0,1,0), right L=(1,0,-1920), bottom L=(0,1,-1080), left L=(1,0,0)，
    图像边线 l = Hᵀ·L（s=H·p ⟹ l_img = Hᵀ·L_screen）。
  - rot=180（sensorLandscape 翻转）时 ωx,ωy 取反后走同一 M（等价 diag(-1,-1,1)·M）。

只使用 numpy + 标准数学，便于纯 Java 移植；采集阶段的连通域用 cv2（Java 侧已有手写 CCL）。
"""
from __future__ import annotations

import numpy as np

NORM_W, NORM_H = 1920.0, 1080.0
IMG_W, IMG_H = 640.0, 360.0

# 设备轴 -> 相机轴（rot=0），由 calib_prop.py 在两段录制上回归一致得出
M_ROT0 = np.array([[0.0, 1.0, 0.0],
                   [1.0, 0.0, 0.0],
                   [0.0, 0.0, -1.0]])

# 屏幕边线（外缘），顺序 top, right, bottom, left；角点 i = 边 i-1 ∩ 边 i (TL,TR,BR,BL)
EDGE_LINES = np.array([
    [0.0, 1.0, 0.0],          # top:    Y=0
    [1.0, 0.0, -NORM_W],      # right:  X=1920
    [0.0, 1.0, -NORM_H],      # bottom: Y=1080
    [1.0, 0.0, 0.0],          # left:   X=0
])
SCREEN_CORNERS = np.array([[0.0, 0.0], [NORM_W, 0.0],
                           [NORM_W, NORM_H], [0.0, NORM_H]])  # TL,TR,BR,BL

# ---- 等级 ----
GRADE_DEAD, GRADE_GYRO, GRADE_EDGE, GRADE_PARTIAL, GRADE_FULL = 0, 1, 2, 3, 4
GRADE_NAMES = ["DEAD", "GYRO", "EDGE", "PARTIAL", "FULL"]


class TrackerParams:
    fov_h_deg = 67.94          # 镜头水平视场角（meta.viewAngle）
    rotation = 0               # detRotation: 0 or 180

    # 边测量
    band = 12.0                # 预测线两侧带宽（640 px；条纹宽 ~7px + 预测误差）
    band_grow = 12.0           # 边连续未测到/测量不可信时每秒带宽外扩（px/s），上限 band_max
    band_max = 24.0
    edge_bin_w = 3.0           # 纵向分箱宽
    min_edge_bins = 12         # 最少有效 bin
    min_support = 0.45         # 支撑率下限（相对可见段）
    max_sigma = 2.5            # 外包络残差 σ 上限（px）
    trim_rounds = 2
    min_visible_len = 28.0     # 边在图内可见长度下限（px）
    dark_margin = 25           # 内侧暗度校验：内侧中位亮度须 < low_thr - margin（余量）
    inside_off = 10.0          # 内侧采样距离（px，垂直边向四边形内）

    # H 校正（相似校正 / DLT 混合 + 增益）
    gain_full = 0.6            # FULL 校正增益
    gain_partial = 0.5
    gain_edge = 0.35
    slew_cap = 60.0            # 单帧校正引起的准星位移上限（规范 px），超限截断（防跳变）

    # GYRO / DEAD
    t_gyro_max = 3.0           # 无视觉外推时限（s）

    # 零偏估计
    bias_alpha = 0.02          # 静止时 EMA
    bias_max_rate = 0.06       # |ω| 低于此值且视觉确认不动才更新（rad/s）

    # 采集
    acq_max_cand = 5           # 候选亮域上限
    acq_min_seeds = 10         # 高亮种子下限（宽放低；四边拟合+暗度校验兜底）
    acq_min_blob_frac = 0.006  # 候选域面积下限
    acq_dark_frac = 0.30       # 内环（缩 18%）内亮像素占比上限（中空校验）
    acq_thr = 190.0            # 高阈值夹紧下限（沿用）
    low_thr_ratio = 0.75
    low_thr_min = 150


def _skew(v):
    return np.array([[0.0, -v[2], v[1]],
                     [v[2], 0.0, -v[0]],
                     [-v[1], v[0], 0.0]])


class Tracker:
    """单应传播 + 逐边视觉校正追踪器。输入 640x360 灰度帧 + 陀螺 tick。"""

    def __init__(self, params: TrackerParams | None = None):
        p = self.P = params or TrackerParams()
        f = (IMG_W / 2) / np.tan(np.radians(p.fov_h_deg) / 2)
        self.K = np.array([[f, 0, IMG_W / 2], [0, f, IMG_H / 2], [0, 0, 1.0]])
        self.Ki = np.linalg.inv(self.K)
        self.H = None              # 3x3，img->norm
        self.grade = GRADE_DEAD
        self.bias = np.zeros(3)    # 设备轴零偏
        self.cross = np.array([np.nan, np.nan])
        self.n_edges = 0           # 本帧测到的边数
        self.last_vision_t = -1e18
        self.t = 0.0
        self._last_gyro_ts = None
        # 诊断
        self.innov = np.nan        # 本帧校正前平均约束残差（norm px 量级）
        self.edges_meas = []       # 本帧测到的边 (idx, line, sigma, support)
        self.acq_candidate = -1
        self.edge_seen_t = [-1e18] * 4   # 每条边最近一次测到的时间（s）
        self._frame_no = 0

    # ---------------------------------------------------------------- 陀螺
    def on_gyro(self, ts_ns, wx, wy, wz):
        if self._last_gyro_ts is None:
            self._last_gyro_ts = ts_ns
            return
        dt = (ts_ns - self._last_gyro_ts) * 1e-9
        self._last_gyro_ts = ts_ns
        if dt <= 0 or dt > 0.1:
            return
        w_raw = np.array([wx, wy, wz])
        # 静止（视觉确认）且读数小 -> 在线零偏
        if getattr(self, "_vision_still", False) \
                and np.abs(w_raw).max() < self.P.bias_max_rate:
            self.bias = (1 - self.P.bias_alpha) * self.bias + self.P.bias_alpha * w_raw
        w = w_raw - self.bias
        if self.P.rotation == 180:
            w = w * np.array([-1.0, -1.0, 1.0])
        # 设备轴 -> 相机轴，立即传播 H（每个陀螺 tick 都更新，
        # 使准星能以陀螺速率输出而非帧率）
        if self.H is not None:
            th = M_ROT0 @ (w * dt)
            T = self.K @ (np.eye(3) + _skew(th)) @ self.Ki   # img old -> img new
            try:
                self.H = _norm_h(self.H @ np.linalg.inv(T))
            except np.linalg.LinAlgError:
                self.H = None

    # ---------------------------------------------------------------- 主入口
    def process(self, g640: np.ndarray, ts_ns):
        p = self.P
        self.t = ts_ns * 1e-9
        self._frame_no += 1
        self.edges_meas = []
        self.innov = np.nan
        self.acq_candidate = -1

        # 2) 阈值（与旧管线一致的全图直方图法）
        thr, low_thr = self._thresholds(g640)

        # 3) 跟踪路径：逐边测量 + H 校正
        corrected = False
        if self.H is not None:
            meas = self._measure_edges(g640, low_thr)
            self.edges_meas = meas
            if meas:
                self._apply_correction(meas)
                corrected = True
                self.last_vision_t = self.t
                self.n_edges = len(meas)
                self.grade = {4: GRADE_FULL, 3: GRADE_PARTIAL, 2: GRADE_PARTIAL,
                              1: GRADE_EDGE}[len(meas)]
                self._update_bias()
            else:
                self.n_edges = 0
                if self.t - self.last_vision_t > p.t_gyro_max:
                    self.H = None
                else:
                    self.grade = GRADE_GYRO

        # 4) 采集路径：无 H 时必须采集；GYRO 超 0.3s 或边数长期不足时并行采集
        #    （追踪漂移/偏置超出门限时由采集纠回；采集校验严格，不会错锁）
        need_acq = self.H is None
        if not need_acq and self.grade == GRADE_GYRO \
                and self.t - self.last_vision_t > 0.3:
            need_acq = True
        if not need_acq and self.n_edges < 3 and self._frame_no % 5 == 0:
            need_acq = True
        if need_acq:
            h_acq = self._acquire(g640, thr, low_thr)
            if h_acq is not None:
                if self.H is None:
                    self.H = h_acq
                    self.grade = GRADE_FULL
                    self.n_edges = 4
                    self.last_vision_t = self.t
                    self.edge_seen_t = [self.t] * 4
                else:
                    # 与现有 H 比较：偏差 >4px 才融合（采集自身的 ~1px 噪声不引入）
                    ca = (h_acq @ np.array([IMG_W / 2, IMG_H / 2, 1.0]))
                    ca = ca[:2] / ca[2]
                    cb = self.H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
                    cb = cb[:2] / cb[2]
                    if np.hypot(*(ca - cb)) > 4.0:
                        h = 0.3 * self.H.reshape(9) + 0.7 * h_acq.reshape(9)
                        self.H = _norm_h(h.reshape(3, 3))
                        self.grade = GRADE_FULL
                        self.n_edges = 4
                        self.last_vision_t = self.t
                        self.edge_seen_t = [self.t] * 4
        if self.H is None:
            self.grade = GRADE_DEAD
            self.cross[:] = np.nan
            return

        # 5) 输出准星 = H·图像中心
        c = self.H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        self.cross = c[:2] / c[2]

    # ---------------------------------------------------------------- 阈值
    @staticmethod
    def _thresholds(g640):
        g = g640[::2, ::2]
        hist = np.bincount(g.ravel(), minlength=256)
        need = int(g.size * 0.02) + 1
        acc, thr = 0, 255
        for v in range(255, -1, -1):
            acc += int(hist[v])
            if acc >= need:
                thr = v
                break
        thr = min(max(thr, TrackerParams.acq_thr), 254)
        low_thr = max(TrackerParams.low_thr_min, int(thr * TrackerParams.low_thr_ratio))
        return thr, low_thr

    # ---------------------------------------------------------------- 边测量
    def _measure_edges(self, g640, low_thr):
        p = self.P
        Hn = _norm_h(self.H)
        lines_pred = Hn.T @ EDGE_LINES.T     # 3x4：每列一条预测图像边线
        # 预测四角（图像坐标）
        Hi = np.linalg.inv(Hn)
        pc = (Hi @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
        pc = pc[:, :2] / pc[:, 2:3]
        meas = []
        for e in range(4):
            # 边 e 端点 = 角点 e 与 e+1（top: TL->TR, right: TR->BR, ...）
            p0, p1 = pc[e], pc[(e + 1) % 4]
            seg = _clip_segment(p0, p1, 4.0)
            if seg is None:
                continue
            q0, q1 = seg
            if np.hypot(*(q1 - q0)) < p.min_visible_len:
                continue
            # 每边自适应带宽：连续未测到越久带宽越大
            band_e = min(p.band + p.band_grow * (self.t - self.edge_seen_t[e]),
                         p.band_max)
            lp = lines_pred[:, e]
            nrm = np.hypot(lp[0], lp[1])
            if nrm < 1e-12:
                continue
            lp = lp / nrm
            cen = pc.mean(axis=0)
            fit = _fit_line_band(g640, low_thr, q0, q1, band_e, p, cen=cen)
            if fit is None:
                continue
            line, sigma, support, pa, pb = fit
            mid = (q0 + q1) / 2
            # 创新门限：拟合线与预测线的平均有向距离（随带宽动态放宽）
            innov = abs(line[0] * mid[0] + line[1] * mid[1] + line[2]
                        - (lp[0] * mid[0] + lp[1] * mid[1] + lp[2]))
            # 两线夹角门限（防止贴合到交叉亮结构）
            ang = abs(line[0] * lp[1] - line[1] * lp[0])
            if innov > band_e or ang > 0.10:
                if DEBUG_SEQ == self._frame_no - 1:
                    print(f"dbg py seq {DEBUG_SEQ} edge {e}: gate innov={innov:.1f} ang={ang:.3f} band={band_e:.1f}")
                continue
            # 内侧暗度：沿边多点向四边形内采样，中位亮度须暗
            d_in = np.array([-line[0], -line[1]])     # line 法向朝外 -> 内侧为负
            L = np.hypot(*(q1 - q0))
            n_s = max(3, int(L / 40))
            ts = np.linspace(0.15, 0.85, n_s)
            samp = []
            for tt in ts:
                sp = q0 + (q1 - q0) * tt + d_in * p.inside_off
                xi, yi = int(round(sp[0])), int(round(sp[1]))
                if 0 <= xi < g640.shape[1] and 0 <= yi < g640.shape[0]:
                    samp.append(int(g640[yi, xi]))
            if len(samp) >= 3 and np.median(samp) > low_thr - p.dark_margin:
                if DEBUG_SEQ == self._frame_no - 1:
                    print(f"dbg py seq {DEBUG_SEQ} edge {e}: darkness reject med={np.median(samp):.0f} thr={low_thr}")
                continue    # 内侧不暗：文字屏/灯具等假边
            # 约束点 = 实测支撑段首末位置（不再用预测端点）
            # 仅当创新量可信时重置带宽计时（边界拟合不收窄带宽，防"窄带锁定错误线"）
            if innov < min(band_e / 2, 5.0):
                self.edge_seen_t[e] = self.t
            meas.append((e, line, sigma, support, pa, pb))
        return meas

    # ---------------------------------------------------------------- H 校正
    def _apply_correction(self, meas):
        """两种机制：
        - 4 边（FULL）：角点交点 -> DLT 直接解 H_meas，向它按比例收敛（绝对复位，
          消除相似校正无法观测的透视自由度漂移）；
        - 1-3 边：图像空间相似校正（平移/旋转/尺度）——每边提供法向偏移 o_e
          （预测线到实测线的有向距离）与夹角 δθ_e；平移由 n_eᵀt=o_e 最小二乘，
          旋转=夹角加权均值，尺度=平行边对间距比。良态、无病态求解。"""
        p = self.P
        h = _norm_h(self.H).reshape(9)
        g = {4: p.gain_full, 3: p.gain_partial, 2: p.gain_partial,
             1: p.gain_edge}[len(meas)]
        if len(meas) == 4:
            lines = {e: line for e, line, sigma, support, pa, pb in meas}
            corners = []
            ok = True
            for k in range(4):
                cr = np.cross(lines[(k - 1) % 4], lines[k])
                if abs(cr[2]) < 1e-9:
                    ok = False
                    break
                corners.append(cr[:2] / cr[2])
            if ok and _geo_valid(np.array(corners)):
                H_meas = _h_from_corners(np.array(corners))
                if H_meas is not None:
                    Hm = _norm_h(H_meas)
                    if float((Hm.reshape(9) @ h)) < 0:
                        Hm = -Hm
                    self._blend_h(Hm, g)
                    return
            # 4 边但角点非法：退回相似校正
        self._similarity_correction(meas, g)

    def _blend_h(self, H_target, g):
        """向目标 H 收敛，准星位移 slew 限幅。"""
        p = self.P
        h0 = _norm_h(self.H)
        c0 = h0 @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        c0 = c0[:2] / c0[2]
        c1 = H_target @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        c1 = c1[:2] / c1[2]
        dist = float(np.hypot(*(c1 - c0)))
        self.innov = dist
        gg = g
        if dist > p.slew_cap:
            gg = g * p.slew_cap / dist
        h = (1 - gg) * h0.reshape(9) + gg * H_target.reshape(9)
        self.H = _norm_h(h.reshape(3, 3))

    def _similarity_correction(self, meas, g):
        p = self.P
        Hn = _norm_h(self.H)
        Hi = np.linalg.inv(Hn)
        pc_pred = (Hi @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
        pc_pred = pc_pred[:, :2] / pc_pred[:, 2:3]
        cen = pc_pred.mean(axis=0)
        lines_pred = Hn.T @ EDGE_LINES.T
        # 平移：n_eᵀ t = o_e（o_e = 实测中点到预测线的有向距离，法向统一朝外）
        trows, tvals, tw = [], [], []
        angles, aw = [], []
        outs = {}
        for e, line, sigma, support, pa, pb in meas:
            lp = lines_pred[:, e]
            nrm = np.hypot(lp[0], lp[1])
            if nrm < 1e-12:
                continue
            lp = lp / nrm
            # 预测线法向统一朝外（背离预测质心），否则 o/δθ 符号混乱
            me = (pc_pred[e] + pc_pred[(e + 1) % 4]) / 2
            if lp[0] * (me[0] - cen[0]) + lp[1] * (me[1] - cen[1]) < 0:
                lp = -lp
            mid = (pa + pb) / 2
            o = lp[0] * mid[0] + lp[1] * mid[1] + lp[2]     # >0 = 实测在预测外侧
            le = float(np.hypot(*(pb - pa)))
            w = support * max(le, 1.0)
            outs[e] = (o, lp)
            trows.append(lp[:2])
            tvals.append(o)
            tw.append(w)
            dth = np.arctan2(lp[0] * line[1] - lp[1] * line[0],
                             lp[0] * line[0] + lp[1] * line[1])
            angles.append(dth)
            aw.append(w)
        if not trows:
            return
        A = np.stack(trows)
        b = np.array(tvals)
        W = np.diag(np.array(tw) / max(tw))
        # 2x2 加权最小二乘；平行边对（top+bottom / left+right）时 A 行近反平行，
        # 垂直于边的方向病态——按特征值截断，只沿可观测方向校正
        ata = A.T @ W @ A
        atb = A.T @ W @ b
        ev, V = np.linalg.eigh(ata)
        t = np.zeros(2)
        for i in range(2):
            if ev[i] > 0.04 * ev[-1]:
                t += (V[:, i] @ atb) / ev[i] * V[:, i]
        theta = float(np.average(angles, weights=aw))
        # 尺度：平行边对间距变化（o 已统一朝外）
        s = 1.0
        s_list = []
        for e0, e1 in ((0, 2), (3, 1)):
            if e0 not in outs or e1 not in outs:
                continue
            o0, lp0 = outs[e0]
            o1, lp1 = outs[e1]
            n_axis = lp0[:2] - lp1[:2]
            na = np.hypot(*n_axis)
            if na < 1e-6:
                continue
            n_axis = n_axis / na
            D_pred = abs(n_axis @ (pc_pred[e0] - pc_pred[e1]))
            if D_pred > 20:
                s_list.append(1.0 + (o0 + o1) / D_pred)
        if s_list:
            s = float(np.clip(np.mean(s_list), 0.9, 1.1))
        if DEBUG_SEQ == self._frame_no - 1:
            print(f"dbg py seq {DEBUG_SEQ}: simcorr t={np.round(t,3)} "
                  f"theta={np.degrees(theta):.3f} s={s:.4f} g={g}")
        #  fractional 应用 + slew 限幅
        t = t * g
        theta = theta * g
        s = 1.0 + (s - 1.0) * g
        if abs(theta) > np.radians(3):
            theta = np.sign(theta) * np.radians(3)
        cx0, cy0 = IMG_W / 2, IMG_H / 2
        ct, st = np.cos(theta), np.sin(theta)
        # C(p) = s·R(θ)·(p-c) + c + t
        C = np.array([[s * ct, -s * st, cx0 - s * ct * cx0 + s * st * cy0 + t[0]],
                      [s * st, s * ct, cy0 - s * st * cx0 - s * ct * cy0 + t[1]],
                      [0.0, 0.0, 1.0]])
        # slew 限幅：比较校正前后准星
        c0 = self.H @ np.array([cx0, cy0, 1.0])
        c0 = c0[:2] / c0[2]
        H1 = _norm_h(self.H @ np.linalg.inv(C))
        c1 = H1 @ np.array([cx0, cy0, 1.0])
        c1 = c1[:2] / c1[2]
        dist = float(np.hypot(*(c1 - c0)))
        self.innov = dist
        if dist > p.slew_cap:
            # 缩小 t 与角度/尺度（简单回退：整体向单位阵插值）
            frac = p.slew_cap / max(dist, 1e-9)
            Ci = (1 - frac) * np.eye(3) + frac * np.linalg.inv(C)
            self.H = _norm_h(self.H @ Ci)
        else:
            self.H = H1

    # ---------------------------------------------------------------- 零偏
    def _update_bias(self):
        p = self.P
        # 视觉校正量小且陀螺读数小 -> 认为静止，更新零偏
        # （调用处保证 meas 非空；innov 已更新）
        # 陀螺读数在 on_gyro 中处理：此处只检查视觉侧条件
        # 简化：innov 小即视觉稳定
        if np.isfinite(self.innov) and self.innov < 2.0:
            self._vision_still = True
        else:
            self._vision_still = False

    # ---------------------------------------------------------------- 采集
    def _acquire(self, g640, thr, low_thr):
        import cv2
        p = self.P
        g = g640[::2, ::2]
        dh, dw = g.shape
        npx = dw * dh
        mask = (g >= low_thr).astype(np.uint8)
        nlab, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        if nlab <= 1:
            return None
        hi = np.bincount(labels[g >= thr].ravel(), minlength=nlab)
        area = stats[:, cv2.CC_STAT_AREA]
        cand = [i for i in range(1, nlab)
                if hi[i] >= p.acq_min_seeds and area[i] >= p.acq_min_blob_frac * npx]
        cand.sort(key=lambda i: -area[i])
        for ci, i in enumerate(cand[:p.acq_max_cand]):
            ys, xs = np.nonzero(labels == i)
            s = xs + ys
            d = xs - ys
            pts = {"tl": (xs[np.argmin(s)], ys[np.argmin(s)]),
                   "br": (xs[np.argmax(s)], ys[np.argmax(s)]),
                   "tr": (xs[np.argmax(d)], ys[np.argmax(d)]),
                   "bl": (xs[np.argmin(d)], ys[np.argmin(d)])}

            def refine(cx, cy):
                j0, j1 = max(0, cy - 2), min(dh - 1, cy + 2)
                i0, i1 = max(0, cx - 2), min(dw - 1, cx + 2)
                win = labels[j0:j1 + 1, i0:i1 + 1]
                wy, wx = np.nonzero(win == i)
                if len(wx) == 0:
                    return float(cx), float(cy)
                return float(wx.mean() + i0), float(wy.mean() + j0)

            quad = np.array([refine(*pts["tl"]), refine(*pts["tr"]),
                             refine(*pts["br"]), refine(*pts["bl"])]) * 2.0  # ->640
            if not _quad_valid(quad):
                continue
            lines = []
            ok = True
            cen = quad.mean(axis=0)
            for e in range(4):
                q0, q1 = quad[e], quad[(e + 1) % 4]   # top: TL->TR, right: TR->BR, ...
                fit = _fit_line_band(g640, low_thr, q0, q1, p.band, p, cen=cen)
                if fit is None:
                    ok = False
                    break
                line, sigma, support, _, _ = fit
                lines.append(line)
            if not ok:
                continue
            # 四角 = 相邻边交点
            corners = []
            for k in range(4):
                cr = np.cross(lines[(k - 1) % 4], lines[k])
                if abs(cr[2]) < 1e-9:
                    ok = False
                    break
                corners.append(cr[:2] / cr[2])
            if not ok:
                continue
            corners = np.array(corners)
            if not _geo_valid(corners):
                continue
            # 中空校验：内缩四边形内亮像素占比须低（游戏区为黑）
            if not _hollow_check(g640, corners, low_thr, p.acq_dark_frac):
                continue
            # 由四角直接解 H（DLT）
            H = _h_from_corners(corners)
            if H is None:
                continue
            self.acq_candidate = ci
            return _norm_h(H)
        return None


# ================================================================ 几何工具

DEBUG_SEQ = -1   # 调试：非负时打印该帧的逐边测量细节

def _norm_h(H):
    """单应规范化为 H[2,2]=1（正号）。||H||=1 规范化会让 h22 ~ 1/340，
    导致准星 = (H·c)/w 的分母 w≈0.003——h8 噪声被放大数百倍，不可用。"""
    if H is None:
        return None
    s = H[2, 2]
    if abs(s) < 1e-12:
        return H
    return H / s


def _clip_segment(p0, p1, inset):
    """线段与图内矩形 [inset, W-inset]x[inset, H-inset] 求交，返回端点或 None。"""
    x0, y0 = inset, inset
    x1, y1 = IMG_W - inset, IMG_H - inset
    d = p1 - p0
    t0, t1 = 0.0, 1.0
    for pp, dd, lo, hi in ((p0[0], d[0], x0, x1), (p0[1], d[1], y0, y1)):
        if abs(dd) < 1e-12:
            if pp < lo or pp > hi:
                return None
            continue
        ta = (lo - pp) / dd
        tb = (hi - pp) / dd
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 >= t1:
            return None
    return p0 + d * t0, p0 + d * t1


def _fit_line_band(g640, low_thr, q0, q1, band, p: TrackerParams, cen=None):
    """沿 q0->q1 线段 ±band 带内定位亮边条纹的**外侧过零边**（亚像素）：
    每个纵向 bin 把像素按 perp 聚合为强度剖面，估计亮/暗电平，从带外侧向
    内扫描亮→暗中点的过零位置（线性插值），要求内侧连续 ≥3px 保持亮
    （排除孤立亮斑）；得到每 bin 一个边点，TLS+2σ 剔除拟合直线。
    相比 95 分位包络：条纹靠近带边时无截断偏差（运动滞后时不产生系统误差）。
    cen = 四边形内侧参考点（定法向朝外）；缺省则法向任意。
    返回 (line, sigma, support, pt0, pt1)：line 为图像齐次线（法向朝外），
    pt0/pt1 = 支撑段首末 bin 中心在拟合线上的位置（约束点）。失败 None。"""
    d = q1 - q0
    L = float(np.hypot(*d))
    if L < 1:
        return None
    d = d / L
    nv = np.array([-d[1], d[0]])
    if cen is not None:
        mid = (q0 + q1) / 2
        if nv[0] * (mid[0] - cen[0]) + nv[1] * (mid[1] - cen[1]) < 0:
            nv = -nv      # 法向朝外（perp 高端 = 条纹外侧）
    x0 = max(int(min(q0[0], q1[0]) - band - 2), 0)
    x1 = min(int(max(q0[0], q1[0]) + band + 2), int(IMG_W))
    y0 = max(int(min(q0[1], q1[1]) - band - 2), 0)
    y1 = min(int(max(q0[1], q1[1]) + band + 2), int(IMG_H))
    sub = g640[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.nonzero(np.ones_like(sub))
    xx = xx + x0
    yy = yy + y0
    val = sub[yy - y0, xx - x0]
    perp = (xx - q0[0]) * nv[0] + (yy - q0[1]) * nv[1]
    lon = (xx - q0[0]) * d[0] + (yy - q0[1]) * d[1]
    sel = (np.abs(perp) <= band) & (lon >= 0) & (lon <= L)
    if sel.sum() < p.min_edge_bins * 2:
        return None
    perp, lon, val = perp[sel], lon[sel], val[sel]
    n_bins = int(L / p.edge_bin_w)
    if n_bins < p.min_edge_bins:
        return None
    bi = np.minimum((lon / p.edge_bin_w).astype(int), n_bins - 1)
    pts = []          # (lon_center, perp_cross)
    pt_bins = []
    for b in range(n_bins):
        m = bi == b
        if m.sum() < 4:
            continue
        bp = perp[m]
        bv = val[m]
        bright = np.median(bv[bv >= low_thr]) if (bv >= low_thr).any() else np.nan
        dark = np.median(bv[bv < low_thr]) if (bv < low_thr).any() else np.nan
        if not np.isfinite(bright) or not np.isfinite(dark) or bright - dark < 30:
            continue
        mid_lvl = (bright + dark) / 2
        # 聚合到整数 perp 栅格（圆心像素最近邻），从带外侧向内找过零
        ip = np.clip(np.round(bp).astype(int), int(-band), int(band))
        rows = np.zeros(2 * int(band) + 1)
        cnt = np.zeros(2 * int(band) + 1)
        idxp = ip - int(-band)
        np.add.at(rows, idxp, bv)
        np.add.at(cnt, idxp, 1)
        rows = np.where(cnt > 0, rows / np.where(cnt > 0, cnt, 1), np.nan)
        # 外侧 = 高 perp（法向朝外由调用处保证？此处 nv 方向任意：
        # 统一从 perp 高端向内扫，调用方负责法向定向——条纹是对称的，
        # 边框条纹特征 = 外侧暗内侧亮；若扫到的是内侧边缘会偏一条纹宽，
        # 由内侧暗度校验兜底拒绝）
        cross = None
        for k in range(len(rows) - 1, 3, -1):
            r0, r1 = rows[k], rows[k - 1]
            if np.isnan(r0) or np.isnan(r1):
                continue
            if r0 < mid_lvl <= r1:
                inward = rows[k - 4:k - 1]
                if np.isnan(inward).any() or (inward >= mid_lvl).sum() < 2:
                    continue
                frac = (mid_lvl - r0) / (r1 - r0 + 1e-9)
                cross = (k - 1 + frac) + int(-band)
                break
        if cross is None:
            continue
        pts.append(((b + 0.5) * p.edge_bin_w, cross))
        pt_bins.append(b)
    support = len(pts) / n_bins
    if len(pts) < p.min_edge_bins or support < p.min_support:
        return None
    arr = np.array(pts)   # (lon, perp_cross)
    # TLS 于 (lon, perp) 平面
    sigma = float("inf")
    keep_bins = np.array(pt_bins)
    for _ in range(p.trim_rounds + 1):
        ctr = arr.mean(axis=0)
        cov = np.cov((arr - ctr).T)
        eigval, eigvec = np.linalg.eigh(cov)
        nv_l = eigvec[:, 0]      # (lon, perp) 平面的法向
        res = (arr - ctr) @ nv_l
        sigma = float(res.std())
        if sigma < 1e-9:
            break
        inl = np.abs(res - res.mean()) <= 2 * sigma
        if inl.all():
            break
        arr = arr[inl]
        keep_bins = keep_bins[inl]
        if len(arr) < p.min_edge_bins:
            return None
    if sigma > p.max_sigma:
        return None
    # (lon,perp) 线 -> 图像线：点 = q0 + d*lon + nv*perp
    # 图像法向 = nv_l[1]*nv（perp 分量）+ nv_l[0]*d（lon 分量）
    normal = nv_l[1] * nv + nv_l[0] * d
    nl = np.hypot(*normal)
    if nl < 1e-12:
        return None
    normal = normal / nl
    if normal @ nv < 0:            # 法向统一朝外（perp 高端）
        normal = -normal
    ctr_img = q0 + d * ctr[0] + nv * ctr[1]
    line = np.array([normal[0], normal[1], -normal @ ctr_img])
    # 支撑段端点（首末 bin 中心投影到线上）
    lon0 = (keep_bins[0] + 0.5) * p.edge_bin_w
    lon1 = (keep_bins[-1] + 0.5) * p.edge_bin_w
    pa = q0 + d * lon0
    pb = q0 + d * lon1
    pa = pa - (line[0] * pa[0] + line[1] * pa[1] + line[2]) * line[:2]
    pb = pb - (line[0] * pb[0] + line[1] * pb[1] + line[2]) * line[:2]
    return line, sigma, support, pa, pb


def _quad_valid(quad640):
    pts = quad640
    area = 0.0
    for i in range(4):
        j = (i + 1) % 4
        area += pts[i, 0] * pts[j, 1] - pts[j, 0] * pts[i, 1]
    if abs(area) / 2 < 0.02 * IMG_W * IMG_H:
        return False
    for i in range(4):
        j = (i + 1) % 4
        if np.hypot(*(pts[j] - pts[i])) < 40:
            return False
    return True


def _geo_valid(corners640):
    tl, tr, br, bl = corners640

    def ang(p, q):
        return np.arctan2(q[1] - p[1], q[0] - p[0])

    def ang_diff(a, b):
        dd = (a - b) % np.pi
        return dd - np.pi if dd > np.pi / 2 else (dd + np.pi if dd < -np.pi / 2 else dd)

    lim = np.deg2rad(15)
    if abs(ang_diff(ang(tl, tr), ang(bl, br))) > lim:
        return False
    if abs(ang_diff(ang(tl, bl), ang(tr, br))) > lim:
        return False
    w = (np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2
    h = (np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2
    if w <= 0 or h <= 0:
        return False
    asp = max(w, h) / min(w, h)
    return 1.1 <= asp <= 3.0


def _hollow_check(g640, corners640, low_thr, max_frac):
    """内缩（线性 0.82）四边形内 >= low_thr 像素占比须 <= max_frac（边框环中空）。"""
    import cv2
    cen = corners640.mean(axis=0)
    inner = cen + (corners640 - cen) * 0.82
    mask = np.zeros(g640.shape, np.uint8)
    cv2.fillConvexPoly(mask, inner.astype(np.int32), 1)
    n = int(mask.sum())
    if n < 100:
        return False
    bright = int(((g640 >= low_thr) & (mask > 0)).sum())
    return bright / n <= max_frac


def _h_from_corners(corners640):
    """DLT 解 img->norm 单应。"""
    A = []
    for (x, y), (X, Y) in zip(corners640, SCREEN_CORNERS):
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y, -X])
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y])
    A = np.array(A)
    try:
        _, _, vt = np.linalg.svd(A)
    except np.linalg.LinAlgError:
        return None
    H = vt[-1].reshape(3, 3)
    if abs(H[2, 2]) < 1e-12:
        return None
    return H / H[2, 2]


# ================================================================ 自测
if __name__ == "__main__":
    """合成场景冒烟：亮环 + 干扰块采集；陀螺匀速 wx 传播方向；空帧 4s -> DEAD。"""
    W, Hh = 640, 360
    g = np.full((Hh, W), 10, np.uint8)
    g[75:286, 100:103] = 255
    g[75:286, 537:541] = 255
    g[75:79, 100:541] = 255
    g[282:286, 100:541] = 255
    g[300:335, 10:55] = 250      # 干扰亮块
    tr = Tracker(TrackerParams())
    tr.process(g, 1_000_000_000)
    assert tr.grade == GRADE_FULL, f"ring acquire: grade={tr.grade}"
    assert abs(tr.cross[0] - 960) < 30 and abs(tr.cross[1] - 540) < 30, f"cross {tr.cross}"
    # 陀螺传播：wy=-0.1 rad/s 1s（200Hz tick），跨 30 个空帧
    t = 1_000_000_000
    for k in range(200):
        t += 5_000_000
        tr.on_gyro(t, 0.0, -0.1, 0.0)
    blank = np.full((Hh, W), 10, np.uint8)
    for k in range(30):
        tr.process(blank, 1_000_000_000 + 5_000_000 * (k + 1))
    assert tr.grade == GRADE_GYRO, f"grade after blanks={tr.grade}"
    dy = tr.cross[1] - 540
    assert dy < -20, f"propagation dy={dy}"
    # 4s 空帧 -> DEAD -> 重新采集
    t2 = 2_000_000_000
    for k in range(120):
        t2 += 33_333_333
        tr.process(blank, t2)
    assert tr.grade == GRADE_DEAD, f"grade after 4s blanks={tr.grade}"
    tr.process(g, t2 + 33_333_333)
    assert tr.grade == GRADE_FULL, "re-acquire after DEAD"
    print(f"guntrack selftest PASS (cross=({tr.cross[0]:.1f},{tr.cross[1]:.1f}), bias={tr.bias.round(4)})")
