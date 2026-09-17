#!/usr/bin/env python3
"""批量评测: 遍历 内容 × level × 随机位置 矩阵，跑 embed->capture->decode 全流程，
输出 results.csv 与 report.md（含失败案例可视化图，存 out/eval/failures/）。

用法: python scripts/run_eval.py [--levels easy,medium,hard,extreme] [--positions 40]
      [--frames-per-case 1] [--include-real] [--quick] [--out out/eval]
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sim import channel, data, decode, embed, metrics
from sim.config import SCREEN_H, SCREEN_W, SEED

# 与 run_demo 一致的 DecodeResult.debug 候选键
_CORRECTED_KEYS = ("corrected", "rectified", "warped", "aligned")
_HEATMAP_KEYS = ("heatmap", "corr_map", "corr", "response")

# 记录到 results.csv 的信道参数列
_CHANNEL_PARAM_KEYS = ("rotation_deg", "perspective_jitter", "defocus_sigma", "moire",
                       "noise_sigma", "flicker_amp", "gamma", "jpeg_quality",
                       "taa_jitter", "exposure_gain")
# 记录到 results.csv 的 decode debug 诊断列（缺失时记 NaN）
_DEBUG_KEYS = ("peak", "mresp", "nlock", "scale", "theta_deg")

_DECODE_PARAMS: set | None = None


def _decode_supports(name: str) -> bool:
    """探测 decode.decode 是否支持某个可选参数（第二期扩展由并行模块提供）。"""
    global _DECODE_PARAMS
    if _DECODE_PARAMS is None:
        _DECODE_PARAMS = set(inspect.signature(decode.decode).parameters)
    return name in _DECODE_PARAMS


def _load_imu():
    """导入 sim.imu（SPEC2.md §1），未就绪时返回 None。"""
    try:
        from sim import imu
        return imu
    except ImportError:
        return None


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TVGun 批量评测（见 SPEC.md 评测节）")
    p.add_argument("--levels", default="easy,medium,hard,extreme", help="逗号分隔的档位列表")
    p.add_argument("--positions", type=int, default=None,
                   help="每个 content×level 的随机位置数（默认 40，--quick 时 8）")
    p.add_argument("--frames-per-case", type=int, default=1, help="每用例连拍帧数（多帧联合解码）")
    p.add_argument("--include-real", action="store_true", help="内容集加入下载成功的真实图片")
    p.add_argument("--quick", action="store_true", help="快速模式: positions=8 且仅 easy+hard")
    p.add_argument("--imu", action="store_true",
                   help="IMU 辅助模式: HandMotion 轨迹驱动连续位置+prior 注入（SPEC2 §7，替代独立随机位置）")
    p.add_argument("--dynamic", action="store_true",
                   help="动态场景模式: generate_sequence 序列帧逐帧 embed 后连拍（SPEC2 §4）")
    p.add_argument("--strength", type=float, default=2.5, help="嵌入强度")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="out/eval", help="输出目录")
    p.add_argument("--max-failure-viz", type=int, default=24, help="失败案例可视化最多保存的张数")
    return p.parse_args(argv)


def _load_contents(args, out_dir: Path) -> list[tuple[str, np.ndarray]]:
    """内容集 = 全部 KINDS + （--include-real 时）下载成功的真实图。"""
    contents = []
    for i, kind in enumerate(data.KINDS):
        contents.append((kind, data.generate_frame(kind, seed=args.seed + 1000 + i)))
    if args.include_real:
        real_dir = out_dir.parent / "real_frames"  # 真实素材缓存复用，不随评测输出目录变动
        paths = data.ensure_real_frames(str(real_dir))
        n_ok = 0
        for pth in paths:
            img = None
            try:
                import cv2
                raw = cv2.imread(pth, cv2.IMREAD_COLOR)
                if raw is not None:
                    img = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
            except Exception:
                img = None
            if img is None:
                print(f"[eval] 真实图片读取失败，跳过: {pth}", flush=True)
                continue
            if img.shape[:2] != (SCREEN_H, SCREEN_W):
                import cv2
                img = cv2.resize(img, (SCREEN_W, SCREEN_H))
            contents.append((f"real_{n_ok:02d}", img))
            n_ok += 1
        print(f"[eval] 真实图片: {n_ok}/{len(paths)} 张可用", flush=True)
    return contents


def _pick_debug(debug: dict, keys) -> np.ndarray | None:
    for k in keys:
        v = debug.get(k)
        if isinstance(v, np.ndarray) and v.size:
            return v
    return None


def _imshow(ax, img, title):
    if img is None:
        ax.text(0.5, 0.5, "N/A", ha="center", va="center", transform=ax.transAxes, color="gray")
    elif img.ndim == 2:
        ax.imshow(img, cmap="gray")
    else:
        ax.imshow(img)
    ax.set_title(title)
    ax.axis("off")


def _save_failure_png(path: Path, content, level, xy, frames, res, err):
    """失败案例可视化: 相机图 / 几何校正图 / 相关热力图。"""
    debug = res.debug if res is not None and isinstance(res.debug, dict) else {}
    corrected = _pick_debug(debug, _CORRECTED_KEYS)
    heatmap = _pick_debug(debug, _HEATMAP_KEYS)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))
    _imshow(axes[0], frames[0], f"camera ({level})")
    _imshow(axes[1], corrected, "corrected")
    _imshow(axes[2], heatmap, "heatmap")
    est = f"({res.x:.1f},{res.y:.1f})" if res is not None else "EXCEPTION"
    conf = f"{res.confidence:.2f}" if res is not None else "0"
    fig.suptitle(f"FAIL | {content}/{level} true=({xy[0]:.1f},{xy[1]:.1f}) est={est} "
                 f"err={err:.2f}px conf={conf}", color="red")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _run_case(wm_seq, state, level, xy, n_frames, case_seed):
    """单用例 embed->capture->decode。decode 异常不中断矩阵，记为失败行。

    wm_seq: 已嵌入帧列表（静态模式长度 1，--dynamic 时为逐帧嵌入的序列帧，
    连拍第 k 帧取 wm_seq[k]，模板相同、内容在变，见 SPEC2.md §4）。
    """
    rng = np.random.default_rng(case_seed)
    cfg = channel.sample_config(rng, level)
    cfg.rng = rng  # 多帧连拍时各帧频闪相位/噪声/taa 抖动不同且可复现
    frames = [channel.capture(wm_seq[k % len(wm_seq)], (float(xy[0]), float(xy[1])), cfg)
              for k in range(n_frames)]
    t0 = time.perf_counter()
    res, exc = None, None
    try:
        res = decode.decode(frames if n_frames > 1 else frames[0], state, fov=cfg.fov)
    except Exception:
        exc = traceback.format_exc(limit=3)
    dt = time.perf_counter() - t0
    return cfg, frames, res, dt, exc, (float(xy[0]), float(xy[1]))


def _run_case_imu(wm_seq, state, level, n_frames, case_seed, imu_mod, fps: float = 30.0):
    """--imu 用例（SPEC2.md §7）：HandMotion 轨迹驱动连续位置 + IMU 先验注入。

    - 轨迹 center 作为真值（多帧连拍以首帧为基准帧，frame_deltas 由解码端预对齐）；
    - MotionState 的 roll/tilt 驱动 ChannelConfig 几何：rotation_deg=roll，
      tilt 俯仰/偏航按每度约 0.5 相机px 近似映射为四角透视扰动幅度；
    - IMUStream.prior_at(t) 作为 imu_prior 注入 decode。
    """
    rng = np.random.default_rng(case_seed)
    mseed = int(rng.integers(0, 2 ** 31))
    speed = "fast" if level == "motion" else "slow"  # motion 档对应 fast 手持（SPEC2 §3）
    motion = imu_mod.HandMotion(mseed, duration_s=max(2.0, n_frames / fps + 0.5), speed=speed)
    stream = imu_mod.simulate_imu(motion, rate_hz=200, seed=mseed + 1)
    base = channel.sample_config(rng, level)
    base.rng = rng
    frames, states = [], []
    for k in range(n_frames):
        ms = motion.sample(k / fps)
        states.append(ms)
        cfg_k = dataclasses.replace(
            base, rotation_deg=float(ms.roll_deg),
            perspective_jitter=max(float(base.perspective_jitter),
                                   0.5 * (abs(float(ms.tilt_pitch_deg))
                                          + abs(float(ms.tilt_yaw_deg)))))
        frames.append(channel.capture(wm_seq[k % len(wm_seq)],
                                      (float(ms.center_x), float(ms.center_y)), cfg_k))
    prior = stream.prior_at((n_frames - 1) / fps, fps=fps, n_frames=n_frames)
    t0 = time.perf_counter()
    res, exc = None, None
    try:
        res = decode.decode(frames if n_frames > 1 else frames[0], state,
                            fov=base.fov, imu_prior=prior)
    except Exception:
        exc = traceback.format_exc(limit=3)
    dt = time.perf_counter() - t0
    truth = (float(states[0].center_x), float(states[0].center_y))  # 首帧中心为真值
    return base, frames, res, dt, exc, truth


def _is_fail(ok: bool, err: float) -> bool:
    return (not ok) or (not np.isfinite(err)) or err > metrics.FAIL_PX


def _write_report(out_dir, args, levels, positions, n_frames, df, failure_imgs, elapsed):
    fails = int(((~df["ok"].astype(bool)) | (df["error"] > metrics.FAIL_PX)
                 | df["error"].isna()).sum())
    n = len(df)
    lines = [
        "# TVGun 批量评测报告", "",
        f"- levels: {', '.join(levels)}",
        f"- positions / (content×level): {positions}",
        f"- frames_per_case: {n_frames}",
        f"- imu: {args.imu}, dynamic: {args.dynamic}",
        f"- seed: {args.seed}, strength: {args.strength}, include_real: {args.include_real}",
        f"- 内容数: {df['content'].nunique()}, 用例总数: {n}, "
        f"失败: {fails} ({fails / max(n, 1):.1%})",
        f"- 总耗时: {elapsed:.1f}s", "",
        "## 汇总（content × level）", "",
        metrics.summarize(df), "",
        f"## 失败案例（err>{metrics.FAIL_PX:.0f}px 或 ok=False，共 {fails} 个）", "",
    ]
    if failure_imgs:
        lines.append(f"以下为前 {len(failure_imgs)} 个失败案例的可视化（全部文件见 `failures/`）：")
        lines.append("")
        for name, content, level, err, conf in failure_imgs:
            lines.append(f"- `{content}` / `{level}` — err={err:.2f}px conf={conf:.2f}  ")
            lines.append(f"  ![{name}](failures/{name})")
    else:
        lines.append("无失败案例。")
    lines.append("")
    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv=None) -> int:
    args = parse_args(argv)
    levels = [s.strip() for s in args.levels.split(",") if s.strip()]
    if args.quick:
        levels = ["easy", "hard"]
    positions = args.positions if args.positions else (8 if args.quick else 40)
    n_frames = max(1, args.frames_per_case)
    if args.dynamic and n_frames < 3:
        n_frames = 3  # 动态场景连拍至少 3 帧（SPEC2 §4/§5-6）
        print("[eval] --dynamic 模式 frames_per_case 提升为 3", flush=True)

    # 第二期依赖前置检查：缺失时明确报错而非静默退化
    imu_mod = None
    if args.imu:
        imu_mod = _load_imu()
        if imu_mod is None:
            raise SystemExit("[eval] --imu 需要 sim/imu.py（SPEC2 §1），当前未提供")
        if not _decode_supports("imu_prior"):
            raise SystemExit("[eval] --imu 需要 decode.decode 支持 imu_prior 参数（SPEC2 §2），当前未实现")
    if args.dynamic and not hasattr(data, "generate_sequence"):
        raise SystemExit("[eval] --dynamic 需要 data.generate_sequence（SPEC2 §4），当前未实现")

    out_dir = Path(args.out)
    fail_dir = out_dir / "failures"
    fail_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    contents = _load_contents(args, out_dir)
    if args.dynamic:  # 序列帧仅支持程序化时序内容，其余剔除
        seq_kinds = set(getattr(data, "SEQ_KINDS", ("game_scene", "terrain", "clouds")))
        contents = [(k, f) for k, f in contents if k in seq_kinds]

    # 每个 level 采样一套位置并跨内容共享，便于横向对比；seed 可复现
    pos_by_level = {}
    for li, level in enumerate(levels):
        rng_pos = np.random.default_rng((args.seed, 7, li))
        pos_by_level[level] = np.asarray(
            data.sample_positions(rng_pos, positions), dtype=np.float64).reshape(positions, 2)

    total = len(contents) * len(levels) * positions
    print(f"[eval] 内容 {len(contents)} × 档位 {len(levels)} × 位置 {positions} = {total} 用例"
          f", frames_per_case={n_frames}, imu={args.imu}, dynamic={args.dynamic}, out={out_dir}",
          flush=True)

    rows, failure_imgs = [], []
    idx = 0
    for ci, (content, frame) in enumerate(contents):
        # 嵌入：静态模式嵌 1 帧；--dynamic 时用 generate_sequence 生成序列并逐帧嵌入
        # （同 seed → 同模板，内容逐帧变化，SPEC2.md §4）
        if args.dynamic:
            seq = data.generate_sequence(content, seed=args.seed + 2000 + ci, n_frames=n_frames)
            wm_seq, state = [], None
            for fr in seq:
                wm, state = embed.embed_signal(fr, strength=args.strength, seed=args.seed)
                wm_seq.append(wm)
        else:
            wm, state = embed.embed_signal(frame, strength=args.strength, seed=args.seed)
            wm_seq = [wm]
        for li, level in enumerate(levels):
            for pi in range(positions):
                idx += 1
                if args.imu:
                    # HandMotion 轨迹提供位置与真值，--imu 下不用随机位置表
                    cfg, frames, res, dt, exc, xy = _run_case_imu(
                        wm_seq, state, level, n_frames, (args.seed, 11, ci, li, pi), imu_mod)
                else:
                    cfg, frames, res, dt, exc, xy = _run_case(
                        wm_seq, state, level, pos_by_level[level][pi], n_frames,
                        (args.seed, 11, ci, li, pi))
                if res is None:
                    est_x = est_y = err = float("nan")
                    conf, ok = 0.0, False
                else:
                    est_x, est_y = float(res.x), float(res.y)
                    conf, ok = float(res.confidence), bool(res.ok)
                    err = metrics.coord_error(xy, (est_x, est_y))
                failed = _is_fail(ok, err)

                row = dict(content=content, level=level, pos_idx=pi,
                           true_x=xy[0], true_y=xy[1], est_x=est_x, est_y=est_y,
                           error=err, ok=ok, confidence=conf, time_s=dt, n_frames=n_frames)
                if args.imu:      # 仅在开启时写列，summarize 检测到列才纳入分组
                    row["imu"] = True
                if args.dynamic:
                    row["dynamic"] = True
                for k in _CHANNEL_PARAM_KEYS:
                    row[k] = getattr(cfg, k, None)
                dbg = res.debug if res is not None and isinstance(res.debug, dict) else {}
                for k in _DEBUG_KEYS:
                    row[k] = dbg.get(k, float("nan"))
                rows.append(row)

                tag = "  <- FAIL" if failed else ""
                print(f"[{idx}/{total}] {content:12s} {level:6s} "
                      f"pos=({xy[0]:7.1f},{xy[1]:6.1f}) err={err:8.2f}px "
                      f"conf={conf:5.2f} ok={int(ok)} {dt * 1e3:8.1f}ms{tag}", flush=True)
                if exc:
                    print(f"    [warn] decode 异常: {exc.splitlines()[-1]}", flush=True)
                if failed and len(failure_imgs) < args.max_failure_viz:
                    name = f"{content}_{level}_p{pi:03d}.png"
                    try:
                        _save_failure_png(fail_dir / name, content, level, xy, frames, res, err)
                        failure_imgs.append((name, content, level, err, conf))
                    except Exception:
                        print(f"    [warn] 失败案例可视化保存出错: {name}", flush=True)

    df = pd.DataFrame(rows)
    csv_path = out_dir / "results.csv"
    df.to_csv(csv_path, index=False)
    report_path = _write_report(out_dir, args, levels, positions, n_frames,
                                df, failure_imgs, time.time() - t_start)
    print(f"[eval] results -> {csv_path}", flush=True)
    print(f"[eval] report  -> {report_path}", flush=True)
    print()
    print(metrics.summarize(df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
