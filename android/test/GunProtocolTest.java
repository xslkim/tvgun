import com.tvgun.gun.GunProtocol;

public class GunProtocolTest {
    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
        System.out.println("PASS " + message);
    }

    public static void main(String[] args) {
        GunProtocol p = new GunProtocol();
        check(p.hello().startsWith("HELLO "), "explicit session identity");
        check(p.aim(100, 200, 4).equals("100.0,200.0,4,0"), "sequenced aim");
        check(p.shot(-10, 500).equals("SHOT -10.0,500.0,1"), "shot captures offscreen coordinates");
        check(p.lost().equals("LOST,2"), "LOST shares sequence counter");
        check(p.aim(110, 210, 1).equals("110.0,210.0,1,3"), "GYRO aim and sequence");
        check(GunProtocol.frame("FRAME 24,48")[1] == 48, "FRAME parser");
        check(GunProtocol.frame("FRAME 0,48") == null, "invalid white border rejected");
        check(GunProtocol.frame("FRAME 24,900") == null, "invalid dark band rejected");
        check(GunProtocol.frame("FRAME hello,48") == null, "noninteger frame rejected");
        check(!new GunProtocol().hello().equals(p.hello()), "new phone session has different token");
    }
}
