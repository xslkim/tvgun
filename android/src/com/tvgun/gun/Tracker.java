package com.tvgun.gun;

import java.util.Arrays;

/**
 * Homography tracker for the TV gun: state is H (3x3, image px -> normalized
 * 1920x1080 screen coords), propagated every gyro tick by
 * H <- H * (K*(I+[M*w*dt]x)*K^-1)^-1 (pure-rotation inter-frame motion, exact
 * regardless of viewing distance), and corrected per camera frame by
 * independent per-edge measurements of the bright screen border:
 *   - each screen edge predicted visible is fitted in a band around the
 *     predicted line (per-bin bright-stripe outer-edge zero crossing,
 *     sub-pixel, TLS + 2-sigma trim);
 *   - 4 edges (FULL): corners = line intersections -> DLT H_meas -> blend;
 *   - 1-3 edges (PARTIAL/EDGE): image-space similarity correction
 *     (translation via truncated 2x2 LS of n_e^T t = o_e, rotation = weighted
 *     mean angle, scale = parallel-pair spacing ratio);
 *   - 0 edges: GYRO (propagation only, <= T_GYRO_MAX 3s), else DEAD.
 * Acquisition (from DEAD or degraded track): multi-candidate blob search with
 * 4-edge fit + hollow/interior-darkness checks (rejects lamps, text screens).
 * Gyro bias is estimated online while vision confirms stillness.
 *
 * Axis mapping (device -> camera, rot=0), regressed on two recordings and
 * identical for both lenses: cam_x = +wy, cam_y = +wx, cam_z = -wz.
 * rot=180 flips wx/wy signs first.
 *
 * Pure Java (no Android deps) so it can be unit-tested offline. All timestamps
 * are caller-supplied nanoseconds from a monotonic clock.
 * Port of scripts/guntrack.py — keep semantics in sync.
 *
 * grade: 0=DEAD 1=GYRO 2=EDGE 3=PARTIAL 4=FULL
 */
public final class Tracker {
    public static final float NORM_W = 1920f;
    public static final float NORM_H = 1080f;

    public static final int GRADE_DEAD = 0;
    public static final int GRADE_GYRO = 1;
    public static final int GRADE_EDGE = 2;
    public static final int GRADE_PARTIAL = 3;
    public static final int GRADE_FULL = 4;
    public static final String[] GRADE_NAMES = {"DEAD", "GYRO", "EDGE", "PARTIAL", "FULL"};

    // ---- tunables (keep in sync with guntrack.TrackerParams) ----
    private static final float BAND = 12f;
    private static final float BAND_GROW = 12f;        // px/s while an edge stays unseen/untrusted
    private static final float BAND_MAX = 24f;
    private static final float EDGE_BIN_W = 3f;
    private static final int MIN_EDGE_BINS = 12;
    private static final float MIN_SUPPORT = 0.45f;
    private static final float MAX_SIGMA = 2.5f;
    private static final int TRIM_ROUNDS = 2;
    private static final float MIN_VISIBLE_LEN = 28f;
    private static final int DARK_MARGIN = 25;
    private static final float INSIDE_OFF = 10f;
    private static final float ANG_GATE = 0.10f;       // |sin| of line-vs-pred angle
    private static final float GAIN_FULL = 0.6f;
    private static final float GAIN_PARTIAL = 0.5f;
    private static final float GAIN_EDGE = 0.35f;
    private static final float SLEW_CAP = 0f;         // 0=不限幅（限幅会把正确采集拖到几十帧收敛，比跳变更糟；防假跳变靠门控）
    private static final float T_GYRO_MAX_S = 3.0f;
    private static final float BIAS_ALPHA = 0.02f;
    private static final float BIAS_MAX_RATE = 0.06f;  // rad/s
    private static final int ACQ_MAX_CAND = 5;
    private static final int ACQ_MIN_SEEDS = 10;
    private static final float ACQ_MIN_BLOB_FRAC = 0.006f;
    private static final float ACQ_DARK_FRAC = 0.30f;
    private static final int THR_CLAMP_LO = 190;
    private static final float LOW_THR_RATIO = 0.75f;
    private static final int LOW_THR_MIN = 150;
    private static final double MAX_DT_S = 0.1;
    private static final float ACQ_RESCUE_S = 0.3f;    // GYRO 超过此时长并行采集
    private static final int ACQ_RETRY_FRAMES = 5;     // n_edges<3 时每 N 帧并行采集

    // device -> camera axis map at rot=0: th_cam = M * w_dev
    private static final double[] M_ROT0 = {0, 1, 0,
                                            1, 0, 0,
                                            0, 0, -1};

    // screen edge lines (outer border edges), order top, right, bottom, left
    private static final double[][] EDGE_LINES = {
            {0, 1, 0}, {1, 0, -NORM_W}, {0, 1, -NORM_H}, {1, 0, 0}};

    // ---- runtime config ----
    private double fovHDeg = 67.94;
    private int rotation;    // 0 or 180

    // ---- state ----
    private final double[] H = new double[9];   // row-major 3x3, gauge H[8]=1
    private boolean haveH;
    public int grade = GRADE_DEAD;
    public int nEdges;
    public final float[] cross = {Float.NaN, Float.NaN};
    public final double[] bias = new double[3]; // device axes
    private double lastVisionS = -1e18;
    private double tNowS;
    private final double[] edgeSeenS = {-1e18, -1e18, -1e18, -1e18};
    private int frameNo;
    private boolean visionStill;
    public float innov = Float.NaN;             // pre-gain correction, norm px
    public int acqCandidate = -1;
    public int lastThr, lastLowThr;
    public static int debugSeq = -1;            // ReplayTest 调试用：逐帧打印边测量细节
    public static int debugEdge = -1;           // 当前正在拟合的边（fitLineBand 打印用）

    // ---- camera intrinsics (computed per frame size) ----
    private int imgW = 640, imgH = 360;
    private double fk = 475, cx0 = 320, cy0 = 180;
    private final double[] K = new double[9];
    private final double[] Ki = new double[9];

    // ---- gyro ring buffer (lazy propagation: integrate only up to the queried time) ----
    private static final int GYRO_CAP = 2048;
    private final long[] gTs = new long[GYRO_CAP];
    private final float[] gWx = new float[GYRO_CAP];
    private final float[] gWy = new float[GYRO_CAP];
    private final float[] gWz = new float[GYRO_CAP];
    private int gHead, gSize;
    private long gyroLastNs = -1;
    private long baseNs = -1;   // H 基准时间（H 处于 baseNs 时刻）

    // ---- work buffers ----
    private byte[] grayA;      // 320x180 coarse
    private int[] labels;
    private int[] stack;
    private float[] fPerp;     // per-edge pixel workspace (sized w*h)
    private float[] fLon;
    private float[] fVal;
    private int[] fBin;
    private double[] profSum = new double[2 * 25 + 2];
    private int[] profCnt = new int[2 * 25 + 2];
    private float[] medBuf;
    private double[] envLon = new double[256];
    private double[] envPerp = new double[256];
    private int[] envBin = new int[256];

    public synchronized void setFov(double deg) {
        fovHDeg = deg;
    }

    public synchronized void setRotation(int deg) {
        rotation = ((deg % 360) + 360) % 360;
    }

    public synchronized void reset() {
        haveH = false;
        grade = GRADE_DEAD;
        cross[0] = cross[1] = Float.NaN;
        Arrays.fill(bias, 0);
        Arrays.fill(edgeSeenS, -1e18);
        lastVisionS = -1e18;
        gyroLastNs = -1;
        gHead = gSize = 0;
        baseNs = -1;
        visionStill = false;
    }

    public int grade() {
        return grade;
    }

