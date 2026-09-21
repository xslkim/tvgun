package com.tvgun.gun;

import android.graphics.Bitmap;
import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.YuvImage;
import android.util.Log;

import java.io.BufferedOutputStream;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;

/**
 * Recording writer on a dedicated IO thread. Producer threads (detect worker,
 * gyro callback) enqueue write tasks and never block; when the queue is full
 * the task is dropped and counted. All timestamps are SystemClock.elapsedRealtimeNanos
 * (the gyro SensorEvent.timestamp shares this monotonic clock).
 *
 * Output layout in the session directory:
 *   meta.txt        session parameters and clock-basis note
 *   frames_idx.csv  seq,tsNs per stored frame
 *   frames.bin      uint8 grayscale frames (display-rotated), concatenated
 *   gyro.csv        tsNs,wx,wy,wz raw gyro samples
 *   detect.csv      per detection frame: lock/cross/corners/fused state
 *   full_<seq>.jpg  full-resolution NV21 JPEG, at most 1/s (written by caller pacing)
 */
public final class Recorder {
    private static final String TAG = "tvgun";
    private static final int QUEUE_CAP = 512;
    private static final Runnable PILL = new Runnable() {
        @Override
        public void run() {
        }
    };

    private final ArrayBlockingQueue<Runnable> queue = new ArrayBlockingQueue<>(QUEUE_CAP);
    private Thread ioThread;
    private File dir;
    private BufferedOutputStream framesBin;
    private Writer framesIdx;
    private Writer gyroCsv;
    private Writer detectCsv;
    private volatile boolean recording;
    private volatile long startNs;
    private int dropped;

    public boolean isRecording() {
        return recording;
    }

    public long getStartNs() {
        return startNs;
    }

    public synchronized int getDropped() {
        return dropped;
    }

    public synchronized File getDir() {
        return dir;
    }

    public synchronized void start(File d, String meta, long nowNs) throws IOException {
        if (recording) return;
        if (!d.mkdirs() && !d.isDirectory()) {
            throw new IOException("mkdir failed: " + d);
        }
        File metaFile = new File(d, "meta.txt");
        FileOutputStream mos = new FileOutputStream(metaFile);
        mos.write(meta.getBytes(StandardCharsets.UTF_8));
        mos.close();
        framesBin = new BufferedOutputStream(new FileOutputStream(new File(d, "frames.bin")), 1 << 20);
        framesIdx = writer(d, "frames_idx.csv");
        framesIdx.write("seq,tsNs\n");
        gyroCsv = writer(d, "gyro.csv");
        gyroCsv.write("tsNs,wx,wy,wz\n");
        detectCsv = writer(d, "detect.csv");
        detectCsv.write("tsNs,locked,crossValid,failStage,thr,lowThr,blobFrac,"
                + "c0x,c0y,c1x,c1y,c2x,c2y,c3x,c3y,detCrossX,detCrossY,fusedX,fusedY,predicted\n");
        dir = d;
        dropped = 0;
        startNs = nowNs;
        recording = true;
        ioThread = new Thread(new Runnable() {
            @Override
            public void run() {
                ioLoop();
            }
        }, "rec-io");
        ioThread.start();
        Log.i(TAG, "rec started: " + d.getAbsolutePath());
    }

    private static Writer writer(File d, String name) throws IOException {
        return new BufferedWriter(new OutputStreamWriter(
                new FileOutputStream(new File(d, name)), StandardCharsets.UTF_8));
    }

    /** Stops accepting tasks, drains the queue, closes files. Safe to call from any thread. */
    public synchronized void stop() {
        if (!recording) return;
        recording = false;
        try {
            queue.put(PILL); // block briefly rather than lose the shutdown marker
        } catch (InterruptedException ignored) {
        }
        try {
            ioThread.join(3000);
        } catch (InterruptedException ignored) {
        }
        Log.i(TAG, "rec stopped: " + (dir != null ? dir.getAbsolutePath() : "?")
                + " dropped=" + dropped);
    }

    private void ioLoop() {
        try {
            while (true) {
                Runnable r;
                try {
                    r = queue.take();
                } catch (InterruptedException e) {
                    break;
                }
                if (r == PILL) break;
                try {
                    r.run();
                } catch (Throwable t) {
                    Log.e(TAG, "rec write error", t);
                }
            }
        } finally {
            closeQuietly();
        }
    }

