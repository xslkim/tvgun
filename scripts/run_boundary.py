#!/usr/bin/env python3
"""边界条件专项测试套件（SPEC2.md §5）。

7 个专项套件，固定内容集（默认 facade/terrain/clouds/game_scene 4 种代表性内容）×
专项变量扫描，每套件输出分组表格（content × 扫描单元格），汇总写 out/boundary/report.md，
各套件明细 CSV 存 out/boundary/<suite>.csv。

套件:
  1 edge       屏幕边缘: 中心距边缘 [8,16,32,64]px（视场部分出屏，可用性边界）
  2 zoom       放大倍率: fov {96,128,192,256} × cam_res {512,768,1024}
  3 distort    镜头畸变: k1 {0,-0.05,-0.1,-0.15} × {已标定,未标定}
  4 lowlight   低光照:   exposure_gain {0.3,0.5,0.8} × shot_peak {20,50,100}
  5 motion     运动:     motion_blur_px {0,2,4,8} × rs_skew_px {0,5,10,20}
  6 dynamic    动态场景: generate_sequence 连拍 3 帧 × {有IMU,无IMU}
  7 imu_ablate IMU 消融: hard/extreme/motion 三档 × {无先验,IMU先验}

用法: python scripts/run_boundary.py [--cases 4] [--contents facade,terrain,clouds,game_scene]
      [--suites 1,2,3,4,5,6,7] [--out out/boundary]
"""
from __future__ import annotations

import argparse
import dataclasses
import inspect
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 保证能 import sim 包

from sim import channel, data, decode, embed, metrics
from sim.config import FOV, SCREEN_H, SCREEN_W, SEED

# ---------------------------------------------------------------- 扫描网格（SPEC2 §5）
EDGE_DISTS = [8, 16, 32, 64]
ZOOM_FOVS = [96, 128, 192, 256]
ZOOM_CAM_RES = [512, 768, 1024]
DISTORT_K1 = [0.0, -0.05, -0.10, -0.15]
LOWLIGHT_GAINS = [0.3, 0.5, 0.8]
LOWLIGHT_PEAKS = [20, 50, 100]
MOTION_BLURS = [0, 2, 4, 8]
MOTION_SKEWS = [0, 5, 10, 20]
ABLATE_LEVELS = ["hard", "extreme", "motion"]

DEFAULT_CONTENTS = ["facade", "terrain", "clouds", "game_scene"]
FPS = 30.0  # 连拍帧率（与 IMU 轨迹/序列帧一致）

_DECODE_PARAMS: set | None = None


def _decode_supports(name: str) -> bool:
    """探测 decode.decode 是否支持可选参数（lens / imu_prior）。"""
    global _DECODE_PARAMS
    if _DECODE_PARAMS is None:
        _DECODE_PARAMS = set(inspect.signature(decode.decode).parameters)
    return name in _DECODE_PARAMS


def _load_imu():
    try:
        from sim import imu
        return imu
    except ImportError:
        return None


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TVGun 边界条件专项套件（SPEC2.md §5）")
    p.add_argument("--contents", default=",".join(DEFAULT_CONTENTS), help="逗号分隔内容集（≥4 种）")
    p.add_argument("--cases", type=int, default=4, help="每 内容×扫描单元格 的用例数")
    p.add_argument("--suites", default="1,2,3,4,5,6,7", help="逗号分隔的套件编号子集")
    p.add_argument("--strength", type=float, default=2.5, help="嵌入强度")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="out/boundary", help="输出目录")
    return p.parse_args(argv)


# ---------------------------------------------------------------- 公共执行件