    // ---------------------------------------------------------------- gyro
    /** Buffers the tick and updates the online bias estimate. No propagation here:
     *  the homography is advanced lazily by propagateTo / propFromBase so that the
     *  prediction used for a camera frame always matches its exposure timestamp
     *  (integrating to "now" overshoots by the worker latency and starves edges). */
    public synchronized void onGyro(long tsNs, float wx, float wy, float wz) {
        if (gyroLastNs >= 0) {
            double dt = (tsNs - gyroLastNs) * 1e-9;
            if (dt > 0 && dt <= MAX_DT_S && visionStill
                    && Math.abs(wx) < BIAS_MAX_RATE && Math.abs(wy) < BIAS_MAX_RATE
                    && Math.abs(wz) < BIAS_MAX_RATE) {
                bias[0] += BIAS_ALPHA * (wx - bias[0]);
                bias[1] += BIAS_ALPHA * (wy - bias[1]);
                bias[2] += BIAS_ALPHA * (wz - bias[2]);
            }
        }
        gyroLastNs = tsNs;
        int i = (gHead + gSize) % GYRO_CAP;
        gTs[i] = tsNs;
        gWx[i] = wx;
        gWy[i] = wy;
        gWz[i] = wz;
        if (gSize < GYRO_CAP) gSize++;
        else gHead = (gHead + 1) % GYRO_CAP;
    }

    /** One propagation step: H <- H * (K*(I+[M*w*dt]x)*Ki)^-1, in place. */
    private boolean gyroStep(double[] Ht, double mx, double my, double mz, double dt) {
        if (rotation == 180) {
            mx = -mx;
            my = -my;
        }
        double tx = (M_ROT0[0] * mx + M_ROT0[1] * my + M_ROT0[2] * mz) * dt;
        double ty = (M_ROT0[3] * mx + M_ROT0[4] * my + M_ROT0[5] * mz) * dt;
        double tz = (M_ROT0[6] * mx + M_ROT0[7] * my + M_ROT0[8] * mz) * dt;
        double[] R = {1, -tz, ty,
                      tz, 1, -tx,
                      -ty, tx, 1};
        double[] T = mul(mul(K, R), Ki);
        double[] Ti = inv3(T);
        if (Ti == null) return false;
        double[] Hn = mul(Ht, Ti);
        normH(Hn);
        System.arraycopy(Hn, 0, Ht, 0, 9);
        return true;
    }

    /** Re-integrate buffered ticks in (baseNs, tsNs] onto a COPY of the base H. */
    private double[] propFromBase(long tsNs) {
        if (!haveH) return null;
        double[] Ht = H.clone();
        long prevTs = Long.MIN_VALUE;
        boolean ok = true;
        for (int k = 0; k < gSize; k++) {
            int i = (gHead + k) % GYRO_CAP;
            long tg = gTs[i];
            if (tg <= baseNs) {
                prevTs = tg;    // dt anchor just before the window
                continue;
            }
            if (tg > tsNs) break;
            double dt = prevTs != Long.MIN_VALUE ? (tg - prevTs) * 1e-9 : 0.0;
            prevTs = tg;
            if (dt <= 0 || dt > MAX_DT_S) continue;
            ok = gyroStep(Ht, gWx[i] - bias[0], gWy[i] - bias[1], gWz[i] - bias[2], dt);
            if (!ok) return null;
        }
        return Ht;
    }

    /** Advances the base (and H) to tsNs, dropping older ticks but keeping the
     *  tick at tsNs as the dt anchor for the next round. */
    private void propagateTo(long tsNs) {
        if (haveH && tsNs > baseNs) {
            double[] Ht = propFromBase(tsNs);
            if (Ht == null) {
                haveH = false;
            } else {
                System.arraycopy(Ht, 0, H, 0, 9);
            }
        }
        baseNs = tsNs;
        while (gSize > 0 && gTs[gHead] < tsNs) {
            gHead = (gHead + 1) % GYRO_CAP;
            gSize--;
        }
    }

    // ---------------------------------------------------------------- frame
    public synchronized void processGray(byte[] g, int w, int h, long tsNs) {
        imgW = w;
        imgH = h;
        cx0 = w / 2.0;
        cy0 = h / 2.0;
        fk = cx0 / Math.tan(Math.toRadians(fovHDeg) / 2);
        setK(K, fk, cx0, cy0);
        inv3into(K, Ki);

        // 1) propagate the base (and H) to the frame's exposure timestamp first
        propagateTo(tsNs);

        tNowS = tsNs * 1e-9;
        frameNo++;
        innov = Float.NaN;
        acqCandidate = -1;

        int[] thrs = thresholds(g, w, h);
        int thr = thrs[0], lowThr = thrs[1];
        lastThr = thr;
        lastLowThr = lowThr;

        boolean corrected = false;
        if (haveH) {
            EdgeMeas[] meas = new EdgeMeas[4];
            int nm = measureEdges(g, w, h, lowThr, meas);
            nEdges = nm;
            if (nm > 0) {
                applyCorrection(meas, nm);
                corrected = true;
                lastVisionS = tNowS;
                grade = nm == 4 ? GRADE_FULL : (nm == 1 ? GRADE_EDGE : GRADE_PARTIAL);
                visionStill = innov < 2.0f;
            } else {
                if (tNowS - lastVisionS > T_GYRO_MAX_S) {
                    haveH = false;
                } else {
                    grade = GRADE_GYRO;
                }
            }
        }

        // acquisition: no H, GYRO>0.3s, or starved edges every N frames
        boolean needAcq = !haveH;
        if (!needAcq && grade == GRADE_GYRO && tNowS - lastVisionS > ACQ_RESCUE_S) needAcq = true;
        if (!needAcq && nEdges < 3 && frameNo % ACQ_RETRY_FRAMES == 0) needAcq = true;
        if (needAcq) {
            java.util.List<double[][]> cands = acqCandidates(g, w, h, thr, lowThr);
            double[] ha = acquire(g, w, h, lowThr, cands);
            int acqEdges = 4;
            if (ha == null) {
                ha = acquirePartial(g, w, h, lowThr, cands);
                acqEdges = 2;
            }
            if (ha != null) {
                if (!haveH) {
                    System.arraycopy(ha, 0, H, 0, 9);
                    haveH = true;
                    grade = acqEdges == 4 ? GRADE_FULL : GRADE_PARTIAL;
                    nEdges = acqEdges;
                    lastVisionS = tNowS;
                    Arrays.fill(edgeSeenS, tNowS);
                } else {
                    // 以四角最大位移判定是否融合（仅看准星会漏判形状不同但中心重合的错误）
                    double[] cA = applyH(ha, cx0, cy0);
                    double[] cB = applyH(H, cx0, cy0);
                    double d = Math.hypot(cA[0] - cB[0], cA[1] - cB[1]);
                    double[] HiA = inv3(normHcopy(ha));
                    double[] HiB = inv3(normHcopy(H));
                    double cdist = 0;
                    if (HiA != null && HiB != null) {
                        double[][] sc = {{0, 0}, {NORM_W, 0}, {NORM_W, NORM_H}, {0, NORM_H}};
                        for (int i = 0; i < 4; i++) {
                            double[] pa = applyH(HiA, sc[i][0], sc[i][1]);
                            double[] pb = applyH(HiB, sc[i][0], sc[i][1]);
                            cdist = Math.max(cdist, Math.max(Math.abs(pa[0] - pb[0]),
                                    Math.abs(pa[1] - pb[1])));
                        }
                    }
                    if (cdist > 6.0) {
                        double gMix = d > 100 ? 0.9 : 0.7;
                        if (SLEW_CAP > 0 && d > SLEW_CAP) gMix = gMix * SLEW_CAP / d;
                        for (int i = 0; i < 9; i++) H[i] = (1 - gMix) * H[i] + gMix * ha[i];
                        normH(H);
                        grade = acqEdges == 4 ? GRADE_FULL : GRADE_PARTIAL;
                        nEdges = acqEdges;
                        lastVisionS = tNowS;
                        Arrays.fill(edgeSeenS, tNowS);
                    }
                }
            }
        }
        if (!haveH) {
            grade = GRADE_DEAD;
            cross[0] = cross[1] = Float.NaN;
            return;
        }
        double[] c = applyH(H, cx0, cy0);
        cross[0] = (float) c[0];
        cross[1] = (float) c[1];
    }

    /** Point-in-time snapshot for aim reporting: lazily re-integrates the buffered
     *  gyro ticks from the base to nowNs (does not advance the base). */
    public synchronized float[] snapshot(long nowNs) {
        double[] Ht = haveH ? (nowNs > baseNs ? propFromBase(nowNs) : H) : null;
        if (Ht == null || grade == GRADE_DEAD) {
            return new float[]{Float.NaN, Float.NaN, grade};
        }
        double[] c = applyH(Ht, cx0, cy0);
        return new float[]{(float) c[0], (float) c[1], grade};
    }

    public synchronized boolean aimValid() {
        return haveH && grade != GRADE_DEAD;
    }

