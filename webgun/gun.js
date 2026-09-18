'use strict';

// ---------- 纯函数（浏览器/node 共用，node 下可 require 自测） ----------

// 4 点排序为 [左上, 右上, 右下, 左下]
function orderCorners(pts) {
  let tl = pts[0], br = pts[0], tr = pts[0], bl = pts[0];
  for (const p of pts) {
    const s = p.x + p.y, d = p.x - p.y;
    if (s < tl.x + tl.y) tl = p;
    if (s > br.x + br.y) br = p;
    if (d > tr.x - tr.y) tr = p;
    if (d < bl.x - bl.y) bl = p;
  }
  return [tl, tr, br, bl];
}

// 4 点单应（h33=1），8x8 高斯消元；返回长度 8 的数组，退化返回 null
function solveHomography(src, dst) {
  const A = [], b = [], n = 8;
  for (let i = 0; i < 4; i++) {
    const x = src[i].x, y = src[i].y, X = dst[i].x, Y = dst[i].y;
    A.push([x, y, 1, 0, 0, 0, -X * x, -X * y]); b.push(X);
    A.push([0, 0, 0, x, y, 1, -Y * x, -Y * y]); b.push(Y);
  }
  for (let c = 0; c < n; c++) {
    let piv = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
    if (Math.abs(A[piv][c]) < 1e-12) return null;
    const ta = A[c]; A[c] = A[piv]; A[piv] = ta;
    const tb = b[c]; b[c] = b[piv]; b[piv] = tb;
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = A[r][c] / A[c][c];
      if (f === 0) continue;
      for (let k = c; k < n; k++) A[r][k] -= f * A[c][k];
      b[r] -= f * b[c];
    }
  }
  return b.map((v, i) => v / A[i][i]);
}

function applyHomography(h, x, y) {
  const den = h[6] * x + h[7] * y + 1;
  return {
    x: (h[0] * x + h[1] * y + h[2]) / den,
    y: (h[3] * x + h[4] * y + h[5]) / den,
  };
}

function quadArea(q) {
  let a = 0;
  for (let i = 0; i < 4; i++) {
    const p = q[i], r = q[(i + 1) % 4];
    a += p.x * r.y - r.x * p.y;
  }
  return Math.abs(a) / 2;
}

// 面积占比 >=2% 且任一边长 >=20px
function quadValid(q, w, h) {
  if (quadArea(q) < 0.02 * w * h) return false;
  for (let i = 0; i < 4; i++) {
    const p = q[i], r = q[(i + 1) % 4];
    if (Math.hypot(p.x - r.x, p.y - r.y) < 20) return false;
  }
  return true;
}

// 灰度掩模（>=thr 为亮）上提取四角点：x±y 极值 + 极值邻域质心细化
function extractCorners(mask, w, h, thr) {
  let maxS = -1e9, minS = 1e9, maxD = -1e9, minD = 1e9, count = 0;
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      if (mask[row + x] >= thr) {
        count++;
        const s = x + y, d = x - y;
        if (s > maxS) maxS = s;
        if (s < minS) minS = s;
        if (d > maxD) maxD = d;
        if (d < minD) minD = d;
      }
    }
  }
  if (count < 50) return null;
  const eps = 2, acc = { minS: [0, 0, 0], maxS: [0, 0, 0], minD: [0, 0, 0], maxD: [0, 0, 0] };
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      if (mask[row + x] < thr) continue;
      const s = x + y, d = x - y;
      if (s <= minS + eps) { acc.minS[0] += x; acc.minS[1] += y; acc.minS[2]++; }
      if (s >= maxS - eps) { acc.maxS[0] += x; acc.maxS[1] += y; acc.maxS[2]++; }
      if (d <= minD + eps) { acc.minD[0] += x; acc.minD[1] += y; acc.minD[2]++; }
      if (d >= maxD - eps) { acc.maxD[0] += x; acc.maxD[1] += y; acc.maxD[2]++; }
    }
  }
  const c = a => ({ x: a[0] / a[2], y: a[1] / a[2] });
  if (!acc.minS[2] || !acc.maxS[2] || !acc.minD[2] || !acc.maxD[2]) return null;
  return [c(acc.minS), c(acc.maxD), c(acc.maxS), c(acc.minD)]; // TL TR BR BL
}

// 自适应阈值：亮度 98 分位，下限 190
function adaptiveThreshold(hist, total) {
  let acc = 0;
  const target = total * 0.02;
  for (let v = 255; v >= 0; v--) {
    acc += hist[v];
    if (acc >= target) return Math.max(v, 190);
  }
  return 190;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { orderCorners, solveHomography, applyHomography, quadArea, quadValid, extractCorners, adaptiveThreshold };
}

