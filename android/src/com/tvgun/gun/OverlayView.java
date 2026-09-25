package com.tvgun.gun;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.os.SystemClock;
import android.view.View;

/** Crosshair + HUD overlay drawn above the camera preview. */
public class OverlayView extends View {
    public static final int FLASH_HIT = 1;
    public static final int FLASH_MISS = 2;
    public static final int FLASH_NOLOCK = 3;

    private static final long FLASH_MS = 150;
    private static final long CONNFAIL_MS = 2000;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();

    private int grade;          // Tracker grade: 0=DEAD 1=GYRO 2=EDGE 3=PARTIAL 4=FULL
    private boolean aimValid;
    private boolean predicted;
    private boolean permissionDenied;
    private float[] corners;
    private int detW = 320;
    private int detH = 180;
    private float crossX;
    private float crossY;
    private float fps;
    private int score;
    private String server = "";
    private int flashType;
    private long flashUntil;
    private long connFailUntil;
    private int recSec = -1; // >=0: recording, elapsed seconds
    private boolean unlockWarn; // vision lost >2s: screen out of view / occluded
    private String lensLabel;
    private long lensUntil;

    public OverlayView(Context context) {
        super(context);
    }

    public synchronized void setState(int grade, float[] corners, int detW, int detH,
                                      float crossX, float crossY, boolean aimValid,
                                      boolean predicted, float fps, int score, String server) {
        this.grade = grade;
        this.corners = corners;
        this.detW = detW;
        this.detH = detH;
        this.crossX = crossX;
        this.crossY = crossY;
        this.aimValid = aimValid;
        this.predicted = predicted;
        this.fps = fps;
        this.score = score;
        this.server = server;
        invalidate();
    }

    public synchronized void setScore(int score) {
        this.score = score;
        invalidate();
    }

    public synchronized void flash(int type) {
        flashType = type;
        flashUntil = SystemClock.elapsedRealtime() + FLASH_MS;
        invalidate();
    }

    public synchronized void setConnFail() {
        connFailUntil = SystemClock.elapsedRealtime() + CONNFAIL_MS;
        invalidate();
    }

    public synchronized void setPermissionDenied() {
        permissionDenied = true;
        invalidate();
    }

    public synchronized void setRecSec(int sec) {
        recSec = sec;
        invalidate();
    }

    public synchronized void setUnlockWarn(boolean warn) {
        unlockWarn = warn;
        invalidate();
    }

    /** Briefly shows the active lens name (shown ~2.5s after camera open/switch). */
    public synchronized void setLensLabel(String label) {
        lensLabel = label;
        lensUntil = SystemClock.elapsedRealtime() + 2500;
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        boolean av, pr, pd, uw;
        int gd;
        float[] cs;
        int dw, dh, sc, ft, rec;
        float cx, cy, f;
        String srv, lens;
        long fu, cfu, lu;
        synchronized (this) {
            gd = grade;
            av = aimValid;
            pr = predicted;
            pd = permissionDenied;
            cs = corners;
            dw = detW;
            dh = detH;
            cx = crossX;
            cy = crossY;
            f = fps;
            sc = score;
            srv = server;
            ft = flashType;
            fu = flashUntil;
            cfu = connFailUntil;
            rec = recSec;
            uw = unlockWarn;
            lens = lensLabel;
            lu = lensUntil;
        }

        long now = SystemClock.elapsedRealtime();
        if (now >= fu) ft = 0;
        boolean connFail = now < cfu;
        if (now < fu || connFail) postInvalidateDelayed(120);

        // Tracked quadrilateral, scaled from image coords to view coords.
        if (gd >= Tracker.GRADE_EDGE && cs != null && dw > 0 && dh > 0) {
            float sx = getWidth() / (float) dw;
            float sy = getHeight() / (float) dh;
            path.reset();
            path.moveTo(cs[0] * sx, cs[1] * sy);
            path.lineTo(cs[2] * sx, cs[3] * sy);
            path.lineTo(cs[4] * sx, cs[5] * sy);
            path.lineTo(cs[6] * sx, cs[7] * sy);
            path.close();
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(3f);
            paint.setColor(gd == Tracker.GRADE_FULL ? Color.GREEN : Color.YELLOW);
            canvas.drawPath(path, paint);
        }

        // Center crosshair: solid cross when vision-informed, hollow circle in GYRO.
        int color;
        if (ft == FLASH_HIT) color = Color.GREEN;
        else if (ft == FLASH_MISS) color = Color.RED;
        else if (ft == FLASH_NOLOCK) color = Color.YELLOW;
        else color = av ? Color.GREEN : Color.GRAY;

        int vx = getWidth() / 2;
        int vy = getHeight() / 2;
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(ft != 0 ? 8f : 4f);
        paint.setColor(color);
        if (!pr) {
            canvas.drawLine(vx - 40, vy, vx + 40, vy, paint);
            canvas.drawLine(vx, vy - 40, vx, vy + 40, paint);
        }
        canvas.drawCircle(vx, vy, 26, paint);

        // HUD, top-left.
        paint.setStyle(Paint.Style.FILL);
        paint.setTextSize(28f);
        paint.setShadowLayer(3f, 1f, 1f, Color.BLACK);
        paint.setColor(av ? Color.GREEN : Color.LTGRAY);
        canvas.drawText(Tracker.GRADE_NAMES[gd] + String.format("  %.1f fps", f), 20, 40, paint);
        paint.setColor(Color.WHITE);
        canvas.drawText("准星: " + (int) cx + ", " + (int) cy, 20, 76, paint);
        canvas.drawText("分数: " + sc, 20, 112, paint);
        canvas.drawText("服务器: " + srv, 20, 148, paint);
        // 版本角标（防版本错配：HUD 永远可见当前运行的构建版本）
        paint.setTextSize(22f);
        paint.setColor(Color.GRAY);
        canvas.drawText(Version.DESCRIBE, 20, getHeight() - 16, paint);
        paint.setTextSize(28f);
        if (connFail) {
            paint.setColor(Color.RED);
            canvas.drawText("连接失败", 20, 184, paint);
        }
        if (rec >= 0) {
            // REC indicator, top-right: red dot + elapsed time
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.RED);
            canvas.drawCircle(getWidth() - 150, 30, 12, paint);
            canvas.drawText(String.format("REC %d:%02d", rec / 60, rec % 60),
                    getWidth() - 125, 40, paint);
        }
        if (uw) {
            paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(44f);
            paint.setColor(Color.YELLOW);
            canvas.drawText("屏幕出画/被遮挡", getWidth() / 2f - 170, getHeight() * 0.75f, paint);
        }
        if (lens != null && now < lu) {
            paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(48f);
            paint.setColor(Color.CYAN);
            canvas.drawText(lens, getWidth() / 2f - 140, getHeight() * 0.25f, paint);
        }
        if (pd) {
            paint.setTextSize(40f);
            paint.setColor(Color.RED);
            canvas.drawText("需要摄像头权限，请在系统设置中授予后重启应用", 40, getHeight() / 2f, paint);
        }
        paint.setShadowLayer(0, 0, 0, 0);
    }
}