    /** Predicted screen quad (TL,TR,BR,BL) in image coords, or null when no H. */
    public synchronized float[] quadImage() {
        if (!haveH) return null;
        double[] Hi = inv3(normHcopy(H));
        if (Hi == null) return null;
        double[][] sc = {{0, 0}, {NORM_W, 0}, {NORM_W, NORM_H}, {0, NORM_H}};
        float[] q = new float[8];
        for (int i = 0; i < 4; i++) {
            double[] p = applyH(Hi, sc[i][0], sc[i][1]);
            q[2 * i] = (float) p[0];
            q[2 * i + 1] = (float) p[1];
        }
        return q;
    }

    /** Time (ns, caller clock) of the last vision-informed frame. */
    public synchronized long lastVisionNs() {
        return (long) (lastVisionS * 1e9);
    }

    // ---------------------------------------------------------------- thresholds
    private int[] thresholds(byte[] g, int w, int h) {
        int step = Math.max(1, Math.max(w, h) / 320);
        int sw = w / step, sh = h / step;
        if (grayA == null || grayA.length != sw * sh) grayA = new byte[sw * sh];
        for (int j = 0; j < sh; j++)
            for (int i = 0; i < sw; i++)
                grayA[j * sw + i] = g[(j * step) * w + i * step];
        int n = sw * sh;
        int[] hist = new int[256];
        for (int k = 0; k < n; k++) hist[grayA[k] & 0xff]++;
        int need = (int) (n * 0.02) + 1;
        int acc = 0, thr = 255;
        for (int v = 255; v >= 0; v--) {
            acc += hist[v];
            if (acc >= need) {
                thr = v;
                break;
            }
        }
        if (thr < THR_CLAMP_LO) thr = THR_CLAMP_LO;
        else if (thr > 254) thr = 254;
        int lowThr = Math.max(LOW_THR_MIN, (int) (thr * LOW_THR_RATIO));
        return new int[]{thr, lowThr};
    }

    // ---------------------------------------------------------------- edge measurement
    private static final class EdgeMeas {
        int edge;
        double[] line = new double[3];  // outward normal
        double sigma, support;
        double paX, paY, pbX, pbY;      // support-span endpoints on the fitted line
    }

    /**
     * For each screen edge whose predicted image segment is visible, fit the
     * border stripe's outer edge in a band around the predicted line.
     * Returns count; fills meas[0..count).
     */
    private int measureEdges(byte[] g, int w, int h, int lowThr, EdgeMeas[] meas) {
        double[] Hn = normHcopy(H);
        double[] Hi = inv3(Hn);
        if (Hi == null) return 0;
        // predicted corners (image coords)
        double[][] pc = new double[4][2];
        double[][] sc = {{0, 0}, {NORM_W, 0}, {NORM_W, NORM_H}, {0, NORM_H}};
        for (int i = 0; i < 4; i++) {
            double[] p = applyH(Hi, sc[i][0], sc[i][1]);
            pc[i][0] = p[0];
            pc[i][1] = p[1];
        }
        double ccx = (pc[0][0] + pc[1][0] + pc[2][0] + pc[3][0]) / 4;
        double ccy = (pc[0][1] + pc[1][1] + pc[2][1] + pc[3][1]) / 4;
        // predicted edge lines: l = H^T * L
        double[][] lp = new double[4][3];
        for (int e = 0; e < 4; e++) {
            for (int r = 0; r < 3; r++) {
                lp[e][r] = Hn[0 * 3 + r] * EDGE_LINES[e][0]
                        + Hn[1 * 3 + r] * EDGE_LINES[e][1]
                        + Hn[2 * 3 + r] * EDGE_LINES[e][2];
            }
            double nl = Math.hypot(lp[e][0], lp[e][1]);
            if (nl < 1e-12) continue;
            lp[e][0] /= nl;
            lp[e][1] /= nl;
            lp[e][2] /= nl;
        }
        int nm = 0;
        for (int e = 0; e < 4; e++) {
            double[] p0 = pc[e], p1 = pc[(e + 1) % 4];
            double[] seg = clipSegment(p0[0], p0[1], p1[0], p1[1], 4.0, w, h);
            if (seg == null) continue;
            double q0x = seg[0], q0y = seg[1], q1x = seg[2], q1y = seg[3];
            double segLen = Math.hypot(q1x - q0x, q1y - q0y);
            if (segLen < MIN_VISIBLE_LEN) continue;
            double band = Math.min(BAND + BAND_GROW * (tNowS - edgeSeenS[e]), BAND_MAX);
            double[] lpE = lp[e];
            if (Math.hypot(lpE[0], lpE[1]) < 1e-9) continue;
            debugEdge = e;
            double[] fit = fitLineBand(g, w, h, lowThr, q0x, q0y, q1x, q1y, band, ccx, ccy);
            debugEdge = -1;
            if (fit == null) {
                if (frameNo - 1 == debugSeq)
                    System.err.println("dbg seq " + debugSeq + " edge " + e + ": fit null"
                            + String.format(" band=%.1f len=%.1f q0=(%.1f,%.1f) q1=(%.1f,%.1f)",
                                    band, segLen, q0x, q0y, q1x, q1y));
                continue;
            }
            // fit = [nx, ny, c, sigma, support, paX, paY, pbX, pbY]
            double midX = (q0x + q1x) / 2, midY = (q0y + q1y) / 2;
            double innovE = Math.abs(fit[0] * midX + fit[1] * midY + fit[2]
                    - (lpE[0] * midX + lpE[1] * midY + lpE[2]));
            double ang = Math.abs(fit[0] * lpE[1] - fit[1] * lpE[0]);
            if (innovE > band || ang > ANG_GATE) {
                if (frameNo - 1 == debugSeq)
                    System.err.println(String.format("dbg seq %d edge %d: gate innov=%.1f ang=%.3f band=%.1f",
                            debugSeq, e, innovE, ang, band));
                continue;
            }
            // interior darkness: samples along the edge, offset inward
            double dInX = -fit[0], dInY = -fit[1];
            int nS = Math.max(3, (int) (segLen / 40));
            int dark = 0, tot = 0;
            double[] samp = new double[nS];
            for (int k = 0; k < nS; k++) {
                double tt = 0.15 + (0.85 - 0.15) * k / Math.max(nS - 1, 1);
                int xi = (int) Math.round(q0x + (q1x - q0x) * tt + dInX * INSIDE_OFF);
                int yi = (int) Math.round(q0y + (q1y - q0y) * tt + dInY * INSIDE_OFF);
                if (xi < 0 || xi >= w || yi < 0 || yi >= h) continue;
                samp[tot++] = g[yi * w + xi] & 0xff;
            }
            if (tot >= 3) {
                Arrays.sort(samp, 0, tot);
                double med = tot % 2 == 1 ? samp[tot / 2] : (samp[tot / 2 - 1] + samp[tot / 2]) / 2;
                if (med > lowThr - DARK_MARGIN) {
                    if (frameNo - 1 == debugSeq)
                        System.err.println(String.format("dbg seq %d edge %d: darkness med=%.0f thr=%d",
                                debugSeq, e, med, lowThr));
                    continue;
                }
            }
            if (frameNo - 1 == debugSeq)
                System.err.println(String.format("dbg seq %d edge %d: OK sigma=%.2f sup=%.2f",
                        debugSeq, e, fit[3], fit[4]));
            EdgeMeas m = meas[nm] == null ? (meas[nm] = new EdgeMeas()) : meas[nm];
            m.edge = e;
            m.line[0] = fit[0];
            m.line[1] = fit[1];
            m.line[2] = fit[2];
            m.sigma = fit[3];
            m.support = fit[4];
            m.paX = fit[5];
            m.paY = fit[6];
            m.pbX = fit[7];
            m.pbY = fit[8];
            // 仅当创新量可信时重置带宽计时（边界拟合不收窄带宽）
            if (innovE < Math.min(band / 2, 5.0)) edgeSeenS[e] = tNowS;
            nm++;
        }
        return nm;
    }

