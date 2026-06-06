from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Tuple

import numpy as np


_EPS = 1e-12
_G_TO_MM_PER_S2 = 9806.65
_MAX_CACHE_SIZE = 2048
_ROUND_DIGITS = 9

_VELOCITY_CACHE: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_SPECTRUM_CACHE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_AUTOCORR_CACHE: "OrderedDict[tuple, np.ndarray]" = OrderedDict()


def _lru_get(cache: OrderedDict, key):
    value = cache.get(key)
    if value is None:
        return None
    cache.move_to_end(key)
    return value


def _lru_set(cache: OrderedDict, key, value):
    cache[key] = value
    cache.move_to_end(key)
    if len(cache) > _MAX_CACHE_SIZE:
        cache.popitem(last=False)


def _digest_float_array(values: np.ndarray) -> tuple:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    if not arr.size:
        return ("empty",)
    rounded = np.round(arr, _ROUND_DIGITS)
    contiguous = np.ascontiguousarray(rounded)
    digest = hashlib.blake2b(contiguous.tobytes(), digest_size=16).hexdigest()
    return (int(contiguous.size), digest)


def _normalize_waveform(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    return arr


def to_velocity_waveform(
    waveform: np.ndarray,
    fs_hz: float,
    signal_type: str,
    acceleration_unit: str = "g",
    integration_low_cut_hz: float = 0.2,
) -> np.ndarray:
    x = _normalize_waveform(waveform)
    fs_hz = float(fs_hz)
    signal_type = str(signal_type or "velocity").strip().lower()
    acceleration_unit = str(acceleration_unit or "g").strip().lower()
    integration_low_cut_hz = float(integration_low_cut_hz)

    key = (
        "velocity",
        _digest_float_array(x),
        round(fs_hz, 9),
        signal_type,
        acceleration_unit,
        round(integration_low_cut_hz, 9),
    )
    cached = _lru_get(_VELOCITY_CACHE, key)
    if cached is not None:
        return cached

    if signal_type in {"velocity", "vel", "mm/s", "mmps"}:
        out = x - float(np.mean(x)) if x.size else x
        out = np.asarray(out, dtype=float)
        _lru_set(_VELOCITY_CACHE, key, out)
        return out

    if signal_type not in {"acceleration", "accel", "acc", "g", "m/s2", "mm/s2"}:
        raise ValueError("signal_type must be 'velocity' or 'acceleration'.")

    if x.size < 2 or fs_hz <= 0.0:
        out = np.asarray([], dtype=float)
        _lru_set(_VELOCITY_CACHE, key, out)
        return out

    if acceleration_unit in {"g", "g_peak", "gpk"}:
        a_mm_s2 = (x - float(np.mean(x))) * _G_TO_MM_PER_S2
    elif acceleration_unit in {"m/s2", "m/s^2", "mps2"}:
        a_mm_s2 = (x - float(np.mean(x))) * 1000.0
    elif acceleration_unit in {"mm/s2", "mm/s^2", "mmps2"}:
        a_mm_s2 = x - float(np.mean(x))
    else:
        raise ValueError("Unsupported acceleration_unit. Use 'g', 'm/s2', or 'mm/s2'.")

    spec = np.fft.rfft(a_mm_s2)
    freqs = np.fft.rfftfreq(a_mm_s2.size, d=1.0 / fs_hz)
    omega = 2.0 * np.pi * freqs
    vel_spec = np.zeros_like(spec, dtype=complex)
    mask = (omega > _EPS) & (freqs >= integration_low_cut_hz)
    vel_spec[mask] = spec[mask] / (1j * omega[mask])
    vel_spec[0] = 0.0
    velocity = np.fft.irfft(vel_spec, n=a_mm_s2.size)
    out = (velocity - float(np.mean(velocity))).astype(float)
    _lru_set(_VELOCITY_CACHE, key, out)
    return out


def one_sided_spectrum(x: np.ndarray, fs_hz: float) -> Tuple[np.ndarray, np.ndarray]:
    arr = _normalize_waveform(x)
    fs_hz = float(fs_hz)
    key = ("spectrum", _digest_float_array(arr), round(fs_hz, 9))
    cached = _lru_get(_SPECTRUM_CACHE, key)
    if cached is not None:
        return cached

    if arr.size < 8 or fs_hz <= 0.0:
        out = (np.asarray([], dtype=float), np.asarray([], dtype=float))
        _lru_set(_SPECTRUM_CACHE, key, out)
        return out

    y = arr - float(np.mean(arr))
    n = y.size
    window = np.hanning(n)
    coherent_gain = max(float(np.sum(window) / n), _EPS)
    fft = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs_hz)
    amps = (2.0 / (n * coherent_gain)) * np.abs(fft)
    if amps.size:
        amps[0] = 0.0
    out = (freqs[1:].astype(float), amps[1:].astype(float))
    _lru_set(_SPECTRUM_CACHE, key, out)
    return out


def normalized_autocorr_fft(x: np.ndarray) -> np.ndarray:
    arr = _normalize_waveform(x)
    key = ("autocorr", _digest_float_array(arr))
    cached = _lru_get(_AUTOCORR_CACHE, key)
    if cached is not None:
        return cached

    if arr.size < 8:
        out = np.asarray([], dtype=float)
        _lru_set(_AUTOCORR_CACHE, key, out)
        return out

    y = arr - float(np.mean(arr))
    std = float(np.std(y))
    if std <= _EPS:
        out = np.asarray([], dtype=float)
        _lru_set(_AUTOCORR_CACHE, key, out)
        return out

    y = y / std
    n = y.size
    nfft = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(y, n=nfft)
    ac = np.fft.irfft(f * np.conjugate(f), n=nfft)[:n]
    if ac.size == 0 or ac[0] <= _EPS:
        out = np.asarray([], dtype=float)
        _lru_set(_AUTOCORR_CACHE, key, out)
        return out

    out = ac / ac[0]
    _lru_set(_AUTOCORR_CACHE, key, out)
    return out


def best_autocorr_near_lag(x: np.ndarray, lag: int, window_pct: float = 0.18) -> float:
    lag = int(lag)
    if lag < 1:
        return 0.0

    ac = normalized_autocorr_fft(x)
    if ac.size < lag + 2:
        return 0.0

    lo = max(1, int(lag * (1.0 - float(window_pct))))
    hi = min(ac.size, int(lag * (1.0 + float(window_pct))) + 1)
    if hi <= lo:
        return 0.0

    return float(max(0.0, min(1.0, np.max(ac[lo:hi]))))