    private void closeQuietly() {
        try {
            if (framesIdx != null) framesIdx.close();
            if (framesBin != null) framesBin.close();
            if (gyroCsv != null) gyroCsv.close();
            if (detectCsv != null) detectCsv.close();
        } catch (IOException e) {
            Log.e(TAG, "rec close error", e);
        }
        framesIdx = null;
        framesBin = null;
        gyroCsv = null;
        detectCsv = null;
    }

    private void offer(Runnable r) {
        if (!recording) return;
        if (!queue.offer(r)) {
            synchronized (this) {
                dropped++;
            }
        }
    }

    /** One grayscale frame (already display-rotated), appended to frames.bin + index line. */
    public void recordFrame(final int seq, final long tsNs, final byte[] gray) {
        if (!recording) return;
        offer(new Runnable() {
            @Override
            public void run() {
                try {
                    framesIdx.write(seq + "," + tsNs + "\n");
                    framesBin.write(gray);
                } catch (IOException e) {
                    Log.e(TAG, "frame write failed", e);
                }
            }
        });
    }

    public void recordGyro(final long tsNs, final float wx, final float wy, final float wz) {
        if (!recording) return;
        offer(new Runnable() {
            @Override
            public void run() {
                try {
                    gyroCsv.write(String.format(Locale.US, "%d,%.6f,%.6f,%.6f\n", tsNs, wx, wy, wz));
                } catch (IOException e) {
                    Log.e(TAG, "gyro write failed", e);
                }
            }
        });
    }

    public void recordDetect(final long tsNs, final boolean locked, final boolean crossValid,
                             final int failStage, final int thr, final int lowThr,
                             final float blobFrac, final float[] corners,
                             final float detCrossX, final float detCrossY,
                             final float fusedX, final float fusedY, final boolean predicted) {
        if (!recording) return;
        final float[] cs = corners != null ? corners.clone() : null;
        offer(new Runnable() {
            @Override
            public void run() {
                try {
                    StringBuilder sb = new StringBuilder(160);
                    sb.append(tsNs).append(',').append(locked ? 1 : 0).append(',')
                            .append(crossValid ? 1 : 0).append(',').append(failStage).append(',')
                            .append(thr).append(',').append(lowThr).append(',')
                            .append(String.format(Locale.US, "%.5f", blobFrac));
                    for (int i = 0; i < 8; i++) {
                        sb.append(',');
                        if (cs != null) sb.append(String.format(Locale.US, "%.2f", cs[i]));
                    }
                    sb.append(String.format(Locale.US, ",%.2f,%.2f,%.2f,%.2f,%d\n",
                            detCrossX, detCrossY, fusedX, fusedY, predicted ? 1 : 0));
                    detectCsv.write(sb.toString());
                } catch (IOException e) {
                    Log.e(TAG, "detect write failed", e);
                }
            }
        });
    }

    /** Full-resolution NV21 frame compressed to JPEG on the IO thread. nv21 must be a private copy. */
    public void recordJpeg(final int seq, final byte[] nv21, final int w, final int h) {
        if (!recording) return;
        offer(new Runnable() {
            @Override
            public void run() {
                try {
                    YuvImage yuv = new YuvImage(nv21, ImageFormat.NV21, w, h, null);
                    File f = new File(dir, String.format(Locale.US, "full_%06d.jpg", seq));
                    BufferedOutputStream os = new BufferedOutputStream(new FileOutputStream(f));
                    yuv.compressToJpeg(new Rect(0, 0, w, h), 85, os);
                    os.close();
                } catch (Throwable t) {
                    Log.e(TAG, "jpeg write failed", t);
                }
            }
        });
    }

    /**
     * Grayscale JPEG from a compact Y plane (camera2 path has no NV21 chroma to
     * spare). yPlane must be a private copy; compressed on the IO thread.
     */
    public void recordGrayJpeg(final int seq, final byte[] yPlane, final int w, final int h) {
        if (!recording) return;
        offer(new Runnable() {
            @Override
            public void run() {
                try {
                    int n = w * h;
                    int[] px = new int[n];
                    for (int i = 0; i < n; i++) {
                        int v = yPlane[i] & 0xff;
                        px[i] = 0xFF000000 | (v << 16) | (v << 8) | v;
                    }
                    Bitmap bmp = Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888);
                    File f = new File(dir, String.format(Locale.US, "full_%06d.jpg", seq));
                    BufferedOutputStream os = new BufferedOutputStream(new FileOutputStream(f));
                    bmp.compress(Bitmap.CompressFormat.JPEG, 85, os);
                    os.close();
                } catch (Throwable t) {
                    Log.e(TAG, "gray jpeg write failed", t);
                }
            }
        });
    }
}
