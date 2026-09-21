package com.tvgun.gun;

import java.util.Arrays;

/**
 * Screen-quadrilateral detector. Input is the 640x360 display-rotated grayscale
 * (processGray), or the raw NV21 Y plane (process, which stride-2 samples and
 * rotates first). Coarse localization is unchanged: 320x180 dual-threshold
 * hysteretic connected components (low-threshold linking + bright seeds),
 * largest blob, extrema + centroid refinement. Corner refinement is the
 * replay-validated line-fit upgrade: per edge, mask pixels within a +-6px band
 * of the coarse edge are binned along the edge (3px bins), each bin contributes
 * its outer-envelope point (95th perpendicular percentile), and a TLS (PCA
 * principal axis) line is fitted with 2 rounds of 2-sigma trimming. Corners are
 * homogeneous intersections of adjacent fitted lines (sub-pixel).
 *
 * An edge fails with fewer than 12 envelope bins, insufficient support
 * (support>=0.5, or span>=0.8 with support>=0.15), or residual sigma>2px; any
 * edge failure fails the frame (fail=6). When coarse localization fails, a
 * tracking fallback fits against the last locked quad (age<=30 frames,
 * |shift|<=15 det px, else fail=7). Geometry envelope relaxed to 15deg opposite
 * edges / aspect [1.1,3.0] (real trapezoid perspective measured up to ~13deg).
 * Corner smoothing alpha=0.5, 3-frame lock hysteresis as before.
 *
 * fail: 0=ok 1=blob too small 2=no extrema 3=quad invalid 4=homography failed
 *       5=geometry rejected 6=edge fit failed 7=tracking fallback out of limits
 */
public final class Detector {
    public static final float NORM_W = 1920f;
    public static final float NORM_H = 1080f;

    private static final int TARGET_W = 320;
    private static final float ALPHA = 0.5f;
    private static final float MIN_AREA_FRAC = 0.02f;   // quadrilateral area vs detection image
    private static final float MIN_BLOB_FRAC = 0.008f;  // largest blob pixel count vs detection image
    private static final float MIN_EDGE = 20f;
    private static final int MAX_MISSES = 3;
    // 双阈值滞后连通：低阈值掩模上做连通域，域内须含 >= MIN_SEED_HI 个高阈值"种子"像素。
    private static final float LOW_THR_RATIO = 0.75f;
    private static final int LOW_THR_MIN = 150;
    private static final int MIN_SEED_HI = 30;
    // 直线拟合角点参数（与 scripts/run_record_replay.py 一致；640x360 全分辨率坐标）
    private static final float EDGE_BAND = 6f;        // 粗边线两侧带宽
    private static final float EDGE_BIN_W = 3f;       // 纵向分箱宽度
    private static final int MIN_EDGE_BINS = 12;      // 边线拟合最少有效 bin 数
    private static final float MIN_SUPPORT = 0.5f;    // 有支撑 bin 占比下限
    private static final float MIN_SPAN = 0.8f;       // 首尾覆盖比例下限（span 规则）
    private static final float MIN_SPAN_SUPPORT = 0.15f; // span 规则下的支撑率下限
    private static final float MAX_EDGE_SIGMA = 2f;   // 外包络点残差 σ 上限（px）
    private static final int TRIM_ROUNDS = 2;         // 2σ 剔除轮数
    private static final float MAX_TRACK_SHIFT = 15f; // 跟踪回退最大位移（det px）
    private static final int MAX_TRACK_AGE = 30;      // 跟踪回退参考最大帧龄
    // 几何校验包络（放宽：真梯形透视汇聚实测最大 ~13deg）
    private static final float MAX_OPP_EDGE_ANG = 15f;  // degrees
    private static final float MIN_ASPECT = 1.1f;
    private static final float MAX_ASPECT = 3.0f;

    public int detW;
    public int detH;
    public int lastThr;
    public int lastLowThr;
    public int lastBestCount;
    public int lastFail;
    public boolean locked;
    /** Smoothed corners TL,TR,BR,BL in detection-image coordinates. */
    public final float[] corners = new float[8];
    /** Preview-center mapped into normalized 1920x1080 coordinates. */
    public final float[] cross = new float[2];
    public boolean crossValid;
    /** true when this frame's lock came from the tracking fallback. */
    public boolean tracked;

