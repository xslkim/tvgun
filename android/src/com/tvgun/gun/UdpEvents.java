package com.tvgun.gun;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

/**
 * UDP 事件模式协议层：事件（射击/换弹/投币/开始/退出）以 ASCII 文本包发到
 * PC 游戏的单个 UDP 端口（Godot 端默认 9000，与坐标流 "x,y" 同端口）。
 * 无连接、不应答，发送失败（如地址解析失败）返回 false 由调用层提示。
 * 纯 Java（无 Android 依赖），桌面 JVM 可直接单测（test/UdpEventsTest.java）。
 */
public final class UdpEvents {
    public static final String EVENT_SHOT = "SHOT";
    public static final String EVENT_RELOAD = "RELOAD";
    public static final String EVENT_COIN = "COIN";
    public static final String EVENT_START = "START";
    public static final String EVENT_EXIT = "EXIT";

    public static final int DEFAULT_PORT = 9000;

    private UdpEvents() {
    }

    /** 发一个 UDP 文本事件包到 host:port；地址/参数非法或发送异常返回 false（不抛）。 */
    public static boolean send(String host, int port, String event) {
        if (host == null || host.isEmpty() || port <= 0 || port > 65535
                || event == null || event.isEmpty()) {
            return false;
        }
        try {
            byte[] buf = event.getBytes("UTF-8");
            DatagramSocket ds = new DatagramSocket();
            try {
                ds.send(new DatagramPacket(buf, buf.length,
                        InetAddress.getByName(host), port));
            } finally {
                ds.close();
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public static boolean sendShot(String host, int port) {
        return send(host, port, EVENT_SHOT);
    }

    public static boolean sendReload(String host, int port) {
        return send(host, port, EVENT_RELOAD);
    }

    public static boolean sendCoin(String host, int port) {
        return send(host, port, EVENT_COIN);
    }

    public static boolean sendStart(String host, int port) {
        return send(host, port, EVENT_START);
    }

    public static boolean sendExit(String host, int port) {
        return send(host, port, EVENT_EXIT);
    }
}