def _capture_decode(wm_seq, state, xy, cfg, n_frames=1, imu_prior=None, lens=None):
    """连拍 n_frames 并 decode，返回 (err, ok, conf, time_s, exc)。

    wm_seq 为已嵌入帧列表（动态场景逐帧嵌入）；xy 为真值（首帧基准）。
    capture/decode 任一环节异常都记为失败行（exc 非 None），不中断套件。
    """
    kwargs = {"fov": cfg.fov}
    if imu_prior is not None and _decode_supports("imu_prior"):
        kwargs["imu_prior"] = imu_prior
    if lens is not None and _decode_supports("lens"):
        kwargs["lens"] = lens
    t0 = time.perf_counter()
    res, exc = None, None
    try:
        frames = [channel.capture(wm_seq[k % len(wm_seq)], (float(xy[0]), float(xy[1])), cfg)
                  for k in range(n_frames)]
        res = decode.decode(frames if n_frames > 1 else frames[0], state, **kwargs)
    except Exception:
        exc = traceback.format_exc(limit=3)
    dt = time.perf_counter() - t0
    if res is None:
        return float("nan"), False, 0.0, dt, exc
    err = metrics.coord_error(xy, (float(res.x), float(res.y)))
    return err, bool(res.ok), float(res.confidence), dt, exc


def _base_cfg(rng, level="medium") -> channel.ChannelConfig:
    cfg = channel.sample_config(rng, level)
    cfg.rng = rng
    return cfg