    private float[] smooth;
    private int missCount;
    private float[] trackRef;   // last locked smoothed quad (det coords), survives lock loss
    private int trackAge;
    private final double[] hg = new double[8];
    private byte[] grayA;       // coarse 320x180
    private byte[] gray640;     // stride-2 + rotated full gray (process() path)
    private int[] labels;
    private int[] stack;
    // fitEdges work buffers (sized w*h of the 640x360 input)
    private int[] fxs;
    private int[] fys;
    private float[] fperp;
    private float[] flon;
    private int[] fbin;
    private int[] forder;

    /**
     * NV21 entry point: stride-2 sample the Y plane and rotate into display
     * coordinates, then run the 640x360 pipeline.
     */
    public void process(byte[] y, int w, int h, int rotation) {
        int step = Math.max(1, w / 640);
        int sw = w / step;
        int sh = h / step;
        if (gray640 == null || gray640.length != sw * sh) {
            gray640 = new byte[sw * sh];
        }
        for (int j = 0; j < sh; j++) {
            int srow = j * step * w;
            int drow = j * sw;
            for (int i = 0; i < sw; i++) {
                gray640[drow + i] = y[srow + i * step];
            }
        }
        final byte[] g;
        final int gw, gh;
        switch (((rotation % 360) + 360) % 360) {
            case 90: // clockwise
                gw = sh;
                gh = sw;
                byte[] b90 = new byte[sw * sh];
                for (int j = 0; j < gh; j++) {
                    for (int i = 0; i < gw; i++) {
                        b90[j * gw + i] = gray640[(sh - 1 - i) * sw + j];
                    }
                }
                g = b90;
                break;
            case 180:
                gw = sw;
                gh = sh;
                byte[] b180 = new byte[sw * sh];
                for (int j = 0; j < gh; j++) {
                    for (int i = 0; i < gw; i++) {
                        b180[j * gw + i] = gray640[(sh - 1 - j) * sw + (sw - 1 - i)];
                    }
                }
                g = b180;
                break;
            case 270: // clockwise (= 90 counter-clockwise)
                gw = sh;
                gh = sw;
                byte[] b270 = new byte[sw * sh];
                for (int j = 0; j < gh; j++) {
                    for (int i = 0; i < gw; i++) {
                        b270[j * gw + i] = gray640[i * sw + (sw - 1 - j)];
                    }
                }
                g = b270;
                break;
            default:
                gw = sw;
                gh = sh;
                g = gray640;
                break;
        }
        processGray(g, gw, gh);
    }

