package com.tvgun.gun;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CameraMetadata;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Log;
import android.util.Range;
import android.util.Size;
import android.util.SizeF;
import android.view.Surface;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Camera2 preview backend: logical+physical back-lens enumeration with FOV
 * computed from focal length and sensor physical size, dual-output session
 * (preview Surface + ImageReader YUV_420_888), 30fps-locked repeating request.
 * Frames are delivered as compact Y-plane byte arrays with timestamps rebased
 * onto SystemClock.elapsedRealtimeNanos (offset measured on the first frame).
 */
public final class Camera2Backend {
    private static final String TAG = "tvgun";

    public interface FrameSink {
        void onFrame(byte[] y, int w, int h, long tsNs);
    }

    public static final class LensInfo {
        public String id;
        public float fovH;              // degrees, 2*atan(sensorW/2/f)
        public int sensorOrientation;
        public boolean publicId;        // listed by getCameraIdList (vs hidden vendor id)
    }

    public interface ErrorListener {
        void onCameraError();
    }

    public volatile ErrorListener errorListener;

    public volatile boolean active;
    public volatile long tsOffset;      // elapsedRealtimeNanos - image.getTimestamp()
    public volatile float inputFrameRate; // measured onImageAvailable rate
    public int width;
    public int height;
    public int sensorOrientation = 90;
    public float fovDeg;
    public String fpsRangeDesc = "unset";
    public String sceneModeDesc = "unset";
    public String afModeDesc = "unset";

    private final CameraManager mgr;
    private CameraDevice device;
    private CameraCaptureSession session;
    private ImageReader reader;
    private HandlerThread thread;
    private Handler handler;
    private FrameSink sink;
    private volatile boolean tsLogged;

    public Camera2Backend(Context ctx) {
        mgr = (CameraManager) ctx.getSystemService(Context.CAMERA_SERVICE);
    }

    /** MIUI keeps aux lenses out of getCameraIdList(); these vendor ids exist in
     *  dumpsys (11 devices) and may still answer getCameraCharacteristics/openCamera. */
    private static final String[] VENDOR_ID_CANDIDATES =
            {"20", "21", "60", "61", "62", "63", "100", "101", "120"};

    /** Enumerate back lenses (logical + physical + hidden vendor ids) with FOV
     *  from focal length + sensor size. */
    public List<LensInfo> enumerateBackLenses() throws CameraAccessException {
        List<LensInfo> out = new ArrayList<>();
        String[] ids = mgr.getCameraIdList();
        Log.i(TAG, "camera2 getCameraIdList=" + Arrays.toString(ids));
        List<String> publicIds = Arrays.asList(ids);
        List<String> all = new ArrayList<>(publicIds);
        for (String vid : VENDOR_ID_CANDIDATES) {
            if (!all.contains(vid)) all.add(vid);
        }
        for (String id : all) {
            CameraCharacteristics ch;
            try {
                ch = mgr.getCameraCharacteristics(id);
            } catch (Exception e) {
                Log.i(TAG, "camera2 id=" + id + " characteristics failed: " + e.getMessage());
                continue;
            }
            Integer facing = ch.get(CameraCharacteristics.LENS_FACING);
            Log.i(TAG, "camera2 id=" + id + " facing="
                    + (facing == null ? "?" : facing == CameraCharacteristics.LENS_FACING_BACK
                            ? "back" : facing == CameraCharacteristics.LENS_FACING_FRONT ? "front" : "ext"));
            if (facing == null || facing != CameraCharacteristics.LENS_FACING_BACK) continue;
            addLens(out, id, ch, null, publicIds.contains(id));
            if (android.os.Build.VERSION.SDK_INT >= 28) {
                Set<String> phys = ch.getPhysicalCameraIds();
                for (String pid : phys) {
                    CameraCharacteristics pch = mgr.getCameraCharacteristics(pid);
                    addLens(out, pid, pch, id, publicIds.contains(id));
                }
            }
        }
        // (FOV dedup in addLens keeps only the first id per distinct field of view)
        return out;
    }