def _positions(rng, n, fov=FOV):
    """合法中心点采样：margin 保证视场完全在屏内。"""
    return data.sample_positions(rng, n, margin=fov // 2 + 16)


def _edge_positions(rng, n, dist):
    """距某条屏幕边缘 dist px 的中心点（视场可部分出屏）。"""
    side = rng.integers(0, 4, n)          # 0左 1右 2上 3下
    u = rng.uniform(FOV, SCREEN_W - FOV, n)   # 水平沿边坐标（上/下边缘用）
    v = rng.uniform(FOV, SCREEN_H - FOV, n)   # 垂直沿边坐标（左/右边缘用）
    pts = np.empty((n, 2))
    for i, s in enumerate(side):
        if s == 0:
            pts[i] = (float(dist), v[i])
        elif s == 1:
            pts[i] = (float(SCREEN_W - dist), v[i])
        elif s == 2:
            pts[i] = (u[i], float(dist))
        else:
            pts[i] = (u[i], float(SCREEN_H - dist))
    return pts


def _imu_trajectory(imu_mod, rng, level, n_frames):
    """构造 (motion, stream, states, prior)：轨迹 center 为真值，roll/tilt 驱动几何。"""
    mseed = int(rng.integers(0, 2 ** 31))
    speed = "fast" if level == "motion" else "slow"
    motion = imu_mod.HandMotion(mseed, duration_s=max(2.0, n_frames / FPS + 0.5), speed=speed)
    stream = imu_mod.simulate_imu(motion, rate_hz=200, seed=mseed + 1)
    states = [motion.sample(k / FPS) for k in range(n_frames)]
    prior = stream.prior_at((n_frames - 1) / FPS, fps=FPS, n_frames=n_frames)
    return motion, stream, states, prior


def _row(content, cell, err, ok, conf, dt, **flags):
    row = dict(content=content, level=cell, error=err, ok=ok, confidence=conf, time_s=dt)
    row.update(flags)
    return row


# ---------------------------------------------------------------- 套件 1~7
# 每个套件函数接收 ctx（contents/args/imu_mod），返回 (标题, 说明, DataFrame|None, 备注|None)。

def suite_edge(ctx):
    rows = []
    for d in EDGE_DISTS:
        for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
            rng = np.random.default_rng((ctx["seed"], 1, d, ci))
            pts = _edge_positions(rng, ctx["cases"], d)
            for pi in range(ctx["cases"]):
                cfg = _base_cfg(np.random.default_rng((ctx["seed"], 1, d, ci, pi)))
                err, ok, conf, dt, exc = _capture_decode(
                    wm_seq, state, pts[pi], cfg)
                rows.append(_row(content, f"edge_{d}px", err, ok, conf, dt))
                if exc:
                    print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    return ("屏幕边缘距离扫描", f"中心距边缘 {EDGE_DISTS}px（BORDER_REPLICATE 区域无信号；"
            f"解码相关需 fov/2+MARGIN={FOV // 2 + 16}px 余量，此为理论可用性下限）",
            pd.DataFrame(rows), None)


def suite_zoom(ctx):
    rows = []
    for fov in ZOOM_FOVS:
        for cam_res in ZOOM_CAM_RES:
            cell = f"fov{fov}_cam{cam_res}"
            for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
                rng = np.random.default_rng((ctx["seed"], 2, fov, cam_res, ci))
                pts = _positions(rng, ctx["cases"], fov)
                for pi in range(ctx["cases"]):
                    cfg = _base_cfg(np.random.default_rng((ctx["seed"], 2, fov, cam_res, ci, pi)))
                    cfg.fov, cfg.cam_res = fov, cam_res
                    err, ok, conf, dt, exc = _capture_decode(wm_seq, state, pts[pi], cfg)
                    rows.append(_row(content, cell, err, ok, conf, dt))
                    if exc:
                        print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    return ("放大倍率网格", f"fov {ZOOM_FOVS} × cam_res {ZOOM_CAM_RES}",
            pd.DataFrame(rows), None)


def suite_distort(ctx):
    rows = []
    calibrated_supported = _decode_supports("lens")
    for k1 in DISTORT_K1:
        for calib in (True, False):
            cell = f"k1={k1:g}_{'标定' if calib else '未标定'}"
            for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
                rng = np.random.default_rng((ctx["seed"], 3, ci))
                pts = _positions(rng, ctx["cases"])
                for pi in range(ctx["cases"]):
                    cfg = _base_cfg(np.random.default_rng((ctx["seed"], 3, ci, pi)))
                    cfg.lens_k1 = k1
                    # 已标定：把畸变参数传给 decode 去畸变；未标定：k1≠0 但不传
                    lens = (k1, 0.0) if calib else None
                    err, ok, conf, dt, exc = _capture_decode(
                        wm_seq, state, pts[pi], cfg, lens=lens)
                    rows.append(_row(content, cell, err, ok, conf, dt))
                    if exc:
                        print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    note = None if calibrated_supported else \
        "decode 尚不支持 lens 参数，『已标定』退化为不去畸变（结果同未标定）"
    return ("镜头畸变 × 标定", f"k1 {DISTORT_K1} × {{已标定,未标定}}", pd.DataFrame(rows), note)


def suite_lowlight(ctx):
    rows = []
    for gain in LOWLIGHT_GAINS:
        for peak in LOWLIGHT_PEAKS:
            cell = f"gain{gain}_peak{peak}"
            for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
                rng = np.random.default_rng((ctx["seed"], 4, ci))
                pts = _positions(rng, ctx["cases"])
                for pi in range(ctx["cases"]):
                    cfg = _base_cfg(np.random.default_rng((ctx["seed"], 4, ci, pi)))
                    cfg.shot_noise, cfg.shot_peak, cfg.exposure_gain = True, float(peak), gain
                    err, ok, conf, dt, exc = _capture_decode(wm_seq, state, pts[pi], cfg)
                    rows.append(_row(content, cell, err, ok, conf, dt))
                    if exc:
                        print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    return ("低光照", f"exposure_gain {LOWLIGHT_GAINS} × shot_peak {LOWLIGHT_PEAKS}"
            "（泊松散粒噪声）", pd.DataFrame(rows), None)


def suite_motion(ctx):
    rows = []
    for blur in MOTION_BLURS:
        for skew in MOTION_SKEWS:
            cell = f"blur{blur}_skew{skew}"
            for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
                rng = np.random.default_rng((ctx["seed"], 5, ci))
                pts = _positions(rng, ctx["cases"])
                for pi in range(ctx["cases"]):
                    cfg = _base_cfg(np.random.default_rng((ctx["seed"], 5, ci, pi)))
                    cfg.motion_blur_px, cfg.rs_skew_px = float(blur), float(skew)
                    err, ok, conf, dt, exc = _capture_decode(wm_seq, state, pts[pi], cfg)
                    rows.append(_row(content, cell, err, ok, conf, dt))
                    if exc:
                        print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    return ("运动模糊 × 卷帘快门", f"motion_blur_px {MOTION_BLURS} × rs_skew_px {MOTION_SKEWS}",
            pd.DataFrame(rows), None)


def suite_dynamic(ctx):
    imu_mod = ctx["imu_mod"]
    if not hasattr(data, "generate_sequence"):
        return ("动态场景 × IMU", "generate_sequence 连拍 3 帧 × {有IMU,无IMU}", None,
                "data.generate_sequence 未就绪，跳过")
    if imu_mod is None or not _decode_supports("imu_prior"):
        return ("动态场景 × IMU", "generate_sequence 连拍 3 帧 × {有IMU,无IMU}", None,
                "sim/imu.py 或 decode(imu_prior) 未就绪，跳过")
    seq_kinds = set(getattr(data, "SEQ_KINDS", ("game_scene", "terrain", "clouds")))
    rows = []
    for ci, (content, _, _) in enumerate(ctx["contents"]):
        if content not in seq_kinds:
            continue  # 仅时序化内容参与动态场景套件
        seq = data.generate_sequence(content, seed=ctx["seed"] + 3000 + ci, n_frames=3)
        wm_seq, state = [], None
        for fr in seq:
            wm, state = embed.embed_signal(fr, strength=ctx["strength"], seed=ctx["seed"])
            wm_seq.append(wm)
        for use_imu in (False, True):
            rng = np.random.default_rng((ctx["seed"], 6, ci, int(use_imu)))
            pts = _positions(rng, ctx["cases"])
            for pi in range(ctx["cases"]):
                crng = np.random.default_rng((ctx["seed"], 6, ci, int(use_imu), pi))
                if use_imu:
                    _, _, states, prior = _imu_trajectory(imu_mod, crng, "medium", 3)
                    # 逐帧按轨迹中心 + roll/tilt 几何拍摄
                    frames = []
                    base = _base_cfg(crng)
                    for k, ms in enumerate(states):
                        cfg_k = dataclasses.replace(
                            base, rotation_deg=float(ms.roll_deg),
                            perspective_jitter=0.5 * (abs(float(ms.tilt_pitch_deg))
                                                      + abs(float(ms.tilt_yaw_deg))))
                        frames.append(channel.capture(
                            wm_seq[k], (float(ms.center_x), float(ms.center_y)), cfg_k))
                    truth = (float(states[0].center_x), float(states[0].center_y))
                    t0 = time.perf_counter()
                    res, exc = None, None
                    try:
                        res = decode.decode(frames, state, fov=base.fov, imu_prior=prior)
                    except Exception:
                        exc = traceback.format_exc(limit=3)
                    dt = time.perf_counter() - t0
                    if res is None:
                        err, ok, conf = float("nan"), False, 0.0
                    else:
                        err = metrics.coord_error(truth, (float(res.x), float(res.y)))
                        ok, conf = bool(res.ok), float(res.confidence)
                else:
                    cfg = _base_cfg(crng)
                    truth = tuple(float(v) for v in pts[pi])
                    err, ok, conf, dt, exc = _capture_decode(
                        wm_seq, state, truth, cfg, n_frames=3)
                rows.append(_row(content, "dynamic3", err, ok, conf, dt,
                                 dynamic=True, imu=use_imu))
                if exc:
                    print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    note = None if any(r["content"] in seq_kinds for r in rows) else "内容集无时序化内容"
    return ("动态场景 × IMU", "generate_sequence 连拍 3 帧（内容位移 1~6px/帧）× {有IMU,无IMU}",
            pd.DataFrame(rows), note)


def suite_imu_ablate(ctx):
    imu_mod = ctx["imu_mod"]
    if imu_mod is None or not _decode_supports("imu_prior"):
        return ("IMU 消融", "hard/extreme/motion × {无先验,IMU先验}", None,
                "sim/imu.py 或 decode(imu_prior) 未就绪，跳过")
    rows = []
    for li, level in enumerate(ABLATE_LEVELS):
        for use_imu in (False, True):
            for ci, (content, wm_seq, state) in enumerate(ctx["contents"]):
                rng = np.random.default_rng((ctx["seed"], 7, li, int(use_imu), ci))
                for pi in range(ctx["cases"]):
                    crng = np.random.default_rng((ctx["seed"], 7, li, int(use_imu), ci, pi))
                    _, _, states, prior = _imu_trajectory(imu_mod, crng, level, 1)
                    ms = states[0]
                    cfg = _base_cfg(crng, level)
                    # 轨迹 roll/tilt 覆盖采样几何，两种臂共享同一轨迹以保证配对对比
                    cfg.rotation_deg = float(ms.roll_deg)
                    cfg.perspective_jitter = max(
                        float(cfg.perspective_jitter),
                        0.5 * (abs(float(ms.tilt_pitch_deg)) + abs(float(ms.tilt_yaw_deg))))
                    truth = (float(ms.center_x), float(ms.center_y))
                    err, ok, conf, dt, exc = _capture_decode(
                        wm_seq, state, truth, cfg,
                        imu_prior=prior if use_imu else None)
                    rows.append(_row(content, level, err, ok, conf, dt, imu=use_imu))
                    if exc:
                        print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
    return ("IMU 消融对比", "hard/extreme/motion × {无先验,IMU先验}（命中率与耗时对比）",
            pd.DataFrame(rows), None)


SUITES = {
    1: suite_edge, 2: suite_zoom, 3: suite_distort, 4: suite_lowlight,
    5: suite_motion, 6: suite_dynamic, 7: suite_imu_ablate,
}
SUITE_NAMES = {1: "edge", 2: "zoom", 3: "distort", 4: "lowlight",
               5: "motion", 6: "dynamic", 7: "imu_ablate"}


def main(argv=None) -> int:
    args = parse_args(argv)
    kinds = [s.strip() for s in args.contents.split(",") if s.strip()]
    suite_ids = [int(s) for s in args.suites.split(",") if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 内容集：逐内容生成静态帧并嵌入（套件 6 内部另行生成序列帧）
    contents = []
    for ci, kind in enumerate(kinds):
        frame = data.generate_frame(kind, seed=args.seed + 4000 + ci)
        wm, state = embed.embed_signal(frame, strength=args.strength, seed=args.seed)
        contents.append((kind, [wm], state))

    ctx = dict(contents=contents, cases=max(1, args.cases), seed=args.seed,
               strength=args.strength, imu_mod=_load_imu())

    t_start = time.time()
    report = ["# TVGun 边界条件专项测试报告（SPEC2.md §5）", "",
              f"- contents: {', '.join(kinds)}",
              f"- cases / (content×cell): {ctx['cases']}",
              f"- seed: {args.seed}, strength: {args.strength}",
              f"- 套件: {', '.join(str(s) for s in suite_ids)}", ""]

    for sid in suite_ids:
        fn = SUITES[sid]
        print(f"[boundary] 套件 {sid} ({SUITE_NAMES[sid]}) ...", flush=True)
        t0 = time.time()
        title, desc, df, note = fn(ctx)
        report += [f"## {sid}. {title}", "", desc, ""]
        if note:
            report += [f"> {note}", ""]
        if df is not None and not df.empty:
            df.to_csv(out_dir / f"{SUITE_NAMES[sid]}.csv", index=False)
            report += [metrics.summarize(df), ""]
            fails = int(((~df["ok"].astype(bool)) | (df["error"] > metrics.FAIL_PX)
                         | df["error"].isna()).sum())
            print(f"[boundary] 套件 {sid} 完成: {len(df)} 用例, 失败 {fails}, "
                  f"{time.time() - t0:.1f}s", flush=True)
        else:
            report += ["_(跳过或无数据)_", ""]
            print(f"[boundary] 套件 {sid} 跳过: {note}", flush=True)

    report += [f"_总耗时 {time.time() - t_start:.1f}s_", ""]
    path = out_dir / "report.md"
    path.write_text("\n".join(report), encoding="utf-8")
    print(f"[boundary] report -> {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