    /** 640x360-class display-coordinate grayscale entry point (recorded-frame replay uses this). */
    public void processGray(byte[] g, int w, int h) {
        // coarse stride targets ~320px on the long side, so it survives 90/270 rotation
        int step = Math.max(1, Math.max(w, h) / TARGET_W);
        int sw = w / step;
        int sh = h / step;
        if (grayA == null || grayA.length != sw * sh) {
            grayA = new byte[sw * sh];
        }
        for (int j = 0; j < sh; j++) {
            int srow = j * step * w;
            int drow = j * sw;
            for (int i = 0; i < sw; i++) {
                grayA[drow + i] = g[srow + i * step];
            }
        }
        detW = sw;
        detH = sh;
        int n = sw * sh;

        int[] hist = new int[256];
        for (int k = 0; k < n; k++) {
            hist[grayA[k] & 0xff]++;
        }
        int need = (int) (n * 0.02) + 1;
        int acc = 0;
        int thr = 255;
        for (int v = 255; v >= 0; v--) {
            acc += hist[v];
            if (acc >= need) {
                thr = v;
                break;
            }
        }
        if (thr < 190) thr = 190;
        else if (thr > 254) thr = 254;
        lastThr = thr;
        final int lowThr = Math.max(LOW_THR_MIN, (int) (thr * LOW_THR_RATIO));
        lastLowThr = lowThr;

        // Connected-component labeling (4-connectivity) on the LOW-threshold mask;
        // a component is kept only if it contains >= MIN_SEED_HI high-threshold seed
        // pixels. Among kept components, keep only the largest.
        if (labels == null || labels.length != n) {
            labels = new int[n];
            stack = new int[n];
        }
        Arrays.fill(labels, 0);
        int nextLabel = 0;
        int bestLabel = 0;
        int bestCount = 0;
        for (int k = 0; k < n; k++) {
            if (labels[k] != 0 || (grayA[k] & 0xff) < lowThr) continue;
            nextLabel++;
            int count = 0;
            int hiCount = 0;
            int sp = 0;
            stack[sp++] = k;
            labels[k] = nextLabel;
            while (sp > 0) {
                int p = stack[--sp];
                count++;
                if ((grayA[p] & 0xff) >= thr) hiCount++;
                int pi = p % sw;
                if (pi > 0 && labels[p - 1] == 0 && (grayA[p - 1] & 0xff) >= lowThr) {
                    labels[p - 1] = nextLabel;
                    stack[sp++] = p - 1;
                }
                if (pi < sw - 1 && labels[p + 1] == 0 && (grayA[p + 1] & 0xff) >= lowThr) {
                    labels[p + 1] = nextLabel;
                    stack[sp++] = p + 1;
                }
                if (p >= sw && labels[p - sw] == 0 && (grayA[p - sw] & 0xff) >= lowThr) {
                    labels[p - sw] = nextLabel;
                    stack[sp++] = p - sw;
                }
                if (p < n - sw && labels[p + sw] == 0 && (grayA[p + sw] & 0xff) >= lowThr) {
                    labels[p + sw] = nextLabel;
                    stack[sp++] = p + sw;
                }
            }
            if (hiCount >= MIN_SEED_HI && count > bestCount) {
                bestCount = count;
                bestLabel = nextLabel;
            }
        }
        lastBestCount = bestCount;

        // ---- coarse corners (extrema + centroid refine) ----
        float[] raw = null;
        int stage = 0;
        if (bestCount < (int) (MIN_BLOB_FRAC * n)) {
            stage = 1;
        } else {
            boolean any = false;
            float minS = 0, maxS = 0, minD = 0, maxD = 0;
            int minSi = 0, maxSi = 0, minDi = 0, maxDi = 0;
            for (int k = 0; k < n; k++) {
                if (labels[k] != bestLabel) continue;
                int i = k % sw;
                int j = k / sw;
                float s = i + j;
                float d = i - j;
                if (!any) {
                    minS = maxS = s;
                    minD = maxD = d;
                    minSi = maxSi = minDi = maxDi = k;
                    any = true;
                } else {
                    if (s < minS) { minS = s; minSi = k; }
                    if (s > maxS) { maxS = s; maxSi = k; }
                    if (d < minD) { minD = d; minDi = k; }
                    if (d > maxD) { maxD = d; maxDi = k; }
                }
            }
            if (!any) {
                stage = 2;
            } else {
                raw = new float[8];
                // TL = argmin(x+y), TR = argmax(x-y), BR = argmax(x+y), BL = argmin(x-y)
                refine(labels, bestLabel, sw, sh, minSi % sw, minSi / sw, raw, 0);
                refine(labels, bestLabel, sw, sh, maxDi % sw, maxDi / sw, raw, 2);
                refine(labels, bestLabel, sw, sh, maxSi % sw, maxSi / sw, raw, 4);
                refine(labels, bestLabel, sw, sh, minDi % sw, minDi / sw, raw, 6);
                if (!valid(raw, sw, sh)) {
                    stage = 3;
                    raw = null;
                }
            }
        }

        // ---- line-fit corner refinement on the full-resolution gray ----
        tracked = false;
        int fitStage = stage;
        if (stage == 0) {
            float[] fitted = fitEdges(g, w, h, raw, lowThr, step);
            if (fitted != null && geoValid(fitted)) {
                accept(fitted);
                return;
            }
            fitStage = fitted != null ? 5 : 6;
        }
        // Tracking fallback: fit against the last locked quad (covers fragmented
        // rings / degraded extrema / transient occlusion). Reference kept at most
        // 30 frames; fitted quad must stay within 15 det px of the reference.
        if (trackRef != null && trackAge <= MAX_TRACK_AGE) {
            float[] fitted2 = fitEdges(g, w, h, trackRef, lowThr, step);
            if (fitted2 != null && geoValid(fitted2) && maxShift(fitted2, trackRef) <= MAX_TRACK_SHIFT) {
                tracked = true;
                accept(fitted2);
                return;
            }
            miss(7);
            return;
        }
        miss(fitStage);
    }