    /**
     * Per-bin outer zero-crossing of the bright stripe, TLS + 2-sigma trim.
     * Returns [nx, ny, c, sigma, support, paX, paY, pbX, pbY] or null.
     */
    private double[] fitLineBand(byte[] g, int w, int h, int lowThr,
                                 double q0x, double q0y, double q1x, double q1y,
                                 double band, double ccx, double ccy) {
        double dx = q1x - q0x, dy = q1y - q0y;
        double L = Math.hypot(dx, dy);
        if (L < 1) return null;
        dx /= L;
        dy /= L;
        double nvx = -dy, nvy = dx;
        double midX = (q0x + q1x) / 2, midY = (q0y + q1y) / 2;
        if (nvx * (midX - ccx) + nvy * (midY - ccy) < 0) {
            nvx = -nvx;
            nvy = -nvy;   // normal outward (high perp = outside the stripe)
        }
        int x0 = Math.max((int) (Math.min(q0x, q1x) - band - 2), 0);
        int x1 = Math.min((int) (Math.max(q0x, q1x) + band + 2), w);
        int y0 = Math.max((int) (Math.min(q0y, q1y) - band - 2), 0);
        int y1 = Math.min((int) (Math.max(q0y, q1y) + band + 2), h);
        int need = w * h;
        if (fPerp == null || fPerp.length < need) {
            fPerp = new float[need];
            fLon = new float[need];
            fVal = new float[need];
            fBin = new int[need];
            medBuf = new float[need];
        }
        int nsel = 0;
        int bandI = (int) band;
        for (int j = y0; j < y1; j++) {
            int row = j * w;
            for (int i = x0; i < x1; i++) {
                double perp = (i - q0x) * nvx + (j - q0y) * nvy;
                if (Math.abs(perp) > band) continue;
                double lon = (i - q0x) * dx + (j - q0y) * dy;
                if (lon < 0 || lon > L) continue;
                fPerp[nsel] = (float) perp;
                fLon[nsel] = (float) lon;
                fVal[nsel] = g[row + i] & 0xff;
                nsel++;
            }
        }
        if (nsel < MIN_EDGE_BINS * 2) {
            if (frameNo - 1 == debugSeq)
                System.err.println(String.format("dbg seq %d edge %d: nsel=%d too few",
                        debugSeq, debugEdge, nsel));
            return null;
        }
        int nBins = (int) (L / EDGE_BIN_W);
        if (nBins < MIN_EDGE_BINS) {
            if (frameNo - 1 == debugSeq)
                System.err.println(String.format("dbg seq %d edge %d: nBins=%d too few",
                        debugSeq, debugEdge, nBins));
            return null;
        }
        if (nBins > envLon.length) {
            envLon = new double[nBins];
            envPerp = new double[nBins];
            envBin = new int[nBins];
        }
        // bucket by longitudinal bin
        int[] binCount = new int[nBins + 1];
        for (int k = 0; k < nsel; k++) {
            int b = (int) (fLon[k] / EDGE_BIN_W);
            if (b >= nBins) b = nBins - 1;
            fBin[k] = b;
            binCount[b + 1]++;
        }
        for (int b = 0; b < nBins; b++) binCount[b + 1] += binCount[b];
        int[] order = new int[nsel];
        int[] cursor = Arrays.copyOf(binCount, nBins + 1);
        for (int k = 0; k < nsel; k++) order[cursor[fBin[k]]++] = k;

        int nEnv = 0;
        for (int b = 0; b < nBins; b++) {
            int s = binCount[b], en = binCount[b + 1];
            int m = en - s;
            if (m < 4) continue;
            // bright/dark medians
            int nb = 0, nd = 0;
            float sumB = 0, sumD = 0;
            // median via partial arrays (two passes: mean proxy is NOT ok; use sort)
            int cnt = 0;
            for (int k = s; k < en; k++) medBuf[cnt++] = fVal[order[k]];
            Arrays.sort(medBuf, 0, cnt);
            float bright, dark;
            {
                // median of >= lowThr and of < lowThr
                int firstHi = cnt;
                for (int k = 0; k < cnt; k++) {
                    if (medBuf[k] >= lowThr) {
                        firstHi = k;
                        break;
                    }
                }
                int nHi = cnt - firstHi;
                int nLo = firstHi;
                if (nHi == 0 || nLo == 0) continue;
                bright = nHi % 2 == 1 ? medBuf[firstHi + nHi / 2]
                        : (medBuf[firstHi + nHi / 2 - 1] + medBuf[firstHi + nHi / 2]) / 2f;
                dark = nLo % 2 == 1 ? medBuf[nLo / 2]
                        : (medBuf[nLo / 2 - 1] + medBuf[nLo / 2]) / 2f;
            }
            if (bright - dark < 30) continue;
            double midLvl = (bright + dark) / 2;
            // perp profile at integer grid
            int width = 2 * bandI + 1;
            Arrays.fill(profSum, 0, width, 0.0);
            Arrays.fill(profCnt, 0, width, 0);
            for (int k = s; k < en; k++) {
                int idx = order[k];
                int ip = Math.round(fPerp[idx]);
                if (ip < -bandI) ip = -bandI;
                if (ip > bandI) ip = bandI;
                profSum[ip + bandI] += fVal[idx];
                profCnt[ip + bandI]++;
            }
            // scan from outside (high perp) inward: dark -> bright mid-level crossing
            double cross = Double.NaN;
            for (int k = width - 1; k > 3; k--) {
                if (profCnt[k] == 0 || profCnt[k - 1] == 0) continue;
                double r0 = profSum[k] / profCnt[k];
                double r1 = profSum[k - 1] / profCnt[k - 1];
                if (r0 < midLvl && r1 >= midLvl) {
                    int okIn = 0, totIn = 0;
                    for (int u = k - 4; u <= k - 2; u++) {   // rows[k-4:k-1]，3 个内侧样本
                        if (profCnt[u] == 0) {
                            totIn = -99;
                            break;
                        }
                        totIn++;
                        if (profSum[u] / profCnt[u] >= midLvl) okIn++;
                    }
                    if (totIn < 0 || okIn < 2) continue;
                    double frac = (midLvl - r0) / (r1 - r0 + 1e-9);
                    cross = (k - 1 + frac) - bandI;
                    break;
                }
            }
            if (Double.isNaN(cross)) continue;
            envLon[nEnv] = (b + 0.5) * EDGE_BIN_W;
            envPerp[nEnv] = cross;
            envBin[nEnv] = b;
            nEnv++;
        }
        double support = (double) nEnv / nBins;
        if (nEnv < MIN_EDGE_BINS || support < MIN_SUPPORT) {
            if (frameNo - 1 == debugSeq)
                System.err.println(String.format("dbg seq %d edge %d: support=%.2f nEnv=%d/%d",
                        debugSeq, debugEdge, support, nEnv, nBins));
            return null;
        }

        // TLS (PCA) in (lon, perp) with 2-sigma trimming
        int m = nEnv;
        double sigma = Double.POSITIVE_INFINITY;
        double nlX = 0, nlY = 0, ctrLon = 0, ctrPerp = 0;
        for (int round = 0; round <= TRIM_ROUNDS; round++) {
            ctrLon = 0;
            ctrPerp = 0;
            for (int i = 0; i < m; i++) {
                ctrLon += envLon[i];
                ctrPerp += envPerp[i];
            }
            ctrLon /= m;
            ctrPerp /= m;
            double sxx = 0, sxy = 0, syy = 0;
            for (int i = 0; i < m; i++) {
                double ddx = envLon[i] - ctrLon;
                double ddy = envPerp[i] - ctrPerp;
                sxx += ddx * ddx;
                sxy += ddx * ddy;
                syy += ddy * ddy;
            }
            double tr = (sxx + syy) / 2;
            double det2 = Math.sqrt(((sxx - syy) / 2) * ((sxx - syy) / 2) + sxy * sxy);
            double lmin = tr - det2;
            if (Math.abs(sxy) > 1e-12) {
                nlX = sxy;
                nlY = lmin - sxx;
            } else {
                if (sxx <= syy) {
                    nlX = 1;
                    nlY = 0;
                } else {
                    nlX = 0;
                    nlY = 1;
                }
            }
            double nl = Math.hypot(nlX, nlY);
            if (nl < 1e-12) return null;
            nlX /= nl;
            nlY /= nl;
            double rmean = 0;
            double[] res = new double[m];
            for (int i = 0; i < m; i++) {
                res[i] = (envLon[i] - ctrLon) * nlX + (envPerp[i] - ctrPerp) * nlY;
                rmean += res[i];
            }
            rmean /= m;
            double var = 0;
            for (int i = 0; i < m; i++) {
                double r = res[i] - rmean;
                var += r * r;
            }
            var /= m;
            sigma = Math.sqrt(var);
            if (sigma < 1e-9) break;
            int nin = 0;
            double lim = 2 * sigma;
            for (int i = 0; i < m; i++) {
                double r = Math.abs((envLon[i] - ctrLon) * nlX + (envPerp[i] - ctrPerp) * nlY - rmean);
                if (r <= lim) {
                    envLon[nin] = envLon[i];
                    envPerp[nin] = envPerp[i];
                    envBin[nin] = envBin[i];
                    nin++;
                }
            }
            if (nin == m) break;
            m = nin;
            if (m < MIN_EDGE_BINS) return null;
        }
        if (sigma > MAX_SIGMA) {
            if (frameNo - 1 == debugSeq)
                System.err.println(String.format("dbg seq %d edge %d: sigma=%.2f > max",
                        debugSeq, debugEdge, sigma));
            return null;
        }
        // line in (lon,perp) -> image line: point = q0 + d*lon + nv*perp
        double nx = nlY * nvx + nlX * dx;
        double ny = nlY * nvy + nlX * dy;
        double nl = Math.hypot(nx, ny);
        if (nl < 1e-12) return null;
        nx /= nl;
        ny /= nl;
        if (nx * nvx + ny * nvy < 0) {   // orient normal outward
            nx = -nx;
            ny = -ny;
        }
        double ctrX = q0x + dx * ctrLon + nvx * ctrPerp;
        double ctrY = q0y + dy * ctrLon + nvy * ctrPerp;
        double c = -(nx * ctrX + ny * ctrY);
        // support-span endpoints projected on the line
        double lon0 = (envBin[0] + 0.5) * EDGE_BIN_W;
        double lon1 = (envBin[m - 1] + 0.5) * EDGE_BIN_W;
        double pax = q0x + dx * lon0, pay = q0y + dy * lon0;
        double pbx = q0x + dx * lon1, pby = q0y + dy * lon1;
        double dd = nx * pax + ny * pay + c;
        pax -= dd * nx;
        pay -= dd * ny;
        dd = nx * pbx + ny * pby + c;
        pbx -= dd * nx;
        pby -= dd * ny;
        return new double[]{nx, ny, c, sigma, support, pax, pay, pbx, pby};
    }

