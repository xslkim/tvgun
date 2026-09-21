import com.tvgun.gun.Detector;
import java.util.Arrays;

public class TestMain {
    static final int W = 1280, H = 720;

    static byte[] scene(boolean border, boolean distractor) {
        byte[] y = new byte[W * H];
        Arrays.fill(y, (byte) 10);
        if (border) {
            // white border ring (200,150)-(1080,570), thickness 6 (thin-border case)
            for (int j = 150; j <= 570; j++)
                for (int i = 200; i <= 1080; i++)
                    if (i < 206 || i > 1074 || j < 156 || j > 564) y[j * W + i] = (byte) 255;
            // bright duck blob inside (not part of the ring)
            int cx = 700, cy = 300, r = 30;
            for (int j = cy - r; j <= cy + r; j++)
                for (int i = cx - r; i <= cx + r; i++)
                    if ((i - cx) * (i - cx) + (j - cy) * (j - cy) <= r * r) y[j * W + i] = (byte) 200;
        }
        if (distractor) {
            // bright block top-left (like a neighboring screen), would win raw argmin(x+y)
            for (int j = 20; j < 70; j++)
                for (int i = 20; i < 90; i++) y[j * W + i] = (byte) 250;
        }
        return y;
    }

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    public static void main(String[] args) {
        byte[] img = scene(true, true);
        byte[] blank = scene(false, false);

        Detector d = new Detector();
        d.process(img, W, H, 0);
        System.out.println("locked=" + d.locked + " cross=" + d.cross[0] + "," + d.cross[1]
                + " valid=" + d.crossValid + " corners=" + Arrays.toString(d.corners));
        check(d.locked, "locked with distractor present");
        check(Math.abs(d.cross[0] - 960) < 25 && Math.abs(d.cross[1] - 540) < 25,
                "cross near (960,540)");
        check(d.corners[0] > 30 && d.corners[1] > 25, "TL from border ring, not distractor");

        d.process(blank, W, H, 0);
        check(d.locked, "still locked after 1 bad frame");
        d.process(blank, W, H, 0);
        check(d.locked, "still locked after 2 bad frames");
        d.process(blank, W, H, 0);
        check(!d.locked, "NO LOCK after 3 consecutive bad frames");
        check(!d.crossValid, "crossValid false when unlocked (aim reporting gate closed)");

        d.process(img, W, H, 0);
        check(d.locked, "re-lock after loss");
        check(Math.abs(d.cross[0] - 960) < 25 && Math.abs(d.cross[1] - 540) < 25,
                "cross sane after re-lock");

        Detector d2 = new Detector();
        d2.process(img, W, H, 180);
        check(d2.locked, "locked at rotation 180");
        check(Math.abs(d2.cross[0] - 960) < 25 && Math.abs(d2.cross[1] - 540) < 25,
                "cross near (960,540) at rotation 180");

        Detector d3 = new Detector();
        d3.process(img, W, H, 90);
        check(d3.locked, "locked at rotation 90");
        check(d3.detW == 180 && d3.detH == 320, "detW/detH swapped at rotation 90");

        // dual-threshold: ring with dim left side (incl. corner stubs) at 200,
        // bright rest at 255; hi percentile lands at 250 so the old single-threshold
        // labeling would fragment the ring and misplace TL. Low-threshold linking
        // must keep the ring whole and lock with correct corners.
        byte[] uneven = unevenRingScene();
        Detector d4 = new Detector();
        d4.process(uneven, W, H, 0);
        System.out.println("uneven: locked=" + d4.locked + " thr=" + d4.lastThr
                + " lowThr=" + d4.lastLowThr + " fail=" + d4.lastFail
                + " cross=" + d4.cross[0] + "," + d4.cross[1]);
        check(d4.lastThr >= 240 && d4.lastLowThr < 200,
                "dual threshold: hi>=240, low below dim segment (200)");
        check(d4.locked, "locked on uneven-brightness ring (dual threshold)");
        check(Math.abs(d4.cross[0] - 960) < 25 && Math.abs(d4.cross[1] - 540) < 25,
                "cross near (960,540) on uneven ring");
        check(Math.abs(d4.corners[0] - 50) < 2 && Math.abs(d4.corners[1] - 37.5f) < 2,
                "TL corner from dim segment recovered");

        // geometry rejection: filled trapezoid whose top edge slopes ~18.8deg vs
        // horizontal bottom edge (> relaxed 15deg limit) must be rejected with fail=5.
        byte[] trap = trapezoidScene();
        Detector d5 = new Detector();
        d5.process(trap, W, H, 0);
        System.out.println("trapezoid: locked=" + d5.locked + " fail=" + d5.lastFail);
        check(!d5.locked && d5.lastFail == 5,
                "skewed trapezoid rejected by geometry check (fail=5)");

        System.out.println("ALL TESTS PASSED");
    }

    /** Border ring (200,150)-(1080,570) t=6; left side + corner stubs dim (200),
     *  rest bright (255); distractor block 250 keeps the 98th percentile high. */
    static byte[] unevenRingScene() {
        byte[] y = new byte[W * H];
        Arrays.fill(y, (byte) 10);
        for (int j = 150; j <= 570; j++) {
            for (int i = 200; i <= 1080; i++) {
                boolean onRing = i < 206 || i > 1074 || j < 156 || j > 564;
                if (!onRing) continue;
                boolean dim = i < 400;  // left side + TL/BL corner stubs
                y[j * W + i] = (byte) (dim ? 200 : 255);
            }
        }
        // distractor: 250-bright block, keeps 98th percentile at 250
        for (int j = 600; j < 700; j++)
            for (int i = 20; i < 120; i++) y[j * W + i] = (byte) 250;
        return y;
    }

    /** Filled convex quad TL(200,150) TR(1080,450) BR(1080,570) BL(200,570):
     *  valid area/edges, but top edge slopes 18.8deg vs bottom edge (> 15deg). */
    static byte[] trapezoidScene() {
        byte[] y = new byte[W * H];
        Arrays.fill(y, (byte) 10);
        for (int j = 150; j <= 570; j++) {
            // above row 450 the right boundary lies on the slanted top edge
            int xR = j < 450 ? 200 + (j - 150) * 880 / 300 : 1080;
            for (int i = 200; i <= xR; i++) y[j * W + i] = (byte) 255;
        }
        return y;
    }
}
