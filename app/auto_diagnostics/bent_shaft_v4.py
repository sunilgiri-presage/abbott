from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
from app.auto_diagnostics.signal_feature_cache_v4 import (
    best_autocorr_near_lag as _cached_best_autocorr_near_lag,
    one_sided_spectrum as _cached_one_sided_spectrum,
    to_velocity_waveform as _cached_to_velocity_waveform,
)


_EPS = 1e-12
_CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_DRIVER_COMPONENT_TYPES = {"motor", "engine", "turbine", "driver"}
_DRIVEN_COMPONENT_TYPES = {"pump", "fan", "blower", "compressor", "chiller", "driven", "load"}
_AXIS_ALIASES = {
    "h": "horizontal", "hor": "horizontal", "horizontal": "horizontal",
    "v": "vertical", "ver": "vertical", "vertical": "vertical",
    "a": "axial", "ax": "axial", "axial": "axial",
    "x": "x", "y": "y", "z": "z", "radial": "radial",
}


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
    return float(np.sqrt(np.mean(values ** 2))) if values.size else 0.0


def _top_mean(values: Iterable[float], n: int = 4) -> float:
    clean = sorted([float(v) for v in values if np.isfinite(v)], reverse=True)
    return float(mean(clean[: min(n, len(clean))])) if clean else 0.0


def _mean_or_zero(values: Iterable[float]) -> float:
    clean = [float(v) for v in values if np.isfinite(v)]
    return float(mean(clean)) if clean else 0.0


def _distinct_count(items: Iterable[str]) -> int:
    return len({str(x) for x in items if str(x)})


def _confidence_from_score(score: float, cap: str = "low") -> str:
    if score >= 70.0:
        confidence = "high"
    elif score >= 45.0:
        confidence = "medium"
    elif score >= 20.0:
        confidence = "low"
    else:
        confidence = "none"

    cap = str(cap or "low").lower()
    if cap not in _CONFIDENCE_ORDER:
        cap = "low"
    return cap if _CONFIDENCE_ORDER[confidence] > _CONFIDENCE_ORDER[cap] else confidence


def _fault_urgency(score: float, confidence: str) -> str:
    if score >= 75.0 and confidence in {"medium", "high"}:
        return "urgent"
    if score >= 45.0 and confidence != "none":
        return "plan"
    return "monitor"


def _as_float_array(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0:
        return arr
    finite = np.isfinite(arr)
    if not np.all(finite):
        if not np.any(finite):
            return np.asarray([], dtype=float)
        arr = arr.copy()
        arr[~finite] = float(np.nanmedian(arr[finite]))
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


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return _AXIS_ALIASES.get(text, text or "axis")


def _axis_is_radial_like(axis: str) -> bool:
    return _norm_axis_name(axis) in {"horizontal", "vertical", "radial", "x", "y", "z", "axis_1"}


def _axis_is_axial(axis: str) -> bool:
    return _norm_axis_name(axis) == "axial"


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)
    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}
    if data.ndim != 2:
        raise ValueError("Vibration TWF array must be 1-D or 2-D.")
    if data.shape[1] == 3:
        axis_names = axes or ["x", "y", "z"]
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[:, i]) for i in range(3)}
    if data.shape[0] == 3:
        axis_names = axes or ["x", "y", "z"]
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[i, :]) for i in range(3)}
    raise ValueError("2-D vibration TWF must have one dimension of size 3 for tri-axial data.")


def _looks_like_axis_map(obj: Mapping[str, Any]) -> bool:
    if not obj:
        return False
    keys = {_norm_axis_name(k) for k in obj.keys()}
    return bool(keys & {"x", "y", "z", "horizontal", "vertical", "axial", "radial"}) and all(
        not isinstance(v, Mapping) for v in obj.values()
    )


def _normalize_triaxial_twf(vibration_twf: Any, axes: Optional[List[str]] = None) -> Dict[str, Dict[str, np.ndarray]]:
    if isinstance(vibration_twf, Mapping):
        if _looks_like_axis_map(vibration_twf):
            return {"endpoint_1": {_norm_axis_name(axis): _as_float_array(values) for axis, values in vibration_twf.items()}}
        endpoints: Dict[str, Dict[str, np.ndarray]] = {}
        for endpoint_id, endpoint_data in vibration_twf.items():
            if isinstance(endpoint_data, Mapping):
                endpoints[str(endpoint_id)] = {
                    _norm_axis_name(axis): _as_float_array(values)
                    for axis, values in endpoint_data.items()
                }
            else:
                endpoints[str(endpoint_id)] = _array_to_axis_map(endpoint_data, axes=axes)
        return endpoints
    return {"endpoint_1": _array_to_axis_map(vibration_twf, axes=axes)}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "de", "drive_end", "drive-end",
        "coupling", "coupling_end", "coupling-end",
    }


