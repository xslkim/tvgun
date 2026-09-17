#!/usr/bin/env python3
"""移动端算力代理基准（SPEC2.md §6）。

固定 cv2.setNumThreads(1) 模拟手机单核，测量 decode 耗时随
cam_res {512,768,1024} × 单/三帧 × 有/无 IMU 的变化，报告 中位/P95 ms 表，
写 out/mobile_bench/report.md 与 results.csv。

优化目标（SPEC2 §6）：三帧 + IMU + cam_res 768 中位 < 150ms。

用法: python scripts/run_mobile_bench.py [--reps 10] [--cam-res 512,768,1024]
      [--contents game_scene,facade] [--out out/mobile_bench]
"""
from __future__ import annotations

import argparse
import dataclasses
import inspect
import sys
import time
import traceback
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 保证能 import sim 包

from sim import channel, data, decode, embed
from sim.config import SEED

FPS = 30.0
TARGET = dict(cam_res=768, n_frames=3, imu=True, median_ms=150.0)  # SPEC2 §6 优化目标

_DECODE_PARAMS: set | None = None


def _decode_supports(name: str) -> bool:
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
    p = argparse.ArgumentParser(description="TVGun 移动端算力代理基准（SPEC2.md §6）")
    p.add_argument("--cam-res", default="512,768,1024", help="逗号分隔的相机分辨率列表")
    p.add_argument("--reps", type=int, default=10, help="每单元格重复次数")
    p.add_argument("--contents", default="game_scene,facade", help="逗号分隔内容集（轮流使用）")
    p.add_argument("--strength", type=float, default=2.5)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="out/mobile_bench", help="输出目录")
    return p.parse_args(argv)


def _prep_case(content_cache, ci, cam_res, n_frames, use_imu, imu_mod, rng):
    """构造一次基准用例：返回 (frames, state, fov, prior)。capture 不计时。"""
    kind, wm, state = content_cache[ci % len(content_cache)]
    base = channel.sample_config(rng, "medium")
    base.cam_res = cam_res
    base.rng = rng
    if use_imu:
        # HandMotion 轨迹驱动连续位置与几何；prior_at 注入 decode（SPEC2 §6 场景）
        mseed = int(rng.integers(0, 2 ** 31))
        motion = imu_mod.HandMotion(mseed, duration_s=max(2.0, n_frames / FPS + 0.5),
                                    speed="slow")
        stream = imu_mod.simulate_imu(motion, rate_hz=200, seed=mseed + 1)
        states = [motion.sample(k / FPS) for k in range(n_frames)]
        prior = stream.prior_at((n_frames - 1) / FPS, fps=FPS, n_frames=n_frames)
        frames = []
        for ms in states:
            cfg_k = dataclasses.replace(
                base, rotation_deg=float(ms.roll_deg),
                perspective_jitter=0.5 * (abs(float(ms.tilt_pitch_deg))
                                          + abs(float(ms.tilt_yaw_deg))))
            frames.append(channel.capture(wm, (float(ms.center_x), float(ms.center_y)), cfg_k))
        return frames, state, base.fov, prior
    margin = base.fov // 2 + 16
    xy = (float(rng.uniform(margin, 1920 - margin)), float(rng.uniform(margin, 1080 - margin)))
    frames = [channel.capture(wm, xy, base) for _ in range(n_frames)]
    return frames, state, base.fov, None


