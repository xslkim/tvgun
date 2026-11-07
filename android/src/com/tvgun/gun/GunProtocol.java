package com.tvgun.gun;

import java.util.Locale;
import java.util.UUID;

/** Sequenced gameplay packets for the UDP game path. */
public final class GunProtocol {
    private long sequence = 0;
    private final String session = UUID.randomUUID().toString();

    public String hello() {
        return "HELLO " + session;
    }

    public synchronized String aim(float x, float y, int grade) {
        return String.format(Locale.US, "%.1f,%.1f,%d,%d", x, y, grade, sequence++);
    }

    public synchronized String lost() {
        return "LOST," + sequence++;
    }

    public synchronized String shot(float x, float y) {
        return String.format(Locale.US, "SHOT %.1f,%.1f,%d", x, y, sequence++);
    }

    public static int[] frame(String text) {
        if (text == null || !text.startsWith("FRAME ")) return null;
        String[] fields = text.substring(6).trim().split(",");
        if (fields.length != 2) return null;
        try {
            int white = Integer.parseInt(fields[0]);
            int dark = Integer.parseInt(fields[1]);
            if (white < 12 || white > 40 || dark < 24 || dark > 72) return null;
            return new int[]{white, dark};
        } catch (NumberFormatException ignored) {
            return null;
        }
    }
}
