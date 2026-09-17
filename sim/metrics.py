"""误差指标与汇总。接口见 SPEC.md『评测』节。"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_ORDER = ["easy", "medium", "hard", "extreme"]

# 评测阈值（SPEC 评测节定义）
HIT1_PX = 1.0    # top-1 命中阈值
HIT4_PX = 4.0    # 次档命中阈值
FAIL_PX = 16.0   # 误差超过该值或 ok=False 计为失败


def coord_error(true_xy, est_xy) -> float:
    """欧氏像素误差。true_xy / est_xy 为 (x, y) 屏幕像素坐标。"""
    return float(np.hypot(float(est_xy[0]) - float(true_xy[0]),
                          float(est_xy[1]) - float(true_xy[1])))


# 第二期扩展分组列（SPEC2.md §7）：df 中存在时自动纳入 summarize 分组
EXTRA_GROUP_COLS = ("imu", "dynamic")


def _fmt_flag(v) -> str:
    """分组标志渲染：布尔显示为 Y/N，其余原样。"""
    if isinstance(v, (bool, np.bool_)):
        return "Y" if v else "N"
    return str(v)


def summarize(df: pd.DataFrame) -> str:
    """按 content × level（存在 imu/dynamic 列时再追加）分组汇总，输出 markdown 表格。

    输入 df 至少包含列: content, level, error(像素), ok(bool), time_s(解码耗时秒)。
    指标: n、top-1 命中率(err≤1px)、err≤4px 率、中位/P95 误差、
    失败率(err>16 或 ok=False)、平均解码耗时。
    """
    if df.empty:
        return "_(无数据)_"
    d = df.copy()
    if "ok" not in d.columns:
        d["ok"] = True
    extra = [c for c in EXTRA_GROUP_COLS if c in d.columns]
    keys = ["content", "level"] + extra
    err = pd.to_numeric(d["error"], errors="coerce")
    ok = d["ok"].astype(bool)
    d["_err"] = err
    d["_fail"] = (~ok) | (err > FAIL_PX) | err.isna()

    rows = []
    for key_vals, g in d.groupby(keys, observed=True, sort=False):
        key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
        e = g["_err"]
        ev = e.dropna()  # 中位/P95 只在有效误差上统计，全 NaN 组避免告警
        row = {
            "content": key_vals[0], "level": key_vals[1], "n": len(g),
            "hit1": float((e <= HIT1_PX).mean()),
            "hit4": float((e <= HIT4_PX).mean()),
            "median": float(ev.median()) if len(ev) else float("nan"),
            "p95": float(ev.quantile(0.95)) if len(ev) else float("nan"),
            "fail": float(g["_fail"].mean()),
            "time_ms": float("nan"),
        }
        for c, v in zip(extra, key_vals[2:]):
            row[c] = v
        if "time_s" in g.columns:
            row["time_ms"] = float(pd.to_numeric(g["time_s"], errors="coerce").mean() * 1e3)
        rows.append(row)

    t = pd.DataFrame(rows)
    order = {lv: i for i, lv in enumerate(LEVEL_ORDER)}
    t["_lk"] = t["level"].map(lambda v: order.get(v, len(order)))
    t = t.sort_values(["content", "_lk"] + extra).drop(columns="_lk")

    # 表头/分隔行按额外分组列动态扩展
    header = ("| content | level |" + "".join(f" {c} |" for c in extra)
              + " n | top-1 (err≤1px) | err≤4px | 中位误差(px) | P95(px) | 失败率 | 平均耗时(ms) |")
    lines = [header, "|" + "---|" * (2 + len(extra) + 7)]
    for _, r in t.iterrows():
        flags = "".join(f" {_fmt_flag(r[c])} |" for c in extra)
        lines.append(
            f"| {r['content']} | {r['level']} |{flags} {r['n']} "
            f"| {r['hit1'] * 100:.1f}% | {r['hit4'] * 100:.1f}% "
            f"| {r['median']:.2f} | {r['p95']:.2f} "
            f"| {r['fail'] * 100:.1f}% | {r['time_ms']:.1f} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    # 自测：coord_error 基本正确性
    assert coord_error((0, 0), (3, 4)) == 5.0
    assert coord_error((100.5, 200.25), (100.5, 200.25)) == 0.0
    assert abs(coord_error((960, 540), (961.5, 540)) - 1.5) < 1e-9

    # 自测：summarize 在合成数据上的分组汇总（含失败与缺失值）
    rng = np.random.default_rng(0)
    rows = []
    for ci, content in enumerate(["game_scene", "facade"]):
        for li, level in enumerate(LEVEL_ORDER):
            for _ in range(30):
                e = float(rng.gamma(1.2 + 0.9 * li + 0.3 * ci, 1.0))
                rows.append(dict(content=content, level=level, error=e,
                                 ok=e <= 30.0, confidence=1.5,
                                 time_s=0.02 + 0.01 * li))
    rows.append(dict(content="facade", level="extreme", error=np.nan,
                     ok=False, confidence=0.0, time_s=0.06))  # decode 异常的情形
    df = pd.DataFrame(rows)
    md = summarize(df)
    print(md)

    # 抽查 facade/extreme 行的统计量
    g = df[(df.content == "facade") & (df.level == "extreme")]
    assert "facade | extreme | 31" in md
    fail_rate = float(((~g.ok) | (g.error > FAIL_PX) | g.error.isna()).mean())
    assert f"{fail_rate * 100:.1f}%" in md
    assert f"{g.error.median():.2f}" in md

    # 自测：存在 imu/dynamic 列时自动纳入分组（SPEC2.md §7）
    rows2 = []
    for imu in (False, True):
        for dyn in (False, True):
            for _ in range(10):
                rows2.append(dict(content="game_scene", level="hard",
                                  error=float(rng.uniform(0, 2)), ok=True,
                                  time_s=0.05, imu=imu, dynamic=dyn))
    md2 = summarize(pd.DataFrame(rows2))
    print("\n" + md2)
    assert "| content | level | imu | dynamic |" in md2
    assert md2.count("| game_scene | hard |") == 4          # 2×2 四组全出现
    assert "| game_scene | hard | Y | N |" in md2

    # 不带扩展列时表头保持第一期格式（向后兼容）
    assert md.splitlines()[0].startswith("| content | level | n |")
    print("\n[metrics] 自测通过")
