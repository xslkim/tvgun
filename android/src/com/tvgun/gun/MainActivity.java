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
import android.util.Size;
import android.view.KeyEvent;
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
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity implements SurfaceHolder.Callback {
    private static final String TAG = "tvgun";
    private static final String PREFS = "tvgun";
    private static final String DEFAULT_SERVER = "192.168.3.19:8000";
    private static final int REQ_CAM = 1;
    private static final long LONG_PRESS_MS = 600;
    private static final long AIM_INTERVAL_MS = 16;    // 60Hz 准星上报

    private SurfaceView surfaceView;
    private OverlayView overlay;

    private final Object camLock = new Object();
    private Camera camera;
    private boolean surfaceReady;
    private int prevW;
    private int prevH;
    private volatile int detRotation;
    private int[] fpsRangeChosen;
    private String sceneModeChosen;
    private float viewAngleDeg;
    private float scaleS;
    private int[] backCameraIds;
    private float[] backViewAngles;
    private int cameraId = -1;
    // camera2 backend (preferred; legacy HAL1 kept as fallback)
    private volatile boolean useCamera2;
    private boolean backendChosen;
    private Camera2Backend c2;
    private List<Camera2Backend.LensInfo> c2Lenses;
    private String c2Id;
    private int sensorOrientation = 90;
    private int c2ErrorRetries;

    private final Recorder recorder = new Recorder();
    private long pendingTs;
    private int recSeq;
    private long lastJpegNs;
    private final int[] grayDims = new int[2];
    private long lastVisionNs = SystemClock.elapsedRealtimeNanos();

    private final Tracker tracker = new Tracker();
    private final Handler ui = new Handler(Looper.getMainLooper());

    private SensorManager sensorManager;
    private Sensor gyro;
    private final SensorEventListener gyroListener = new SensorEventListener() {
        @Override
        public void onSensorChanged(SensorEvent e) {
            tracker.onGyro(e.timestamp, e.values[0], e.values[1], e.values[2]);
            recorder.recordGyro(e.timestamp, e.values[0], e.values[1], e.values[2]);
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

    // aim streaming: 60Hz self-timed sender reads tracker.snapshot() directly
    private final Object aimLock = new Object();

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
        Log.i(TAG, "tvgun version " + Version.DESCRIBE);

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
            boolean ok = sensorManager.registerListener(gyroListener, gyro, SensorManager.SENSOR_DELAY_FASTEST);
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
        recorder.stop();
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
        openCamera(); // setFixedSize resize lands here: retry opening with the new surface
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            checkOrientationChange();
        }
    }

    /** Standard back-camera display-orientation formula. out = {sensorOrientation, displayRotation}. */
    private int computeDisplayOrientation(int[] out) {
        int rotation = getWindowManager().getDefaultDisplay().getRotation();
        int degrees = rotation * 90; // ROTATION_0/90/180/270 -> 0/90/180/270
        if (out != null) {
            out[0] = sensorOrientation;
            out[1] = rotation;
        }
        return (sensorOrientation - degrees + 360) % 360;
    }

    /** Re-applies the display orientation if the device rotation changed (sensorLandscape 180° flips). */
    private void checkOrientationChange() {
        int newVal = computeDisplayOrientation(null);
        if (newVal == detRotation) return;
        detRotation = newVal;
        tracker.setRotation(newVal);
        synchronized (camLock) {
            if (!useCamera2 && camera != null) {
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
            if (!backendChosen) {
                backendChosen = true;
                c2 = new Camera2Backend(this);
                c2.errorListener = new Camera2Backend.ErrorListener() {
                    @Override
                    public void onCameraError() {
                        ui.postDelayed(new Runnable() {
                            @Override
                            public void run() {
                                synchronized (camLock) {
                                    if (!useCamera2 || c2.active) return;
                                    c2ErrorRetries++;
                                    if (c2ErrorRetries > 5) {
                                        Log.e(TAG, "camera2 kept failing, fallback to legacy HAL1");
                                        useCamera2 = false;
                                        c2.close();
                                        if (cameraId < 0) cameraId = selectInitialCameraLocked();
                                    }
                                }
                                openCamera();
                            }
                        }, 800);
                    }
                };
                try {
                    c2Lenses = c2.enumerateBackLenses();
                    useCamera2 = !c2Lenses.isEmpty();
                } catch (Exception e) {
                    Log.e(TAG, "camera2 enumeration failed, fallback to legacy HAL1", e);
                    useCamera2 = false;
                }
                if (useCamera2) {
                    c2Id = selectInitialC2Locked();
                } else if (cameraId < 0) {
                    cameraId = selectInitialCameraLocked();
                }
            }
            if (useCamera2) {
                if (!surfaceReady || !hasCameraPermission()) {
                    return; // surfaceCreated/permission callback will retry
                }
                try {
                    openCamera2Locked(c2Id);
                    return; // active now, or a surface-resize retry was scheduled
                } catch (Exception e) {
                    Log.e(TAG, "camera2 open failed, fallback to legacy HAL1", e);
                    useCamera2 = false;
                    c2.close();
                    if (cameraId < 0) cameraId = selectInitialCameraLocked();
                }
            }
        }
        openCamera(cameraId);
    }

    /** Persisted camera2 id if still present, else the widest back lens. Call with camLock held. */
    private String selectInitialC2Locked() {
        String pref = prefs.getString("camera2Id", null);
        Camera2Backend.LensInfo widest = null;
        for (Camera2Backend.LensInfo li : c2Lenses) {
            if (li.id.equals(pref)) {
                Log.i(TAG, String.format(Locale.US,
                        "camera2 id=%s FOV=%.1f (restored from prefs)", li.id, li.fovH));
                return li.id;
            }
            if (widest == null || li.fovH > widest.fovH) widest = li;
        }
        Log.i(TAG, String.format(Locale.US, "camera2 id=%s FOV=%.1f (widest of %d back)",
                widest.id, widest.fovH, c2Lenses.size()));
        return widest.id;
    }

    /**
     * Opens the camera2 backend on id and syncs all pipeline state; throws on real
     * failure. A surface-resize retry schedules a reopen via surfaceChanged and
     * returns without throwing. Call with camLock held.
     */
    private void openCamera2Locked(String id) throws Exception {
        if (c2.active || !surfaceReady || !hasCameraPermission()) return;
        Size yuvSize = c2.chooseYuvSize(id);
        // camera2 needs the preview surface at a supported size: a full-screen
        // SurfaceView buffer (e.g. 2340x1080) negotiates silently to a black preview.
        android.graphics.Rect frame = surfaceView.getHolder().getSurfaceFrame();
        if (frame.width() != yuvSize.getWidth() || frame.height() != yuvSize.getHeight()) {
            Log.i(TAG, "preview surface resize " + frame.width() + "x" + frame.height()
                    + " -> " + yuvSize.getWidth() + "x" + yuvSize.getHeight());
            surfaceView.getHolder().setFixedSize(yuvSize.getWidth(), yuvSize.getHeight());
            return; // surfaceChanged/Created re-fires and reopens
        }
        c2.open(id, surfaceView.getHolder().getSurface(), c2Sink);
        c2ErrorRetries = 0;
        prevW = c2.width;
        prevH = c2.height;
        viewAngleDeg = c2.fovDeg;
        scaleS = (float) (Tracker.NORM_W / Math.toRadians(viewAngleDeg));
        tracker.setFov(viewAngleDeg);
        sensorOrientation = c2.sensorOrientation;
        int[] dbg = new int[2];
        detRotation = computeDisplayOrientation(dbg);
        tracker.setRotation(detRotation);
        Log.i(TAG, String.format(Locale.US,
                "camera2 started: id=%s preview %dx%d S=%.1f viewAngle=%.1f detRotation=%d",
                id, prevW, prevH, scaleS, viewAngleDeg, detRotation));
        final String lens = lensLabelC2(id);
        ui.post(new Runnable() {
            @Override
            public void run() {
                overlay.setLensLabel("镜头: " + lens);
            }
        });
    }

    /** Lens name by FOV rank among camera2 back lenses (widest=超广角, narrowest=长焦). */
    private String lensLabelC2(String id) {
        if (c2Lenses == null) return "后置" + id;
        Camera2Backend.LensInfo self = null;
        int wider = 0, narrower = 0;
        for (Camera2Backend.LensInfo li : c2Lenses) {
            if (li.id.equals(id)) self = li;
        }
        if (self == null) return "后置" + id;
        for (Camera2Backend.LensInfo li : c2Lenses) {
            if (li.fovH > self.fovH) wider++;
            if (li.fovH < self.fovH) narrower++;
        }
        String kind;
        if (wider == 0 && c2Lenses.size() >= 2) kind = "超广角";
        else if (narrower == 0 && c2Lenses.size() >= 3) kind = "长焦";
        else kind = "主摄";
        return String.format(Locale.US, "%s %.0f°", kind, self.fovH);
    }

    private final Camera2Backend.FrameSink c2Sink = new Camera2Backend.FrameSink() {
        @Override
        public void onFrame(byte[] y, int w, int h, long tsNs) {
            synchronized (frameLock) {
                if (pending == null) {
                    pending = y;
                    pendingTs = tsNs;
                    frameLock.notify();
                }
                // drop otherwise: private copy, nothing to recycle
            }
        }
    };

    /**
     * Enumerates back cameras (open/probe viewAngle/release each), logs every id,
     * returns the persisted id if still present, else the widest. Falls back to id 0.
     * Call with camLock held.
     */
    private int selectInitialCameraLocked() {
        List<Integer> ids = new ArrayList<>();
        List<Float> angles = new ArrayList<>();
        int n = Camera.getNumberOfCameras();
        Log.i(TAG, "getNumberOfCameras=" + n);
        Camera.CameraInfo info = new Camera.CameraInfo();
        for (int i = 0; i < n; i++) {
            try {
                Camera.getCameraInfo(i, info);
            } catch (Exception e) {
                continue;
            }
            Log.i(TAG, "camera id=" + i + " facing="
                    + (info.facing == Camera.CameraInfo.CAMERA_FACING_BACK ? "back" : "front")
                    + " orientation=" + info.orientation);
            if (info.facing != Camera.CameraInfo.CAMERA_FACING_BACK) continue;
            float va = Float.NaN;
            Camera probe = null;
            try {
                probe = Camera.open(i);
                va = probe.getParameters().getHorizontalViewAngle();
            } catch (Exception e) {
                Log.w(TAG, "camera id=" + i + " probe failed: " + e.getMessage());
            } finally {
                if (probe != null) {
                    try {
                        probe.release();
                    } catch (Exception ignored) {
                    }
                }
            }
            if (Float.isNaN(va)) continue;
            ids.add(i);
            angles.add(va);
            Log.i(TAG, String.format(Locale.US, "back camera id=%d viewAngle=%.1f", i, va));
        }
        backCameraIds = new int[ids.size()];
        backViewAngles = new float[angles.size()];
        int widest = 0;
        for (int i = 0; i < ids.size(); i++) {
            backCameraIds[i] = ids.get(i);
            backViewAngles[i] = angles.get(i);
            if (angles.get(i) > angles.get(widest)) widest = i;
        }
        if (ids.isEmpty()) {
            Log.w(TAG, "no back cameras enumerated, fallback id 0");
            backCameraIds = new int[]{0};
            backViewAngles = new float[]{Float.NaN};
            return 0;
        }
        int prefId = prefs.getInt("cameraId", -1);
        for (int i = 0; i < backCameraIds.length; i++) {
            if (backCameraIds[i] == prefId) {
                Log.i(TAG, String.format(Locale.US,
                        "camera id=%d viewAngle=%.1f (restored from prefs)", prefId, backViewAngles[i]));
                return prefId;
            }
        }
        Log.i(TAG, String.format(Locale.US, "camera id=%d viewAngle=%.1f (widest of %d back)",
                backCameraIds[widest], backViewAngles[widest], backCameraIds.length));
        return backCameraIds[widest];
    }

    /** Lens name by viewAngle rank among the back cameras (widest=超广角, narrowest=长焦). */
    private String lensLabel(int id) {
        if (backCameraIds == null) return "后置" + id;
        int idx = -1;
        for (int i = 0; i < backCameraIds.length; i++) {
            if (backCameraIds[i] == id) idx = i;
        }
        if (idx < 0) return "后置" + id;
        float va = backViewAngles[idx];
        int wider = 0, narrower = 0;
        for (float a : backViewAngles) {
            if (a > va) wider++;
            if (a < va) narrower++;
        }
        String kind;
        if (wider == 0 && backCameraIds.length >= 2) kind = "超广角";
        else if (narrower == 0 && backCameraIds.length >= 3) kind = "长焦";
        else kind = "主摄";
        return String.format(Locale.US, "%s %.0f°", kind, va);
    }

    /** Volume-up: cycle to the next back camera, skipping ids that fail to open. */
    private void switchCamera() {
        synchronized (camLock) {
            if (recorder.isRecording()) {
                Log.w(TAG, "camera switch ignored while recording");
                return;
            }
            if (useCamera2) {
                if (c2Lenses == null || c2Lenses.size() < 2) {
                    Log.w(TAG, "camera switch ignored (single back lens)");
                    return;
                }
                int cur = 0;
                for (int i = 0; i < c2Lenses.size(); i++) {
                    if (c2Lenses.get(i).id.equals(c2Id)) cur = i;
                }
                for (int attempt = 0; attempt < c2Lenses.size(); attempt++) {
                    cur = (cur + 1) % c2Lenses.size();
                    String next = c2Lenses.get(cur).id;
                    c2.close();
                    try {
                        c2Id = next;
                        openCamera2Locked(next);
                        // success: active now, or reopen scheduled after surface resize
                        prefs.edit().putString("camera2Id", next).apply();
                        Log.i(TAG, "camera switched -> id=" + next + " " + lensLabelC2(next));
                        return;
                    } catch (Exception e) {
                        Log.w(TAG, "camera2 id=" + next + " open failed: " + e.getMessage());
                    }
                }
                Log.w(TAG, "all camera2 ids failed, fallback to legacy HAL1");
                useCamera2 = false;
                c2.close();
                if (cameraId < 0) cameraId = selectInitialCameraLocked();
                openCamera(cameraId);
                return;
            }
            if (backCameraIds == null || backCameraIds.length < 2 || cameraId < 0) {
                Log.w(TAG, "camera switch ignored (back ids not ready)");
                return;
            }
            int cur = 0;
            for (int i = 0; i < backCameraIds.length; i++) {
                if (backCameraIds[i] == cameraId) cur = i;
            }
            for (int attempt = 0; attempt < backCameraIds.length; attempt++) {
                cur = (cur + 1) % backCameraIds.length;
                int next = backCameraIds[cur];
                releaseCamera();
                cameraId = next;
                openCamera(next);
                if (camera != null) {
                    prefs.edit().putInt("cameraId", next).apply();
                    Log.i(TAG, "camera switched -> id=" + next + " " + lensLabel(next));
                    return;
                }
                Log.w(TAG, "camera id=" + next + " open failed, trying next");
            }
            releaseCamera();
            cameraId = 0;
            Log.w(TAG, "all back cameras failed, fallback id 0");
            openCamera(0);
        }
    }

    private void openCamera(int id) {
        synchronized (camLock) {
            if (camera != null || !surfaceReady || !hasCameraPermission()) return;
            try {
                camera = Camera.open(id);
                Camera.CameraInfo info = new Camera.CameraInfo();
                Camera.getCameraInfo(id, info);
                sensorOrientation = info.orientation;
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
                // Fixed 30fps: prefer an exact [30000,30000] range, else the
                // narrowest range containing 30000. Prevents the dark-scene
                // frame-rate collapse (seen as fps=14 in logcat).
                List<int[]> ranges = p.getSupportedPreviewFpsRange();
                int[] chosenRange = null;
                if (ranges != null) {
                    for (int[] r : ranges) {
                        if (r[0] == 30000 && r[1] == 30000) {
                            chosenRange = r;
                            break;
                        }
                    }
                    if (chosenRange == null) {
                        for (int[] r : ranges) {
                            if (r[0] <= 30000 && r[1] >= 30000
                                    && (chosenRange == null
                                            || r[1] - r[0] < chosenRange[1] - chosenRange[0])) {
                                chosenRange = r;
                            }
                        }
                    }
                }
                if (chosenRange != null) {
                    p.setPreviewFpsRange(chosenRange[0], chosenRange[1]);
                }
                StringBuilder rs = new StringBuilder();
                if (ranges != null) {
                    for (int[] r : ranges) {
                        if (rs.length() > 0) rs.append(' ');
                        rs.append('[').append(r[0]).append(',').append(r[1]).append(']');
                    }
                }
                Log.i(TAG, "fps range chosen=" + (chosenRange == null ? "none"
                        : "[" + chosenRange[0] + "," + chosenRange[1] + "]") + " supported=" + rs);
                // Short-exposure scene mode against motion blur.
                List<String> scenes = p.getSupportedSceneModes();
                String sceneMode = null;
                if (scenes != null) {
                    if (scenes.contains(Camera.Parameters.SCENE_MODE_SPORTS)) {
                        sceneMode = Camera.Parameters.SCENE_MODE_SPORTS;
                    } else if (scenes.contains(Camera.Parameters.SCENE_MODE_ACTION)) {
                        sceneMode = Camera.Parameters.SCENE_MODE_ACTION;
                    }
                }
                if (sceneMode != null) {
                    p.setSceneMode(sceneMode);
                }
                Log.i(TAG, "scene mode=" + sceneMode + " supported=" + scenes);
                float viewAngle = p.getHorizontalViewAngle();
                float scale = (float) (Tracker.NORM_W / Math.toRadians(viewAngle));
                tracker.setFov(viewAngle);
                fpsRangeChosen = chosenRange;
                sceneModeChosen = sceneMode;
                viewAngleDeg = viewAngle;
                scaleS = scale;
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
                tracker.setRotation(displayOrientation);
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
                Log.i(TAG, "camera started: id=" + id + " preview " + prevW + "x" + prevH);
                final String lens = lensLabel(id);
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        overlay.setLensLabel("镜头: " + lens);
                    }
                });
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
            if (c2 != null && c2.active) {
                c2.close();
            }
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
            long ts = SystemClock.elapsedRealtimeNanos();
            synchronized (frameLock) {
                if (pending == null) {
                    pending = data;
                    pendingTs = ts;
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
            final long frameTs;
            synchronized (frameLock) {
                while (running && pending == null) {
                    try {
                        frameLock.wait();
                    } catch (InterruptedException ignored) {
                    }
                }
                d = pending;
                pending = null;
                frameTs = pendingTs;
            }
            if (d == null) continue;
            try {
                byte[] gray = sampleGray(d, prevW, prevH, detRotation, grayDims);
                tracker.processGray(gray, grayDims[0], grayDims[1], frameTs);
                frames++;
                long now = SystemClock.elapsedRealtime();
                if (fpsWindowStart == 0) fpsWindowStart = now;
                if (now - fpsWindowStart >= 1000) {
                    fps = frames * 1000f / (now - fpsWindowStart);
                    frames = 0;
                    fpsWindowStart = now;
                    Log.i(TAG, String.format(Locale.US,
                            "fps=%.1f grade=%s edges=%d thr=%d cross=%d,%d",
                            fps, Tracker.GRADE_NAMES[tracker.grade], tracker.nEdges,
                            tracker.lastThr,
                            (int) tracker.cross[0], (int) tracker.cross[1]));
                }
                final int grade = tracker.grade;
                final boolean av = tracker.aimValid();
                final float[] cs = tracker.quadImage();
                final int dw = grayDims[0];
                final int dh = grayDims[1];
                final long nowNs = SystemClock.elapsedRealtimeNanos();
                if (grade >= Tracker.GRADE_EDGE) lastVisionNs = nowNs;
                if (recorder.isRecording()) {
                    if (nowNs - recorder.getStartNs() > 60_000_000_000L) {
                        stopRecording();
                    } else {
                        final int seq = recSeq++;
                        recorder.recordFrame(seq, frameTs, gray);
                        recorder.recordDetect(frameTs, grade >= Tracker.GRADE_EDGE, av, grade,
                                tracker.lastThr, tracker.lastLowThr, 0f,
                                cs, tracker.cross[0], tracker.cross[1],
                                tracker.cross[0], tracker.cross[1],
                                grade == Tracker.GRADE_GYRO);
                        if (frameTs - lastJpegNs >= 1_000_000_000L) {
                            lastJpegNs = frameTs;
                            if (useCamera2) {
                                recorder.recordGrayJpeg(seq, d.clone(), prevW, prevH);
                            } else {
                                recorder.recordJpeg(seq, d.clone(), prevW, prevH);
                            }
                        }
                    }
                }
                final int recSec = recorder.isRecording()
                        ? (int) ((nowNs - recorder.getStartNs()) / 1_000_000_000L) : -1;
                final boolean uw = nowNs - lastVisionNs > 2_000_000_000L;
                final float ax = tracker.cross[0];
                final float ay = tracker.cross[1];
                final boolean pr = grade == Tracker.GRADE_GYRO;
                final float f = fps;
                final int sc = score;
                final String srv = server;
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        overlay.setState(grade, cs, dw, dh, ax, ay, av, pr, f, sc, srv);
                        overlay.setRecSec(recSec);
                        overlay.setUnlockWarn(uw);
                    }
                });
            } catch (Throwable t) {
                Log.e(TAG, "detect error", t);
            }
            if (useCamera2) {
                c2.releaseBuffer(d);
            } else {
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
    }

    // ---- aim streaming ----

    /**
     * 60Hz self-timed aim sender: reads the tracker snapshot directly (the tracker
     * propagates H on every gyro tick, so the cross is fresh at gyro rate, not
     * limited to camera frames). Latest-wins: HTTP latency only delays, never queues.
     */
    private void startAimSender() {
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                long lastLog = 0;
                int failStreak = 0;
                while (true) {
                    if (!running) return;
                    long nowMs = SystemClock.elapsedRealtime();
                    if (tracker.aimValid()) {
                        float[] st = tracker.snapshot();
                        boolean ok = postAim("http://" + server + "/aim",
                                String.format(Locale.US, "{\"x\":%.1f,\"y\":%.1f}", st[0], st[1]));
                        failStreak = ok ? 0 : failStreak + 1;
                        if (nowMs - lastLog >= 1000) {
                            lastLog = nowMs;
                            Log.i(TAG, String.format(Locale.US, "aim (%.0f,%.0f) grade=%s fail=%d",
                                    st[0], st[1], Tracker.GRADE_NAMES[(int) st[2]], failStreak));
                        }
                    }
                    long elapsed = SystemClock.elapsedRealtime() - nowMs;
                    long sleep = AIM_INTERVAL_MS - elapsed;
                    if (failStreak > 30) sleep = Math.max(sleep, 500);   // 断连退避
                    if (sleep > 0) {
                        try {
                            Thread.sleep(sleep);
                        } catch (InterruptedException ignored) {
                        }
                    }
                }
            }
        }, "aim");
        t.setDaemon(true);
        t.start();
    }

    /** request() with 1s timeouts and silent failure; runs on the "aim" thread only.
     * Returns false on failure so the caller can back off (otherwise a dead server
     * would stall the 60Hz loop on 1s connect timeouts). */
    private static boolean postAim(String urlStr, String body) {
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
            return true;
        } catch (Exception ignored) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    // ---- recording ----

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) {
            if (event.getRepeatCount() == 0) {
                toggleRecording();
            }
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_VOLUME_UP) {
            if (event.getRepeatCount() == 0) {
                switchCamera();
            }
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN || keyCode == KeyEvent.KEYCODE_VOLUME_UP) {
            return true; // consume: don't let the system change the volume
        }
        return super.onKeyUp(keyCode, event);
    }

    private void toggleRecording() {
        if (recorder.isRecording()) {
            stopRecording();
            return;
        }
        if (prevW == 0) {
            Log.w(TAG, "rec: camera not open, ignored");
            return;
        }
        String ts = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
        File dir = new File(getExternalFilesDir(null), "record/" + ts);
        try {
            recorder.start(dir, buildMeta(), SystemClock.elapsedRealtimeNanos());
            recSeq = 0;
            lastJpegNs = 0;
        } catch (IOException e) {
            Log.e(TAG, "rec start failed", e);
        }
    }

    private void stopRecording() {
        recorder.stop(); // logs the output dir and drop count
    }

    /** Stride-subsampled Y plane gray, rotated into display coords; outDims gets {w,h}. */
    private byte[] sampleGray(byte[] y, int w, int h, int rotation, int[] outDims) {
        int step = Math.max(1, w / 640);
        int sw = w / step;
        int sh = h / step;
        byte[] a = new byte[sw * sh];
        for (int j = 0; j < sh; j++) {
            int srow = j * step * w;
            int drow = j * sw;
            for (int i = 0; i < sw; i++) {
                a[drow + i] = y[srow + i * step];
            }
        }
        switch (((rotation % 360) + 360) % 360) {
            case 90:
                byte[] b90 = new byte[a.length];
                for (int j = 0; j < sw; j++) {
                    for (int i = 0; i < sh; i++) {
                        b90[j * sh + i] = a[(sh - 1 - i) * sw + j];
                    }
                }
                outDims[0] = sh;
                outDims[1] = sw;
                return b90;
            case 180:
                byte[] b180 = new byte[a.length];
                for (int j = 0; j < sh; j++) {
                    for (int i = 0; i < sw; i++) {
                        b180[j * sw + i] = a[(sh - 1 - j) * sw + (sw - 1 - i)];
                    }
                }
                outDims[0] = sw;
                outDims[1] = sh;
                return b180;
            case 270:
                byte[] b270 = new byte[a.length];
                for (int j = 0; j < sw; j++) {
                    for (int i = 0; i < sh; i++) {
                        b270[j * sh + i] = a[i * sw + (sw - 1 - j)];
                    }
                }
                outDims[0] = sh;
                outDims[1] = sw;
                return b270;
            default:
                outDims[0] = sw;
                outDims[1] = sh;
                return a;
        }
    }

    private String buildMeta() {
        int recStep = Math.max(1, prevW / 640);
        int rsw = prevW / recStep;
        int rsh = prevH / recStep;
        boolean swap = ((detRotation % 360) + 360) % 360 == 90
                || ((detRotation % 360) + 360) % 360 == 270;
        int rw = swap ? rsh : rsw;
        int rh = swap ? rsw : rsh;
        int detStep = Math.max(1, prevW / 320);
        int dsw = prevW / detStep;
        int dsh = prevH / detStep;
        int dw = swap ? dsh : dsw;
        int dh = swap ? dsw : dsh;
        StringBuilder sb = new StringBuilder(512);
        sb.append("preview=").append(prevW).append('x').append(prevH).append('\n');
        sb.append("detect=").append(dw).append('x').append(dh)
                .append(" (stride ").append(detStep).append(")\n");
        sb.append("recordGray=").append(rw).append('x').append(rh)
                .append(" (stride ").append(recStep)
                .append(" from Y plane, rotated detRotation into display coords)\n");
        sb.append("detRotation=").append(detRotation).append('\n');
        sb.append("cameraId=").append(useCamera2 ? "c2:" + c2Id : String.valueOf(cameraId)).append('\n');
        sb.append("camera2TsOffsetNs=").append(c2 != null ? c2.tsOffset : 0)
                .append(" (image.getTimestamp vs elapsedRealtimeNanos, 0 when same clock or legacy)\n");
        sb.append(String.format(Locale.US, "S=%.2f\n", scaleS));
        sb.append(String.format(Locale.US, "viewAngle=%.2f\n", viewAngleDeg));
        sb.append("fpsRange=").append(fpsRangeChosen == null ? "unset"
                : "[" + fpsRangeChosen[0] + "," + fpsRangeChosen[1] + "]").append('\n');
        sb.append("sceneMode=").append(sceneModeChosen == null ? "unset" : sceneModeChosen).append('\n');
        sb.append("appVersion=").append(Version.DESCRIBE).append('\n');
        sb.append("clock=SystemClock.elapsedRealtimeNanos (ns, monotonic; "
                + "gyro SensorEvent.timestamp uses the same clock)\n");
        sb.append("frames.bin=uint8 gray, ").append(rw).append('x').append(rh)
                .append(" per frame, concatenated, indexed by frames_idx.csv seq\n");
        sb.append("full_<seq>.jpg=NV21 preview compressed q85, <=1/s\n");
        return sb.toString();
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
        if (!tracker.aimValid()) {
            overlay.flash(OverlayView.FLASH_NOLOCK);
            Log.i(TAG, "fire: no lock, skipped");
            return;
        }
        final float[] st = tracker.snapshot();
        final float x = st[0];
        final float y = st[1];
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
