import com.tvgun.gun.Detector;
import com.tvgun.gun.Fusion;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Offline equivalence test: replays the on-device recording
 * (frames.bin 640x360 uint8 + frames_idx.csv + gyro.csv) through the ported
 * Java Detector (line-fit corners) and Fusion (corrected axis mapping), then
 * compares against the Python reference outputs:
 *   linefit_replay.csv  seq,locked,fail,tracked,thr,low_thr,cross_x,cross_y,cross_valid,...
 *   fusion_replay.csv   seq,tsNs,locked,cross_x,cross_y,fused_x,fused_y,valid,predicted,lock
 * Hard gates: lock agreement > 95%, median cross diff on co-locked frames < 2 norm px.
 *
 * Usage: java ReplayTest [recDir] [refDir]
 */
public class ReplayTest {
    static final int FW = 640, FH = 360, FSIZE = FW * FH;

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    static List<String[]> readCsv(String path) throws IOException {
        List<String[]> rows = new ArrayList<>();
        List<String> lines = Files.readAllLines(Paths.get(path));
        for (int i = 1; i < lines.size(); i++) { // skip header
            String ln = lines.get(i).trim();
            if (!ln.isEmpty()) rows.add(ln.split(","));
        }
        return rows;
    }

    static boolean bool(String s) {
        return s.equalsIgnoreCase("true") || s.equals("1");
    }

    static double median(double[] v, int n) {
        double[] c = Arrays.copyOf(v, n);
        Arrays.sort(c);
        return n % 2 == 1 ? c[n / 2] : (c[n / 2 - 1] + c[n / 2]) / 2;
    }

    public static void main(String[] args) throws Exception {
        String recDir = args.length > 0 ? args[0] : "D:/tvgun/out/record_20260919_104442";
        String refDir = args.length > 1 ? args[1] : "D:/tvgun/out/record_replay";

        double S = 1619.31;
        for (String line : Files.readAllLines(Paths.get(recDir, "meta.txt"))) {
            if (line.startsWith("S=")) S = Double.parseDouble(line.substring(2).trim());
        }

        List<String[]> idx = readCsv(recDir + "/frames_idx.csv");
        int n = idx.size();
        long[] fts = new long[n];
        for (int i = 0; i < n; i++) fts[i] = Long.parseLong(idx.get(i)[1]);

        byte[] all = Files.readAllBytes(Paths.get(recDir, "frames.bin"));
        check(all.length == n * FSIZE, "frames.bin size = frames*230400 (" + all.length + ")");

        List<String[]> gyroRows = readCsv(recDir + "/gyro.csv");
        int ng = gyroRows.size();
        long[] gts = new long[ng];
        float[] gwx = new float[ng], gwy = new float[ng], gwz = new float[ng];
        for (int i = 0; i < ng; i++) {
            String[] r = gyroRows.get(i);
            gts[i] = Long.parseLong(r[0]);
            gwx[i] = Float.parseFloat(r[1]);
            gwy[i] = Float.parseFloat(r[2]);
            gwz[i] = Float.parseFloat(r[3]);
        }

        List<String[]> refDet = readCsv(refDir + "/linefit_replay.csv");
        List<String[]> refFus = readCsv(refDir + "/fusion_replay.csv");
        check(refDet.size() == n && refFus.size() == n, "reference row counts match frames");

        Detector det = new Detector();
        Fusion fus = new Fusion();
        fus.setScale((float) S);
        fus.setRotation(0);

        boolean[] jLock = new boolean[n];
        double[] jCx = new double[n], jCy = new double[n];
        boolean[] jValid = new boolean[n], jPred = new boolean[n];
        double[] jFx = new double[n], jFy = new double[n];
        int gi = 0;
        long t0 = System.nanoTime();
        for (int s = 0; s < n; s++) {
            byte[] frame = Arrays.copyOfRange(all, s * FSIZE, (s + 1) * FSIZE);
            det.processGray(frame, FW, FH);
            // play gyro ticks up to this frame's timestamp (same order as Python replay)
            while (gi < ng && gts[gi] <= fts[s]) {
                fus.onGyro(gts[gi], gwx[gi], gwy[gi], gwz[gi]);
                gi++;
            }
            if (det.locked && det.crossValid) {
                fus.onCameraLock(fts[s], det.cross[0], det.cross[1]);
            } else {
                fus.onCameraUnlock(fts[s]);
            }
            Fusion.State st = fus.snapshot(fts[s]);
            jLock[s] = det.locked;
            jCx[s] = det.cross[0];
            jCy[s] = det.cross[1];
            jValid[s] = st.valid;
            jPred[s] = st.predicted;
            jFx[s] = st.x;
            jFy[s] = st.y;
        }
        long ms = (System.nanoTime() - t0) / 1_000_000;
        System.out.println(String.format("replayed %d frames in %d ms (%.1f ms/frame)", n, ms, (double) ms / n));

        // ---- detector equivalence vs linefit_replay.csv ----
        int agree = 0;
        int jLockN = 0, pLockN = 0;
        double[] diffs = new double[n];
        int nd = 0;
        for (int s = 0; s < n; s++) {
            boolean pLock = bool(refDet.get(s)[1]);
            if (pLock == jLock[s]) agree++;
            if (jLock[s]) jLockN++;
            if (pLock) pLockN++;
            if (pLock && jLock[s]) {
                double dx = jCx[s] - Double.parseDouble(refDet.get(s)[6]);
                double dy = jCy[s] - Double.parseDouble(refDet.get(s)[7]);
                diffs[nd++] = Math.hypot(dx, dy);
            }
        }
        double agreeRate = (double) agree / n;
        double med = median(diffs, nd);
        System.out.println(String.format(
                "[det] lock agree %.2f%% (%d/%d), java lock %d vs python %d, "
                        + "co-locked cross diff median %.3f norm px (n=%d)",
                agreeRate * 100, agree, n, jLockN, pLockN, med, nd));
        check(agreeRate > 0.95, "lock agreement > 95%");
        check(med < 2.0, "co-locked cross diff median < 2 norm px");

        // ---- fusion equivalence vs fusion_replay.csv ----
        int vAgree = 0;
        double[] fdiff = new double[n];
        int nf = 0;
        for (int s = 0; s < n; s++) {
            String[] r = refFus.get(s);
            boolean pValid = bool(r[7]);
            if (pValid == jValid[s]) vAgree++;
            double pfx = Double.parseDouble(r[5]); // NaN when uninitialized
            double pfy = Double.parseDouble(r[6]);
            if (pValid && jValid[s] && !Double.isNaN(pfx)) {
                fdiff[nf++] = Math.hypot(jFx[s] - pfx, jFy[s] - pfy);
            }
        }
        double fmed = nf > 0 ? median(fdiff, nf) : Double.NaN;
        System.out.println(String.format(
                "[fusion] valid agree %.2f%%, co-valid fused diff median %.3f norm px (n=%d)",
                100.0 * vAgree / n, fmed, nf));
        check(vAgree > 0.95 * n, "fusion valid agreement > 95%");
        check(nf > 0 && fmed < 2.0, "co-valid fused diff median < 2 norm px");

        System.out.println("ALL REPLAY EQUIVALENCE TESTS PASSED");
    }
}
