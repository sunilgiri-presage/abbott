from __future__ import annotations

import math
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import numpy as np
from app.auto_diagnostics.signal_feature_cache_v4 import (
    normalized_autocorr_fft as _cached_normalized_autocorr_fft,
)
from scipy.signal import butter, detrend, filtfilt, hilbert


_EPS = 1e-12
_BEARING_FAMILIES = ("bpfo", "bpfi", "bsf", "ftf")
NumericOrMap = Union[float, int, Mapping[str, Union[float, int]]]


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    return float(num / den) if abs(den) > _EPS else float(default)


def _score_linear(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    return _clamp((float(value) - low) / (high - low), 0.0, 1.0)


def _rms(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(values ** 2)))


def _top_mean(values: List[float], n: int = 3) -> float:
    clean = sorted([float(v) for v in values if np.isfinite(v)], reverse=True)
    if not clean:
        return 0.0
    return float(mean(clean[: min(n, len(clean))]))


def _confidence_from_score(score: float) -> str:
    if score >= 70.0:
        return "high"
    if score >= 45.0:
        return "medium"
    if score >= 20.0:
        return "low"
    return "none"


def _as_float_array(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0:
        return arr

    finite = np.isfinite(arr)
    if not np.all(finite):
        if np.any(finite):
            fill = float(np.nanmedian(arr[finite]))
            arr = arr.copy()
            arr[~finite] = fill
        else:
            return np.asarray([], dtype=float)

    return arr


def _crest_factor(x: np.ndarray) -> float:
    x = _as_float_array(x)
    if x.size == 0:
        return 0.0
    rms = _rms(x)
    return float(np.max(np.abs(x)) / rms) if rms > _EPS else 0.0


def _kurtosis_excess(x: np.ndarray) -> float:
    x = _as_float_array(x)
    if x.size < 4:
        return 0.0

    std = float(np.std(x))
    if std <= _EPS:
        return 0.0

    z = (x - np.mean(x)) / std
    return float(np.mean(z ** 4) - 3.0)


_AXIS_ALIASES = {
    "h": "horizontal",
    "hor": "horizontal",
    "horizontal": "horizontal",
    "v": "vertical",
    "ver": "vertical",
    "vertical": "vertical",
    "a": "axial",
    "ax": "axial",
    "axial": "axial",
    "x": "x",
    "y": "y",
    "z": "z",
    "radial": "radial",
}


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return _AXIS_ALIASES.get(text, text or "axis")


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)

    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}

    if data.ndim != 2:
        raise ValueError("Acceleration TWF array must be 1-D or 2-D.")

    if data.shape[1] == 3:
        axis_names = axes or ["x", "y", "z"]
        return {
            _norm_axis_name(axis_names[i]): _as_float_array(data[:, i])
            for i in range(3)
        }

    if data.shape[0] == 3:
        axis_names = axes or ["x", "y", "z"]
        return {
            _norm_axis_name(axis_names[i]): _as_float_array(data[i, :])
            for i in range(3)
        }

    raise ValueError("2-D acceleration TWF must have one dimension of size 3 for tri-axial data.")


def _looks_like_axis_map(obj: Mapping[str, Any]) -> bool:
    if not obj:
        return False

    keys = {_norm_axis_name(k) for k in obj.keys()}
    axis_like = bool(keys & {"x", "y", "z", "horizontal", "vertical", "axial", "radial"})
    values_are_not_nested_maps = all(not isinstance(v, Mapping) for v in obj.values())
    return axis_like and values_are_not_nested_maps


def _normalize_acceleration_twf(
    acceleration_twf: Any,
    axes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, np.ndarray]]:
    if isinstance(acceleration_twf, Mapping):
        if _looks_like_axis_map(acceleration_twf):
            return {
                "endpoint_1": {
                    _norm_axis_name(axis): _as_float_array(values)
                    for axis, values in acceleration_twf.items()
                }
            }

        endpoints: Dict[str, Dict[str, np.ndarray]] = {}
        for endpoint_id, endpoint_data in acceleration_twf.items():
            endpoint_key = str(endpoint_id)
            if isinstance(endpoint_data, Mapping):
                endpoints[endpoint_key] = {
                    _norm_axis_name(axis): _as_float_array(values)
                    for axis, values in endpoint_data.items()
                }
            else:
                endpoints[endpoint_key] = _array_to_axis_map(endpoint_data, axes=axes)
        return endpoints

    return {"endpoint_1": _array_to_axis_map(acceleration_twf, axes=axes)}


def _one_sided_spectrum(x: np.ndarray, fs_hz: float) -> Tuple[np.ndarray, np.ndarray]:
    x = _as_float_array(x)
    fs_hz = float(fs_hz)

    if x.size < 8 or fs_hz <= 0.0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    y = detrend(x, type="linear") if x.size >= 16 else x - np.mean(x)
    n = y.size
    window = np.hanning(n)
    coherent_gain = max(float(np.sum(window) / n), _EPS)

    fft = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs_hz)
    amps = (2.0 / (n * coherent_gain)) * np.abs(fft)
    if amps.size:
        amps[0] = 0.0

    return freqs[1:], amps[1:]


def _peak_at(
    freqs_hz: np.ndarray,
    amplitudes: np.ndarray,
    target_hz: float,
    tolerance_hz: float,
) -> Tuple[float, float]:
    if target_hz <= 0.0 or tolerance_hz <= 0.0 or freqs_hz.size == 0 or amplitudes.size == 0:
        return 0.0, 0.0

    lo = int(np.searchsorted(freqs_hz, target_hz - tolerance_hz, side="left"))
    hi = int(np.searchsorted(freqs_hz, target_hz + tolerance_hz, side="right"))
    if hi <= lo:
        return 0.0, 0.0

    local_amps = amplitudes[lo:hi]
    if local_amps.size == 0:
        return 0.0, 0.0

    idx = int(np.argmax(local_amps))
    return float(freqs_hz[lo + idx]), float(local_amps[idx])