    private void addLens(List<LensInfo> out, String id, CameraCharacteristics ch,
                         String parent, boolean publicId) {
        float[] focals = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
        SizeF sensor = ch.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE);
        Integer so = ch.get(CameraCharacteristics.SENSOR_ORIENTATION);
        if (focals == null || focals.length == 0 || sensor == null
                || sensor.getWidth() <= 0 || focals[0] <= 0) {
            Log.i(TAG, "camera2 id=" + id + " no focal/sensor info, skipped");
            return;
        }
        float fov = (float) Math.toDegrees(2.0 * Math.atan(sensor.getWidth() / (2.0 * focals[0])));
        for (LensInfo li : out) {
            if (li.id.equals(id)) return; // duplicate id via another logical parent
            if (Math.abs(li.fovH - fov) < 2f) {
                Log.i(TAG, "camera2 id=" + id + " skipped (duplicate FOV of id=" + li.id + ")");
                return;
            }
        }
        LensInfo li = new LensInfo();
        li.id = id;
        li.fovH = fov;
        li.sensorOrientation = so != null ? so : 90;
        li.publicId = publicId;
        out.add(li);
        Log.i(TAG, String.format(Locale.US,
                "camera2 back id=%s f=%.2fmm sensor=%.2fx%.2fmm FOV_h=%.1f orientation=%d%s",
                id, focals[0], sensor.getWidth(), sensor.getHeight(), fov,
                li.sensorOrientation, parent != null ? " (physical of " + parent + ")" : ""));
    }

    /** YUV_420_888 output size closest to 1280x720 for this camera. */
    public Size chooseYuvSize(String id) throws CameraAccessException {
        CameraCharacteristics ch = mgr.getCameraCharacteristics(id);
        StreamConfigurationMap map = ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        Size[] sizes = map.getOutputSizes(ImageFormat.YUV_420_888);
        Size best = null;
        long bestDiff = Long.MAX_VALUE;
        for (Size s : sizes) {
            long diff = Math.abs((long) s.getWidth() * s.getHeight() - 1280L * 720L);
            if (diff < bestDiff) {
                bestDiff = diff;
                best = s;
            }
        }
        return best;
    }

    /**
     * Opens the camera, creates the dual-output session and starts the repeating
     * request. Blocks until the session is configured (or throws).
     */
    @SuppressLint("MissingPermission")
    public void open(String id, Surface previewSurface, FrameSink frameSink) throws Exception {
        close();
        CameraCharacteristics ch = mgr.getCameraCharacteristics(id);
        Integer so = ch.get(CameraCharacteristics.SENSOR_ORIENTATION);
        sensorOrientation = so != null ? so : 90;
        float[] focals = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
        SizeF sensor = ch.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE);
        fovDeg = (float) Math.toDegrees(2.0 * Math.atan(sensor.getWidth() / (2.0 * focals[0])));

        StreamConfigurationMap map = ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        Size[] sizes = map.getOutputSizes(ImageFormat.YUV_420_888);
        Size best = null;
        long bestDiff = Long.MAX_VALUE;
        for (Size s : sizes) {
            long diff = Math.abs((long) s.getWidth() * s.getHeight() - 1280L * 720L);
            if (diff < bestDiff) {
                bestDiff = diff;
                best = s;
            }
        }
        width = best.getWidth();
        height = best.getHeight();

        final Range<Integer>[] ranges =
                ch.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES);
        Range<Integer> chosen = null;
        for (Range<Integer> r : ranges) {
            if (r.getLower() == 30 && r.getUpper() == 30) {
                chosen = r;
                break;
            }
        }
        if (chosen == null) {
            for (Range<Integer> r : ranges) {
                if (r.getLower() <= 30 && r.getUpper() >= 30
                        && (chosen == null
                        || r.getUpper() - r.getLower() < chosen.getUpper() - chosen.getLower())) {
                    chosen = r;
                }
            }
        }
        fpsRangeDesc = chosen != null ? chosen.toString() + " of " + Arrays.toString(ranges) : "unset";
        final Range<Integer> fpsRange = chosen;

        int[] scenes = ch.get(CameraCharacteristics.CONTROL_AVAILABLE_SCENE_MODES);
        final boolean sports = scenes != null && contains(scenes, CameraMetadata.CONTROL_SCENE_MODE_SPORTS);
        sceneModeDesc = sports ? "sports" : "unset (" + Arrays.toString(scenes) + ")";

        int[] afs = ch.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES);
        final boolean contVideo = afs != null
                && contains(afs, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
        afModeDesc = contVideo ? "continuous-video" : "off " + Arrays.toString(afs);

        Log.i(TAG, "camera2 open id=" + id + " size=" + width + "x" + height
                + " fpsRange=" + fpsRangeDesc + " scene=" + sceneModeDesc + " af=" + afModeDesc
                + String.format(Locale.US, " FOV_h=%.1f", fovDeg));

        tsLogged = false;
        thread = new HandlerThread("c2cb");
        thread.start();
        handler = new Handler(thread.getLooper());
        sink = frameSink;
        reader = ImageReader.newInstance(width, height, ImageFormat.YUV_420_888, 3);
        reader.setOnImageAvailableListener(readListener, handler);
        previewSurfaceRef = previewSurface;

        final CountDownLatch openLatch = new CountDownLatch(1);
        final boolean[] openOk = {false};
        mgr.openCamera(id, new CameraDevice.StateCallback() {
            @Override
            public void onOpened(CameraDevice d) {
                device = d;
                openOk[0] = true;
                openLatch.countDown();
            }

            @Override
            public void onDisconnected(CameraDevice d) {
                Log.w(TAG, "camera2 disconnected");
                active = false;
                d.close();
                openLatch.countDown();
                ErrorListener l = errorListener;
                if (l != null) l.onCameraError();
            }

            @Override
            public void onError(CameraDevice d, int error) {
                Log.e(TAG, "camera2 device error=" + error);
                active = false;
                d.close();
                openLatch.countDown();
                ErrorListener l = errorListener;
                if (l != null) l.onCameraError();
            }
        }, handler);
        if (!openLatch.await(4, TimeUnit.SECONDS) || !openOk[0] || device == null) {
            throw new Exception("camera2 open failed: id=" + id);
        }

        final CountDownLatch sessLatch = new CountDownLatch(1);
        final boolean[] sessOk = {false};
        List<Surface> outputs = new ArrayList<>();
        outputs.add(previewSurface);
        outputs.add(reader.getSurface());
        device.createCaptureSession(outputs, new CameraCaptureSession.StateCallback() {
            @Override
            public void onConfigured(CameraCaptureSession s) {
                session = s;
                try {
                    CaptureRequest.Builder b = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                    b.addTarget(previewSurfaceRef);
                    b.addTarget(reader.getSurface());
                    if (fpsRange != null) {
                        b.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fpsRange);
                    }
                    if (sports) {
                        b.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_USE_SCENE_MODE);
                        b.set(CaptureRequest.CONTROL_SCENE_MODE, CameraMetadata.CONTROL_SCENE_MODE_SPORTS);
                    }
                    if (contVideo) {
                        b.set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
                    } else {
                        b.set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_OFF);
                        b.set(CaptureRequest.LENS_FOCUS_DISTANCE, 0f);
                    }
                    s.setRepeatingRequest(b.build(), null, handler);
                    sessOk[0] = true;
                } catch (CameraAccessException e) {
                    Log.e(TAG, "camera2 repeating request failed", e);
                }
                sessLatch.countDown();
            }

            @Override
            public void onConfigureFailed(CameraCaptureSession s) {
                Log.e(TAG, "camera2 session configure failed");
                sessLatch.countDown();
            }
        }, handler);
        if (!sessLatch.await(4, TimeUnit.SECONDS) || !sessOk[0]) {
            throw new Exception("camera2 session failed: id=" + id);
        }
        active = true;
        Log.i(TAG, "camera2 started: id=" + id);
    }

    // preview surface kept as a field so the session callback closure can reach it
    private Surface previewSurfaceRef;

    private static boolean contains(int[] a, int v) {
        for (int x : a) {
            if (x == v) return true;
        }
        return false;
    }

    // small frame-buffer pool: the mailbox holds at most 1 frame and the worker
    // at most 1, so 2 buffers suffice; avoids 27MB/s of GC churn at 30fps.
    private final Object poolLock = new Object();
    private byte[] poolA;
    private byte[] poolB;
    private int rateFrames;
    private long rateWindowStart;

    private byte[] borrowBuffer(int n) {
        synchronized (poolLock) {
            if (poolA != null && poolA.length == n) {
                byte[] b = poolA;
                poolA = null;
                return b;
            }
            if (poolB != null && poolB.length == n) {
                byte[] b = poolB;
                poolB = null;
                return b;
            }
        }
        return new byte[n];
    }

    /** Returns a frame buffer previously delivered via FrameSink.onFrame. */
    public void releaseBuffer(byte[] b) {
        synchronized (poolLock) {
            if (poolA == null) {
                poolA = b;
            } else {
                poolB = b;
            }
        }
    }

    private final ImageReader.OnImageAvailableListener readListener =
            new ImageReader.OnImageAvailableListener() {
                @Override
                public void onImageAvailable(ImageReader r) {
                    Image im = r.acquireLatestImage();
                    if (im == null) return;
                    try {
                        long nowMs = SystemClock.elapsedRealtime();
                        rateFrames++;
                        if (rateWindowStart == 0) rateWindowStart = nowMs;
                        if (nowMs - rateWindowStart >= 1000) {
                            inputFrameRate = rateFrames * 1000f / (nowMs - rateWindowStart);
                            Log.i(TAG, String.format(Locale.US, "camera2 input rate=%.1f", inputFrameRate));
                            rateFrames = 0;
                            rateWindowStart = nowMs;
                        }
                        Image.Plane y = im.getPlanes()[0];
                        if (y.getPixelStride() != 1) {
                            Log.w(TAG, "unexpected Y pixelStride=" + y.getPixelStride());
                            return;
                        }
                        int w = im.getWidth();
                        int h = im.getHeight();
                        int rs = y.getRowStride();
                        java.nio.ByteBuffer buf = y.getBuffer();
                        byte[] out = borrowBuffer(w * h);
                        if (rs == w) {
                            buf.get(out, 0, w * h);
                        } else {
                            for (int j = 0; j < h; j++) {
                                buf.position(j * rs);
                                buf.get(out, j * w, w);
                            }
                        }
                        long ts = im.getTimestamp();
                        if (!tsLogged) {
                            tsLogged = true;
                            long now = SystemClock.elapsedRealtimeNanos();
                            tsOffset = now - ts;
                            Log.i(TAG, "camera2 ts check: imageTs=" + ts + " elapsed=" + now
                                    + " offset=" + tsOffset + "ns");
                        }
                        FrameSink s = sink;
                        // camera2 image.getTimestamp() is the sensor exposure time on the
                        // same CLOCK_MONOTONIC base as elapsedRealtimeNanos on this device;
                        // use it directly (exposure time aligns better with gyro than arrival).
                        if (s != null) s.onFrame(out, w, h, ts);
                    } finally {
                        im.close();
                    }
                }
            };

    public void close() {
        active = false;
        try {
            if (session != null) session.close();
        } catch (Exception ignored) {
        }
        session = null;
        try {
            if (device != null) device.close();
        } catch (Exception ignored) {
        }
        device = null;
        try {
            if (reader != null) reader.close();
        } catch (Exception ignored) {
        }
        reader = null;
        if (thread != null) {
            thread.quitSafely();
            thread = null;
            handler = null;
        }
    }
}
