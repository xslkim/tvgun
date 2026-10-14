import com.tvgun.gun.UdpEvents;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.nio.charset.StandardCharsets;

/**
 * Offline unit tests for UdpEvents (pure Java, no Android deps).
 * 本地起 UDP listener（DatagramSocket 绑定随机端口），断言：
 *   1. sendShot/sendReload/sendCoin/sendStart/sendExit 各发出一个包，
 *      内容恰为 "SHOT"/"RELOAD"/"COIN"/"START"/"EXIT"（UTF-8，无多余字节）；
 *   2. send 通用方法与便捷方法等价；
 *   3. 非法参数（空 host/空事件/非法端口）返回 false 而不抛异常、不发包；
 *   4. 不可解析主机名返回 false 而不抛异常。
 */
public class UdpEventsTest {

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    /** 收一个包并返回其文本内容（2s 超时）。 */
    static String receiveOne(DatagramSocket ds) throws Exception {
        byte[] buf = new byte[256];
        DatagramPacket p = new DatagramPacket(buf, buf.length);
        ds.receive(p);
        return new String(p.getData(), 0, p.getLength(), StandardCharsets.UTF_8);
    }

    static void exercise(DatagramSocket ds, String expected, boolean ok) throws Exception {
        check(ok, "send returns true for " + expected);
        String got = receiveOne(ds);
        check(expected.equals(got), "packet content is \"" + expected + "\" (got \"" + got + "\")");
    }

    public static void main(String[] args) throws Exception {
        DatagramSocket ds = new DatagramSocket(0);
        ds.setSoTimeout(2000);
        int port = ds.getLocalPort();
        String host = "127.0.0.1";

        // 1) 五个事件：内容逐字节相符
        exercise(ds, "SHOT", UdpEvents.sendShot(host, port));
        exercise(ds, "RELOAD", UdpEvents.sendReload(host, port));
        exercise(ds, "COIN", UdpEvents.sendCoin(host, port));
        exercise(ds, "START", UdpEvents.sendStart(host, port));
        exercise(ds, "EXIT", UdpEvents.sendExit(host, port));

        // 2) 通用 send 与便捷方法同格式
        exercise(ds, "SHOT", UdpEvents.send(host, port, UdpEvents.EVENT_SHOT));

        // 3) 非法参数 -> false，不抛，且端口上收不到包
        check(!UdpEvents.send("", port, "SHOT"), "empty host -> false");
        check(!UdpEvents.send(null, port, "SHOT"), "null host -> false");
        check(!UdpEvents.send(host, 0, "SHOT"), "port 0 -> false");
        check(!UdpEvents.send(host, 65536, "SHOT"), "port >65535 -> false");
        check(!UdpEvents.send(host, port, ""), "empty event -> false");
        check(!UdpEvents.send(host, port, null), "null event -> false");
        ds.setSoTimeout(300);
        try {
            receiveOne(ds);
            check(false, "no packet expected for rejected sends");
        } catch (java.net.SocketTimeoutException expected) {
            check(true, "no packet sent for rejected args");
        }

        // 4) 不可解析主机 -> false，不抛
        check(!UdpEvents.send("no.such.host.invalid", port, "SHOT"),
                "unresolvable host -> false (no throw)");

        ds.close();
        System.out.println("ALL UDPEVENTS TESTS PASSED");
    }
}