def _bandpass_for_envelope(
    x: np.ndarray,
    fs_hz: float,
    shaft_hz: float,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
) -> np.ndarray:
    x = _as_float_array(x)
    if x.size < 32:
        return x - np.mean(x) if x.size else x

    y = detrend(x, type="linear")
    nyq = 0.5 * float(fs_hz)
    if nyq <= 0.0:
        return y

    if envelope_band_hz is not None:
        low_hz, high_hz = envelope_band_hz
    elif nyq >= 1000.0:
        low_hz = max(500.0, 5.0 * shaft_hz)
        high_hz = min(0.90 * nyq, 10000.0)
    else:
        low_hz = max(10.0, 3.0 * shaft_hz)
        high_hz = 0.90 * nyq

    low_hz = float(max(0.0, low_hz))
    high_hz = float(min(high_hz, 0.95 * nyq))
    if not (0.0 < low_hz < high_hz < nyq):
        return y

    try:
        b, a = butter(N=4, Wn=[low_hz / nyq, high_hz / nyq], btype="bandpass")
        padlen = 3 * max(len(a), len(b))
        if y.size <= padlen:
            return y
        return filtfilt(b, a, y)
    except Exception:
        return y


def _envelope_spectrum(
    x: np.ndarray,
    fs_hz: float,
    shaft_hz: float,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    filtered = _bandpass_for_envelope(
        x=x,
        fs_hz=fs_hz,
        shaft_hz=shaft_hz,
        envelope_band_hz=envelope_band_hz,
    )

    if filtered.size < 16:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    envelope = np.abs(hilbert(filtered))
    envelope = envelope - np.mean(envelope)
    return _one_sided_spectrum(envelope, fs_hz)


def _impact_autocorr_series(x: np.ndarray) -> np.ndarray:
    x = _as_float_array(x)
    if x.size < 16:
        return np.asarray([], dtype=float)
    impact_series = np.abs(np.diff(x, prepend=x[0]))
    return _cached_normalized_autocorr_fft(impact_series)


def _global_impact_periodicity(x: np.ndarray, fs_hz: float) -> float:
    ac = _impact_autocorr_series(x)
    if ac.size < 8 or fs_hz <= 0.0:
        return 0.0

    min_lag = max(2, int(0.002 * fs_hz))
    max_lag = min(ac.size, int(1.0 * fs_hz))
    if max_lag <= min_lag:
        max_lag = ac.size
    if max_lag <= min_lag:
        return 0.0

    return _clamp(float(math.sqrt(max(0.0, np.max(ac[min_lag:max_lag])))), 0.0, 1.0)


def _target_impact_periodicity(
    x: np.ndarray,
    fs_hz: float,
    target_hz: float,
    window_pct: float = 0.18,
) -> float:
    if fs_hz <= 0.0 or target_hz <= 0.0:
        return 0.0

    ac = _impact_autocorr_series(x)
    if ac.size < 8:
        return 0.0

    lag = int(round(fs_hz / target_hz))
    if lag < 1 or lag >= ac.size:
        return 0.0

    lo = max(1, int(lag * (1.0 - window_pct)))
    hi = min(ac.size, int(lag * (1.0 + window_pct)) + 1)
    if hi <= lo:
        return 0.0

    return _clamp(float(np.max(ac[lo:hi])), 0.0, 1.0)


def _normalize_bearing_fault_frequencies(
    bearing_fault_frequencies: Mapping[str, Any],
    rpm: float,
    fault_frequency_units: str = "hz",
    bsf_order_multiplier: float = 2.0,
) -> Dict[str, float]:
    if not isinstance(bearing_fault_frequencies, Mapping):
        raise ValueError("bearing_fault_frequencies must be a dictionary-like object.")

    shaft_hz = float(rpm) / 60.0 if rpm else 0.0
    units = str(fault_frequency_units or "hz").strip().lower()
    out: Dict[str, float] = {}

    for family in _BEARING_FAMILIES:
        raw_value = None
        for candidate_key in (
            family,
            family.upper(),
            f"{family}_hz",
            f"{family.upper()}_HZ",
            f"{family}_order",
            f"{family.upper()}_ORDER",
        ):
            if candidate_key in bearing_fault_frequencies:
                raw_value = bearing_fault_frequencies[candidate_key]
                break

        if raw_value is None:
            continue

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue

        if value <= 0.0:
            continue

        if units in {"order", "orders", "x", "multiple"}:
            multiplier = bsf_order_multiplier if family == "bsf" else 1.0
            out[family] = value * shaft_hz * multiplier
        else:
            out[family] = value

    return out


def _envelope_harmonic_hit_score(
    env_freqs_hz: np.ndarray,
    env_amps: np.ndarray,
    target_hz: float,
    tolerance_hz: float,
    harmonics: int = 4,
) -> Tuple[float, int, List[Dict[str, float]]]:
    if target_hz <= 0.0 or tolerance_hz <= 0.0 or env_freqs_hz.size == 0 or env_amps.size == 0:
        return 0.0, 0, []

    env_rms = max(_rms(env_amps), _EPS)
    hits = 0
    strengths: List[float] = []
    details: List[Dict[str, float]] = []

    for order in range(1, harmonics + 1):
        harmonic_hz = order * target_hz
        if harmonic_hz > env_freqs_hz[-1]:
            details.append({
                "order": float(order),
                "target_hz": float(harmonic_hz),
                "peak_hz": 0.0,
                "peak_amp": 0.0,
                "amp_over_env_rms": 0.0,
                "score_0_1": 0.0,
            })
            strengths.append(0.0)
            continue

        peak_hz, peak_amp = _peak_at(env_freqs_hz, env_amps, harmonic_hz, tolerance_hz)
        amp_ratio = _safe_ratio(peak_amp, env_rms)
        strength = _score_linear(amp_ratio, 1.1, 4.0)
        if strength > 0.2:
            hits += 1

        strengths.append(strength)
        details.append({
            "order": float(order),
            "target_hz": float(harmonic_hz),
            "peak_hz": float(peak_hz),
            "peak_amp": float(peak_amp),
            "amp_over_env_rms": float(amp_ratio),
            "score_0_1": float(strength),
        })

    env_score = 100.0 * (
        0.65 * _top_mean(strengths, n=3)
        + 0.35 * _score_linear(float(hits), 1.0, float(harmonics))
    )
    return float(env_score), int(hits), details


def _extract_acceleration_axis_features(
    x: np.ndarray,
    fs_hz: float,
    rpm: float,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    x = _as_float_array(x)

    if x.size < 128:
        raise ValueError("Need at least 128 samples for bearing-frequency detection.")

    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")

    shaft_hz = float(rpm) / 60.0 if rpm else 0.0
    acc_freqs, acc_amps = _one_sided_spectrum(x, fs_hz)
    env_freqs, env_amps = _envelope_spectrum(
        x=x,
        fs_hz=fs_hz,
        shaft_hz=shaft_hz,
        envelope_band_hz=envelope_band_hz,
    )

    acc_rms = max(_rms(acc_amps), _EPS)
    if acc_freqs.size:
        hf_start_hz = max(5.0 * shaft_hz, 50.0 if acc_freqs[-1] >= 100.0 else 3.0 * shaft_hz)
        hf_mask = acc_freqs >= hf_start_hz
        hf_rms_ratio = _safe_ratio(_rms(acc_amps[hf_mask]) if np.any(hf_mask) else 0.0, acc_rms)
    else:
        hf_start_hz = 0.0
        hf_rms_ratio = 0.0

    freq_resolution_hz = (
        float(np.median(np.diff(env_freqs)))
        if env_freqs.size > 1
        else max(0.1, 0.03 * shaft_hz)
    )

    return {
        "samples": int(x.size),
        "duration_s": float(x.size / fs_hz),
        "shaft_hz": float(shaft_hz),
        "acc_freqs_hz": acc_freqs,
        "acc_spectrum": acc_amps,
        "env_freqs_hz": env_freqs,
        "env_spectrum": env_amps,
        "freq_resolution_hz": float(freq_resolution_hz),
        "acc_spectrum_rms": float(acc_rms),
        "hf_start_hz": float(hf_start_hz),
        "hf_rms_ratio": float(hf_rms_ratio),
        "crest_factor": float(_crest_factor(x)),
        "kurtosis_excess": float(_kurtosis_excess(x)),
        "global_impact_periodicity": float(_global_impact_periodicity(x, fs_hz)),
    }


def build_impact_axis_feature_cache(
    acceleration_twf: Any,
    sampling_frequency_hz: float,
    rpm: float,
    *,
    axes: Optional[List[str]] = None,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for impact diagnostics.")

    endpoints = _normalize_acceleration_twf(acceleration_twf, axes=axes)
    feature_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for endpoint_id, axis_map in endpoints.items():
        endpoint_key = str(endpoint_id)
        endpoint_cache: Dict[str, Dict[str, Any]] = {}
        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            x = _as_float_array(axis_values)
            row: Dict[str, Any] = {"x": x, "features": None, "error": None}
            try:
                row["features"] = _extract_acceleration_axis_features(
                    x=x,
                    fs_hz=fs_hz,
                    rpm=rpm,
                    envelope_band_hz=envelope_band_hz,
                )
            except Exception as exc:
                row["error"] = str(exc)
            endpoint_cache[axis] = row
        feature_cache[endpoint_key] = endpoint_cache

    return feature_cache


def _default_axis_weight(axis: str) -> float:
    axis = _norm_axis_name(axis)
    if axis == "axial":
        return 0.75
    return 1.0


def _score_bearing_family_on_axis(
    family: str,
    target_hz: float,
    axis: str,
    x: np.ndarray,
    fs_hz: float,
    features: Dict[str, Any],
    target_tolerance_pct: float,
    harmonics: int,
    axis_weight: float,
) -> Dict[str, Any]:
    env_freqs = features["env_freqs_hz"]
    env_amps = features["env_spectrum"]
    shaft_hz = float(features["shaft_hz"])
    df = float(features["freq_resolution_hz"])
    tolerance_hz = max(1.5 * df, abs(shaft_hz) * 0.03, abs(target_hz) * target_tolerance_pct / 100.0)

    env_score, hits, harmonic_details = _envelope_harmonic_hit_score(
        env_freqs_hz=env_freqs,
        env_amps=env_amps,
        target_hz=target_hz,
        tolerance_hz=tolerance_hz,
        harmonics=harmonics,
    )

    target_periodicity = _target_impact_periodicity(x=x, fs_hz=fs_hz, target_hz=target_hz)
    global_periodicity = float(features["global_impact_periodicity"])
    periodicity = max(target_periodicity, 0.75 * global_periodicity)

    hf = float(features["hf_rms_ratio"])
    kurt = float(features["kurtosis_excess"])
    crest = float(features["crest_factor"])
    raw_score = (
        56.0 * _score_linear(env_score, 18.0, 75.0)
        + 16.0 * _score_linear(hf, 0.7, 2.5)
        + 10.0 * _score_linear(max(kurt, 0.0), 0.4, 2.8)
        + 6.0 * _score_linear(crest, 3.4, 6.5)
        + 12.0 * _score_linear(periodicity, 0.25, 0.80)
    )
    score = _clamp(raw_score * axis_weight, 0.0, 100.0)

    return {
        "fault": f"bearing_{family}",
        "family": family.upper(),
        "target_hz": float(target_hz),
        "axis": axis,
        "score": float(score),
        "confidence": _confidence_from_score(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "envelope_score": float(env_score),
            "envelope_hits": float(hits),
            "tolerance_hz": float(tolerance_hz),
            "hf_rms_ratio": hf,
            "kurtosis_excess": kurt,
            "crest_factor": crest,
            "target_impact_periodicity": float(target_periodicity),
            "global_impact_periodicity": float(global_periodicity),
            "used_impact_periodicity": float(periodicity),
            "axis_weight": float(axis_weight),
        },
        "harmonic_details": harmonic_details,
        "evidence": (
            f"{family.upper()}={target_hz:.2f} Hz on {axis}: "
            f"score={score:.1f}, env_score={env_score:.1f}, "
            f"hits={hits}/{harmonics}, HF={hf:.2f}, "
            f"kurtosis={kurt:.2f}, crest={crest:.2f}, "
            f"periodicity={periodicity:.2f}"
        ),
    }


def detect_bearing_fault_frequencies(
    acceleration_twf: Any,
    sampling_frequency_hz: float,
    rpm: float,
    bearing_fault_frequencies: Mapping[str, Any],
    *,
    asset_id: Optional[str] = None,
    fault_frequency_units: str = "hz",
    axes: Optional[List[str]] = None,
    min_score: float = 20.0,
    target_tolerance_pct: float = 3.0,
    harmonics: int = 4,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
    axis_weights: Optional[Mapping[str, float]] = None,
    axis_feature_cache: Optional[Mapping[str, Mapping[str, Mapping[str, Any]]]] = None,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)

    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")

    if rpm <= 0.0:
        raise ValueError("rpm must be positive for bearing-frequency detection.")

    fault_freqs_hz = _normalize_bearing_fault_frequencies(
        bearing_fault_frequencies=bearing_fault_frequencies,
        rpm=rpm,
        fault_frequency_units=fault_frequency_units,
    )

    if not fault_freqs_hz:
        raise ValueError("No valid bearing fault frequencies were provided. Expected BPFO/BPFI/BSF/FTF in Hz or orders.")

    if axis_feature_cache is None:
        axis_feature_cache_map = build_impact_axis_feature_cache(
            acceleration_twf=acceleration_twf,
            sampling_frequency_hz=fs_hz,
            rpm=rpm,
            axes=axes,
            envelope_band_hz=envelope_band_hz,
        )
    else:
        axis_feature_cache_map = {
            str(endpoint_id): {str(axis_name): dict(row) for axis_name, row in (axis_rows or {}).items()}
            for endpoint_id, axis_rows in axis_feature_cache.items()
        }

    shaft_hz = rpm / 60.0
    endpoint_results: Dict[str, Any] = {}
    endpoint_family_scores: Dict[str, List[Dict[str, Any]]] = {family: [] for family in fault_freqs_hz}

    for endpoint_id, axis_map in axis_feature_cache_map.items():
        endpoint_results[endpoint_id] = {"axes": {}, "fault_summary": {}}
        endpoint_axis_family_scores: Dict[str, List[Dict[str, Any]]] = {family: [] for family in fault_freqs_hz}

        for axis_name, axis_row in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "faults": [], "error": None}

            try:
                x = _as_float_array(axis_row.get("x"))
                features = axis_row.get("features")
                if not isinstance(features, Mapping):
                    raise ValueError(str(axis_row.get("error") or "Failed to prepare axis features."))

                axis_result["valid"] = True
                axis_result["samples"] = features["samples"]
                axis_result["duration_s"] = features["duration_s"]
                axis_result["hf_start_hz"] = features["hf_start_hz"]
                axis_result["base_metrics"] = {
                    "hf_rms_ratio": features["hf_rms_ratio"],
                    "kurtosis_excess": features["kurtosis_excess"],
                    "crest_factor": features["crest_factor"],
                    "global_impact_periodicity": features["global_impact_periodicity"],
                    "freq_resolution_hz": features["freq_resolution_hz"],
                }

                if axis_weights and axis in axis_weights:
                    axis_weight = float(axis_weights[axis])
                else:
                    axis_weight = _default_axis_weight(axis)

                for family, target_hz in fault_freqs_hz.items():
                    family_result = _score_bearing_family_on_axis(
                        family=family,
                        target_hz=float(target_hz),
                        axis=axis,
                        x=x,
                        fs_hz=fs_hz,
                        features=features,
                        target_tolerance_pct=target_tolerance_pct,
                        harmonics=harmonics,
                        axis_weight=axis_weight,
                    )
                    axis_result["faults"].append(family_result)
                    endpoint_axis_family_scores[family].append({
                        "endpoint_id": endpoint_id,
                        "axis": axis,
                        **family_result,
                    })
            except Exception as exc:
                axis_result["error"] = str(exc)

            endpoint_results[endpoint_id]["axes"][axis] = axis_result

        for family, rows in endpoint_axis_family_scores.items():
            axis_scores = [float(r["score"]) for r in rows]
            supporting_axes = [r for r in rows if float(r["score"]) >= 45.0]
            if not axis_scores:
                endpoint_score = 0.0
            else:
                endpoint_score = _clamp(max(axis_scores) + 8.0 * _score_linear(len(supporting_axes), 2.0, 3.0), 0.0, 100.0)

            best_axis = max(rows, key=lambda r: r["score"]) if rows else None
            endpoint_fault_summary = {
                "fault": f"bearing_{family}",
                "family": family.upper(),
                "target_hz": float(fault_freqs_hz[family]),
                "score": float(endpoint_score),
                "confidence": _confidence_from_score(endpoint_score),
                "possible": bool(endpoint_score >= min_score),
                "supporting_axes": [r["axis"] for r in supporting_axes],
                "best_axis": best_axis["axis"] if best_axis else None,
                "best_axis_score": float(best_axis["score"]) if best_axis else 0.0,
                "best_axis_evidence": best_axis["evidence"] if best_axis else "",
            }
            endpoint_results[endpoint_id]["fault_summary"][family] = endpoint_fault_summary
            endpoint_family_scores[family].append({"endpoint_id": endpoint_id, **endpoint_fault_summary})

    possible_faults: List[Dict[str, Any]] = []
    for family, endpoint_rows in endpoint_family_scores.items():
        if not endpoint_rows:
            continue

        best_endpoint = max(endpoint_rows, key=lambda r: r["score"])
        supporting_endpoints = [row for row in endpoint_rows if float(row["score"]) >= 45.0]
        supporting_axis_count = 0
        for endpoint_result in endpoint_results.values():
            for axis_result in endpoint_result["axes"].values():
                for fault_row in axis_result.get("faults", []):
                    if fault_row["family"].lower() == family and fault_row["score"] >= 45.0:
                        supporting_axis_count += 1

        asset_score = _clamp(
            float(best_endpoint["score"])
            + 10.0 * _score_linear(len(supporting_endpoints), 2.0, 4.0)
            + 5.0 * _score_linear(supporting_axis_count, 2.0, 6.0),
            0.0,
            100.0,
        )

        possible_faults.append({
            "fault": f"bearing_{family}",
            "family": family.upper(),
            "target_hz": float(fault_freqs_hz[family]),
            "score": float(asset_score),
            "confidence": _confidence_from_score(asset_score),
            "possible": bool(asset_score >= min_score),
            "best_endpoint": best_endpoint["endpoint_id"],
            "best_axis": best_endpoint.get("best_axis"),
            "supporting_endpoints": [row["endpoint_id"] for row in supporting_endpoints],
            "supporting_axis_count": int(supporting_axis_count),
            "evidence": best_endpoint.get("best_axis_evidence", ""),
        })

    possible_faults = [fault for fault in possible_faults if fault["score"] >= min_score]
    possible_faults.sort(key=lambda row: row["score"], reverse=True)
    primary_fault = possible_faults[0] if possible_faults else None

    return {
        "asset_id": asset_id,
        "rpm": float(rpm),
        "shaft_hz": float(shaft_hz),
        "sampling_frequency_hz": float(fs_hz),
        "bearing_fault_frequencies_hz": {family.upper(): float(freq) for family, freq in fault_freqs_hz.items()},
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "endpoint_results": endpoint_results,
        "limitations": [
            "This function uses acceleration TWF only; it does not use temperature, velocity, phase, load, or process data.",
            "Bearing-family confidence depends on correct RPM, sampling frequency, and BPFO/BPFI/BSF/FTF values.",
            "Envelope band is automatically selected unless envelope_band_hz is provided; tune it per sensor type and sampling rate.",
            "Multiple endpoints are evaluated locally. The asset summary reports repeatability, but does not perform shaft-style cross-endpoint correlation.",
        ],
    }


def _lookup_endpoint_numeric(
    value: Optional[NumericOrMap],
    endpoint_id: str,
) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, Mapping):
        if endpoint_id not in value:
            return None
        try:
            number = float(value[endpoint_id])
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if np.isfinite(number) else None


def _resolve_temperature_delta_c(
    endpoint_id: str,
    surface_temperature_c: Optional[NumericOrMap] = None,
    baseline_temperature_c: Optional[NumericOrMap] = None,
    temperature_delta_c: Optional[NumericOrMap] = None,
) -> float:
    direct_delta = _lookup_endpoint_numeric(temperature_delta_c, endpoint_id)
    if direct_delta is not None:
        return float(direct_delta)

    surface = _lookup_endpoint_numeric(surface_temperature_c, endpoint_id)
    baseline = _lookup_endpoint_numeric(baseline_temperature_c, endpoint_id)
    if surface is not None and baseline is not None:
        return float(surface - baseline)

    if surface is not None and isinstance(surface_temperature_c, Mapping):
        peer_values: List[float] = []
        for key, raw_value in surface_temperature_c.items():
            if str(key) == str(endpoint_id):
                continue
            try:
                peer_value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(peer_value):
                peer_values.append(peer_value)

        if peer_values:
            return float(surface - float(np.median(peer_values)))

    return 0.0


def _axis_synchronous_order_ratio(features: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    acc_freqs = features["acc_freqs_hz"]
    acc_amps = features["acc_spectrum"]
    shaft_hz = float(features["shaft_hz"])
    df = float(features["freq_resolution_hz"])
    acc_rms = max(float(features["acc_spectrum_rms"]), _EPS)

    if shaft_hz <= 0.0 or acc_freqs.size == 0:
        return 0.0, {"amp_1x": 0.0, "amp_2x": 0.0, "amp_3x": 0.0}

    tolerance_hz = max(1.5 * df, 0.03 * shaft_hz)
    _, amp_1x = _peak_at(acc_freqs, acc_amps, 1.0 * shaft_hz, tolerance_hz)
    _, amp_2x = _peak_at(acc_freqs, acc_amps, 2.0 * shaft_hz, tolerance_hz)
    _, amp_3x = _peak_at(acc_freqs, acc_amps, 3.0 * shaft_hz, tolerance_hz)
    ratio = (amp_1x + amp_2x + amp_3x) / acc_rms

    return float(ratio), {
        "amp_1x": float(amp_1x),
        "amp_2x": float(amp_2x),
        "amp_3x": float(amp_3x),
        "order_123_ratio": float(ratio),
        "order_tolerance_hz": float(tolerance_hz),
    }


def _periodic_bearing_defect_evidence(
    x: np.ndarray,
    fs_hz: float,
    rpm: float,
    features: Dict[str, Any],
    bearing_fault_frequencies: Optional[Mapping[str, Any]],
    *,
    fault_frequency_units: str = "hz",
    target_tolerance_pct: float = 3.0,
    harmonics: int = 4,
) -> Dict[str, Any]:
    empty = {
        "provided": False,
        "best_defect_family": None,
        "best_defect_target_hz": 0.0,
        "best_defect_env_score": 0.0,
        "best_defect_env_hits": 0,
        "best_defect_periodicity": 0.0,
        "raceway_fraction": 0.0,
        "families": {},
    }

    if not bearing_fault_frequencies:
        return empty

    fault_freqs_hz = _normalize_bearing_fault_frequencies(
        bearing_fault_frequencies=bearing_fault_frequencies,
        rpm=rpm,
        fault_frequency_units=fault_frequency_units,
    )
    if not fault_freqs_hz:
        return empty

    env_freqs = features["env_freqs_hz"]
    env_amps = features["env_spectrum"]
    shaft_hz = float(features["shaft_hz"])
    df = float(features["freq_resolution_hz"])
    family_rows: Dict[str, Dict[str, Any]] = {}

    for family, target_hz in fault_freqs_hz.items():
        target_hz = float(target_hz)
        tolerance_hz = max(
            1.5 * df,
            abs(shaft_hz) * 0.03,
            abs(target_hz) * target_tolerance_pct / 100.0,
        )
        env_score, hits, harmonic_details = _envelope_harmonic_hit_score(
            env_freqs_hz=env_freqs,
            env_amps=env_amps,
            target_hz=target_hz,
            tolerance_hz=tolerance_hz,
            harmonics=harmonics,
        )
        defect_periodicity = _target_impact_periodicity(x=x, fs_hz=fs_hz, target_hz=target_hz)
        family_rows[family] = {
            "family": family.upper(),
            "target_hz": target_hz,
            "env_score": float(env_score),
            "env_hits": int(hits),
            "defect_periodicity": float(defect_periodicity),
            "tolerance_hz": float(tolerance_hz),
            "harmonic_details": harmonic_details,
        }

    if not family_rows:
        return empty

    best_family = max(
        family_rows,
        key=lambda key: (
            float(family_rows[key]["env_score"]),
            float(family_rows[key]["defect_periodicity"]),
        ),
    )
    best = family_rows[best_family]
    total_env_score = sum(float(row["env_score"]) for row in family_rows.values())
    raceway_env_score = sum(
        float(family_rows[key]["env_score"])
        for key in ("bpfo", "bpfi")
        if key in family_rows
    )
    raceway_fraction = raceway_env_score / total_env_score if total_env_score > _EPS else 0.0

    return {
        "provided": True,
        "best_defect_family": best["family"],
        "best_defect_target_hz": float(best["target_hz"]),
        "best_defect_env_score": float(best["env_score"]),
        "best_defect_env_hits": int(best["env_hits"]),
        "best_defect_periodicity": float(best["defect_periodicity"]),
        "raceway_fraction": float(raceway_fraction),
        "families": family_rows,
    }


def _periodic_bearing_defect_evidence_from_axis_faults(
    bearing_axis_faults: Optional[List[Mapping[str, Any]]],
) -> Dict[str, Any]:
    empty = {
        "provided": False,
        "best_defect_family": None,
        "best_defect_target_hz": 0.0,
        "best_defect_env_score": 0.0,
        "best_defect_env_hits": 0,
        "best_defect_periodicity": 0.0,
        "raceway_fraction": 0.0,
        "families": {},
    }
    if not bearing_axis_faults:
        return empty

    family_rows: Dict[str, Dict[str, Any]] = {}
    for row in bearing_axis_faults:
        if not isinstance(row, Mapping):
            continue
        family_label = str(row.get("family") or "").strip().lower()
        if not family_label:
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
        env_score = float(metrics.get("envelope_score") or 0.0)
        env_hits = int(metrics.get("envelope_hits") or 0)
        defect_periodicity = float(metrics.get("target_impact_periodicity") or 0.0)
        tolerance_hz = float(metrics.get("tolerance_hz") or 0.0)
        harmonic_details = row.get("harmonic_details") if isinstance(row.get("harmonic_details"), list) else []
        target_hz = float(row.get("target_hz") or 0.0)

        family_rows[family_label] = {
            "family": family_label.upper(),
            "target_hz": target_hz,
            "env_score": env_score,
            "env_hits": env_hits,
            "defect_periodicity": defect_periodicity,
            "tolerance_hz": tolerance_hz,
            "harmonic_details": harmonic_details,
        }

    if not family_rows:
        return empty

    best_family = max(
        family_rows,
        key=lambda key: (
            float(family_rows[key]["env_score"]),
            float(family_rows[key]["defect_periodicity"]),
        ),
    )
    best = family_rows[best_family]
    total_env_score = sum(float(row["env_score"]) for row in family_rows.values())
    raceway_env_score = sum(
        float(family_rows[key]["env_score"])
        for key in ("bpfo", "bpfi")
        if key in family_rows
    )
    raceway_fraction = raceway_env_score / total_env_score if total_env_score > _EPS else 0.0

    return {
        "provided": True,
        "best_defect_family": best["family"],
        "best_defect_target_hz": float(best["target_hz"]),
        "best_defect_env_score": float(best["env_score"]),
        "best_defect_env_hits": int(best["env_hits"]),
        "best_defect_periodicity": float(best["defect_periodicity"]),
        "raceway_fraction": float(raceway_fraction),
        "families": family_rows,
    }


def _bearing_axis_fault_rows_from_diagnosis(
    bearing_diagnosis: Optional[Mapping[str, Any]],
    endpoint_id: str,
    axis: str,
) -> List[Mapping[str, Any]]:
    if not isinstance(bearing_diagnosis, Mapping):
        return []
    endpoint_results = bearing_diagnosis.get("endpoint_results")
    if not isinstance(endpoint_results, Mapping):
        return []
    endpoint_row = endpoint_results.get(str(endpoint_id))
    if not isinstance(endpoint_row, Mapping):
        return []
    axes_map = endpoint_row.get("axes")
    if not isinstance(axes_map, Mapping):
        return []

    axis_key = _norm_axis_name(axis)
    axis_row = axes_map.get(axis_key)
    if not isinstance(axis_row, Mapping):
        axis_row = axes_map.get(str(axis))
    if not isinstance(axis_row, Mapping):
        return []

    faults = axis_row.get("faults")
    if not isinstance(faults, list):
        return []
    return [row for row in faults if isinstance(row, Mapping)]


def _axis_weight_for_lubrication(
    axis: str,
    axis_weights: Optional[Mapping[str, float]] = None,
) -> float:
    axis_key = str(axis).strip().lower()
    if axis_weights:
        if axis_key in axis_weights:
            return float(axis_weights[axis_key])
        normalized = _norm_axis_name(axis_key)
        if normalized in axis_weights:
            return float(axis_weights[normalized])

    normalized = _norm_axis_name(axis_key)
    if normalized == "axial":
        return 0.75
    return 1.0


def _score_lubrication_axis(
    *,
    endpoint_id: str,
    axis: str,
    x: np.ndarray,
    fs_hz: float,
    rpm: float,
    features: Dict[str, Any],
    temp_delta_c: float,
    bearing_fault_frequencies: Optional[Mapping[str, Any]],
    bearing_axis_faults: Optional[List[Mapping[str, Any]]],
    fault_frequency_units: str,
    target_tolerance_pct: float,
    harmonics: int,
    axis_weight: float,
) -> Dict[str, Any]:
    impact_periodicity = float(features["global_impact_periodicity"])
    random_impact = 1.0 - impact_periodicity
    order_123_ratio, order_metrics = _axis_synchronous_order_ratio(features)

    hf_ratio = float(features["hf_rms_ratio"])
    kurtosis_excess = float(features["kurtosis_excess"])
    crest_factor = float(features["crest_factor"])

    hf_score = _score_linear(hf_ratio, 0.6, 2.5)
    kurtosis_score = _score_linear(max(kurtosis_excess, 0.0), 0.4, 2.5)
    crest_score = _score_linear(crest_factor, 3.4, 6.5)
    temp_score = _score_linear(temp_delta_c, 4.0, 18.0)
    low_shaft_order_score = 1.0 - _score_linear(order_123_ratio, 2.5, 7.0)
    random_impact_score = _score_linear(random_impact, 0.25, 0.80)

    raw_score = (
        28.0 * hf_score
        + 14.0 * kurtosis_score
        + 12.0 * crest_score
        + 12.0 * temp_score
        + 12.0 * low_shaft_order_score
        + 22.0 * random_impact_score
    )
    limitations: List[str] = []

    if max(hf_score, kurtosis_score, crest_score) < 0.15:
        raw_score *= 0.50
        limitations.append(
            "Reduced because random/non-periodic impact evidence is not backed by high-frequency or impulsive acceleration."
        )

    periodic_defect = _periodic_bearing_defect_evidence_from_axis_faults(bearing_axis_faults)
    if not periodic_defect["provided"]:
        periodic_defect = _periodic_bearing_defect_evidence(
            x=x,
            fs_hz=fs_hz,
            rpm=rpm,
            features=features,
            bearing_fault_frequencies=bearing_fault_frequencies,
            fault_frequency_units=fault_frequency_units,
            target_tolerance_pct=target_tolerance_pct,
            harmonics=harmonics,
        )

    if (
        periodic_defect["provided"]
        and periodic_defect["best_defect_env_score"] >= 55.0
        and impact_periodicity >= 0.30
    ):
        raw_score *= 0.62
        limitations.append(
            "Reduced because periodic bearing-defect envelope evidence is stronger than the random-impact pattern expected from pure lubrication distress."
        )

    if (
        periodic_defect["provided"]
        and periodic_defect["raceway_fraction"] >= 0.62
        and periodic_defect["best_defect_env_score"] >= 55.0
    ):
        raw_score *= 0.70
        limitations.append(
            "Reduced because raceway-family envelope content is too strong for a clean lubrication-only diagnosis."
        )

    score = _clamp(raw_score * axis_weight, 0.0, 100.0)
    return {
        "fault": "lubrication_distress",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "confidence": _confidence_from_score(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "hf_rms_ratio": hf_ratio,
            "kurtosis_excess": kurtosis_excess,
            "crest_factor": crest_factor,
            "temperature_delta_c": float(temp_delta_c),
            "waveform_impact_periodicity": impact_periodicity,
            "random_impact_ratio": float(random_impact),
            "order_123_ratio": float(order_123_ratio),
            "axis_weight": float(axis_weight),
            "hf_score_0_1": float(hf_score),
            "kurtosis_score_0_1": float(kurtosis_score),
            "crest_score_0_1": float(crest_score),
            "temperature_score_0_1": float(temp_score),
            "low_shaft_order_score_0_1": float(low_shaft_order_score),
            "random_impact_score_0_1": float(random_impact_score),
            **order_metrics,
        },
        "periodic_defect_evidence": periodic_defect,
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: lubrication score={score:.1f}, "
            f"HF={hf_ratio:.2f}, kurtosis={kurtosis_excess:.2f}, "
            f"crest={crest_factor:.2f}, random_impact={random_impact:.2f}, "
            f"impact_periodicity={impact_periodicity:.2f}, "
            f"1x+2x+3x ratio={order_123_ratio:.2f}, "
            f"temp_delta={temp_delta_c:.1f}C"
        ),
    }


def detect_lubrication_issue(
    acceleration_twf: Any,
    sampling_frequency_hz: float,
    rpm: float,
    *,
    asset_id: Optional[str] = None,
    axes: Optional[List[str]] = None,
    surface_temperature_c: Optional[NumericOrMap] = None,
    baseline_temperature_c: Optional[NumericOrMap] = None,
    temperature_delta_c: Optional[NumericOrMap] = None,
    bearing_fault_frequencies: Optional[Mapping[str, Any]] = None,
    fault_frequency_units: str = "hz",
    min_score: float = 20.0,
    target_tolerance_pct: float = 3.0,
    harmonics: int = 4,
    envelope_band_hz: Optional[Tuple[float, float]] = None,
    axis_weights: Optional[Mapping[str, float]] = None,
    axis_feature_cache: Optional[Mapping[str, Mapping[str, Mapping[str, Any]]]] = None,
    bearing_diagnosis: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)

    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for lubrication detection.")

    if axis_feature_cache is None:
        axis_feature_cache_map = build_impact_axis_feature_cache(
            acceleration_twf=acceleration_twf,
            sampling_frequency_hz=fs_hz,
            rpm=rpm,
            axes=axes,
            envelope_band_hz=envelope_band_hz,
        )
    else:
        axis_feature_cache_map = {
            str(endpoint_id): {str(axis_name): dict(row) for axis_name, row in (axis_rows or {}).items()}
            for endpoint_id, axis_rows in axis_feature_cache.items()
        }

    shaft_hz = rpm / 60.0
    endpoint_results: Dict[str, Any] = {}
    endpoint_summaries: List[Dict[str, Any]] = []
    all_axis_rows: List[Dict[str, Any]] = []

    for endpoint_id, axis_map in axis_feature_cache_map.items():
        endpoint_axis_rows: List[Dict[str, Any]] = []
        endpoint_results[endpoint_id] = {"axes": {}, "fault_summary": None}
        temp_delta = _resolve_temperature_delta_c(
            endpoint_id=endpoint_id,
            surface_temperature_c=surface_temperature_c,
            baseline_temperature_c=baseline_temperature_c,
            temperature_delta_c=temperature_delta_c,
        )

        for axis_name, axis_row in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "fault": None, "error": None}

            try:
                x = _as_float_array(axis_row.get("x"))
                features = axis_row.get("features")
                if not isinstance(features, Mapping):
                    raise ValueError(str(axis_row.get("error") or "Failed to prepare axis features."))
                axis_weight = _axis_weight_for_lubrication(axis=axis, axis_weights=axis_weights)
                bearing_axis_faults = _bearing_axis_fault_rows_from_diagnosis(
                    bearing_diagnosis=bearing_diagnosis,
                    endpoint_id=str(endpoint_id),
                    axis=axis,
                )
                fault_result = _score_lubrication_axis(
                    endpoint_id=endpoint_id,
                    axis=axis,
                    x=x,
                    fs_hz=fs_hz,
                    rpm=rpm,
                    features=features,
                    temp_delta_c=temp_delta,
                    bearing_fault_frequencies=bearing_fault_frequencies,
                    bearing_axis_faults=bearing_axis_faults,
                    fault_frequency_units=fault_frequency_units,
                    target_tolerance_pct=target_tolerance_pct,
                    harmonics=harmonics,
                    axis_weight=axis_weight,
                )
                axis_result["valid"] = True
                axis_result["samples"] = features["samples"]
                axis_result["duration_s"] = features["duration_s"]
                axis_result["hf_start_hz"] = features["hf_start_hz"]
                axis_result["fault"] = fault_result
                endpoint_axis_rows.append(fault_result)
                all_axis_rows.append(fault_result)
            except Exception as exc:
                axis_result["error"] = str(exc)

            endpoint_results[endpoint_id]["axes"][axis] = axis_result

        axis_scores = [float(row["score"]) for row in endpoint_axis_rows]
        supporting_axes = [row for row in endpoint_axis_rows if float(row["score"]) >= 45.0]
        if axis_scores:
            endpoint_score = _clamp(
                0.70 * _top_mean(axis_scores, n=3)
                + 18.0 * _score_linear(len(endpoint_axis_rows), 1.0, 3.0)
                + 12.0 * _score_linear(len(supporting_axes), 1.0, 3.0),
                0.0,
                100.0,
            )
            best_axis = max(endpoint_axis_rows, key=lambda row: row["score"])
        else:
            endpoint_score = 0.0
            best_axis = None

        endpoint_summary = {
            "fault": "lubrication_distress",
            "endpoint_id": endpoint_id,
            "score": float(endpoint_score),
            "confidence": _confidence_from_score(endpoint_score),
            "possible": bool(endpoint_score >= min_score),
            "best_axis": best_axis["axis"] if best_axis else None,
            "best_axis_score": float(best_axis["score"]) if best_axis else 0.0,
            "supporting_axes": [row["axis"] for row in supporting_axes],
            "temperature_delta_c": float(temp_delta),
            "evidence": best_axis["evidence"] if best_axis else "",
            "limitations": best_axis.get("limitations", []) if best_axis else [],
        }
        endpoint_results[endpoint_id]["fault_summary"] = endpoint_summary
        endpoint_summaries.append(endpoint_summary)

    supporting_endpoints = [row for row in endpoint_summaries if float(row["score"]) >= 45.0]
    supporting_axis_count = sum(1 for row in all_axis_rows if float(row["score"]) >= 45.0)

    if endpoint_summaries:
        best_endpoint = max(endpoint_summaries, key=lambda row: row["score"])
        asset_score = _clamp(
            float(best_endpoint["score"])
            + 10.0 * _score_linear(len(supporting_endpoints), 2.0, 4.0)
            + 5.0 * _score_linear(supporting_axis_count, 2.0, 6.0),
            0.0,
            100.0,
        )
        primary_fault = {
            "fault": "lubrication_distress",
            "score": float(asset_score),
            "confidence": _confidence_from_score(asset_score),
            "possible": bool(asset_score >= min_score),
            "best_endpoint": best_endpoint["endpoint_id"],
            "best_axis": best_endpoint["best_axis"],
            "supporting_endpoints": [row["endpoint_id"] for row in supporting_endpoints],
            "supporting_axis_count": int(supporting_axis_count),
            "evidence": best_endpoint["evidence"],
            "limitations": list(best_endpoint.get("limitations", [])),
        }
    else:
        primary_fault = None

    possible_faults = []
    if primary_fault and primary_fault["score"] >= min_score:
        possible_faults.append(primary_fault)

    return {
        "asset_id": asset_id,
        "rpm": float(rpm),
        "shaft_hz": float(shaft_hz),
        "sampling_frequency_hz": float(fs_hz),
        "primary_fault": primary_fault if possible_faults else None,
        "possible_faults": possible_faults,
        "endpoint_results": endpoint_results,
        "limitations": [
            "This detects a lubrication-distress vibration pattern, not lubricant chemistry, viscosity, or contamination directly.",
            "Surface temperature is only corroborative and should not be used as a standalone lubrication diagnosis.",
            "If bearing fault frequencies are provided, strong periodic BPFO/BPFI/BSF/FTF evidence reduces the lubrication-only score.",
            "Multiple endpoints are evaluated locally. The asset summary reports repeatability, but does not perform shaft-style cross-endpoint correlation.",
        ],
    }
