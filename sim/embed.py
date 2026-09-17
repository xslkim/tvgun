"""定位模板生成与嵌入（见 SPEC.md『嵌入信号』一节）。

频域随机相位带通模板（周期 4~24px 环形带通，零均值 std=1）+ 4 组导频光栅，
经 9×9 高斯局部对比度感知加权后嵌入到 Y 通道。
"""
from __future__ import annotations

import cv2
import numpy as np

try:
    from .config import SEED, SCREEN_H, SCREEN_W, PILOT_FREQS, PILOT_AMP, EmbedState
except ImportError:  # 支持 python3 sim/embed.py 直接运行自测
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim.config import SEED, SCREEN_H, SCREEN_W, PILOT_FREQS, PILOT_AMP, EmbedState

_PERIOD_MIN, _PERIOD_MAX = 4.0, 24.0  # 带通周期范围（屏幕像素）


def generate_template(seed: int = SEED) -> np.ndarray:
    """频域随机相位带通模板，(1080,1920) float32，零均值 std=1，逐比特可复现。"""
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(SCREEN_H)[:, None]  # cycles/px
    fx = np.fft.fftfreq(SCREEN_W)[None, :]
    fr = np.hypot(fx, fy)
    band = (fr >= 1.0 / _PERIOD_MAX) & (fr <= 1.0 / _PERIOD_MIN)

    phase = rng.uniform(0.0, 2.0 * np.pi, (SCREEN_H, SCREEN_W))
    spec = np.zeros((SCREEN_H, SCREEN_W), dtype=np.complex64)
    spec[band] = np.exp(1j * phase[band])
    # numpy IFFT 内部用 float64 计算，1080x1920 复数谱约 130MB 瞬态内存，可接受
    t = np.fft.ifft2(spec).real.astype(np.float32)
    t -= t.mean()
    t /= t.std()
    return t.astype(np.float32)


def _pilot_gratings() -> np.ndarray:
    """4 组几何导频正弦光栅之和，幅度 PILOT_AMP，确定性（无随机量）。"""
    xx = np.arange(SCREEN_W, dtype=np.float32)[None, :]
    yy = np.arange(SCREEN_H, dtype=np.float32)[:, None]
    g = np.zeros((SCREEN_H, SCREEN_W), dtype=np.float32)
    for fx, fy in PILOT_FREQS:
        g += (PILOT_AMP * np.cos(2.0 * np.pi * (fx * xx + fy * yy))).astype(np.float32)
    return g


def _full_signal(seed: int) -> np.ndarray:
    """含导频的完整信号；模板部分已归一化 std=1，直接叠加导频。"""
    return (generate_template(seed) + _pilot_gratings()).astype(np.float32)


def embed_signal(
    frame_u8: np.ndarray, strength: float = 2.5, seed: int = SEED
) -> tuple[np.ndarray, EmbedState]:
    """感知加权亮度域嵌入，返回 (嵌入后帧 uint8, EmbedState)。"""
    if frame_u8.shape != (SCREEN_H, SCREEN_W, 3) or frame_u8.dtype != np.uint8:
        raise ValueError("frame_u8 须为 (1080,1920,3) uint8 RGB")
    signal = _full_signal(seed)

    ycc = cv2.cvtColor(frame_u8, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    y = ycc[..., 0]
    # 9×9 高斯窗估计局部 std：sqrt(E[y^2] - E[y]^2)
    mu = cv2.GaussianBlur(y, (9, 9), 1.5)
    mu2 = cv2.GaussianBlur(y * y, (9, 9), 1.5)
    local_std = np.sqrt(np.maximum(mu2 - mu * mu, 0.0))
    mask = np.clip(0.45 + local_std / 25.0, 0.45, 1.6)

    ycc[..., 0] = y + strength * mask * signal
    frame_wm = cv2.cvtColor(np.clip(ycc, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)
    return frame_wm, EmbedState(seed=seed, strength=strength, template=signal)


def get_signal(state: EmbedState) -> np.ndarray:
    """重建含导频的完整信号，(1080,1920) float32。"""
    return state.template


if __name__ == "__main__":
    # 1. 可复现性：同 seed 两次生成逐比特一致
    t1 = generate_template(seed=SEED)
    t2 = generate_template(seed=SEED)
    assert np.array_equal(t1, t2), "模板不可复现"
    assert t1.dtype == np.float32 and t1.shape == (SCREEN_H, SCREEN_W)
    print(f"[repro] 两次生成逐比特一致 OK, shape={t1.shape}, dtype={t1.dtype}")

    # 2. 零均值 / std=1
    print(f"[stats] template mean={t1.mean():.3e}, std={t1.std():.6f}")
    assert abs(float(t1.mean())) < 1e-4, "模板非零均值"
    assert abs(float(t1.std()) - 1.0) < 1e-4, "模板 std 不为 1"
    s = _full_signal(SEED)
    print(f"[stats] full signal mean={s.mean():.3e}, std={s.std():.6f} (含导频)")

    # 3. 不可见性：构造渐变+轻纹理测试帧，嵌入后 PSNR 应 > 38dB
    rng = np.random.default_rng(0)
    grad = np.linspace(30, 200, SCREEN_W, dtype=np.float32)[None, :, None]
    frame = np.broadcast_to(grad, (SCREEN_H, SCREEN_W, 3)).copy()
    frame += rng.normal(0, 10, frame.shape).astype(np.float32)
    frame = np.clip(frame, 0, 255).astype(np.uint8)

    frame_wm, state = embed_signal(frame, strength=2.5, seed=SEED)
    assert frame_wm.dtype == np.uint8 and frame_wm.shape == frame.shape
    mse = float(np.mean((frame.astype(np.float64) - frame_wm.astype(np.float64)) ** 2))
    psnr = 10.0 * np.log10(255.0 ** 2 / mse)
    print(f"[psnr] MSE={mse:.4f}, PSNR={psnr:.2f} dB")
    assert psnr > 38.0, f"PSNR {psnr:.2f}dB 低于 38dB，不可见性不达标"

    # 4. 嵌入可复现 & get_signal 接口
    frame_wm2, state2 = embed_signal(frame, strength=2.5, seed=SEED)
    assert np.array_equal(frame_wm, frame_wm2), "嵌入结果不可复现"
    assert np.array_equal(get_signal(state), state.template)
    print("[psnr] 嵌入可复现 OK；get_signal 返回含导频完整信号 OK")
    print("全部自测通过。")
