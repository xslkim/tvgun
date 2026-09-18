package com.tvgun.gun;

/**
 * Gyro + camera complementary fusion for the crosshair position p in
 * normalized 1920x1080 screen coordinates. Pure Java (no Android deps) so it
 * can be unit-tested offline; all timestamps are caller-supplied nanoseconds
 * from a monotonic clock (SensorEvent.timestamp / SystemClock.elapsedRealtimeNanos).
 *
 * Gyro tick:  p += (omega_h*dt*S, omega_v*dt*S), S = 1920 / horizontalFoV(rad).
 * Camera lock (locked && crossValid): p <- 0.7*p + 0.3*p_camera.
 * Lock lost <=1s: gyro extrapolation continues, predicted=true.
 * Lock lost >1s: frozen, predicted=false, snapshot invalid (not reported).
 * Re-lock: correction resumes and predicted clears.
 * Before the first camera lock p is undefined: gyro ticks only advance the
 * clock (no output); the first lock initializes p from p_camera.
 *
 * Axis mapping (device is locked to sensorLandscape, so detRotation is only
 * ever 0 or 180). rot=0:  dx = ROT0_SIGN_H * omega_y*dt*S,
 *                         dy = ROT0_SIGN_V * omega_x*dt*S.
 * rot=180 flips both signs. If real-device testing shows reversed movement,
 * flip ROT0_SIGN_H / ROT0_SIGN_V here only.
 */
public final class Fusion {
    // ---- axis sign table (待真机验证：方向反了只改这两个常量) ----
    public static final int ROT0_SIGN_H = +1;
    public static final int ROT0_SIGN_V = +1;

    private static final float CAMERA_GAIN = 0.3f;      // complementary correction gain
    private static final long PREDICT_NS = 1_000_000_000L; // 1s extrapolation window
    private static final float MAX_DT_S = 0.1f;         // gyro gap clamp (pause/jitter)

    public static final class State {
        public float x;
        public float y;
        /** safe to report: initialized and (locked or within the 1s predict window). */
        public boolean valid;
        /** camera lock lost but still extrapolating (<=1s since last lock). */
        public boolean predicted;
    }

    private float scale = 1f;   // S: normalized px per radian
    private int rotation;       // detRotation: 0 or 180
    private boolean initialized;
    private boolean locked;
    private float x;
    private float y;
    private long lastGyroNs = -1;
    private long lastLockNs = -1;

    public synchronized void setScale(float s) {
        scale = s;
    }

    public synchronized void setRotation(int deg) {
        rotation = deg;
    }

    public synchronized void reset() {
        initialized = false;
        locked = false;
        x = y = 0;
        lastGyroNs = -1;
        lastLockNs = -1;
    }

    /** Gyroscope tick. wx/wy/wz are device-axis angular velocities in rad/s. */
    public synchronized void onGyro(long tsNs, float wx, float wy, float wz) {
        if (lastGyroNs < 0) {
            lastGyroNs = tsNs;
            return;
        }
        float dt = (tsNs - lastGyroNs) * 1e-9f;
        lastGyroNs = tsNs;
        if (dt <= 0 || dt > MAX_DT_S) return;  // clock gap (pause/resume): skip
        if (!initialized) return;              // pre-first-lock: advance clock only
        if (!locked && tsNs - lastLockNs > PREDICT_NS) return; // frozen
        int sign = (rotation == 180) ? -1 : 1;
        x += ROT0_SIGN_H * sign * wy * dt * scale;
        y += ROT0_SIGN_V * sign * wx * dt * scale;
    }

    /** Camera frame with a valid crosshair (detector.locked && crossValid). */
    public synchronized void onCameraLock(long tsNs, float cx, float cy) {
        if (!initialized) {
            x = cx;
            y = cy;
            initialized = true;
        } else {
            x = (1f - CAMERA_GAIN) * x + CAMERA_GAIN * cx;
            y = (1f - CAMERA_GAIN) * y + CAMERA_GAIN * cy;
        }
        locked = true;
        lastLockNs = tsNs;
    }

    /** Camera lock lost (detector.locked went false). Extrapolation continues for 1s. */
    public synchronized void onCameraUnlock(long tsNs) {
        locked = false;
    }

    /** Point-in-time snapshot; callers pass the current monotonic time. */
    public synchronized State snapshot(long nowNs) {
        State s = new State();
        s.x = x;
        s.y = y;
        if (!initialized) {
            s.valid = false;
            s.predicted = false;
            return s;
        }
        boolean within = locked || (nowNs - lastLockNs <= PREDICT_NS);
        s.predicted = !locked && within;
        s.valid = within;
        return s;
    }
}
