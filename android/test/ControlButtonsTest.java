import com.tvgun.gun.ControlButtons;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/**
 * Offline unit tests for ControlButtons (pure Java, no Android deps).
 * 手写迷你 HTTP 假服务器（ServerSocket），断言：
 *   1. sendCoin/sendStart/sendReload/sendExit 分别发出 POST /coin|/start|/reload|/exit，
 *      请求体为 {}，{"ok":true} 被解析为成功；
 *   2. 服务器回 500 时返回 false 而不抛异常；
 *   3. 服务器不应答（超时）时在限定时间内返回 false 而不抛异常；
 *   4. buildUrl/parseOk 纯函数边界。
 */
public class ControlButtonsTest {

    static void check(boolean ok, String msg) {
        System.out.println((ok ? "PASS " : "FAIL ") + msg);
        if (!ok) System.exit(1);
    }

    /** 捕获到的一条 HTTP 请求。 */
    static class Captured {
        String requestLine;
        String body;
    }

    /** 单请求假服务器：accept 一次，读请求，按给定状态行/响应体回复。 */
    static class FakeServer {
        final ServerSocket ss;
        final Captured captured = new Captured();
        final Thread thread;
        volatile String error;

        FakeServer(final int statusCode, final String respBody, final long hangMs) throws Exception {
            ss = new ServerSocket(0);
            thread = new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        Socket s = ss.accept();
                        s.setSoTimeout(5000);
                        InputStream in = s.getInputStream();
                        ByteArrayOutputStream head = new ByteArrayOutputStream();
                        int contentLength = 0;
                        // 读到空行（\r\n\r\n）为止
                        int prev3 = -1, prev2 = -1, prev1 = -1, cur;
                        while (true) {
                            cur = in.read();
                            if (cur == -1) throw new Exception("eof before headers end");
                            head.write(cur);
                            if (prev3 == '\r' && prev2 == '\n' && prev1 == '\r' && cur == '\n') break;
                            prev3 = prev2; prev2 = prev1; prev1 = cur;
                        }
                        String headers = new String(head.toByteArray(), StandardCharsets.ISO_8859_1);
                        captured.requestLine = headers.substring(0, headers.indexOf("\r\n"));
                        for (String line : headers.split("\r\n")) {
                            if (line.toLowerCase().startsWith("content-length:")) {
                                contentLength = Integer.parseInt(line.substring(15).trim());
                            }
                        }
                        byte[] body = new byte[contentLength];
                        int off = 0;
                        while (off < contentLength) {
                            int r = in.read(body, off, contentLength - off);
                            if (r == -1) throw new Exception("eof in body");
                            off += r;
                        }
                        captured.body = new String(body, StandardCharsets.UTF_8);
                        if (hangMs > 0) {
                            Thread.sleep(hangMs);  // 模拟服务器不响应，触发客户端超时
                        }
                        byte[] rb = respBody == null ? new byte[0]
                                : respBody.getBytes(StandardCharsets.UTF_8);
                        String resp = "HTTP/1.1 " + statusCode + " X\r\n"
                                + "Content-Type: application/json\r\n"
                                + "Content-Length: " + rb.length + "\r\n"
                                + "Connection: close\r\n\r\n";
                        OutputStream out = s.getOutputStream();
                        out.write(resp.getBytes(StandardCharsets.ISO_8859_1));
                        out.write(rb);
                        out.flush();
                        s.close();
                    } catch (Exception e) {
                        error = e.toString();
                    }
                }
            }, "fake-http");
            thread.start();
        }

        int port() {
            return ss.getLocalPort();
        }

        void join() throws Exception {
            thread.join(8000);
            ss.close();
        }
    }

    static String exercise(String path) throws Exception {
        FakeServer fs = new FakeServer(200, "{\"ok\":true}", 0);
        boolean ok = ControlButtons.send("http://127.0.0.1:" + fs.port(), path, 3000);
        fs.join();
        check(fs.error == null, "fake server no error for " + path + " (got " + fs.error + ")");
        check(ok, "send " + path + " returns true on {\"ok\":true}");
        check(fs.captured.requestLine != null
                        && fs.captured.requestLine.equals("POST " + path + " HTTP/1.1"),
                "request line is 'POST " + path + " HTTP/1.1' (got " + fs.captured.requestLine + ")");
        check("{}".equals(fs.captured.body), "body is {} (got " + fs.captured.body + ")");
        return fs.captured.requestLine;
    }

    public static void main(String[] args) throws Exception {
        // 1) 四个端点：路径、方法、body、ok 解析
        exercise(ControlButtons.PATH_COIN);
        exercise(ControlButtons.PATH_START);
        exercise(ControlButtons.PATH_RELOAD);
        exercise(ControlButtons.PATH_EXIT);

        // 便捷方法与 send 同路径（各走一遍真服务器）
        {
            FakeServer fs = new FakeServer(200, "{\"ok\":true}", 0);
            String base = "http://127.0.0.1:" + fs.port();
            check(ControlButtons.sendCoin(base), "sendCoin ok");
            fs.join();
            check(fs.captured.requestLine.startsWith("POST /coin "), "sendCoin hits /coin");
        }
        {
            FakeServer fs = new FakeServer(200, "{\"ok\":true}", 0);
            String base = "http://127.0.0.1:" + fs.port();
            check(ControlButtons.sendStart(base), "sendStart ok");
            fs.join();
            check(fs.captured.requestLine.startsWith("POST /start "), "sendStart hits /start");
        }
        {
            FakeServer fs = new FakeServer(200, "{\"ok\":true}", 0);
            String base = "http://127.0.0.1:" + fs.port();
            check(ControlButtons.sendReload(base), "sendReload ok");
            fs.join();
            check(fs.captured.requestLine.startsWith("POST /reload "), "sendReload hits /reload");
        }
        {
            FakeServer fs = new FakeServer(200, "{\"ok\":true}", 0);
            String base = "http://127.0.0.1:" + fs.port();
            check(ControlButtons.sendExit(base), "sendExit ok");
            fs.join();
            check(fs.captured.requestLine.startsWith("POST /exit "), "sendExit hits /exit");
        }

        // 2) 500 + {"ok":false} -> false，不抛
        {
            FakeServer fs = new FakeServer(500, "{\"ok\":false}", 0);
            boolean ok = ControlButtons.send("http://127.0.0.1:" + fs.port(),
                    ControlButtons.PATH_COIN, 3000);
            fs.join();
            check(!ok, "500 response -> false (no throw)");
        }

        // 3) 服务器挂着不应答 -> 超时返回 false，不抛，且不阻塞远超 timeout
        {
            FakeServer fs = new FakeServer(200, "{\"ok\":true}", 3000);
            long t0 = System.currentTimeMillis();
            boolean ok = ControlButtons.send("http://127.0.0.1:" + fs.port(),
                    ControlButtons.PATH_COIN, 400);
            long dt = System.currentTimeMillis() - t0;
            fs.join();
            check(!ok, "hang server -> false (no throw)");
            check(dt < 3000, "timeout honored (dt=" + dt + "ms)");
        }

        // 4) 纯函数边界
        check(ControlButtons.buildUrl("http://a:8000/", "/coin").equals("http://a:8000/coin"),
                "buildUrl strips trailing slash");
        check(ControlButtons.buildUrl("http://a:8000", "/exit").equals("http://a:8000/exit"),
                "buildUrl plain join");
        check(Boolean.TRUE.equals(ControlButtons.parseOk("{\"ok\":true}")), "parseOk true");
        check(Boolean.TRUE.equals(ControlButtons.parseOk(" { \"ok\" : true } ")),
                "parseOk whitespace tolerant");
        check(Boolean.FALSE.equals(ControlButtons.parseOk("{\"ok\":false}")), "parseOk false");
        check(ControlButtons.parseOk("{\"hit\":true}") == null, "parseOk missing field -> null");
        check(ControlButtons.parseOk(null) == null, "parseOk null -> null");

        // 5) 连不上（端口无监听）-> false，不抛
        {
            ServerSocket tmp = new ServerSocket(0);
            int deadPort = tmp.getLocalPort();
            tmp.close();
            check(!ControlButtons.send("http://127.0.0.1:" + deadPort,
                    ControlButtons.PATH_START, 1000), "connection refused -> false (no throw)");
        }

        System.out.println("ALL CONTROLBUTTONS TESTS PASSED");
    }
}
