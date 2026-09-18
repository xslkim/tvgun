package com.tvgun.gun;

import java.util.Arrays;

/**
 * Per-frame screen-quadrilateral detector operating on the NV21 Y plane.
 * Downsamples to ~320px wide, rotates into display coordinates, thresholds at
 * the 98th luminance percentile (clamped to [190, 254]), keeps only the largest
 * 4-connected blob (the game border ring), finds its four extreme corners,
 * refines them by local centroid, smooths (alpha=0.3) with a 3-frame lock
 * hysteresis, then solves a 4-point homography into the 1920x1080 normalized
 * frame.
 */
public final class Detector {
    public static final float NORM_W = 1920f;
    public static final float NORM_H = 1080f;

    private static final int TARGET_W = 320;
    private static final float ALPHA = 0.3f;
    private static final float MIN_AREA_FRAC = 0.02f;   // quadrilateral area vs detection image
    private static final float MIN_BLOB_FRAC = 0.008f;  // largest blob pixel count vs detection image
    private static final float MIN_EDGE = 20f;
    private static final int MAX_MISSES = 3;
    // 双阈值滞后连通：低阈值掩模上做连通域，域内须含 >= MIN_SEED_HI 个高阈值"种子"像素。
    // 暗段边框（拍屏/侧视时亮度下降）仍与亮段连成完整环，无高亮种子的干扰块被排除。
    private static final float LOW_THR_RATIO = 0.75f;   // lowThr = hiThr * ratio
    private static final int LOW_THR_MIN = 150;         // 低阈值固定下限
    private static final int MIN_SEED_HI = 30;          // 连通域保留所需的高阈值像素数
    // 四边形几何校验：对边方向角差上限（透视允许小发散）与宽高比包络（16:9 屏幕）。
    private static final float MAX_OPP_EDGE_ANG = 10f;  // degrees
    private static final float MIN_ASPECT = 1.2f;       // max(w,h)/min(w,h) 下限
    private static final float MAX_ASPECT = 2.6f;       // 上限

    public int detW;
    public int detH;
    public int lastThr;
    public int lastLowThr;
    public int lastBestCount;
    /** 0=ok, 1=blob too small, 2=no extrema, 3=quad invalid, 4=homography failed,
     *  5=quad geometry rejected (opposite-edge angle / aspect out of envelope). */
    public int lastFail;
    public boolean locked;
    /** Smoothed corners TL,TR,BR,BL in detection-image coordinates. */
    public final float[] corners = new float[8];
    /** Preview-center mapped into normalized 1920x1080 coordinates. */
    public final float[] cross = new float[2];
    public boolean crossValid;

    private float[] smooth;
    private int missCount;
    private final double[] hg = new double[8];
    private byte[] grayA;
    private byte[] grayB;
    private int[] labels;
    private int[] stack;

