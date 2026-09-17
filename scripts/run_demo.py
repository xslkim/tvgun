#!/usr/bin/env python3
"""端到端 Demo: embed -> capture -> decode 单命令运行，保存 2x3 面板可视化 PNG。

用法: python scripts/run_demo.py --kind game_scene --level medium [--x 960 --y 540] [--frames 3] --out out/demo
退出码: 误差 ≤ 1px 为 0，否则为 1。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 保证能 import sim 包

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sim import channel, data, decode, embed, metrics
from sim.config import SEED

LEVELS = ["easy", "medium", "hard", "extreme"]
# DecodeResult.debug 可视化中间结果的候选键（与 decode.py 约定，取第一个存在的 ndarray）
_CORRECTED_KEYS = ("corrected", "rectified", "warped", "aligned")
_HEATMAP_KEYS = ("heatmap", "corr_map", "corr", "response")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TVGun 端到端 Demo（见 SPEC.md Demo 节）")
    p.add_argument("--kind", default="game_scene",
                   choices=list(getattr(data, "KINDS", [])) or None, help="画面类型")
    p.add_argument("--level", default="medium", choices=LEVELS, help="信道档位")
    p.add_argument("--x", type=float, default=None, help="区域中心 x（屏幕像素，缺省随机）")
    p.add_argument("--y", type=float, default=None, help="区域中心 y（屏幕像素，缺省随机）")
    p.add_argument("--frames", type=int, default=1, help="连拍帧数（多帧联合解码）")
    p.add_argument("--strength", type=float, default=2.5, help="嵌入强度")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="out/demo", help="输出目录")
    return p.parse_args(argv)


def _pick_debug(debug: dict, keys) -> np.ndarray | None:
    for k in keys:
        v = debug.get(k)
        if isinstance(v, np.ndarray) and v.size:
            return v
    return None


def _imshow(ax, img, title):
    if img is None:
        ax.text(0.5, 0.5, "N/A (not in decode debug)", ha="center", va="center",
                transform=ax.transAxes, color="gray")
    elif img.ndim == 2:
        ax.imshow(img, cmap="gray")
    else:
        ax.imshow(img)
    ax.set_title(title)
    ax.axis("off")


def _save_panel(out_path, args, frame, frame_wm, frames, result, true_xy, err, dt):
    """2x3 面板: 原图 / 残差x20 / 嵌入后 / 相机图 / 校正图 / 相关热力图+结论。"""
    debug = result.debug if isinstance(result.debug, dict) else {}
    corrected = _pick_debug(debug, _CORRECTED_KEYS)
    heatmap = _pick_debug(debug, _HEATMAP_KEYS)
    # 嵌入残差放大 20 倍并加 128 偏移，使正负扰动可见
    resid = np.clip((frame_wm.astype(np.float32) - frame.astype(np.float32)) * 20 + 128,
                    0, 255).astype(np.uint8)
    passed = err <= 1.0
    color = "green" if passed else "red"
    verdict = f"err={err:.2f}px conf={result.confidence:.2f} -> {'PASS' if passed else 'FAIL'}"

    fig, axes = plt.subplots(2, 3, figsize=(17, 9.5))
    _imshow(axes[0, 0], frame, "original frame")
    _imshow(axes[0, 1], resid, "embed residual x20 (+128)")
    _imshow(axes[0, 2], frame_wm, f"watermarked (strength={args.strength})")
    _imshow(axes[1, 0], frames[0],
            f"camera capture ({args.level}, {frames[0].shape[0]}px, n={len(frames)})")
    _imshow(axes[1, 1], corrected, "geometrically corrected" if corrected is not None else "corrected")
    ax = axes[1, 2]
    _imshow(ax, heatmap, "")
    ax.set_title(f"correlation heatmap\n{verdict}", color=color)
    if heatmap is None:
        ax.text(0.5, 0.5, verdict, ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color=color)
    fig.suptitle(
        f"TVGun demo | kind={args.kind} level={args.level} | "
        f"true=({true_xy[0]:.1f},{true_xy[1]:.1f}) est=({result.x:.1f},{result.y:.1f}) | "
        f"{verdict} | decode {dt * 1e3:.0f}ms",
        color=color)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path


def main(argv=None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    frame = data.generate_frame(args.kind, seed=args.seed)
    frame_wm, state = embed.embed_signal(frame, strength=args.strength, seed=args.seed)

    # 位置缺省时随机（同一 seed 可复现）；给定的坐标覆盖随机值
    pts = np.asarray(data.sample_positions(rng, 1), dtype=np.float64).reshape(-1, 2)
    x = float(args.x) if args.x is not None else float(pts[0, 0])
    y = float(args.y) if args.y is not None else float(pts[0, 1])

    cfg = channel.sample_config(rng, args.level)
    cfg.rng = rng  # 信道内部随机量（频闪相位/噪声/taa）纳入 seed 复现链
    n_frames = max(1, args.frames)
    frames = [channel.capture(frame_wm, (x, y), cfg) for _ in range(n_frames)]

    t0 = time.perf_counter()
    result = decode.decode(frames if n_frames > 1 else frames[0], state)
    dt = time.perf_counter() - t0

    err = metrics.coord_error((x, y), (result.x, result.y))
    passed = err <= 1.0
    print(f"真值坐标: ({x:.2f}, {y:.2f})")
    print(f"解码坐标: ({result.x:.2f}, {result.y:.2f})")
    print(f"误差: {err:.3f} px")
    print(f"置信度: {result.confidence:.3f} (ok={result.ok}, n_frames={n_frames})")
    print(f"耗时: {dt * 1e3:.1f} ms")
    print(f"判定: {'PASS (误差≤1px)' if passed else 'FAIL (误差>1px)'}")

    png = _save_panel(out_dir / f"demo_{args.kind}_{args.level}.png",
                      args, frame, frame_wm, frames, result, (x, y), err, dt)
    print(f"可视化已保存: {png}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