    // ---------------------------------------------------------------- correction
    private void applyCorrection(EdgeMeas[] meas, int nm) {
        float g = nm == 4 ? GAIN_FULL : (nm == 1 ? GAIN_EDGE : GAIN_PARTIAL);
        if (nm == 4) {
            // corners = intersections of adjacent fitted lines
            double[][] lines = new double[4][];
            for (int i = 0; i < nm; i++) lines[meas[i].edge] = meas[i].line;
            double[][] corn = new double[4][2];
            boolean ok = true;
            for (int k = 0; k < 4; k++) {
                double[] a = lines[(k + 3) % 4], b = lines[k];
                double px = a[1] * b[2] - a[2] * b[1];
                double py = a[2] * b[0] - a[0] * b[2];
                double pw = a[0] * b[1] - a[1] * b[0];
                if (Math.abs(pw) < 1e-9) {
                    ok = false;
                    break;
                }
                corn[k][0] = px / pw;
                corn[k][1] = py / pw;
            }
            if (ok && geoValid(corn)) {
                double[] hm = hFromCorners(corn);
                if (hm != null) {
                    blendH(hm, g);
                    return;
                }
            }
            // fall through to similarity if degenerate
        }
        similarityCorrection(meas, nm, g);
    }

    private void blendH(double[] Ht, float g) {
        normH(Ht);
        double[] c0 = applyH(H, cx0, cy0);
        double[] c1 = applyH(Ht, cx0, cy0);
        double dist = Math.hypot(c1[0] - c0[0], c1[1] - c0[1]);
        innov = (float) dist;
        double gg = g;
        if (SLEW_CAP > 0 && dist > SLEW_CAP) gg = g * SLEW_CAP / dist;
        for (int i = 0; i < 9; i++) H[i] = (1 - gg) * H[i] + gg * Ht[i];
        normH(H);
    }

    private void similarityCorrection(EdgeMeas[] meas, int nm, float g) {
        double[] Hn = normHcopy(H);
        double[] Hi = inv3(Hn);
        if (Hi == null) return;
        double[][] sc = {{0, 0}, {NORM_W, 0}, {NORM_W, NORM_H}, {0, NORM_H}};
        double[][] pc = new double[4][2];
        for (int i = 0; i < 4; i++) {
            double[] p = applyH(Hi, sc[i][0], sc[i][1]);
            pc[i][0] = p[0];
            pc[i][1] = p[1];
        }
        double ccx = (pc[0][0] + pc[1][0] + pc[2][0] + pc[3][0]) / 4;
        double ccy = (pc[0][1] + pc[1][1] + pc[2][1] + pc[3][1]) / 4;
        double[][] lp = new double[4][3];
        for (int e = 0; e < 4; e++) {
            for (int r = 0; r < 3; r++) {
                lp[e][r] = Hn[0 * 3 + r] * EDGE_LINES[e][0]
                        + Hn[1 * 3 + r] * EDGE_LINES[e][1]
                        + Hn[2 * 3 + r] * EDGE_LINES[e][2];
            }
            double nl = Math.hypot(lp[e][0], lp[e][1]);
            if (nl < 1e-12) continue;
            for (int r = 0; r < 3; r++) lp[e][r] /= nl;
        }
        // translation: rows n_e^T t = o_e (outward normals), truncated 2x2 eig
        double ata00 = 0, ata01 = 0, ata11 = 0, atb0 = 0, atb1 = 0;
        double angSum = 0, angW = 0;
        double[] oE = new double[4];
        boolean[] hasE = new boolean[4];
        double[][] lpOut = new double[4][];
        for (int i = 0; i < nm; i++) {
            EdgeMeas m = meas[i];
            int e = m.edge;
            double[] l = lp[e];
            double nrm = Math.hypot(l[0], l[1]);
            if (nrm < 1e-9) continue;
            double nx = l[0] / nrm, ny = l[1] / nrm, lc = l[2] / nrm;
            double meX = (pc[e][0] + pc[(e + 1) % 4][0]) / 2;
            double meY = (pc[e][1] + pc[(e + 1) % 4][1]) / 2;
            if (nx * (meX - ccx) + ny * (meY - ccy) < 0) {
                nx = -nx;
                ny = -ny;
                lc = -lc;
            }
            double midX = (m.paX + m.pbX) / 2, midY = (m.paY + m.pbY) / 2;
            double o = nx * midX + ny * midY + lc;
            double le = Math.hypot(m.pbX - m.paX, m.pbY - m.paY);
            double w = m.support * Math.max(le, 1.0);
            oE[e] = o;
            hasE[e] = true;
            lpOut[e] = new double[]{nx, ny, lc};
            ata00 += w * nx * nx;
            ata01 += w * nx * ny;
            ata11 += w * ny * ny;
            atb0 += w * nx * o;
            atb1 += w * ny * o;
            double dth = Math.atan2(nx * m.line[1] - ny * m.line[0],
                    nx * m.line[0] + ny * m.line[1]);
            angSum += w * dth;
            angW += w;
        }
        if (angW <= 0) return;
        // truncated eigen decomposition of ata (2x2)
        double tr = (ata00 + ata11) / 2;
        double det = Math.sqrt(((ata00 - ata11) / 2) * ((ata00 - ata11) / 2) + ata01 * ata01);
        double evMax = tr + det, evMin = tr - det;
        double tX = 0, tY = 0;
        // eigenvectors: for (a - l)b form
        double[][] vv = new double[2][2];
        for (int k = 0; k < 2; k++) {
            double ev = k == 0 ? evMax : evMin;
            double vx, vy;
            if (Math.abs(ata01) > 1e-12) {
                vx = ata01;
                vy = ev - ata00;
            } else {
                vx = ata00 >= ata11 ? 1 : 0;
                vy = ata00 >= ata11 ? 0 : 1;
            }
            double vl = Math.hypot(vx, vy);
            if (vl < 1e-12) continue;
            vv[k][0] = vx / vl;
            vv[k][1] = vy / vl;
        }
        for (int k = 0; k < 2; k++) {
            double ev = k == 0 ? evMax : evMin;
            if (ev > 0.04 * evMax) {
                double dot = vv[k][0] * atb0 + vv[k][1] * atb1;
                tX += dot / ev * vv[k][0];
                tY += dot / ev * vv[k][1];
            }
        }
        double theta = angSum / angW;
        // scale from parallel pairs
        double s = 1.0;
        int sN = 0;
        double sSum = 0;
        for (int pr = 0; pr < 2; pr++) {
            int e0 = pr == 0 ? 0 : 3, e1 = pr == 0 ? 2 : 1;
            if (!hasE[e0] || !hasE[e1]) continue;
            double nAxX = lpOut[e0][0] - lpOut[e1][0];
            double nAxY = lpOut[e0][1] - lpOut[e1][1];
            double na = Math.hypot(nAxX, nAxY);
            if (na < 1e-6) continue;
            nAxX /= na;
            nAxY /= na;
            double dPred = Math.abs(nAxX * (pc[e0][0] - pc[e1][0]) + nAxY * (pc[e0][1] - pc[e1][1]));
            if (dPred > 20) {
                sSum += 1.0 + (oE[e0] + oE[e1]) / dPred;
                sN++;
            }
        }
        if (sN > 0) {
            s = sSum / sN;
            if (s < 0.9) s = 0.9;
            if (s > 1.1) s = 1.1;
        }
        if (frameNo - 1 == debugSeq)
            System.err.println(String.format("dbg seq %d: simcorr t=(%.3f,%.3f) theta=%.3fdeg s=%.4f g=%.2f",
                    debugSeq, tX, tY, Math.toDegrees(theta), s, g));
        // fractional apply + slew cap
        tX *= g;
        tY *= g;
        theta *= g;
        s = 1.0 + (s - 1.0) * g;
        if (Math.abs(theta) > Math.toRadians(3)) theta = Math.signum(theta) * Math.toRadians(3);
        double ct = Math.cos(theta), st = Math.sin(theta);
        // C(p) = s*R(th)*(p-c) + c + t
        double[] C = {s * ct, -s * st, cx0 - s * ct * cx0 + s * st * cy0 + tX,
                      s * st, s * ct, cy0 - s * st * cx0 - s * ct * cy0 + tY,
                      0, 0, 1};
        double[] Ci = inv3(C);
        if (Ci == null) return;
        double[] c0 = applyH(H, cx0, cy0);
        double[] H1 = mul(H, Ci);
        double[] c1 = applyH(H1, cx0, cy0);
        double dist = Math.hypot(c1[0] - c0[0], c1[1] - c0[1]);
        innov = (float) dist;
        if (SLEW_CAP > 0 && dist > SLEW_CAP) {
            double frac = SLEW_CAP / Math.max(dist, 1e-9);
            for (int i = 0; i < 9; i++) Ci[i] = (1 - frac) * (i == 0 || i == 4 || i == 8 ? 1 : 0) + frac * Ci[i];
            System.arraycopy(mul(H, Ci), 0, H, 0, 9);
            normH(H);
        } else {
            System.arraycopy(H1, 0, H, 0, 9);
            normH(H);
        }
    }

