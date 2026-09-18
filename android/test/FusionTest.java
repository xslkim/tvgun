import com.tvgun.gun.Fusion;

/**
 * Offline unit tests for the gyro/camera fusion core (no Android deps).
 * Timestamps are synthetic monotonic nanoseconds.
 */
public class FusionTest {
    static final long NS = 1_000_000_000L;

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    static void feedGyro(Fusion f, long t0Ns, long t1Ns, int ticks, float wx, float wy) {
        long step = (t1Ns - t0Ns) / ticks;
        for (int i = 1; i <= ticks; i++) {
            f.onGyro(t0Ns + step * i, wx, wy, 0);
        }
    }

    public static void main(String[] args) {
        // 1) constant angular velocity extrapolation: S=1000 px/rad, lock at (960,540),
        //    wy=0.1 rad/s, wx=0.05 rad/s for 1s -> dx=+100, dy=+50 at rot=0
        Fusion f = new Fusion();
        f.setScale(1000f);
        f.setRotation(0);
        f.onCameraLock(NS, 960, 540);
        f.onGyro(NS, 0, 0, 0); // first tick only seeds the clock
        feedGyro(f, NS, 2 * NS, 10, 0.05f, 0.1f);
        Fusion.State s = f.snapshot(2 * NS);
        System.out.println("extrapolation: x=" + s.x + " y=" + s.y);
        check(s.valid && !s.predicted, "locked snapshot valid, not predicted");
        check(Math.abs(s.x - 1060f) < 0.5f, "dx = +wy*dt*S = +100 at rot=0");
        check(Math.abs(s.y - 590f) < 0.5f, "dy = +wx*dt*S = +50 at rot=0");

        // 2) complementary correction converges to the camera observation
        f = new Fusion();
        f.setScale(1000f);
        f.onCameraLock(NS, 800, 600);
        f.onGyro(NS, 0, 0, 0);
        feedGyro(f, NS, (long) (1.2 * NS), 2, 0f, 0.1f); // p.x -> 840
        long t = (long) (1.2 * NS);
        for (int i = 0; i < 30; i++) {
            t += 33_000_000L; // ~30fps camera corrections of the true position
            f.onCameraLock(t, 800, 600);
        }
        s = f.snapshot(t);
        System.out.println("convergence: x=" + s.x);
        check(Math.abs(s.x - 800f) < 0.5f, "repeated 0.7/0.3 corrections converge to observation");
        check(Math.abs(s.y - 600f) < 0.5f, "y stays on observation");

        // 3) lock loss: extrapolate <=1s (predicted), freeze >1s (invalid)
        f = new Fusion();
        f.setScale(1000f);
        f.onCameraLock(2 * NS, 960, 540);
        f.onGyro(2 * NS, 0, 0, 0);
        f.onCameraUnlock(2_050_000_000L);
        feedGyro(f, 2 * NS, (long) (3.5 * NS), 15, 0f, 0.1f); // 0.1s ticks up to t=3.5s
        s = f.snapshot(3 * NS);
        System.out.println("predict window: x=" + s.x + " valid=" + s.valid + " pred=" + s.predicted);
        check(Math.abs(s.x - 1060f) < 0.5f, "only ticks <=1s after last lock integrate (10 ticks = 100px)");
        check(s.valid && s.predicted, "predicted=true within 1s of lock loss");
        s = f.snapshot((long) (3.5 * NS));
        check(!s.valid && !s.predicted, "frozen >1s after lock loss: invalid, not predicted");
        s = f.snapshot((long) (2.9 * NS));
        check(Math.abs(s.x - 1060f) < 0.5f, "state frozen after window (no drift)");

        // 3b) re-lock corrects and clears predicted
        f.onCameraLock((long) (3.6 * NS), 960, 540);
        s = f.snapshot((long) (3.6 * NS));
        check(s.valid && !s.predicted, "re-lock clears predicted");
        check(Math.abs(s.x - 0.7f * 1060f - 0.3f * 960f) < 0.5f,
                "re-lock applies 0.7/0.3 correction from extrapolated state");

        // 4) sign mapping: rot=180 negates both axes
        f = new Fusion();
        f.setScale(1000f);
        f.setRotation(180);
        f.onCameraLock(NS, 960, 540);
        f.onGyro(NS, 0, 0, 0);
        feedGyro(f, NS, 2 * NS, 10, 0.05f, 0.1f);
        s = f.snapshot(2 * NS);
        System.out.println("rot180: x=" + s.x + " y=" + s.y);
        check(Math.abs(s.x - 860f) < 0.5f, "rot=180 negates dx");
        check(Math.abs(s.y - 490f) < 0.5f, "rot=180 negates dy");

        // 5) pre-first-lock: gyro advances clock only, no output; first lock initializes
        f = new Fusion();
        f.setScale(1000f);
        f.onGyro(NS, 0.05f, 0.1f, 0);
        feedGyro(f, NS, 2 * NS, 10, 0.05f, 0.1f);
        s = f.snapshot(2 * NS);
        check(!s.valid && !s.predicted, "no output before first lock");
        // gyro keeps ticking; tick at t=2.1s lands just before the first lock
        feedGyro(f, 2 * NS, 2_100_000_000L, 1, 0.05f, 0.1f);
        f.onCameraLock(2_100_000_000L, 700, 400);
        s = f.snapshot(2_100_000_000L);
        check(s.valid && !s.predicted && s.x == 700f && s.y == 400f,
                "first lock initializes p from p_camera");
        feedGyro(f, 2_100_000_000L, 2_200_000_000L, 1, 0f, 0.1f); // dt=0.1s
        s = f.snapshot(2_200_000_000L);
        check(Math.abs(s.x - 710f) < 0.5f, "gyro dt seamless across first lock (clock pre-accumulated)");

        // 6) clock gap (>MAX_DT) does not produce a jump
        f = new Fusion();
        f.setScale(1000f);
        f.onCameraLock(NS, 960, 540);
        f.onGyro(NS, 0, 0, 0);
        f.onGyro(NS + 500_000_000L, 0, 10f, 0); // 0.5s gap: skipped
        s = f.snapshot(NS + 500_000_000L);
        check(s.x == 960f, "gyro gap > MAX_DT is clamped (no jump)");
        f.onGyro(NS + 550_000_000L, 0, 10f, 0); // 0.05s: integrates
        s = f.snapshot(NS + 550_000_000L);
        check(Math.abs(s.x - 960f - 0.05f * 10f * 1000f) < 0.5f, "integration resumes after gap");

        System.out.println("ALL FUSION TESTS PASSED");
    }
}