    /**
     * Per-edge TLS line fit. ref: 8 floats TL,TR,BR,BL in detection coordinates;
     * cstep is the coarse downsampling stride (det -> full-res scale).
     * Returns fitted corners in detection coordinates, or null if any edge fails.
     */
    private float[] fitEdges(byte[] g, int w, int h, float[] ref, int lowThr, int cstep) {
        double[] c = new double[8];
        double ccx = 0, ccy = 0;
        for (int i = 0; i < 4; i++) {
            c[2 * i] = ref[2 * i] * (double) cstep;      // det -> full-res
            c[2 * i + 1] = ref[2 * i + 1] * (double) cstep;
            ccx += c[2 * i];
            ccy += c[2 * i + 1];
        }
        ccx /= 4;
        ccy /= 4;
        double[][] lines = new double[4][];
        for (int e = 0; e < 4; e++) {
            int e2 = (e + 1) % 4;
            double[] line = fitEdge(g, w, h, lowThr,
                    c[2 * e], c[2 * e + 1], c[2 * e2], c[2 * e2 + 1], ccx, ccy);
            if (line == null) return null;
            lines[e] = line;
        }
        // corner i = intersection of edge i-1 and edge i (order TL,TR,BR,BL)
        float[] out = new float[8];
        for (int i = 0; i < 4; i++) {
            double[] a = lines[(i + 3) % 4];
            double[] b = lines[i];
            double px = a[1] * b[2] - a[2] * b[1];
            double py = a[2] * b[0] - a[0] * b[2];
            double pw = a[0] * b[1] - a[1] * b[0];
            if (Math.abs(pw) < 1e-9) return null;
            out[2 * i] = (float) (px / pw / cstep);
            out[2 * i + 1] = (float) (py / pw / cstep);
        }
        return out;
    }