def _float_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _endpoint_role_from_text(text: Any) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return "unknown"
    normalized = re.sub(r"[^a-z0-9]+", "_", raw)
    tokens = [token for token in normalized.split("_") if token]
    joined = "_".join(tokens)
    if joined in {"nde", "non_drive_end", "non_drive", "non_de"}:
        return "NDE"
    if joined in {"de", "drive_end", "drive", "coupling_end", "coupling"}:
        return "DE"
    if "nde" in tokens or ("non" in tokens and "drive" in tokens) or "non_drive_end" in joined:
        return "NDE"
    if "de" in tokens or ("drive" in tokens and "end" in tokens) or ("coupling" in tokens and "end" in tokens):
        return "DE"
    return "unknown"


def _resolve_endpoint_role(endpoint_id: str, raw_meta: Mapping[str, Any]) -> str:
    for field in [
        "endpoint_role", "end_role", "end_type", "end", "endpoint_flag",
        "de_nde", "drive_end_flag", "bearing_end", "location_end", "position",
    ]:
        if field in raw_meta and raw_meta.get(field) not in {None, ""}:
            role = _endpoint_role_from_text(raw_meta.get(field))
            if role != "unknown":
                return role
    if _truthy(raw_meta.get("is_nde")):
        return "NDE"
    if _truthy(raw_meta.get("is_de")) or _truthy(raw_meta.get("is_drive_end")) or _truthy(raw_meta.get("is_coupling_end")):
        return "DE"
    for candidate in [
        endpoint_id, raw_meta.get("location_tag"), raw_meta.get("endpoint_tag"),
        raw_meta.get("name"), raw_meta.get("mount_name"), raw_meta.get("composite_id"),
        raw_meta.get("composite_key"),
    ]:
        role = _endpoint_role_from_text(candidate)
        if role != "unknown":
            return role
    return "unknown"


def _component_side(component_type: str, endpoint_id: str = "") -> str:
    ctype = str(component_type or "").strip().lower()
    endpoint_text = str(endpoint_id or "").strip().lower()
    if ctype in _DRIVER_COMPONENT_TYPES or "motor" in endpoint_text:
        return "driver"
    if ctype in _DRIVEN_COMPONENT_TYPES or any(word in endpoint_text for word in ["pump", "fan", "blower", "compressor"]):
        return "driven"
    return "unknown"


def _endpoint_metadata(endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]], endpoint_id: str) -> Dict[str, Any]:
    raw_meta: Mapping[str, Any] = {}
    if endpoint_metadata and endpoint_id in endpoint_metadata:
        raw_meta = endpoint_metadata[endpoint_id] or {}
    installed_on = str(raw_meta.get("installed_on") or raw_meta.get("mount_type") or raw_meta.get("mounted_on") or "unknown").strip().lower()
    component_type = str(raw_meta.get("component_type") or raw_meta.get("component") or "unknown").strip().lower()
    endpoint_role = _resolve_endpoint_role(endpoint_id, raw_meta)
    shaft_group_id = str(
        raw_meta.get("shaft_group_id") or raw_meta.get("shaft_id") or raw_meta.get("train_id")
        or raw_meta.get("coupling_group_id") or ""
    ).strip().lower()
    local_rpm = _float_or_none(raw_meta.get("local_rpm") or raw_meta.get("rpm") or raw_meta.get("running_rpm"))
    is_coupling_end = bool(_truthy(raw_meta.get("is_coupling_end")) or _truthy(raw_meta.get("coupling_end")) or endpoint_role == "DE")
    return {
        "installed_on": installed_on,
        "component_type": component_type,
        "endpoint_role": endpoint_role,
        "is_coupling_end": is_coupling_end,
        "shaft_group_id": shaft_group_id,
        "local_rpm": local_rpm,
        "component_side": _component_side(component_type, endpoint_id),
    }


def _peak_at(freqs_hz: np.ndarray, amplitudes: np.ndarray, target_hz: float, tolerance_hz: float) -> Tuple[float, float]:
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