    // ---------------------------------------------------------------- acquisition
    /**
     * Connected-component candidate enumeration on the coarse grid.
     * Returns quads (TL,TR,BR,BL in full-res coords) of candidates passing
     * seed/area/quad checks, area-desc, up to ACQ_MAX_CAND.
     */
    private java.util.List<double[][]> acqCandidates(byte[] g, int w, int h, int thr, int lowThr) {
        java.util.List<double[][]> out = new java.util.ArrayList<>();
        // coarse 320x180 (uses grayA from thresholds())
        int step = Math.max(1, Math.max(w, h) / 320);
        int sw = w / step, sh = h / step;
        int n = sw * sh;
        if (labels == null || labels.length != n) {
            labels = new int[n];
            stack = new int[n];
        }
        Arrays.fill(labels, 0);
        int nextLabel = 0;
        int[] candArea = new int[ACQ_MAX_CAND + 1];
        int[] candLabel = new int[ACQ_MAX_CAND + 1];
        int nCand = 0;
        for (int k = 0; k < n; k++) {
            if (labels[k] != 0 || (grayA[k] & 0xff) < lowThr) continue;
            nextLabel++;
            int count = 0, hiCount = 0, sp = 0;
            stack[sp++] = k;
            labels[k] = nextLabel;
            while (sp > 0) {
                int ppxy = stack[--sp];
                count++;
                if ((grayA[ppxy] & 0xff) >= thr) hiCount++;
                int pi = ppxy % sw;
                if (pi > 0 && labels[ppxy - 1] == 0 && (grayA[ppxy - 1] & 0xff) >= lowThr) {
                    labels[ppxy - 1] = nextLabel;
                    stack[sp++] = ppxy - 1;
                }
                if (pi < sw - 1 && labels[ppxy + 1] == 0 && (grayA[ppxy + 1] & 0xff) >= lowThr) {
                    labels[ppxy + 1] = nextLabel;
                    stack[sp++] = ppxy + 1;
                }
                if (ppxy >= sw && labels[ppxy - sw] == 0 && (grayA[ppxy - sw] & 0xff) >= lowThr) {
                    labels[ppxy - sw] = nextLabel;
                    stack[sp++] = ppxy - sw;
                }
                if (ppxy < n - sw && labels[ppxy + sw] == 0 && (grayA[ppxy + sw] & 0xff) >= lowThr) {
                    labels[ppxy + sw] = nextLabel;
                    stack[sp++] = ppxy + sw;
                }
            }
            // candidate: seeds >= ACQ_MIN_SEEDS and area >= frac*n; keep top-ACQ_MAX_CAND by area
            if (hiCount >= ACQ_MIN_SEEDS && count >= (int) (ACQ_MIN_BLOB_FRAC * n)) {
                int ins = nCand < ACQ_MAX_CAND ? nCand++ : ACQ_MAX_CAND - 1;
                while (ins > 0 && candArea[ins - 1] < count) {
                    candArea[ins] = candArea[ins - 1];
                    candLabel[ins] = candLabel[ins - 1];
                    ins--;
                }
                candArea[ins] = count;
                candLabel[ins] = nextLabel;
            }
        }
        for (int ci = 0; ci < nCand; ci++) {
            int best = candLabel[ci];
            // extrema corners on the coarse grid
            boolean any = false;
            int minSi = 0, maxSi = 0, minDi = 0, maxDi = 0;
            float minS = 0, maxS = 0, minD = 0, maxD = 0;
            for (int k = 0; k < n; k++) {
                if (labels[k] != best) continue;
                int i = k % sw, j = k / sw;
                float ss = i + j, dd = i - j;
                if (!any) {
                    minS = maxS = ss;
                    minD = maxD = dd;
                    minSi = maxSi = minDi = maxDi = k;
                    any = true;
                } else {
                    if (ss < minS) { minS = ss; minSi = k; }
                    if (ss > maxS) { maxS = ss; maxSi = k; }
                    if (dd < minD) { minD = dd; minDi = k; }
                    if (dd > maxD) { maxD = dd; maxDi = k; }
                }
            }
            if (!any) continue;
            double[][] quad = new double[4][2];
            if (!refineExtrema(grayA, labels, best, sw, sh, minSi % sw, minSi / sw, quad[0])) continue;
            refineExtrema(grayA, labels, best, sw, sh, maxDi % sw, maxDi / sw, quad[1]);
            refineExtrema(grayA, labels, best, sw, sh, maxSi % sw, maxSi / sw, quad[2]);
            refineExtrema(grayA, labels, best, sw, sh, minDi % sw, minDi / sw, quad[3]);
            for (int i = 0; i < 4; i++) {
                quad[i][0] *= step;
                quad[i][1] *= step;
            }
            if (!quadValid(quad, w, h)) continue;
            out.add(quad);
        }
        return out;
    }