    /**
     * Fit one edge: mask pixels within +-EDGE_BAND of the coarse edge, binned
     * along the edge; per bin the outer-envelope point (95th perp percentile
     * pixel mean); TLS (PCA) fit + TRIM_ROUNDS of 2-sigma trimming.
     * Returns homogeneous line [nx, ny, c], or null on failure.
     */
    private double[] fitEdge(byte[] g, int w, int h, int lowThr,
                             double p0x, double p0y, double p1x, double p1y,
                             double ccx, double ccy) {
        double dx = p1x - p0x;
        double dy = p1y - p0y;
        double len = Math.hypot(dx, dy);
        if (len < 1) return null;
        dx /= len;
        dy /= len;
        double nvx = -dy;
        double nvy = dx;
        if (nvx * (p0x - ccx) + nvy * (p0y - ccy) < 0) {
            nvx = -nvx;
            nvy = -nvy; // normal points outwards from the quad
        }
        int x0 = Math.max((int) (Math.min(p0x, p1x) - EDGE_BAND - 2), 0);
        int x1 = Math.min((int) (Math.max(p0x, p1x) + EDGE_BAND + 2), w);
        int y0 = Math.max((int) (Math.min(p0y, p1y) - EDGE_BAND - 2), 0);
        int y1 = Math.min((int) (Math.max(p0y, p1y) + EDGE_BAND + 2), h);
        if (fxs == null || fxs.length < w * h) {
            fxs = new int[w * h];
            fys = new int[w * h];
            fperp = new float[w * h];
            flon = new float[w * h];
            fbin = new int[w * h];
            forder = new int[w * h];
        }
        int nsel = 0;
        for (int j = y0; j < y1; j++) {
            int row = j * w;
            for (int i = x0; i < x1; i++) {
                if ((g[row + i] & 0xff) < lowThr) continue;
                double perp = (i - p0x) * nvx + (j - p0y) * nvy;
                if (Math.abs(perp) > EDGE_BAND) continue;
                double lon = (i - p0x) * dx + (j - p0y) * dy;
                if (lon < 0 || lon > len) continue;
                fxs[nsel] = i;
                fys[nsel] = j;
                fperp[nsel] = (float) perp;
                flon[nsel] = (float) lon;
                nsel++;
            }
        }
        if (nsel == 0) return null;
        int nBins = (int) (len / EDGE_BIN_W);
        if (nBins < MIN_EDGE_BINS) return null;

        // bucket selected pixels by longitudinal bin
        int[] binCount = new int[nBins + 1];
        for (int k = 0; k < nsel; k++) {
            int b = (int) (flon[k] / EDGE_BIN_W);
            if (b >= nBins) b = nBins - 1;
            fbin[k] = b;
            binCount[b + 1]++;
        }
        for (int b = 0; b < nBins; b++) {
            binCount[b + 1] += binCount[b];
        }
        int[] cursor = Arrays.copyOf(binCount, nBins + 1);
        for (int k = 0; k < nsel; k++) {
            forder[cursor[fbin[k]]++] = k;
        }

        // per-bin outer-envelope point: mean of pixels with perp >= 95th percentile
        double[] envX = new double[nBins];
        double[] envY = new double[nBins];
        int nEnv = 0;
        int firstBin = -1;
        int lastBin = -1;
        float[] vals = new float[nsel];
        for (int b = 0; b < nBins; b++) {
            int s = binCount[b];
            int e = binCount[b + 1];
            int m = e - s;
            if (m == 0) continue;
            for (int k = 0; k < m; k++) {
                vals[k] = fperp[forder[s + k]];
            }
            Arrays.sort(vals, 0, m);
            double rank = 0.95 * (m - 1);
            int lo = (int) rank;
            double thr95 = lo + 1 < m
                    ? vals[lo] + (rank - lo) * (vals[lo + 1] - vals[lo])
                    : vals[lo];
            double mx = 0, my = 0;
            int cnt = 0;
            for (int k = s; k < e; k++) {
                int idx = forder[k];
                if (fperp[idx] >= thr95 - 1e-9) {
                    mx += fxs[idx];
                    my += fys[idx];
                    cnt++;
                }
            }
            envX[nEnv] = mx / cnt;
            envY[nEnv] = my / cnt;
            nEnv++;
            if (firstBin < 0) firstBin = b;
            lastBin = b;
        }
        double support = (double) nEnv / nBins;
        double span = nEnv > 0 ? (double) (lastBin - firstBin + 1) / nBins : 0;
        if (nEnv < MIN_EDGE_BINS
                || !(support >= MIN_SUPPORT || (span >= MIN_SPAN && support >= MIN_SPAN_SUPPORT))) {
            return null;
        }

        // TLS (PCA principal axis) with TRIM_ROUNDS of 2-sigma trimming
        double[] tx = Arrays.copyOf(envX, nEnv);
        double[] ty = Arrays.copyOf(envY, nEnv);
        double[] res = new double[nEnv];
        boolean[] keep = new boolean[nEnv];
        int m = nEnv;
        double sigma = Double.POSITIVE_INFINITY;
        double nx = 0, ny = 0, ctrX = 0, ctrY = 0;
        for (int round = 0; round <= TRIM_ROUNDS; round++) {
            ctrX = 0;
            ctrY = 0;
            for (int i = 0; i < m; i++) {
                ctrX += tx[i];
                ctrY += ty[i];
            }
            ctrX /= m;
            ctrY /= m;
            double sxx = 0, sxy = 0, syy = 0;
            for (int i = 0; i < m; i++) {
                double ddx = tx[i] - ctrX;
                double ddy = ty[i] - ctrY;
                sxx += ddx * ddx;
                sxy += ddx * ddy;
                syy += ddy * ddy;
            }
            // smallest-eigenvalue eigenvector of [[sxx,sxy],[sxy,syy]] = line normal
            double tr = (sxx + syy) / 2;
            double det2 = Math.sqrt(((sxx - syy) / 2) * ((sxx - syy) / 2) + sxy * sxy);
            double lmin = tr - det2;
            if (Math.abs(sxy) > 1e-12) {
                nx = sxy;
                ny = lmin - sxx;
            } else {
                if (sxx <= syy) {
                    nx = 1;
                    ny = 0;
                } else {
                    nx = 0;
                    ny = 1;
                }
            }
            double nl = Math.hypot(nx, ny);
            if (nl < 1e-12) return null;
            nx /= nl;
            ny /= nl;
            double rmean = 0;
            for (int i = 0; i < m; i++) {
                res[i] = (tx[i] - ctrX) * nx + (ty[i] - ctrY) * ny;
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
                keep[i] = Math.abs(res[i] - rmean) <= lim;
                if (keep[i]) nin++;
            }
            if (nin == m) break;
            int o = 0;
            for (int i = 0; i < m; i++) {
                if (keep[i]) {
                    tx[o] = tx[i];
                    ty[o] = ty[i];
                    o++;
                }
            }
            m = nin;
            if (m < MIN_EDGE_BINS) return null;
        }
        if (sigma > MAX_EDGE_SIGMA) return null;
        return new double[]{nx, ny, -(nx * ctrX + ny * ctrY)};
    }

