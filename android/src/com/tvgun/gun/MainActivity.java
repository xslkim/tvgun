package com.tvgun.gun;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Rect;
import android.hardware.Camera;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.os.Vibrator;
import android.util.Log;
import android.view.MotionEvent;
import android.view.OrientationEventListener;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.FrameLayout;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity implements SurfaceHolder.Callback {
    private static final String TAG = "tvgun";
    private static final String PREFS = "tvgun";
    private static final String DEFAULT_SERVER = "192.168.3.19:8000";
    private static final int REQ_CAM = 1;
    private static final long LONG_PRESS_MS = 600;
    private static final long AIM_INTERVAL_MS = 66;

    private SurfaceView surfaceView;
    private OverlayView overlay;

    private final Object camLock = new Object();
    private Camera camera;
    private boolean surfaceReady;
    private int prevW;
    private int prevH;
    private volatile int detRotation;

    private final Detector detector = new Detector();
    private final Fusion fusion = new Fusion();
    private final Handler ui = new Handler(Looper.getMainLooper());

    private SensorManager sensorManager;
    private Sensor gyro;
    private final SensorEventListener gyroListener = new SensorEventListener() {
        @Override
        public void onSensorChanged(SensorEvent e) {
            fusion.onGyro(e.timestamp, e.values[0], e.values[1], e.values[2]);
        }

        @Override
        public void onAccuracyChanged(Sensor sensor, int accuracy) {
        }
    };

    private final Object frameLock = new Object();
    private byte[] pending;
    private volatile boolean running;
    private Thread worker;

    private int frames;
    private long fpsWindowStart;
    private float fps;

    // aim streaming: mailbox consumed by a dedicated sender thread
    private final Object aimLock = new Object();
    private boolean aimPending;
    private float aimX;
    private float aimY;
    private long lastAimSent;
    private long lastAimLog;

    private SharedPreferences prefs;
    private String server;
    private volatile int score;

    private boolean longPressFired;
    private final Runnable longPressRunnable = new Runnable() {
        @Override
        public void run() {
            longPressFired = true;
            showServerDialog();
        }
    };

    private OrientationEventListener orientationListener;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        server = prefs.getString("server", DEFAULT_SERVER);

        sensorManager = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
        gyro = sensorManager != null ? sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE) : null;
        if (gyro == null) {
            Log.w(TAG, "no gyroscope sensor; camera-only aiming");
        }

        FrameLayout root = new FrameLayout(this);
        surfaceView = new SurfaceView(this);
        overlay = new OverlayView(this);
        root.addView(surfaceView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(overlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        surfaceView.getHolder().addCallback(this);

        if (!hasCameraPermission()) {
            requestCameraPermission();
        }
        orientationListener = new OrientationEventListener(this, SensorManager.SENSOR_DELAY_UI) {
            @Override
            public void onOrientationChanged(int orientation) {
                if (orientation == ORIENTATION_UNKNOWN) return;
                checkOrientationChange();
            }
        };
        startWorker();
        startAimSender();
        syncScore();
    }

    @Override
    protected void onResume() {
        super.onResume();
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        if (orientationListener != null && orientationListener.canDetectOrientation()) {
            orientationListener.enable();
        }
        if (gyro != null) {
            boolean ok = sensorManager.registerListener(gyroListener, gyro, SensorManager.SENSOR_DELAY_GAME);
            Log.i(TAG, "gyro registered=" + ok + " delay=GAME");
        }
        openCamera();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (orientationListener != null) {
            orientationListener.disable();
        }
        if (gyro != null) {
            sensorManager.unregisterListener(gyroListener);
            Log.i(TAG, "gyro unregistered");
        }
        releaseCamera();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        running = false;
        synchronized (frameLock) {
            frameLock.notifyAll();
        }
        synchronized (aimLock) {
            aimLock.notifyAll();
        }
    }

    // ---- camera ----

    private boolean hasCameraPermission() {
        return Build.VERSION.SDK_INT < 23
                || checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestCameraPermission() {
        if (Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAM);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == REQ_CAM) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                openCamera();
            } else {
                overlay.setPermissionDenied();
            }
        }
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        surfaceReady = true;
        openCamera();
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        checkOrientationChange();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            checkOrientationChange();
        }
    }

    /** Standard back-camera display-orientation formula. out = {info.orientation, displayRotation}. */
    private int computeDisplayOrientation(int[] out) {
        Camera.CameraInfo info = new Camera.CameraInfo();
        Camera.getCameraInfo(0, info);
        int rotation = getWindowManager().getDefaultDisplay().getRotation();
        int degrees = rotation * 90; // ROTATION_0/90/180/270 -> 0/90/180/270
        if (out != null) {
            out[0] = info.orientation;
            out[1] = rotation;
        }
        return (info.orientation - degrees + 360) % 360;
    }

    /** Re-applies the display orientation if the device rotation changed (sensorLandscape 180° flips). */
    private void checkOrientationChange() {
        int newVal = computeDisplayOrientation(null);
        if (newVal == detRotation) return;
        detRotation = newVal;
        fusion.setRotation(newVal);
        synchronized (camLock) {
            if (camera != null) {
                try {
                    camera.setDisplayOrientation(newVal);
                } catch (Exception e) {
                    Log.e(TAG, "setDisplayOrientation failed", e);
                }
            }
        }
        Log.i(TAG, "orientation changed: displayOrientation=" + newVal);
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        surfaceReady = false;
        releaseCamera();
    }

    private void openCamera() {
        synchronized (camLock) {
            if (camera != null || !surfaceReady || !hasCameraPermission()) return;
            try {
                camera = Camera.open();
                Camera.Parameters p = camera.getParameters();
                Camera.Size best = null;
                long bestDiff = Long.MAX_VALUE;
                for (Camera.Size s : p.getSupportedPreviewSizes()) {
                    long diff = Math.abs((long) s.width * s.height - 1280L * 720L);
                    if (diff < bestDiff) {
                        bestDiff = diff;
                        best = s;
                    }
                }
                prevW = best.width;
                prevH = best.height;
                p.setPreviewSize(prevW, prevH);
                p.setRecordingHint(true);
                float viewAngle = p.getHorizontalViewAngle();
                float scale = (float) (Detector.NORM_W / Math.toRadians(viewAngle));
                fusion.setScale(scale);
                Log.i(TAG, String.format(Locale.US, "S=%.1f viewAngle=%.1f", scale, viewAngle));
                List<String> supportedFocus = p.getSupportedFocusModes();
                String focusMode = null;
                if (supportedFocus != null) {
                    if (supportedFocus.contains(Camera.Parameters.FOCUS_MODE_CONTINUOUS_VIDEO)) {
                        focusMode = Camera.Parameters.FOCUS_MODE_CONTINUOUS_VIDEO;
                    } else if (supportedFocus.contains(Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE)) {
                        focusMode = Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE;
                    } else if (supportedFocus.contains(Camera.Parameters.FOCUS_MODE_AUTO)) {
                        focusMode = Camera.Parameters.FOCUS_MODE_AUTO;
                    }
                }
                if (focusMode != null) {
                    p.setFocusMode(focusMode);
                }
                Log.i(TAG, "focus mode=" + focusMode + " supported=" + supportedFocus);
                try {
                    if (p.getMaxNumFocusAreas() > 0) {
                        // center 60% region, full weight
                        List<Camera.Area> areas = new ArrayList<Camera.Area>();
                        areas.add(new Camera.Area(new Rect(-600, -600, 600, 600), 1000));
                        p.setFocusAreas(areas);
                        if (p.getMaxNumMeteringAreas() > 0) {
                            p.setMeteringAreas(areas);
                        }
                        Log.i(TAG, "focus/metering areas set: center 60%");
                    }
                } catch (Exception e) {
                    Log.w(TAG, "focus/metering areas unsupported", e);
                }
                camera.setParameters(p);
                int[] dbg = new int[2];
                int displayOrientation = computeDisplayOrientation(dbg);
                camera.setDisplayOrientation(displayOrientation);
                detRotation = displayOrientation;
                fusion.setRotation(displayOrientation);
                Log.i(TAG, "orientation: info.orientation=" + dbg[0]
                        + " rotation=" + dbg[1] + " displayOrientation=" + displayOrientation);
                int bufSize = prevW * prevH * 3 / 2;
                for (int i = 0; i < 3; i++) {
                    camera.addCallbackBuffer(new byte[bufSize]);
                }
                camera.setPreviewCallbackWithBuffer(previewCallback);
                camera.setPreviewDisplay(surfaceView.getHolder());
                camera.startPreview();
                if (Camera.Parameters.FOCUS_MODE_AUTO.equals(focusMode)) {
                    try {
                        camera.autoFocus(null);
                        Log.i(TAG, "autoFocus() fallback triggered");
                    } catch (Exception e) {
                        Log.w(TAG, "autoFocus failed", e);
                    }
                }
                Log.i(TAG, "camera started, preview " + prevW + "x" + prevH);
            } catch (Exception e) {
                Log.e(TAG, "openCamera failed", e);
                if (camera != null) {
                    try {
                        camera.release();
                    } catch (Exception ignored) {
                    }
                    camera = null;
                }
            }
        }
    }

    private void releaseCamera() {
        synchronized (camLock) {
            if (camera == null) return;
            try {
                camera.setPreviewCallbackWithBuffer(null);
                camera.stopPreview();
                camera.release();
            } catch (Exception e) {
                Log.e(TAG, "releaseCamera error", e);
            }
            camera = null;
        }
    }

    private final Camera.PreviewCallback previewCallback = new Camera.PreviewCallback() {
        @Override
        public void onPreviewFrame(byte[] data, Camera cam) {
            synchronized (frameLock) {
                if (pending == null) {
                    pending = data;
                    frameLock.notify();
                    return;
                }
            }
            // worker still busy: drop the frame, recycle its buffer
            synchronized (camLock) {
                if (camera != null) {
                    try {
                        camera.addCallbackBuffer(data);
                    } catch (Exception ignored) {
                    }
                }
            }
        }
    };

    // ---- detection worker ----

    private void startWorker() {
        running = true;
        worker = new Thread(new Runnable() {
            @Override
            public void run() {
                workerLoop();
            }
        }, "detect");
        worker.start();
    }

    private void workerLoop() {
        while (running) {
            byte[] d;
            synchronized (frameLock) {
                while (running && pending == null) {
                    try {
                        frameLock.wait();
                    } catch (InterruptedException ignored) {
                    }
                }
                d = pending;
                pending = null;
            }
            if (d == null) continue;
            try {
                detector.process(d, prevW, prevH, detRotation);
                frames++;
                long now = SystemClock.elapsedRealtime();
                if (fpsWindowStart == 0) fpsWindowStart = now;
                if (now - fpsWindowStart >= 1000) {
                    fps = frames * 1000f / (now - fpsWindowStart);
                    frames = 0;
                    fpsWindowStart = now;
                    Log.i(TAG, String.format(Locale.US,
                            "fps=%.1f locked=%b thr=%d cross=%d,%d valid=%b fail=%d blob=%.2f%%",
                            fps, detector.locked, detector.lastThr,
                            (int) detector.cross[0], (int) detector.cross[1], detector.crossValid,
                            detector.lastFail,
                            detector.detW * detector.detH > 0
                                    ? 100f * detector.lastBestCount / (detector.detW * detector.detH) : 0f));
                }
                final boolean lk = detector.locked;
                final float[] cs = lk ? detector.corners.clone() : null;
                final int dw = detector.detW;
                final int dh = detector.detH;
                final boolean cv = detector.crossValid;
                final long nowNs = SystemClock.elapsedRealtimeNanos();
                if (lk && cv) {
                    fusion.onCameraLock(nowNs, detector.cross[0], detector.cross[1]);
                } else if (!lk) {
                    fusion.onCameraUnlock(nowNs);
                }
                final Fusion.State st = fusion.snapshot(nowNs);
                if (st.valid) {
                    long t = SystemClock.elapsedRealtime();
                    if (t - lastAimSent >= AIM_INTERVAL_MS) {
                        lastAimSent = t;
                        offerAim(st.x, st.y);
                        if (t - lastAimLog >= 1000) {
                            lastAimLog = t;
                            Log.i(TAG, String.format(Locale.US, "aim (%.0f,%.0f) pred=%d",
                                    st.x, st.y, st.predicted ? 1 : 0));
                        }
                    }
                }
                final float ax = st.x;
                final float ay = st.y;
                final boolean av = st.valid;
                final boolean pr = st.predicted;
                final float f = fps;
                final int sc = score;
                final String srv = server;
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        overlay.setState(lk, cs, dw, dh, ax, ay, av, pr, f, sc, srv);
                    }
                });
            } catch (Throwable t) {
                Log.e(TAG, "detect error", t);
            }
            synchronized (camLock) {
                if (camera != null) {
                    try {
                        camera.addCallbackBuffer(d);
                    } catch (Exception ignored) {
                    }
                }
            }
        }
    }

    // ---- aim streaming ----

    private void startAimSender() {
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                while (true) {
                    float x, y;
                    String srv;
                    synchronized (aimLock) {
                        while (running && !aimPending) {
                            try {
                                aimLock.wait();
                            } catch (InterruptedException ignored) {
                            }
                        }
                        if (!running) return;
                        x = aimX;
                        y = aimY;
                        aimPending = false;
                        srv = server;
                    }
                    postAim("http://" + srv + "/aim",
                            String.format(Locale.US, "{\"x\":%.1f,\"y\":%.1f}", x, y));
                }
            }
        }, "aim");
        t.setDaemon(true);
        t.start();
    }

    private void offerAim(float x, float y) {
        synchronized (aimLock) {
            aimX = x;
            aimY = y;
            aimPending = true;
            aimLock.notify();
        }
    }

    /** request() with 1s timeouts and silent failure; runs on the "aim" thread only. */
    private static void postAim(String urlStr, String body) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(urlStr).openConnection();
            c.setConnectTimeout(1000);
            c.setReadTimeout(1000);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json");
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();
            c.getResponseCode();
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.disconnect();
        }
    }

    // ---- trigger ----

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                longPressFired = false;
                ui.postDelayed(longPressRunnable, LONG_PRESS_MS);
                fire();
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                ui.removeCallbacks(longPressRunnable);
                break;
        }
        return true;
    }

    private void fire() {
        final Fusion.State st = fusion.snapshot(SystemClock.elapsedRealtimeNanos());
        if (!st.valid) {
            overlay.flash(OverlayView.FLASH_NOLOCK);
            Log.i(TAG, "fire: no lock, skipped");
            return;
        }
        final float x = st.x;
        final float y = st.y;
        final String srv = server;
        new Thread(new Runnable() {
            @Override
            public void run() {
                JSONObject resp = null;
                try {
                    resp = request("POST", "http://" + srv + "/shot",
                            "{\"x\":" + x + ",\"y\":" + y + "}");
                } catch (Exception e) {
                    Log.e(TAG, "shot failed", e);
                }
                if (resp == null) {
                    ui.post(new Runnable() {
                        @Override
                        public void run() {
                            overlay.setConnFail();
                        }
                    });
                    return;
                }
                final boolean hit = resp.optBoolean("hit");
                score = resp.optInt("score", score);
                Log.i(TAG, "shot (" + (int) x + "," + (int) y + ") hit=" + hit + " score=" + score);
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        overlay.flash(hit ? OverlayView.FLASH_HIT : OverlayView.FLASH_MISS);
                        overlay.setScore(score);
                        if (hit) {
                            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
                            if (v != null) v.vibrate(50);
                        }
                    }
                });
            }
        }, "shot").start();
    }

    // ---- server config / state ----

    private void showServerDialog() {
        final EditText et = new EditText(this);
        et.setText(server);
        et.setSingleLine();
        new AlertDialog.Builder(this)
                .setTitle("服务器地址 (host:port)")
                .setView(et)
                .setPositiveButton("保存", (d, w) -> {
                    String s = et.getText().toString().trim();
                    if (!s.isEmpty()) {
                        server = s;
                        prefs.edit().putString("server", s).apply();
                        syncScore();
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void syncScore() {
        final String srv = server;
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    JSONObject resp = request("GET", "http://" + srv + "/state", null);
                    if (resp != null) {
                        score = resp.optInt("score", score);
                        ui.post(new Runnable() {
                            @Override
                            public void run() {
                                overlay.setScore(score);
                            }
                        });
                    }
                } catch (Exception e) {
                    Log.w(TAG, "syncScore failed: " + e.getMessage());
                }
            }
        }, "state").start();
    }

    private static JSONObject request(String method, String urlStr, String body) throws Exception {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(urlStr).openConnection();
            c.setConnectTimeout(3000);
            c.setReadTimeout(3000);
            c.setRequestMethod(method);
            if (body != null) {
                c.setRequestProperty("Content-Type", "application/json");
                c.setDoOutput(true);
                OutputStream os = c.getOutputStream();
                os.write(body.getBytes("UTF-8"));
                os.close();
            }
            if (c.getResponseCode() != 200) return null;
            InputStream is = c.getInputStream();
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[1024];
            int r;
            while ((r = is.read(buf)) != -1) {
                bos.write(buf, 0, r);
            }
            is.close();
            return new JSONObject(bos.toString("UTF-8"));
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