    /** Full acquisition: 4-edge fit + geometry + hollow check. Returns H or null. */
    private double[] acquire(byte[] g, int w, int h, int lowThr, java.util.List<double[][]> cands) {
        for (int ci = 0; ci < cands.size(); ci++) {
            double[][] quad = cands.get(ci);
            double ccx = (quad[0][0] + quad[1][0] + quad[2][0] + quad[3][0]) / 4;
            double ccy = (quad[0][1] + quad[1][1] + quad[2][1] + quad[3][1]) / 4;
            double[][] lines = new double[4][];
            boolean ok = true;
            for (int e = 0; e < 4; e++) {
                lines[e] = fitLineBand(g, w, h, lowThr,
                        quad[e][0], quad[e][1], quad[(e + 1) % 4][0], quad[(e + 1) % 4][1],
                        BAND, ccx, ccy);
                if (lines[e] == null) {
                    ok = false;
                    break;
                }
            }
            if (!ok) continue;
            double[][] corn = new double[4][2];
            for (int k = 0; k < 4; k++) {
                double[] a = lines[(k + 3) % 4], b = lines[k];
                double px = a[1] * b[2] - a[2] * b[1];
                double py = a[2] * b[0] - a[0] * b[2];
                double pw = a[0] * b[1] - a[1] * b[0];
                if (Math.abs(pw) < 1e-9) {
                    ok = false;
                    break;
                }
                corn[k][0] = px / pw;
                corn[k][1] = py / pw;
            }
            if (!ok || !geoValid(corn)) continue;
            if (!hollowCheck(g, w, h, corn, lowThr)) continue;
            double[] hm = hFromCorners(corn);
            if (hm == null) continue;
            acqCandidate = ci;
            return hm;
        }
        return null;
    }

    /**
     * Partial acquisition for a partially visible screen.
     * - GYRO (H exists): correct the CURRENT H with the candidate's fitted lines
     *   (the clipped coarse quad is never trusted to initialize an existing track);
     * - DEAD (no H): rebuild from corrected corners — corners with both adjacent
     *   edges fitted become their intersection (true), corners with one adjacent
     *   edge get projected onto that line (clipping only moves the corner
     *   perpendicular to the edge), others keep the coarse value; then a full-gain
     *   similarity correction;
     * - consistency gate: predicted lines within 4px / 3deg of the measured ones;
     * - hollow check rejects lamps / text screens.
     */
    private double[] acquirePartial(byte[] g, int w, int h, int lowThr,
                                    java.util.List<double[][]> cands) {
        double[] hSave = haveH ? H.clone() : null;
        for (int ci = 0; ci < cands.size(); ci++) {
            double[][] quad = cands.get(ci);
            double ccx = (quad[0][0] + quad[1][0] + quad[2][0] + quad[3][0]) / 4;
            double ccy = (quad[0][1] + quad[1][1] + quad[2][1] + quad[3][1]) / 4;
            EdgeMeas[] tmp = new EdgeMeas[4];
            int nf = 0;
            boolean[] hasE = new boolean[4];
            for (int e = 0; e < 4; e++) {
                double[] fit = fitLineBand(g, w, h, lowThr,
                        quad[e][0], quad[e][1], quad[(e + 1) % 4][0], quad[(e + 1) % 4][1],
                        BAND, ccx, ccy);
                if (fit == null) continue;
                tmp[nf] = new EdgeMeas();
                tmp[nf].edge = e;
                tmp[nf].line[0] = fit[0];
                tmp[nf].line[1] = fit[1];
                tmp[nf].line[2] = fit[2];
                tmp[nf].sigma = fit[3];
                tmp[nf].support = fit[4];
                tmp[nf].paX = fit[5];
                tmp[nf].paY = fit[6];
                tmp[nf].pbX = fit[7];
                tmp[nf].pbY = fit[8];
                hasE[e] = true;
                nf++;
            }
            if (nf < 2) continue;
            boolean adjacent = false;
            for (int e = 0; e < 4; e++) {
                if (hasE[e] && hasE[(e + 1) % 4]) {
                    adjacent = true;
                    break;
                }
            }
            boolean twoAxes = (hasE[0] || hasE[2]) && (hasE[1] || hasE[3]);
            if (!adjacent && !twoAxes) continue;
            EdgeMeas[] meas = java.util.Arrays.copyOf(tmp, nf);
            if (!hollowCheck(g, w, h, quad, lowThr)) continue;
            double[] H1;
            if (hSave != null) {
                System.arraycopy(hSave, 0, H, 0, 9);
                similarityCorrection(meas, nf, 0.7f);
                H1 = H.clone();
                System.arraycopy(hSave, 0, H, 0, 9);
            } else {
                double[][] corn = new double[4][2];
                for (int i = 0; i < 4; i++) {
                    corn[i][0] = quad[i][0];
                    corn[i][1] = quad[i][1];
                }
                for (int k = 0; k < 4; k++) {
                    int ePrev = (k + 3) % 4, eNext = k;
                    if (hasE[ePrev] && hasE[eNext]) {
                        double[] a = lineOf(meas, nf, ePrev), b = lineOf(meas, nf, eNext);
                        double px = a[1] * b[2] - a[2] * b[1];
                        double py = a[2] * b[0] - a[0] * b[2];
                        double pw = a[0] * b[1] - a[1] * b[0];
                        if (Math.abs(pw) > 1e-9) {
                            corn[k][0] = px / pw;
                            corn[k][1] = py / pw;
                        }
                    } else if (hasE[ePrev] || hasE[eNext]) {
                        double[] fe = lineOf(meas, nf, hasE[ePrev] ? ePrev : eNext);
                        double dd = fe[0] * corn[k][0] + fe[1] * corn[k][1] + fe[2];
                        corn[k][0] -= dd * fe[0];
                        corn[k][1] -= dd * fe[1];
                    }
                }
                double[] H0 = hFromCorners(corn);
                if (H0 == null) continue;
                System.arraycopy(H0, 0, H, 0, 9);
                similarityCorrection(meas, nf, 1.0f);
                H1 = H.clone();
                haveH = hSave != null;
            }
            if (H1 == null) continue;
            // consistency gate: predicted lines within 4px / 3deg of measured
            boolean ok = true;
            for (int i = 0; i < nf; i++) {
                EdgeMeas m = meas[i];
                double[] L = EDGE_LINES[m.edge];
                double lp0 = H1[0] * L[0] + H1[3] * L[1] + H1[6] * L[2];
                double lp1 = H1[1] * L[0] + H1[4] * L[1] + H1[7] * L[2];
                double lp2 = H1[2] * L[0] + H1[5] * L[1] + H1[8] * L[2];
                double nl = Math.hypot(lp0, lp1);
                if (nl < 1e-12) {
                    ok = false;
                    break;
                }
                lp0 /= nl;
                lp1 /= nl;
                lp2 /= nl;
                double midX = (m.paX + m.pbX) / 2, midY = (m.paY + m.pbY) / 2;
                double dist = Math.abs(lp0 * midX + lp1 * midY + lp2
                        - (m.line[0] * midX + m.line[1] * midY + m.line[2]));
                double ang = Math.abs(lp0 * m.line[1] - lp1 * m.line[0]);
                if (dist > 4.0 || ang > Math.sin(Math.toRadians(3))) {
                    ok = false;
                    break;
                }
            }
            if (!ok) continue;
            acqCandidate = ci;
            return H1;
        }
        return null;
    }

    private static double[] lineOf(EdgeMeas[] meas, int nf, int e) {
        for (int i = 0; i < nf; i++) {
            if (meas[i].edge == e) return meas[i].line;
        }
        return null;
    }

    private static boolean refineExtrema(byte[] grayA, int[] labels, int best, int sw, int sh,
                                         int cx, int cy, double[] out) {
        float sx = 0, sy = 0;
        int c = 0;
        int j0 = Math.max(0, cy - 2), j1 = Math.min(sh - 1, cy + 2);
        int i0 = Math.max(0, cx - 2), i1 = Math.min(sw - 1, cx + 2);
        for (int j = j0; j <= j1; j++) {
            int row = j * sw;
            for (int i = i0; i <= i1; i++) {
                if (labels[row + i] == best) {
                    sx += i;
                    sy += j;
                    c++;
                }
            }
        }
        if (c == 0) {
            out[0] = cx;
            out[1] = cy;
        } else {
            out[0] = sx / c;
            out[1] = sy / c;
        }
        return true;
    }