    /** Smoothing + homography + lock. Shared by the coarse and tracking-fallback paths. */
    private void accept(float[] raw) {
        missCount = 0;
        lastFail = 0;
        if (smooth == null) {
            smooth = raw.clone();
        } else {
            for (int i = 0; i < 8; i++) {
                smooth[i] += ALPHA * (raw[i] - smooth[i]);
            }
        }
        System.arraycopy(smooth, 0, corners, 0, 8);
        trackRef = corners.clone();
        trackAge = 0;
        if (!computeHomography(corners)) {
            miss(4);
            return;
        }
        locked = true;
        map(detW / 2f, detH / 2f, cross);
        crossValid = cross[0] >= 0 && cross[0] <= NORM_W && cross[1] >= 0 && cross[1] <= NORM_H;
    }

    /**
     * Lock hysteresis: up to MAX_MISSES-1 consecutive failed frames keep the last
     * smoothed corners and stay locked; only a sustained failure drops the lock
     * and clears the smoothing state. trackRef survives for the tracking fallback.
     */
    private void miss(int stage) {
        lastFail = stage;
        missCount++;
        trackAge++;
        if (smooth == null || missCount >= MAX_MISSES) {
            locked = false;
            crossValid = false;
            smooth = null;
            missCount = 0;
        }
    }

    private static float maxShift(float[] a, float[] b) {
        float m = 0;
        for (int i = 0; i < 8; i++) {
            float d = Math.abs(a[i] - b[i]);
            if (d > m) m = d;
        }
        return m;
    }

    private static void refine(int[] labels, int bestLabel, int dw, int dh,
                               int cx, int cy, float[] out, int off) {
        float sx = 0, sy = 0;
        int c = 0;
        int j0 = Math.max(0, cy - 2), j1 = Math.min(dh - 1, cy + 2);
        int i0 = Math.max(0, cx - 2), i1 = Math.min(dw - 1, cx + 2);
        for (int j = j0; j <= j1; j++) {
            int row = j * dw;
            for (int i = i0; i <= i1; i++) {
                if (labels[row + i] == bestLabel) {
                    sx += i;
                    sy += j;
                    c++;
                }
            }
        }
        if (c == 0) {
            out[off] = cx;
            out[off + 1] = cy;
        } else {
            out[off] = sx / c;
            out[off + 1] = sy / c;
        }
    }