    /**
     * @param rotation display orientation in degrees (0/90/180/270, same value passed to
     *                 Camera.setDisplayOrientation); the downsampled grayscale is rotated by
     *                 this amount so detection happens in display coordinates.
     */
    public void process(byte[] y, int w, int h, int rotation) {
        int step = Math.max(1, w / TARGET_W);
        int sw = w / step;
        int sh = h / step;
        if (grayA == null || grayA.length != sw * sh) {
            grayA = new byte[sw * sh];
            grayB = new byte[sw * sh];
        }
        for (int j = 0; j < sh; j++) {
            int srow = j * step * w;
            int drow = j * sw;
            for (int i = 0; i < sw; i++) {
                grayA[drow + i] = y[srow + i * step];
            }
        }

        final byte[] g;
        final int dw, dh;
        switch (((rotation % 360) + 360) % 360) {
            case 90: // clockwise
                dw = sh;
                dh = sw;
                for (int j = 0; j < dh; j++) {
                    for (int i = 0; i < dw; i++) {
                        grayB[j * dw + i] = grayA[(sh - 1 - i) * sw + j];
                    }
                }
                g = grayB;
                break;
            case 180:
                dw = sw;
                dh = sh;
                for (int j = 0; j < dh; j++) {
                    for (int i = 0; i < dw; i++) {
                        grayB[j * dw + i] = grayA[(sh - 1 - j) * sw + (sw - 1 - i)];
                    }
                }
                g = grayB;
                break;
            case 270: // clockwise (= 90 counter-clockwise)
                dw = sh;
                dh = sw;
                for (int j = 0; j < dh; j++) {
                    for (int i = 0; i < dw; i++) {
                        grayB[j * dw + i] = grayA[i * sw + (sw - 1 - j)];
                    }
                }
                g = grayB;
                break;
            default:
                dw = sw;
                dh = sh;
                g = grayA;
                break;
        }
        detW = dw;
        detH = dh;
        int n = dw * dh;

        int[] hist = new int[256];
        for (int k = 0; k < n; k++) {
            hist[g[k] & 0xff]++;
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
            if (labels[k] != 0 || (g[k] & 0xff) < lowThr) continue;
            nextLabel++;
            int count = 0;
            int hiCount = 0;
            int sp = 0;
            stack[sp++] = k;
            labels[k] = nextLabel;
            while (sp > 0) {
                int p = stack[--sp];
                count++;
                if ((g[p] & 0xff) >= thr) hiCount++;
                int pi = p % dw;
                if (pi > 0 && labels[p - 1] == 0 && (g[p - 1] & 0xff) >= lowThr) {
                    labels[p - 1] = nextLabel;
                    stack[sp++] = p - 1;
                }
                if (pi < dw - 1 && labels[p + 1] == 0 && (g[p + 1] & 0xff) >= lowThr) {
                    labels[p + 1] = nextLabel;
                    stack[sp++] = p + 1;
                }
                if (p >= dw && labels[p - dw] == 0 && (g[p - dw] & 0xff) >= lowThr) {
                    labels[p - dw] = nextLabel;
                    stack[sp++] = p - dw;
                }
                if (p < n - dw && labels[p + dw] == 0 && (g[p + dw] & 0xff) >= lowThr) {
                    labels[p + dw] = nextLabel;
                    stack[sp++] = p + dw;
                }
            }
            if (hiCount >= MIN_SEED_HI && count > bestCount) {
                bestCount = count;
                bestLabel = nextLabel;
            }
        }
        lastBestCount = bestCount;
        if (bestCount < (int) (MIN_BLOB_FRAC * n)) {
            miss(1);
            return;
        }

        boolean any = false;
        float minS = 0, maxS = 0, minD = 0, maxD = 0;
        int minSi = 0, maxSi = 0, minDi = 0, maxDi = 0;
        for (int k = 0; k < n; k++) {
            if (labels[k] != bestLabel) continue;
            int i = k % dw;
            int j = k / dw;
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
            miss(2);
            return;
        }

        float[] raw = new float[8];
        // TL = argmin(x+y), TR = argmax(x-y), BR = argmax(x+y), BL = argmin(x-y)
        refine(labels, bestLabel, dw, dh, minSi % dw, minSi / dw, raw, 0);
        refine(labels, bestLabel, dw, dh, maxDi % dw, maxDi / dw, raw, 2);
        refine(labels, bestLabel, dw, dh, maxSi % dw, maxSi / dw, raw, 4);
        refine(labels, bestLabel, dw, dh, minDi % dw, minDi / dw, raw, 6);

        if (!valid(raw, dw, dh)) {
            miss(3);
            return;
        }
        if (!geoValid(raw)) {
            miss(5);
            return;
        }

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
     * and clears the smoothing state.
     */
    private void miss(int stage) {
        lastFail = stage;
        missCount++;
        if (smooth == null || missCount >= MAX_MISSES) {
            locked = false;
            crossValid = false;
            smooth = null;
            missCount = 0;
        }
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
     * Geometric sanity of the ordered quad (TL,TR,BR,BL), checked on the raw
     * corners before smoothing/locking: opposite edges must be near-parallel
     * (perspective allows small divergence) and the aspect ratio must fit the
     * 16:9 screen envelope. Rejects quads locked onto border fragments.
     */
    private static boolean geoValid(float[] c) {
        // horizontal edges taken left-to-right, vertical edges top-to-bottom
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
