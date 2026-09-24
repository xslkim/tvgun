import com.tvgun.gun.Tracker;

import java.util.Arrays;

/**
 * Offline unit tests for Tracker (pure Java, no Android deps).
 * Synthetic 640x360 scenes (the processGray input format):
 *   1. border ring + distractor block -> acquire FULL, cross near (960,540)
 *   2. gyro propagation: locked scene, then blank + constant wx -> cross moves -x,
 *      grade GYRO (vision lost, within 3s window)
 *   3. blank frames beyond 3s -> DEAD
 *   4. uneven-brightness ring (dim left side) -> acquire
 *   5. skewed trapezoid (top edge 18.8deg) -> rejected (DEAD)
 *   6. filled bright lamp blob -> hollow check rejects (DEAD)
 *   7. text-like filled pattern (bright interior) -> rejected (DEAD)
 */
public class TrackerTest {
    static final int W = 640, H = 360;

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    /** Black scene with white border ring (100,75)-(540,285) thickness 3 + optional extras. */
    static byte[] ringScene(int bright, int dimLeft) {
        byte[] g = new byte[W * H];
        Arrays.fill(g, (byte) 10);
        for (int j = 75; j <= 285; j++) {
            for (int i = 100; i <= 540; i++) {
                boolean onRing = i < 103 || i > 537 || j < 78 || j > 282;
                if (!onRing) continue;
                int v = bright;
                if (dimLeft > 0 && i < 220) v = dimLeft;
                g[j * W + i] = (byte) v;
            }
        }
        return g;
    }

    static byte[] blank() {
        byte[] g = new byte[W * H];
        Arrays.fill(g, (byte) 10);
        return g;
    }

    static byte[] lampScene() {
        byte[] g = blank();
        // filled bright blob (lamp-like): 80x60 at (260,150)
        for (int j = 150; j < 210; j++)
            for (int i = 260; i < 340; i++) g[j * W + i] = (byte) 250;
        return g;
    }

    static byte[] textScene() {
        byte[] g = blank();
        // text-monitor-like: NO ring, only horizontal bright text lines
        java.util.Random r = new java.util.Random(7);
        for (int j = 90; j < 270; j += 6) {
            int x = 130 + r.nextInt(40);
            int len = 100 + r.nextInt(300);
            for (int i = x; i < Math.min(x + len, 520); i++) g[j * W + i] = (byte) 240;
        }
        return g;
    }

    static byte[] trapezoidScene() {
        byte[] g = new byte[W * H];
        Arrays.fill(g, (byte) 10);
        for (int j = 75; j <= 285; j++) {
            int xR = j < 225 ? 100 + (j - 75) * 440 / 150 : 540;
            for (int i = 100; i <= xR; i++) g[j * W + i] = (byte) 255;
        }
        return g;
    }

    public static void main(String[] args) {
        long t0 = 1_000_000_000L;

        // 1) ring + distractor
        {
            byte[] g = ringScene(255, 0);
            // distractor block (bright, bottom-left)
            for (int j = 300; j < 335; j++)
                for (int i = 10; i < 55; i++) g[j * W + i] = (byte) 250;
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(g, W, H, t0);
            System.out.println("ring: grade=" + tr.grade + " cross=" + tr.cross[0] + "," + tr.cross[1]);
            check(tr.grade == Tracker.GRADE_FULL, "ring: FULL acquire");
            check(Math.abs(tr.cross[0] - 960) < 30 && Math.abs(tr.cross[1] - 540) < 30,
                    "ring: cross near (960,540)");
        }

        // 2) gyro propagation: lock, then blank + constant wx ticks -> GYRO, cross moves -x
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(ringScene(255, 0), W, H, t0);
            check(tr.grade == Tracker.GRADE_FULL, "prop: initial FULL");
            float cx0 = tr.cross[0];
            float cy0 = tr.cross[1];
            // 1s of gyro at wy=-0.1 rad/s (maps to cross +x direction at rot=0: dy=+wy? no:
            // device->camera M: cam_x=+wy -> image x grows -> cross moves +x in norm)
            long t = t0;
            for (int k = 0; k < 200; k++) {
                t += 5_000_000L; // 200Hz
                tr.onGyro(t, 0f, -0.1f, 0f);
            }
            // camera frames during that second: blank (no vision)
            for (int k = 0; k < 30; k++) {
                t0 += 33_333_333L;
                tr.processGray(blank(), W, H, t0 + 5_000_000L * k);
            }
            System.out.println("prop: grade=" + tr.grade + " cross=" + tr.cross[0] + "," + tr.cross[1]
                    + " (from " + cx0 + "," + cy0 + ")");
            check(tr.grade == Tracker.GRADE_GYRO, "prop: GYRO within 3s window");
            float dy = tr.cross[1] - cy0;
            check(dy < -20, "prop: constant -wy moves cross up (-y) (got dy=" + dy + ")");
            check(Math.abs(tr.cross[0] - cx0) < 20, "prop: x stable");
        }

        // 3) blank beyond 3s -> DEAD
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(ringScene(255, 0), W, H, t0);
            long t = t0;
            for (int k = 0; k < 120; k++) {  // 4s of blank frames
                t += 33_333_333L;
                tr.processGray(blank(), W, H, t);
            }
            check(tr.grade == Tracker.GRADE_DEAD, "blank 4s -> DEAD");
            check(!tr.aimValid(), "DEAD -> aim invalid");
            // re-acquire after DEAD
            tr.processGray(ringScene(255, 0), W, H, t + 33_333_333L);
            check(tr.grade == Tracker.GRADE_FULL, "re-acquire after DEAD");
        }

        // 4) uneven ring (dim left side at 200, rest 255)
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(ringScene(255, 200), W, H, t0);
            System.out.println("uneven: grade=" + tr.grade + " cross=" + tr.cross[0] + "," + tr.cross[1]);
            check(tr.grade == Tracker.GRADE_FULL, "uneven ring: FULL acquire");
            check(Math.abs(tr.cross[0] - 960) < 30, "uneven: cross x near 960");
        }

        // 5) trapezoid -> rejected
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(trapezoidScene(), W, H, t0);
            check(tr.grade == Tracker.GRADE_DEAD, "trapezoid rejected (DEAD)");
        }

        // 6) lamp blob -> rejected (filled interior)
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(lampScene(), W, H, t0);
            check(tr.grade == Tracker.GRADE_DEAD, "lamp blob rejected (DEAD)");
        }

        // 7) text scene (text lines only, no ring) -> rejected
        {
            Tracker tr = new Tracker();
            tr.setFov(67.94);
            tr.processGray(textScene(), W, H, t0);
            System.out.println("text: grade=" + tr.grade);
            check(tr.grade == Tracker.GRADE_DEAD, "text scene rejected (DEAD)");
        }

        System.out.println("ALL TRACKER TESTS PASSED");
    }
}