def _extract_bent_shaft_axis_features(
    waveform: np.ndarray,
    fs_hz: float,
    rpm: float,
    *,
    signal_type: str,
    acceleration_unit: str,
    integration_low_cut_hz: float,
    target_tolerance_pct: float,
) -> Dict[str, Any]:
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for bent-shaft detection.")
    source = _as_float_array(waveform)
    if source.size < 128:
        raise ValueError("Need at least 128 samples for bent-shaft detection.")
    velocity = _cached_to_velocity_waveform(
        _as_float_array(source),
        fs_hz,
        signal_type=signal_type,
        acceleration_unit=acceleration_unit,
        integration_low_cut_hz=integration_low_cut_hz,
    )
    if velocity.size < 128:
        raise ValueError("Velocity waveform could not be prepared from input signal.")
    freqs, amps = _cached_one_sided_spectrum(_as_float_array(velocity), fs_hz)
    if freqs.size == 0 or amps.size == 0:
        raise ValueError("Could not compute a valid velocity spectrum.")

    shaft_hz = float(rpm) / 60.0
    freq_resolution_hz = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(shaft_hz * 0.03, 0.1)
    tolerance_hz = max(abs(shaft_hz) * float(target_tolerance_pct) / 100.0, 1.5 * freq_resolution_hz)
    order_targets = {
        "05x": 0.5, "1x": 1.0, "15x": 1.5, "2x": 2.0, "25x": 2.5, "3x": 3.0,
        "35x": 3.5, "4x": 4.0, "5x": 5.0, "6x": 6.0, "7x": 7.0, "8x": 8.0,
        "9x": 9.0, "10x": 10.0,
    }
    order_peaks: Dict[str, Dict[str, float]] = {}
    for name, order_value in order_targets.items():
        peak_hz, amp = _peak_at(freqs, amps, order_value * shaft_hz, tolerance_hz)
        order_peaks[name] = {"order": float(order_value), "target_hz": float(order_value * shaft_hz), "peak_hz": float(peak_hz), "amp": float(amp)}

    rms_spectrum = max(_rms(amps), _EPS)
    noise_floor = float(np.median(np.abs(amps))) if amps.size else 0.0
    dominant_idx = int(np.argmax(amps))
    dominant_freq_hz = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])
    dominant_order = _safe_ratio(dominant_freq_hz, shaft_hz)

    def amp(name: str) -> float:
        return float(order_peaks[name]["amp"])

    def ratio(value: float) -> float:
        return _safe_ratio(value, rms_spectrum)

    fractional = amp("05x") + amp("15x") + amp("25x")
    fractional_with_35 = fractional + amp("35x")
    harmonic_3x_5x = amp("3x") + amp("4x") + amp("5x")
    harmonic_2x_5x = amp("2x") + harmonic_3x_5x
    high_harmonics = amp("6x") + amp("7x") + amp("8x") + amp("9x") + amp("10x")
    abs_velocity = np.abs(velocity - float(np.mean(velocity)))
    wf_1x_pulse = _cached_best_autocorr_near_lag(abs_velocity, int(round(fs_hz / shaft_hz))) if shaft_hz > 0.0 else 0.0
    wf_2x_pulse = _cached_best_autocorr_near_lag(abs_velocity, int(round(fs_hz / (2.0 * shaft_hz)))) if shaft_hz > 0.0 else 0.0

    return {
        "samples": int(source.size),
        "duration_s": float(source.size / fs_hz),
        "shaft_hz": float(shaft_hz),
        "freq_resolution_hz": float(freq_resolution_hz),
        "tolerance_hz": float(tolerance_hz),
        "velocity_waveform": velocity,
        "freqs_hz": freqs,
        "spectrum": amps,
        "rms_spectrum": float(rms_spectrum),
        "noise_floor": float(noise_floor),
        "noise_floor_ratio": ratio(noise_floor),
        "dominant_freq_hz": float(dominant_freq_hz),
        "dominant_amp": float(dominant_amp),
        "dominant_order": float(dominant_order),
        "crest_factor": float(_crest_factor(velocity)),
        "kurtosis_excess": float(_kurtosis_excess(velocity)),
        "wf_1x_pulse": float(wf_1x_pulse),
        "wf_2x_pulse": float(wf_2x_pulse),
        "order_peaks": order_peaks,
        "ratio_1x": ratio(amp("1x")),
        "ratio_2x": ratio(amp("2x")),
        "ratio_2x_over_1x": _safe_ratio(amp("2x"), max(amp("1x"), _EPS)),
        "ratio_1x_over_2x": _safe_ratio(amp("1x"), max(amp("2x"), _EPS), 99.0),
        "fractional_ratio": ratio(fractional),
        "fractional_with_35x_ratio": ratio(fractional_with_35),
        "harmonic_3x_5x_ratio": ratio(harmonic_3x_5x),
        "harmonic_2x_5x_ratio": ratio(harmonic_2x_5x),
        "high_harmonics_ratio": ratio(high_harmonics),
    }


def _axis_weight_bent_shaft(axis: str, installed_on: str) -> float:
    base = 1.0 if _axis_is_axial(axis) else 0.50
    if str(installed_on or "unknown").lower() in {"base", "foundation"}:
        base *= 0.70
    return float(base)