// ---------- 浏览器端应用 ----------
if (typeof window !== 'undefined') (function () {
  const NORM = [{ x: 0, y: 0 }, { x: 1920, y: 0 }, { x: 1920, y: 1080 }, { x: 0, y: 1080 }];
  const ALPHA = 0.3;
  const DET_W = 320;
  const TEST = new URLSearchParams(location.search).get('test') === '1';

  const video = document.getElementById('cam');
  const testCanvas = document.getElementById('testsrc');
  const overlay = document.getElementById('overlay');
  const octx = overlay.getContext('2d');
  const hud = document.getElementById('hud');
  const errBox = document.getElementById('err');
  const detCanvas = document.createElement('canvas');
  const dctx = detCanvas.getContext('2d', { willReadFrequently: true });

  let srcW = 0, srcH = 0, detH = 0;
  let locked = false, smoothQ = null, aim = null, homog = null;
  let score = 0, frames = 0, fps = 0, lastFpsT = performance.now();
  let flashColor = null, flashUntil = 0, mouseSuppressed = false;
  let testAngle = 0, lastT = performance.now(), lastLogT = 0, testDev = null;

  function showErr(msg) {
    errBox.textContent = msg;
    errBox.style.display = 'block';
  }

  function fitRect() {
    const s = Math.min(innerWidth / srcW, innerHeight / srcH);
    const w = srcW * s, h = srcH * s;
    return { x: (innerWidth - w) / 2, y: (innerHeight - h) / 2, w, h };
  }

  function resize() {
    overlay.width = innerWidth;
    overlay.height = innerHeight;
  }
  addEventListener('resize', resize);
  resize();

  function renderTestFrame(dt) {
    testAngle += dt * 0.4;
    const c = testCanvas.getContext('2d');
    const w = testCanvas.width, h = testCanvas.height;
    c.fillStyle = '#0a0a0a';
    c.fillRect(0, 0, w, h);
    const qw = 400, qh = 240;
    const k = 0.18 * Math.sin(testAngle * 0.7);
    const wt = qw * (1 - k), wb = qw * (1 + k);
    const local = [
      { x: -wt / 2, y: -qh / 2 }, { x: wt / 2, y: -qh / 2 },
      { x: wb / 2, y: qh / 2 }, { x: -wb / 2, y: qh / 2 },
    ];
    const ca = Math.cos(testAngle), sa = Math.sin(testAngle);
    const pts = local.map(p => ({
      x: w / 2 + p.x * ca - p.y * sa,
      y: h / 2 + p.x * sa + p.y * ca,
    }));
    c.fillStyle = '#fff';
    c.beginPath();
    c.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < 4; i++) c.lineTo(pts[i].x, pts[i].y);
    c.closePath();
    c.fill();
  }

  function detect() {
    dctx.drawImage(TEST ? testCanvas : video, 0, 0, DET_W, detH);
    const img = dctx.getImageData(0, 0, DET_W, detH).data;
    const n = DET_W * detH;
    const gray = new Uint8Array(n);
    const hist = new Uint32Array(256);
    for (let i = 0; i < n; i++) {
      const g = (img[i * 4] * 2 + img[i * 4 + 1] * 5 + img[i * 4 + 2]) >> 3;
      gray[i] = g;
      hist[g]++;
    }
    const thr = adaptiveThreshold(hist, n);
    const q = extractCorners(gray, DET_W, detH, thr);
    if (q && quadValid(q, DET_W, detH)) {
      if (smoothQ) {
        for (let i = 0; i < 4; i++) {
          smoothQ[i].x += ALPHA * (q[i].x - smoothQ[i].x);
          smoothQ[i].y += ALPHA * (q[i].y - smoothQ[i].y);
        }
      } else {
        smoothQ = q.map(p => ({ x: p.x, y: p.y }));
      }
      const sx = srcW / DET_W, sy = srcH / detH;
      const vq = smoothQ.map(p => ({ x: p.x * sx, y: p.y * sy }));
      homog = solveHomography(vq, NORM);
      locked = !!homog;
    } else {
      locked = false;
      homog = null;
    }
    aim = locked ? applyHomography(homog, srcW / 2, srcH / 2) : null;
    if (TEST && aim) {
      testDev = Math.hypot(aim.x - 960, aim.y - 540);
      if (performance.now() - lastLogT > 1000) {
        lastLogT = performance.now();
        console.log('[test] 准星规范坐标=(' + aim.x.toFixed(1) + ',' + aim.y.toFixed(1) + ') 与渲染中心(960,540)偏差=' + testDev.toFixed(2) + 'px');
      }
    }
  }

  function draw() {
    octx.clearRect(0, 0, overlay.width, overlay.height);
    if (!srcW) return;
    const r = fitRect();
    const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
    if (smoothQ && locked) {
      const sx = r.w / DET_W, sy = r.h / detH;
      octx.strokeStyle = 'rgba(0,255,0,0.5)';
      octx.lineWidth = 2;
      octx.beginPath();
      smoothQ.forEach((p, i) => {
        const X = r.x + p.x * sx, Y = r.y + p.y * sy;
        i ? octx.lineTo(X, Y) : octx.moveTo(X, Y);
      });
      octx.closePath();
      octx.stroke();
    }
    const inRange = aim && aim.x >= 0 && aim.x <= 1920 && aim.y >= 0 && aim.y <= 1080;
    let color = locked && inRange ? '#0f0' : '#888';
    if (performance.now() < flashUntil) color = flashColor;
    octx.strokeStyle = color;
    octx.lineWidth = 2;
    octx.beginPath();
    octx.moveTo(cx - 18, cy); octx.lineTo(cx + 18, cy);
    octx.moveTo(cx, cy - 18); octx.lineTo(cx, cy + 18);
    octx.stroke();
    octx.beginPath();
    octx.arc(cx, cy, 8, 0, Math.PI * 2);
    octx.stroke();
    const pos = aim ? Math.round(aim.x) + ',' + Math.round(aim.y) : '--,--';
    hud.style.color = locked ? '#0f0' : '#f44';
    hud.textContent =
      (locked ? 'LOCK' : 'NO LOCK') +
      '\nfps: ' + fps +
      '\npos: ' + pos +
      '\nscore: ' + score +
      (TEST ? '\ntest偏差: ' + (testDev == null ? '--' : testDev.toFixed(2) + 'px') : '');
  }

  function loop(now) {
    const dt = Math.min((now - lastT) / 1000, 0.1);
    lastT = now;
    if (TEST) {
      renderTestFrame(dt);
      srcW = testCanvas.width; srcH = testCanvas.height;
    } else if (video.readyState >= 2 && video.videoWidth) {
      srcW = video.videoWidth; srcH = video.videoHeight;
    } else {
      srcW = 0;
    }
    if (srcW) {
      detH = Math.round(DET_W * srcH / srcW);
      if (detCanvas.width !== DET_W || detCanvas.height !== detH) {
        detCanvas.width = DET_W;
        detCanvas.height = detH;
      }
      detect();
    }
    draw();
    frames++;
    if (now - lastFpsT >= 500) {
      fps = Math.round(frames * 1000 / (now - lastFpsT));
      frames = 0;
      lastFpsT = now;
    }
    requestAnimationFrame(loop);
  }

  function flash(color) {
    flashColor = color;
    flashUntil = performance.now() + 150;
  }

  function fire() {
    if (!locked || !aim) { flash('#ff0'); return; }
    fetch('/shot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x: aim.x, y: aim.y }),
    }).then(r => r.json()).then(res => {
      score = res.score;
      if (res.hit) {
        if (navigator.vibrate) navigator.vibrate(50);
        flash('#0f0');
      } else {
        flash('#f00');
      }
    }).catch(() => flash('#f00'));
  }

  addEventListener('touchstart', e => {
    mouseSuppressed = true;
    if (e.touches.length > 1) return;
    e.preventDefault();
    fire();
  }, { passive: false });
  addEventListener('mousedown', e => {
    if (mouseSuppressed) return;
    fire();
  });

  if (TEST) {
    video.style.display = 'none';
    testCanvas.style.display = 'block';
  } else {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showErr('当前环境不支持摄像头调用。\n请确认通过 http://localhost:8000 访问（或 HTTPS），并使用支持 getUserMedia 的浏览器。');
    } else {
      navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      }).then(stream => {
        video.srcObject = stream;
      }).catch(err => {
        showErr('摄像头启动失败：' + err.message + '\n请检查摄像头权限，并确认通过 http://localhost:8000（或 HTTPS）访问。');
      });
    }
  }

  fetch('/state').then(r => r.json()).then(s => { score = s.score; }).catch(() => {});
  requestAnimationFrame(loop);
})();