    private static boolean quadValid(double[][] q, int w, int h) {
        double area = 0;
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            area += q[i][0] * q[j][1] - q[j][0] * q[i][1];
        }
        if (Math.abs(area) / 2 < 0.02 * w * h) return false;
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            if (Math.hypot(q[j][0] - q[i][0], q[j][1] - q[i][1]) < 40) return false;
        }
        return true;
    }

    /** 15deg opposite-edge parallelism + aspect [1.1, 3.0] (same as guntrack._geo_valid). */
    private static boolean geoValid(double[][] c) {
        double angTop = Math.atan2(c[1][1] - c[0][1], c[1][0] - c[0][0]);
        double angBot = Math.atan2(c[2][1] - c[3][1], c[2][0] - c[3][0]);
        double angLft = Math.atan2(c[3][1] - c[0][1], c[3][0] - c[0][0]);
        double angRgt = Math.atan2(c[2][1] - c[1][1], c[2][0] - c[1][0]);
        double lim = Math.toRadians(15);
        if (Math.abs(angDiff(angTop, angBot)) > lim) return false;
        if (Math.abs(angDiff(angLft, angRgt)) > lim) return false;
        double lenTop = Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]);
        double lenBot = Math.hypot(c[2][0] - c[3][0], c[2][1] - c[3][1]);
        double lenLft = Math.hypot(c[3][0] - c[0][0], c[3][1] - c[0][1]);
        double lenRgt = Math.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1]);
        double wAvg = (lenTop + lenBot) / 2, hAvg = (lenLft + lenRgt) / 2;
        if (wAvg <= 0 || hAvg <= 0) return false;
        double aspect = Math.max(wAvg, hAvg) / Math.min(wAvg, hAvg);
        return aspect >= 1.1 && aspect <= 3.0;
    }

    private static double angDiff(double a, double b) {
        double d = (a - b) % Math.PI;
        if (d > Math.PI / 2) d -= Math.PI;
        else if (d < -Math.PI / 2) d += Math.PI;
        return d;
    }

    /** Hollow check: bright fraction inside the 0.82-shrunk quad must be <= ACQ_DARK_FRAC. */
    private static boolean hollowCheck(byte[] g, int w, int h, double[][] corn, int lowThr) {
        double ccx = 0, ccy = 0;
        for (int i = 0; i < 4; i++) {
            ccx += corn[i][0];
            ccy += corn[i][1];
        }
        ccx /= 4;
        ccy /= 4;
        double[][] in = new double[4][2];
        int minX = w, maxX = 0, minY = h, maxY = 0;
        for (int i = 0; i < 4; i++) {
            in[i][0] = ccx + (corn[i][0] - ccx) * 0.82;
            in[i][1] = ccy + (corn[i][1] - ccy) * 0.82;
            minX = Math.min(minX, (int) Math.floor(in[i][0]));
            maxX = Math.max(maxX, (int) Math.ceil(in[i][0]));
            minY = Math.min(minY, (int) Math.floor(in[i][1]));
            maxY = Math.max(maxY, (int) Math.ceil(in[i][1]));
        }
        minX = Math.max(minX, 0);
        maxX = Math.min(maxX, w - 1);
        minY = Math.max(minY, 0);
        maxY = Math.min(maxY, h - 1);
        int total = 0, bright = 0;
        for (int j = minY; j <= maxY; j++) {
            for (int i = minX; i <= maxX; i++) {
                if (!pointInConvexQuad(i, j, in)) continue;
                total++;
                if ((g[j * w + i] & 0xff) >= lowThr) bright++;
            }
        }
        if (total < 100) return false;
        return (double) bright / total <= ACQ_DARK_FRAC;
    }

    private static boolean pointInConvexQuad(double x, double y, double[][] q) {
        // consistent winding: all cross products same sign
        double sign = 0;
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            double cr = (q[j][0] - q[i][0]) * (y - q[i][1]) - (q[j][1] - q[i][1]) * (x - q[i][0]);
            if (cr != 0) {
                if (sign == 0) sign = Math.signum(cr);
                else if (sign != Math.signum(cr)) return false;
            }
        }
        return true;
    }

    // ---------------------------------------------------------------- small linalg
    private static void setK(double[] K2, double f, double cx, double cy) {
        K2[0] = f;
        K2[1] = 0;
        K2[2] = cx;
        K2[3] = 0;
        K2[4] = f;
        K2[5] = cy;
        K2[6] = 0;
        K2[7] = 0;
        K2[8] = 1;
    }

    private static double[] mul(double[] a, double[] b) {
        double[] o = new double[9];
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
        return o;
    }

    private static double[] inv3(double[] m) {
        double a = m[0], b = m[1], c = m[2];
        double d = m[3], e = m[4], f = m[5];
        double g = m[6], h = m[7], i = m[8];
        double A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
        double det = a * A + b * B + c * C;
        if (Math.abs(det) < 1e-12) return null;
        double[] o = new double[9];
        o[0] = A / det;
        o[1] = -(b * i - c * h) / det;
        o[2] = (b * f - c * e) / det;
        o[3] = B / det;
        o[4] = (a * i - c * g) / det;
        o[5] = -(a * f - c * d) / det;
        o[6] = C / det;
        o[7] = -(a * h - b * g) / det;
        o[8] = (a * e - b * d) / det;
        return o;
    }

    private static void inv3into(double[] m, double[] o) {
        double[] r = inv3(m);
        if (r != null) System.arraycopy(r, 0, o, 0, 9);
    }

    /** Normalize in place to H[8]=1 gauge. */
    private static void normH(double[] m) {
        double s = m[8];
        if (Math.abs(s) < 1e-12) return;
        for (int i = 0; i < 9; i++) m[i] /= s;
    }

    private static double[] normHcopy(double[] m) {
        double[] o = m.clone();
        normH(o);
        return o;
    }

    private static double[] applyH(double[] Hm, double x, double y) {
        double w = Hm[6] * x + Hm[7] * y + Hm[8];
        return new double[]{(Hm[0] * x + Hm[1] * y + Hm[2]) / w,
                (Hm[3] * x + Hm[4] * y + Hm[5]) / w};
    }

    /** DLT homography from 4 corner correspondences (Gauss-Jordan, h22=1 gauge). */
    private static double[] hFromCorners(double[][] corners) {
        double[] X = {0, NORM_W, NORM_W, 0};
        double[] Y = {0, 0, NORM_H, NORM_H};
        double[][] m = new double[8][9];
        for (int i = 0; i < 4; i++) {
            double x = corners[i][0], y = corners[i][1];
            m[2 * i] = new double[]{x, y, 1, 0, 0, 0, -x * X[i], -y * X[i], X[i]};
            m[2 * i + 1] = new double[]{0, 0, 0, x, y, 1, -x * Y[i], -y * Y[i], Y[i]};
        }
        for (int col = 0; col < 8; col++) {
            int piv = col;
            for (int r = col + 1; r < 8; r++) {
                if (Math.abs(m[r][col]) > Math.abs(m[piv][col])) piv = r;
            }
            if (Math.abs(m[piv][col]) < 1e-10) return null;
            double[] tmp = m[col];
            m[col] = m[piv];
            m[piv] = tmp;
            for (int r = 0; r < 8; r++) {
                if (r == col) continue;
                double f = m[r][col] / m[col][col];
                if (f == 0) continue;
                for (int c = col; c < 9; c++) m[r][c] -= f * m[col][c];
            }
        }
        double[] hg = new double[9];
        for (int i = 0; i < 8; i++) hg[i] = m[i][8] / m[i][i];
        hg[8] = 1.0;
        return hg;
    }

    /** Segment a-b clipped to the image rect inset by `inset` px; null if empty. */
    private static double[] clipSegment(double ax, double ay, double bx, double by,
                                        double inset, int w, int h) {
        double t0 = 0, t1 = 1;
        double dx = bx - ax, dy = by - ay;
        for (int axis = 0; axis < 2; axis++) {
            double pp = axis == 0 ? ax : ay;
            double dd = axis == 0 ? dx : dy;
            double lo = inset, hi = (axis == 0 ? w : h) - inset;
            if (Math.abs(dd) < 1e-12) {
                if (pp < lo || pp > hi) return null;
                continue;
            }
            double ta = (lo - pp) / dd, tb = (hi - pp) / dd;
            if (ta > tb) {
                double tt = ta;
                ta = tb;
                tb = tt;
            }
            t0 = Math.max(t0, ta);
            t1 = Math.min(t1, tb);
            if (t0 >= t1) return null;
        }
        return new double[]{ax + dx * t0, ay + dy * t0, ax + dx * t1, ay + dy * t1};
    }
}