def _score_bent_shaft_axis(
    *,
    endpoint_id: str,
    axis: str,
    features: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> Dict[str, Any]:
    ratio1 = float(features["ratio_1x"])
    ratio2 = float(features["ratio_2x"])
    ratio12 = float(features["ratio_2x_over_1x"])
    axial_primary = ratio1 if _axis_is_axial(axis) else 0.0
    harmonic_3x_5x = float(features["harmonic_3x_5x_ratio"])
    frac = float(features["fractional_ratio"])
    frac_with_35 = float(features["fractional_with_35x_ratio"])
    dominant_order = float(features["dominant_order"])
    dominant_near_1x = 1.0 - min(abs(dominant_order - 1.0), 1.0)
    raw_score = (
        34.0 * _score_linear(axial_primary, 0.8, 3.5)
        + 24.0 * _score_linear(ratio1, 1.0, 4.0)
        + 18.0 * _score_linear(ratio12, 0.30, 1.20)
        + 14.0 * (1.0 - _score_linear(harmonic_3x_5x, 0.8, 2.8))
        + 10.0 * (1.0 - _score_linear(frac, 0.6, 2.5))
    )
    if not _axis_is_axial(axis):
        raw_score *= 0.72
    installed_on = str(meta.get("installed_on", "unknown"))
    component_type = str(meta.get("component_type", "unknown"))
    axis_weight = _axis_weight_bent_shaft(axis, installed_on)
    score = _clamp(raw_score * axis_weight, 0.0, 100.0)
    limitations: List[str] = []
    if not _axis_is_axial(axis):
        limitations.append("Non-axial evidence is down-weighted; bent shaft/bow normally needs axial confirmation.")
    if installed_on in {"base", "foundation"}:
        limitations.append("Base/foundation endpoint is down-weighted for bent shaft / rotor bow.")
    if ratio12 < 0.30:
        limitations.append("2X / 1X content is weak for a bent-shaft/bow pattern.")
    if harmonic_3x_5x >= 2.8 or frac_with_35 >= 2.5:
        limitations.append("Harmonic/fractional clutter makes a clean bent-shaft call less specific.")
    return {
        "fault": "bent_shaft_or_bow",
        "label": "Possible bent shaft / rotor bow",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "confidence": _confidence_from_score(score, cap="low"),
        "possible": bool(score >= 20.0),
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "is_coupling_end": bool(meta.get("is_coupling_end", False)),
        "component_type": component_type,
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": installed_on,
        "shaft_group_id": str(meta.get("shaft_group_id", "")),
        "local_rpm": float(meta.get("local_rpm") or 0.0),
        "metrics": {
            "ratio_1x": ratio1,
            "ratio_2x": ratio2,
            "ratio_2x_over_1x": ratio12,
            "ratio_1x_over_2x": float(features["ratio_1x_over_2x"]),
            "axial_1x_ratio": float(axial_primary),
            "fractional_ratio": frac,
            "fractional_with_35x_ratio": frac_with_35,
            "harmonic_3x_5x_ratio": harmonic_3x_5x,
            "harmonic_2x_5x_ratio": float(features["harmonic_2x_5x_ratio"]),
            "high_harmonics_ratio": float(features["high_harmonics_ratio"]),
            "dominant_order": dominant_order,
            "dominant_near_1x_score_0_1": float(max(0.0, dominant_near_1x)),
            "dominant_freq_hz": float(features["dominant_freq_hz"]),
            "dominant_amp": float(features["dominant_amp"]),
            "waveform_1x_pulse": float(features["wf_1x_pulse"]),
            "waveform_2x_pulse": float(features["wf_2x_pulse"]),
            "crest_factor": float(features["crest_factor"]),
            "kurtosis_excess": float(features["kurtosis_excess"]),
            "noise_floor_ratio": float(features["noise_floor_ratio"]),
            "axis_weight": float(axis_weight),
            "component_weight": 1.0,
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: bent-shaft score={score:.1f}, "
            f"1X={ratio1:.2f}xRMS, axial_1X={axial_primary:.2f}xRMS, "
            f"2X/1X={ratio12:.2f}, 3X-5X={harmonic_3x_5x:.2f}xRMS, "
            f"fractional={frac:.2f}xRMS, dominant={dominant_order:.2f}X, "
            f"role={meta.get('endpoint_role', 'unknown')}, mount={installed_on}"
        ),
    }


def _unbalance_like_axis_score(row: Mapping[str, Any]) -> float:
    m = row.get("metrics", {}) or {}

    def value(key: str) -> float:
        try:
            number = float(m.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return number if np.isfinite(number) else 0.0

    axis = str(row.get("axis", ""))
    radial_factor = 1.0 if _axis_is_radial_like(axis) and not _axis_is_axial(axis) else 0.35
    score = (
        35.0 * _score_linear(value("ratio_1x"), 1.8, 5.0)
        + 20.0 * _score_linear(value("ratio_1x_over_2x"), 1.2, 3.5)
        + 15.0 * _score_linear(value("dominant_near_1x_score_0_1"), 0.55, 0.95)
        + 15.0 * (1.0 - _score_linear(value("harmonic_2x_5x_ratio"), 2.5, 6.0))
        + 15.0 * (1.0 - _score_linear(value("fractional_ratio"), 1.0, 3.0))
    )
    return _clamp(score * radial_factor, 0.0, 100.0)


def _best_de_row_per_endpoint(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if str(row.get("endpoint_role", "unknown")).upper() != "DE" and not bool(row.get("is_coupling_end", False)):
            continue
        endpoint_id = str(row.get("endpoint_id", ""))
        if not endpoint_id:
            continue
        current = best.get(endpoint_id)
        if current is None or float(row.get("score", 0.0)) > float(current.get("score", 0.0)):
            best[endpoint_id] = row
    return best


def _rows_are_same_shaft_compatible(left: Mapping[str, Any], right: Mapping[str, Any], *, rpm_tolerance_pct: float = 5.0) -> bool:
    if str(left.get("endpoint_id")) == str(right.get("endpoint_id")):
        return False
    left_group = str(left.get("shaft_group_id", "") or "").strip().lower()
    right_group = str(right.get("shaft_group_id", "") or "").strip().lower()
    if left_group and right_group and left_group != right_group:
        return False
    left_rpm = _float_or_none(left.get("local_rpm"))
    right_rpm = _float_or_none(right.get("local_rpm"))
    if left_rpm and right_rpm and left_rpm > 0.0 and right_rpm > 0.0:
        avg_rpm = 0.5 * (left_rpm + right_rpm)
        if 100.0 * abs(left_rpm - right_rpm) / max(avg_rpm, _EPS) > rpm_tolerance_pct:
            return False
    return True


def _bent_shaft_pair_vector(row: Mapping[str, Any]) -> np.ndarray:
    metrics = row.get("metrics", {}) or {}

    def value(key: str) -> float:
        try:
            number = float(metrics.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return number if np.isfinite(number) else 0.0

    return np.asarray(
        [
            value("axial_1x_ratio"),
            value("ratio_1x"),
            value("ratio_2x_over_1x"),
            value("dominant_near_1x_score_0_1"),
            1.0 / (1.0 + value("harmonic_3x_5x_ratio")),
            1.0 / (1.0 + value("fractional_ratio")),
        ],
        dtype=float,
    )


def _log_vector_similarity(left_vector: np.ndarray, right_vector: np.ndarray) -> float:
    left = np.asarray(left_vector, dtype=float)
    right = np.asarray(right_vector, dtype=float)
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    left = np.maximum(left, 0.0)
    right = np.maximum(right, 0.0)
    delta = np.abs(np.log1p(left) - np.log1p(right))
    return _clamp(float(np.exp(-float(np.mean(delta)))), 0.0, 1.0)


def _de_pair_preference_multiplier(left: Mapping[str, Any], right: Mapping[str, Any]) -> Tuple[float, str]:
    sides = {str(left.get("component_side", "unknown")), str(right.get("component_side", "unknown"))}
    if sides == {"driver", "driven"}:
        return 1.12, "driver_driven_de_pair"
    if "unknown" not in sides and len(sides) == 2:
        return 1.05, "different_component_de_pair"
    if len(sides) == 1 and "unknown" not in sides:
        return 0.94, "same_component_side_de_pair"
    return 1.0, "generic_de_pair"


def _axis_pair_factor(left_axis: str, right_axis: str) -> float:
    left_axis = _norm_axis_name(left_axis)
    right_axis = _norm_axis_name(right_axis)
    if _axis_is_axial(left_axis) and _axis_is_axial(right_axis):
        return 1.0
    if left_axis == right_axis:
        return 0.90
    if _axis_is_radial_like(left_axis) and _axis_is_radial_like(right_axis):
        return 0.82
    return 0.72


def _best_de_pair_support(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    de_rows = list(_best_de_row_per_endpoint(rows).values())
    if len(de_rows) < 2:
        return {"available": False, "used": False, "reason": "Less than two DE/coupling-end endpoints are available.", "pair_score": 0.0, "similarity": 0.0}
    best: Optional[Dict[str, Any]] = None
    for i in range(len(de_rows)):
        for j in range(i + 1, len(de_rows)):
            left = de_rows[i]
            right = de_rows[j]
            if not _rows_are_same_shaft_compatible(left, right):
                continue
            similarity = _log_vector_similarity(_bent_shaft_pair_vector(left), _bent_shaft_pair_vector(right))
            left_score = float(left.get("score", 0.0))
            right_score = float(right.get("score", 0.0))
            axis_factor = _axis_pair_factor(str(left.get("axis")), str(right.get("axis")))
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            pair_score = (0.68 * min(left_score, right_score) + 0.32 * 0.5 * (left_score + right_score)) * (0.55 + 0.45 * similarity) * axis_factor * pair_multiplier
            pair_score = _clamp(pair_score, 0.0, 100.0)
            candidate = {
                "available": True,
                "used": bool(pair_score >= 35.0),
                "pair_class": pair_class,
                "pair_score": float(pair_score),
                "similarity": float(similarity),
                "endpoint_a": str(left.get("endpoint_id")),
                "axis_a": str(left.get("axis")),
                "score_a": float(left_score),
                "component_type_a": str(left.get("component_type", "unknown")),
                "endpoint_b": str(right.get("endpoint_id")),
                "axis_b": str(right.get("axis")),
                "score_b": float(right_score),
                "component_type_b": str(right.get("component_type", "unknown")),
                "shaft_group_id": str(left.get("shaft_group_id") or right.get("shaft_group_id") or ""),
                "local_rpm_a": float(left.get("local_rpm", 0.0) or 0.0),
                "local_rpm_b": float(right.get("local_rpm", 0.0) or 0.0),
            }
            if best is None or candidate["pair_score"] > best["pair_score"]:
                best = candidate
    if best is None:
        return {"available": False, "used": False, "reason": "DE endpoints exist, but no compatible same-shaft/same-speed pair was found.", "pair_score": 0.0, "similarity": 0.0}
    return best


def _aggregate_global_bent_shaft(
    axis_rows: List[Dict[str, Any]],
    *,
    min_score: float,
    de_pair_support: Optional[Mapping[str, Any]],
    phase_or_runout_available: bool,
) -> Dict[str, Any]:
    confidence_cap = "medium" if phase_or_runout_available else "low"
    if not axis_rows:
        return {
            "fault": "bent_shaft_or_bow",
            "score": 0.0,
            "confidence": "none",
            "possible": False,
            "evidence": "No valid endpoint-axis rows were available.",
            "limitations": ["No valid vibration data was available for bent-shaft detection."],
            "metrics": {},
        }
    scores = [float(row["score"]) for row in axis_rows]
    endpoint_ids = [str(row["endpoint_id"]) for row in axis_rows]
    high_rows = [row for row in axis_rows if float(row["score"]) >= 45.0]
    axial_high_rows = [row for row in high_rows if _axis_is_axial(str(row.get("axis")))]
    base_score = _clamp(
        0.65 * _top_mean(scores, n=4)
        + 20.0 * _score_linear(_distinct_count(endpoint_ids), 1.0, 4.0)
        + 15.0 * _score_linear(len(high_rows), 1.0, 4.0),
        0.0,
        100.0,
    )
    de_pair_score = 0.0
    de_pair_similarity = 0.0
    de_pair_boost = 0.0
    de_pair_text = ""
    if de_pair_support and bool(de_pair_support.get("available", False)):
        de_pair_score = float(de_pair_support.get("pair_score", 0.0))
        de_pair_similarity = float(de_pair_support.get("similarity", 0.0))
        de_pair_boost = 10.0 * _score_linear(de_pair_score, 35.0, 75.0)
        de_pair_text = (
            f"DE-pair support {de_pair_support.get('endpoint_a')}/{de_pair_support.get('axis_a')} "
            f"<-> {de_pair_support.get('endpoint_b')}/{de_pair_support.get('axis_b')}: "
            f"pair_score={de_pair_score:.1f}, similarity={de_pair_similarity:.2f}, class={de_pair_support.get('pair_class')}"
        )
    score = _clamp(base_score + de_pair_boost, 0.0, 100.0)
    mean_1x = _mean_or_zero(row["metrics"]["ratio_1x"] for row in axis_rows)
    mean_2x = _mean_or_zero(row["metrics"]["ratio_2x"] for row in axis_rows)
    mean_2x_over_1x = _mean_or_zero(row["metrics"]["ratio_2x_over_1x"] for row in axis_rows)
    supporting_2x_over_1x = _mean_or_zero(row["metrics"]["ratio_2x_over_1x"] for row in (axial_high_rows or high_rows or axis_rows))
    mean_axial_1x = _mean_or_zero(row["metrics"]["axial_1x_ratio"] for row in axis_rows)
    mean_fractional = _mean_or_zero(row["metrics"]["fractional_ratio"] for row in axis_rows)
    mean_harmonic_3x_5x = _mean_or_zero(row["metrics"]["harmonic_3x_5x_ratio"] for row in axis_rows)
    mean_high_harmonics = _mean_or_zero(row["metrics"]["high_harmonics_ratio"] for row in axis_rows)
    mean_wf_1x = _mean_or_zero(row["metrics"]["waveform_1x_pulse"] for row in axis_rows)
    mean_wf_2x = _mean_or_zero(row["metrics"]["waveform_2x_pulse"] for row in axis_rows)
    limitations: List[str] = []
    reduction_factor = 1.0
    num_supporting_endpoints = _distinct_count(row["endpoint_id"] for row in high_rows)
    if num_supporting_endpoints < 2:
        reduction_factor *= 0.72
        limitations.append("Reduced because bent-shaft diagnosis is weak when based on a single sensor location.")
    if len(axial_high_rows) < 1:
        reduction_factor *= 0.55
        limitations.append("Reduced because axial dominance is weak for a bent-shaft/bow pattern.")
    if supporting_2x_over_1x < 0.30:
        reduction_factor *= 0.60
        limitations.append("Reduced because 2X content is too weak for a bent-shaft/bow pattern.")
    unbalance_like_score = max(_unbalance_like_axis_score(row) for row in axis_rows)
    if unbalance_like_score >= 45.0 and mean_fractional < 0.60 and len(axial_high_rows) < 2:
        reduction_factor *= 0.72
        limitations.append("Reduced because the pattern overlaps more closely with simple 1X unbalance.")
    score = _clamp(score * reduction_factor, 0.0, 100.0)
    best_row = max(axis_rows, key=lambda row: float(row["score"]))
    if not phase_or_runout_available:
        limitations.append("Confidence capped at low because bent shaft / rotor bow is normally separated from misalignment by phase or runout checks.")
    else:
        limitations.append("Confidence still capped at medium; use phase/runout to confirm before final root-cause closure.")
    if not de_pair_support or not bool(de_pair_support.get("available", False)):
        limitations.append("No usable DE-to-DE same-shaft pair was available; result falls back to endpoint/axis aggregation.")
    if mean_harmonic_3x_5x >= 2.0 or mean_high_harmonics >= 1.5:
        limitations.append("Higher harmonic clutter is present; check looseness or rub-like faults as alternatives.")
    evidence = best_row["evidence"]
    if de_pair_text:
        evidence = f"{evidence} | {de_pair_text}"
    confidence = _confidence_from_score(score, cap=confidence_cap)
    return {
        "fault": "bent_shaft_or_bow",
        "label": "Possible bent shaft / rotor bow",
        "scope": "asset_wide",
        "score": float(score),
        "base_score_before_de_pair": float(base_score),
        "de_pair_boost": float(de_pair_boost),
        "postprocess_reduction_factor": float(reduction_factor),
        "confidence": confidence,
        "possible": bool(score >= min_score),
        "urgency": _fault_urgency(score, confidence),
        "best_endpoint": best_row["endpoint_id"],
        "best_axis": best_row["axis"],
        "best_axis_score": float(best_row["score"]),
        "supporting_endpoints": sorted({str(row["endpoint_id"]) for row in high_rows}),
        "supporting_axis_count": int(len(high_rows)),
        "axial_supporting_axis_count": int(len(axial_high_rows)),
        "evidence": evidence,
        "limitations": limitations,
        "de_pair_support": dict(de_pair_support or {}),
        "recommendations": [
            "Confirm with axial phase, dial indicator runout, shaft bow check, or slow-roll/runout data before corrective action.",
            "Separate from coupling misalignment, soft foot, and simple unbalance before replacing or straightening shaft components.",
            "Inspect coupling, shaft extension, rotor fit, recent mechanical shock, overheating, and maintenance history if the pattern repeats.",
        ],
        "metrics": {
            "num_evaluated_axes": float(len(axis_rows)),
            "num_evaluated_endpoints": float(_distinct_count(endpoint_ids)),
            "num_high_support_axes": float(len(high_rows)),
            "num_supporting_endpoints": float(num_supporting_endpoints),
            "num_axial_support_axes": float(len(axial_high_rows)),
            "mean_1x_ratio": float(mean_1x),
            "mean_2x_ratio": float(mean_2x),
            "mean_2x_over_1x": float(mean_2x_over_1x),
            "supporting_2x_over_1x": float(supporting_2x_over_1x),
            "mean_axial_1x_ratio": float(mean_axial_1x),
            "mean_fractional_ratio": float(mean_fractional),
            "mean_harmonic_3x_5x_ratio": float(mean_harmonic_3x_5x),
            "mean_high_harmonics_ratio": float(mean_high_harmonics),
            "mean_waveform_1x_pulse": float(mean_wf_1x),
            "mean_waveform_2x_pulse": float(mean_wf_2x),
            "unbalance_like_score": float(unbalance_like_score),
            "de_pair_score": float(de_pair_score),
            "de_pair_similarity": float(de_pair_similarity),
            "de_pair_boost": float(de_pair_boost),
        },
    }


def _endpoint_summary(endpoint_id: str, axis_rows: List[Dict[str, Any]], min_score: float) -> Dict[str, Any]:
    if not axis_rows:
        return {
            "fault": "bent_shaft_or_bow",
            "endpoint_id": endpoint_id,
            "score": 0.0,
            "confidence": "none",
            "possible": False,
            "best_axis": None,
            "best_axis_score": 0.0,
            "supporting_axes": [],
            "evidence": "",
        }
    best_axis = max(axis_rows, key=lambda row: float(row["score"]))
    supporting_axes = [row for row in axis_rows if float(row["score"]) >= 45.0]
    axial_supporting_axes = [row for row in supporting_axes if _axis_is_axial(str(row.get("axis")))]
    axis_scores = [float(row["score"]) for row in axis_rows]
    endpoint_score = _clamp(
        max(axis_scores)
        + 8.0 * _score_linear(len(supporting_axes), 2.0, 3.0)
        + 6.0 * _score_linear(len(axial_supporting_axes), 1.0, 2.0),
        0.0,
        100.0,
    )
    return {
        "fault": "bent_shaft_or_bow",
        "endpoint_id": endpoint_id,
        "score": float(endpoint_score),
        "confidence": _confidence_from_score(endpoint_score, cap="low"),
        "possible": bool(endpoint_score >= min_score),
        "best_axis": best_axis["axis"],
        "best_axis_score": float(best_axis["score"]),
        "supporting_axes": [row["axis"] for row in supporting_axes],
        "axial_supporting_axes": [row["axis"] for row in axial_supporting_axes],
        "evidence": best_axis["evidence"],
    }


def detect_bent_shaft(
    vibration_twf: Any,
    sampling_frequency_hz: float,
    rpm: float,
    *,
    asset_id: Optional[str] = None,
    signal_type: str = "velocity",
    acceleration_unit: str = "g",
    integration_low_cut_hz: float = 0.2,
    endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
    axes: Optional[List[str]] = None,
    min_score: float = 20.0,
    target_tolerance_pct: float = 3.0,
    de_pair_enabled: bool = True,
    phase_or_runout_available: bool = False,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for bent-shaft detection.")
    endpoints = _normalize_triaxial_twf(vibration_twf, axes=axes)
    shaft_hz = rpm / 60.0
    endpoint_results: Dict[str, Any] = {}
    all_axis_rows: List[Dict[str, Any]] = []
    for endpoint_id, axis_map in endpoints.items():
        meta = _endpoint_metadata(endpoint_metadata, endpoint_id)
        endpoint_rpm = float(meta.get("local_rpm") or rpm)
        meta = dict(meta)
        meta["local_rpm"] = endpoint_rpm
        endpoint_results[endpoint_id] = {"metadata": meta, "rpm_used": float(endpoint_rpm), "axes": {}, "fault_summary": None}
        endpoint_axis_rows: List[Dict[str, Any]] = []
        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "features": {}, "fault": None, "error": None}
            try:
                features = _extract_bent_shaft_axis_features(
                    waveform=axis_values,
                    fs_hz=fs_hz,
                    rpm=endpoint_rpm,
                    signal_type=signal_type,
                    acceleration_unit=acceleration_unit,
                    integration_low_cut_hz=integration_low_cut_hz,
                    target_tolerance_pct=target_tolerance_pct,
                )
                row = _score_bent_shaft_axis(endpoint_id=endpoint_id, axis=axis, features=features, meta=meta)
                endpoint_axis_rows.append(row)
                all_axis_rows.append(row)
                axis_result["valid"] = True
                axis_result["features"] = {
                    "samples": features["samples"],
                    "duration_s": features["duration_s"],
                    "shaft_hz": features["shaft_hz"],
                    "rpm_used": float(endpoint_rpm),
                    "freq_resolution_hz": features["freq_resolution_hz"],
                    "tolerance_hz": features["tolerance_hz"],
                    "dominant_freq_hz": features["dominant_freq_hz"],
                    "dominant_order": features["dominant_order"],
                    "rms_spectrum": features["rms_spectrum"],
                    "ratio_1x": features["ratio_1x"],
                    "ratio_2x": features["ratio_2x"],
                    "ratio_2x_over_1x": features["ratio_2x_over_1x"],
                    "fractional_ratio": features["fractional_ratio"],
                    "harmonic_3x_5x_ratio": features["harmonic_3x_5x_ratio"],
                    "high_harmonics_ratio": features["high_harmonics_ratio"],
                    "waveform_1x_pulse": features["wf_1x_pulse"],
                    "waveform_2x_pulse": features["wf_2x_pulse"],
                }
                axis_result["fault"] = row
            except Exception as exc:
                axis_result["error"] = str(exc)
            endpoint_results[endpoint_id]["axes"][axis] = axis_result
        endpoint_results[endpoint_id]["fault_summary"] = _endpoint_summary(endpoint_id, endpoint_axis_rows, min_score)
    if de_pair_enabled:
        de_pair_support = _best_de_pair_support(all_axis_rows)
    else:
        de_pair_support = {"available": False, "used": False, "reason": "DE-pair logic disabled by caller.", "pair_score": 0.0, "similarity": 0.0}
    primary_fault = _aggregate_global_bent_shaft(
        all_axis_rows,
        min_score=min_score,
        de_pair_support=de_pair_support,
        phase_or_runout_available=phase_or_runout_available,
    )
    possible_faults = [primary_fault] if primary_fault.get("possible") else []
    return {
        "asset_id": asset_id,
        "rpm": float(rpm),
        "shaft_hz": float(shaft_hz),
        "sampling_frequency_hz": float(fs_hz),
        "signal_type": str(signal_type).lower(),
        "velocity_basis": (
            "direct_velocity_twf"
            if str(signal_type).lower() in {"velocity", "vel", "mm/s", "mmps"}
            else "derived_velocity_from_acceleration_twf"
        ),
        "de_pair_logic": {
            "enabled": bool(de_pair_enabled),
            "description": (
                "Compatible DE/coupling-end endpoints are compared first. If a same-shaft DE pair supports "
                "the same axial 1X plus 2X/1X bent-shaft pattern, the asset score receives a bounded boost. "
                "Otherwise the detector falls back to endpoint/axis aggregation."
            ),
            "support": de_pair_support,
        },
        "primary_fault": primary_fault if possible_faults else None,
        "possible_faults": possible_faults,
        "endpoint_results": endpoint_results,
        "limitations": [
            "Bent shaft / rotor bow is evaluated as an asset-wide shaft/train fault using velocity-domain shaft-order evidence.",
            "Velocity TWF is preferred. If acceleration TWF is supplied, velocity is derived by frequency-domain integration.",
            "DE-to-DE comparison is only used when compatible same-shaft/same-speed DE endpoints are available.",
            "NDE endpoints still contribute to normal asset-wide aggregation, but they do not drive the special DE-pair boost.",
            "Without phase, runout, or slow-roll data, bent shaft and misalignment can overlap; confidence is capped at low by default.",
        ],
    }


__all__ = ["detect_bent_shaft"]