def main(argv=None) -> int:
    args = parse_args(argv)
    cv2.setNumThreads(1)  # 模拟手机单核（SPEC2 §6），必须在任何 cv2 运算前设定
    cam_res_list = [int(s) for s in args.cam_res.split(",") if s.strip()]
    kinds = [s.strip() for s in args.contents.split(",") if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    imu_mod = _load_imu()
    imu_ready = imu_mod is not None and _decode_supports("imu_prior")
    if not imu_ready:
        print("[bench] 警告: sim/imu.py 或 decode(imu_prior) 未就绪，IMU 单元格记为 N/A", flush=True)

    # 内容嵌入一次缓存复用（基准只关心 decode 耗时）
    content_cache = []
    for ci, kind in enumerate(kinds):
        frame = data.generate_frame(kind, seed=args.seed + 5000 + ci)
        wm, state = embed.embed_signal(frame, strength=args.strength, seed=args.seed)
        content_cache.append((kind, wm, state))

    rows = []
    total = len(cam_res_list) * 2 * 2 * args.reps
    idx = 0
    for cam_res in cam_res_list:
        for n_frames in (1, 3):
            for use_imu in (False, True):
                cell = dict(cam_res=cam_res, n_frames=n_frames, imu=use_imu)
                if use_imu and not imu_ready:
                    rows.append(dict(**cell, rep=-1, time_ms=float("nan")))
                    continue
                for rep in range(args.reps):
                    idx += 1
                    rng = np.random.default_rng(
                        (args.seed, cam_res, n_frames, int(use_imu), rep))
                    try:
                        frames, state, fov, prior = _prep_case(
                            content_cache, rep, cam_res, n_frames, use_imu, imu_mod, rng)
                        kwargs = {"fov": fov}
                        if prior is not None:
                            kwargs["imu_prior"] = prior
                        t0 = time.perf_counter()  # 只计 decode 耗时
                        decode.decode(frames if n_frames > 1 else frames[0], state, **kwargs)
                        dt = time.perf_counter() - t0
                    except Exception:
                        traceback.print_exc(limit=2)
                        dt = float("nan")
                    rows.append(dict(**cell, rep=rep, time_ms=dt * 1e3))
                    print(f"[{idx}/{total}] cam_res={cam_res} frames={n_frames} "
                          f"imu={int(use_imu)} rep={rep}: {dt * 1e3:.1f}ms", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "results.csv", index=False)

    # 汇总：中位 / P95
    lines = ["# TVGun 移动端算力代理基准（SPEC2.md §6）", "",
             "- cv2.setNumThreads(1)（手机单核代理），仅计 decode 耗时",
             f"- reps/单元格: {args.reps}, seed: {args.seed}, contents: {', '.join(kinds)}", "",
             "| cam_res | 帧数 | IMU | n | 中位(ms) | P95(ms) |",
             "|---|---|---|---|---|---|"]
    for (cam_res, n_frames, use_imu), g in df.groupby(["cam_res", "n_frames", "imu"]):
        t = g["time_ms"].dropna()
        if len(t):
            lines.append(f"| {cam_res} | {n_frames} | {'Y' if use_imu else 'N'} | {len(t)} "
                         f"| {t.median():.1f} | {t.quantile(0.95):.1f} |")
        else:
            lines.append(f"| {cam_res} | {n_frames} | {'Y' if use_imu else 'N'} | 0 | N/A | N/A |")

    # SPEC2 §6 优化目标核查
    tgt = df[(df.cam_res == TARGET["cam_res"]) & (df.n_frames == TARGET["n_frames"])
             & (df.imu == TARGET["imu"])]["time_ms"].dropna()
    lines += ["", "## 优化目标核查", ""]
    if len(tgt):
        med = float(tgt.median())
        verdict = "达标" if med < TARGET["median_ms"] else "未达标"
        lines.append(f"- 三帧 + IMU + cam_res {TARGET['cam_res']}: 中位 {med:.1f}ms "
                     f"（目标 < {TARGET['median_ms']:.0f}ms）→ **{verdict}**")
        if med >= TARGET["median_ms"]:
            lines.append("- 可行裁剪（SPEC2 §6）：减小 FFT 尺寸、有 prior 时相关搜索窗限 ±32px、"
                         "降低透视迭代次数")
    else:
        lines.append("- 目标单元格无数据（IMU 依赖未就绪）")
    lines.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[bench] results -> {out_dir / 'results.csv'}", flush=True)
    print(f"[bench] report  -> {path}", flush=True)
    print("\n".join(lines[4:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