    private static boolean valid(float[] c, int dw, int dh) {
        float area = 0;
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            area += c[2 * i] * c[2 * j + 1] - c[2 * j] * c[2 * i + 1];
        }
        area = Math.abs(area) / 2f;
        if (area < MIN_AREA_FRAC * dw * dh) return false;
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            float dx = c[2 * j] - c[2 * i];
            float dy = c[2 * j + 1] - c[2 * i + 1];
            if (Math.sqrt(dx * dx + dy * dy) < MIN_EDGE) return false;
        }
        return true;
    }

    /**
     * Geometric sanity of the ordered quad (TL,TR,BR,BL): opposite edges must be
     * near-parallel (perspective allowance relaxed to 15deg) and the aspect ratio
     * must fit the widened 16:9 envelope [1.1, 3.0].
     */
    private static boolean geoValid(float[] c) {
        double angTop = Math.atan2(c[3] - c[1], c[2] - c[0]);
        double angBot = Math.atan2(c[5] - c[7], c[4] - c[6]);
        double angLft = Math.atan2(c[7] - c[1], c[6] - c[0]);
        double angRgt = Math.atan2(c[5] - c[3], c[4] - c[2]);
        double lim = Math.toRadians(MAX_OPP_EDGE_ANG);
        if (Math.abs(angDiff(angTop, angBot)) > lim) return false;
        if (Math.abs(angDiff(angLft, angRgt)) > lim) return false;
        double lenTop = Math.hypot(c[2] - c[0], c[3] - c[1]);
        double lenBot = Math.hypot(c[4] - c[6], c[5] - c[7]);
        double lenLft = Math.hypot(c[6] - c[0], c[7] - c[1]);
        double lenRgt = Math.hypot(c[4] - c[2], c[5] - c[3]);
        double wAvg = (lenTop + lenBot) / 2;
        double hAvg = (lenLft + lenRgt) / 2;
        if (wAvg <= 0 || hAvg <= 0) return false;
        double aspect = Math.max(wAvg, hAvg) / Math.min(wAvg, hAvg);
        return aspect >= MIN_ASPECT && aspect <= MAX_ASPECT;
    }

    private static double angDiff(double a, double b) {
        double d = (a - b) % Math.PI;
        if (d > Math.PI / 2) d -= Math.PI;
        else if (d < -Math.PI / 2) d += Math.PI;
        return d;
    }

    /** Solves for H mapping detection-image points to normalized coords (h33 = 1). */
    private boolean computeHomography(float[] p) {
        double[] X = {0, NORM_W, NORM_W, 0};
        double[] Y = {0, 0, NORM_H, NORM_H};
        double[][] m = new double[8][9];
        for (int i = 0; i < 4; i++) {
            double x = p[2 * i];
            double yy = p[2 * i + 1];
            m[2 * i]     = new double[]{x, yy, 1, 0, 0, 0, -x * X[i], -yy * X[i], X[i]};
            m[2 * i + 1] = new double[]{0, 0, 0, x, yy, 1, -x * Y[i], -yy * Y[i], Y[i]};
        }
        for (int col = 0; col < 8; col++) {
            int piv = col;
            for (int r = col + 1; r < 8; r++) {
                if (Math.abs(m[r][col]) > Math.abs(m[piv][col])) piv = r;
            }
            if (Math.abs(m[piv][col]) < 1e-10) return false;
            double[] tmp = m[col];
            m[col] = m[piv];
            m[piv] = tmp;
            for (int r = 0; r < 8; r++) {
                if (r == col) continue;
                double f = m[r][col] / m[col][col];
                if (f == 0) continue;
                for (int c = col; c < 9; c++) {
                    m[r][c] -= f * m[col][c];
                }
            }
        }
        for (int i = 0; i < 8; i++) {
            hg[i] = m[i][8] / m[i][i];
        }
        return true;
    }

    private void map(float x, float y, float[] out) {
        double den = hg[6] * x + hg[7] * y + 1.0;
        out[0] = (float) ((hg[0] * x + hg[1] * y + hg[2]) / den);
        out[1] = (float) ((hg[3] * x + hg[4] * y + hg[5]) / den);
    }
}
