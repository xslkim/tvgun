package com.tvgun.gun;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * 虚拟按键（投币/开始/换弹/退出）协议层：POST 空 JSON 到 PC 桥接端点，解析 {"ok":true}。
 * 纯 Java（无 Android 依赖），桌面 JVM 可直接单测（test/ControlButtonsTest.java）；
 * Android 层（MainActivity）只负责按钮、线程与提示。
 */
public final class ControlButtons {
    public static final String PATH_COIN = "/coin";
    public static final String PATH_START = "/start";
    public static final String PATH_RELOAD = "/reload";
    public static final String PATH_EXIT = "/exit";

    public static final int DEFAULT_TIMEOUT_MS = 3000;
    private static final String BODY = "{}";

    private ControlButtons() {
    }

    /** baseUrl 例 "http://192.168.1.10:8000"；去掉尾部斜杠后拼 path。 */
    public static String buildUrl(String baseUrl, String path) {
        String b = baseUrl;
        while (b.endsWith("/")) {
            b = b.substring(0, b.length() - 1);
        }
        return b + path;
    }

    /**
     * 解析响应 JSON 的 "ok" 字段（桥接端点统一回 {"ok":true}）。
     * 极简解析，避免依赖 org.json（桌面 JVM 单测没有 Android 运行时）。
     * 找不到字段返回 null（视为无法确认，按失败处理）。
     */
    public static Boolean parseOk(String json) {
        if (json == null) {
            return null;
        }
        int i = json.indexOf("\"ok\"");
        if (i < 0) {
            return null;
        }
        int c = json.indexOf(':', i + 4);
        if (c < 0) {
            return null;
        }
        int j = c + 1;
        while (j < json.length() && Character.isWhitespace(json.charAt(j))) {
            j++;
        }
        if (json.startsWith("true", j)) {
            return Boolean.TRUE;
        }
        if (json.startsWith("false", j)) {
            return Boolean.FALSE;
        }
        return null;
    }

    /**
     * POST {} 到 baseUrl+path，200 且 ok==true 返回 true；
     * 网络异常/超时/非 200/ok!=true 一律返回 false（不抛，由调用层提示）。
     */
    public static boolean send(String baseUrl, String path, int timeoutMs) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(buildUrl(baseUrl, path)).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json");
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(BODY.getBytes("UTF-8"));
            os.close();
            if (c.getResponseCode() != 200) {
                return false;
            }
            InputStream is = c.getInputStream();
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[1024];
            int r;
            while ((r = is.read(buf)) != -1) {
                bos.write(buf, 0, r);
            }
            is.close();
            return Boolean.TRUE.equals(parseOk(bos.toString("UTF-8")));
        } catch (Exception e) {
            return false;
        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    public static boolean sendCoin(String baseUrl) {
        return send(baseUrl, PATH_COIN, DEFAULT_TIMEOUT_MS);
    }

    public static boolean sendStart(String baseUrl) {
        return send(baseUrl, PATH_START, DEFAULT_TIMEOUT_MS);
    }

    public static boolean sendReload(String baseUrl) {
        return send(baseUrl, PATH_RELOAD, DEFAULT_TIMEOUT_MS);
    }

    public static boolean sendExit(String baseUrl) {
        return send(baseUrl, PATH_EXIT, DEFAULT_TIMEOUT_MS);
    }
}
