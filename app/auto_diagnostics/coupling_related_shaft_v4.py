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

_DRIVER_COMPONENT_TYPES = {"motor", "engine", "turbine", "driver"}
_DRIVEN_COMPONENT_TYPES = {"pump", "fan", "blower", "compressor", "chiller", "driven", "load"}


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


def _top_mean(values: Iterable[float], n: int = 4) -> float:
    clean = sorted([float(v) for v in values if np.isfinite(v)], reverse=True)
    if not clean:
        return 0.0
    return float(mean(clean[: min(n, len(clean))]))


def _mean_or_zero(values: Iterable[float]) -> float:
    clean = [float(v) for v in values if np.isfinite(v)]
    return float(mean(clean)) if clean else 0.0


def _distinct_count(items: Iterable[str]) -> int:
    return len({str(x) for x in items if str(x)})


def _confidence_from_score(score: float, cap: str = "medium") -> str:
    if score >= 70.0:
        confidence = "high"
    elif score >= 45.0:
        confidence = "medium"
    elif score >= 20.0:
        confidence = "low"
    else:
        confidence = "none"
    cap = str(cap or "medium").lower()
    if cap not in _CONFIDENCE_ORDER:
        cap = "medium"
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
        if np.any(finite):
            fill = float(np.nanmedian(arr[finite]))
            arr = arr.copy()
            arr[~finite] = fill
        else:
            return np.asarray([], dtype=float)
    return arr


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return _AXIS_ALIASES.get(text, text or "axis")


def _axis_is_axial(axis: str) -> bool:
    return _norm_axis_name(axis) == "axial"


def _axis_is_radial_like(axis: str) -> bool:
    return _norm_axis_name(axis) in {"horizontal", "vertical", "radial", "x", "y", "z", "axis_1"}


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)
    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}
    if data.ndim != 2:
        raise ValueError("Vibration TWF array must be 1-D or 2-D.")
    axis_names = axes or ["x", "y", "z"]
    if data.shape[1] == 3:
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[:, i]) for i in range(3)}
    if data.shape[0] == 3:
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[i, :]) for i in range(3)}
    raise ValueError("2-D vibration TWF must have one dimension of size 3 for tri-axial data.")


def _looks_like_axis_map(obj: Mapping[str, Any]) -> bool:
    if not obj:
        return False
    keys = {_norm_axis_name(k) for k in obj.keys()}
    axis_like = bool(keys & {"x", "y", "z", "horizontal", "vertical", "axial", "radial"})
    values_are_not_nested_maps = all(not isinstance(v, Mapping) for v in obj.values())
    return axis_like and values_are_not_nested_maps


def _normalize_triaxial_twf(vibration_twf: Any, axes: Optional[List[str]] = None) -> Dict[str, Dict[str, np.ndarray]]:
    if isinstance(vibration_twf, Mapping):
        if _looks_like_axis_map(vibration_twf):
            return {"endpoint_1": {_norm_axis_name(axis): _as_float_array(values) for axis, values in vibration_twf.items()}}
        endpoints: Dict[str, Dict[str, np.ndarray]] = {}
        for endpoint_id, endpoint_data in vibration_twf.items():
            endpoint_key = str(endpoint_id)
            if isinstance(endpoint_data, Mapping):
                endpoints[endpoint_key] = {_norm_axis_name(axis): _as_float_array(values) for axis, values in endpoint_data.items()}
            else:
                endpoints[endpoint_key] = _array_to_axis_map(endpoint_data, axes=axes)
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
        "1", "true", "yes", "y", "de", "drive_end", "drive-end", "coupling", "coupling_end", "coupling-end",
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
    explicit_fields = [
        "endpoint_role", "end_role", "end_type", "end", "endpoint_flag", "de_nde",
        "drive_end_flag", "bearing_end", "location_end", "position",
    ]
    for field in explicit_fields:
        if field in raw_meta and raw_meta.get(field) not in {None, ""}:
            role = _endpoint_role_from_text(raw_meta.get(field))
            if role != "unknown":
                return role
    if _truthy(raw_meta.get("is_nde")):
        return "NDE"
    if _truthy(raw_meta.get("is_de")) or _truthy(raw_meta.get("is_drive_end")) or _truthy(raw_meta.get("is_coupling_end")):
        return "DE"
    for candidate in [
        endpoint_id, raw_meta.get("location_tag"), raw_meta.get("endpoint_tag"), raw_meta.get("name"),
        raw_meta.get("mount_name"), raw_meta.get("composite_id"), raw_meta.get("composite_key"),
    ]:
        role = _endpoint_role_from_text(candidate)
        if role != "unknown":
            return role
    return "unknown"


def _component_side(component_type: str, endpoint_id: str = "") -> str:
    ctype = str(component_type or "").strip().lower()
    endpoint_text = str(endpoint_id or "").strip().lower()
    if ctype in _DRIVER_COMPONENT_TYPES:
        return "driver"
    if ctype in _DRIVEN_COMPONENT_TYPES:
        return "driven"
    if "motor" in endpoint_text:
        return "driver"
    if any(word in endpoint_text for word in ["pump", "fan", "blower", "compressor"]):
        return "driven"
    return "unknown"


def _endpoint_metadata(endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]], endpoint_id: str) -> Dict[str, Any]:
    raw_meta: Mapping[str, Any] = endpoint_metadata.get(endpoint_id, {}) if endpoint_metadata and endpoint_id in endpoint_metadata else {}
    installed_on = str(raw_meta.get("installed_on") or raw_meta.get("mount_type") or raw_meta.get("mounted_on") or "unknown").strip().lower()
    component_type = str(raw_meta.get("component_type") or raw_meta.get("component") or "unknown").strip().lower()
    endpoint_role = _resolve_endpoint_role(endpoint_id, raw_meta)
    shaft_group_id = str(raw_meta.get("shaft_group_id") or raw_meta.get("shaft_id") or raw_meta.get("train_id") or raw_meta.get("coupling_group_id") or "").strip().lower()
    coupling_id = str(raw_meta.get("coupling_id") or raw_meta.get("coupling") or raw_meta.get("coupling_group_id") or "").strip().lower()
    local_rpm = _float_or_none(raw_meta.get("local_rpm") or raw_meta.get("rpm") or raw_meta.get("running_rpm"))
    is_coupling_end = bool(_truthy(raw_meta.get("is_coupling_end")) or _truthy(raw_meta.get("coupling_end")) or endpoint_role == "DE")
    return {
        "installed_on": installed_on,
        "component_type": component_type,
        "endpoint_role": endpoint_role,
        "is_coupling_end": is_coupling_end,
        "shaft_group_id": shaft_group_id,
        "coupling_id": coupling_id,
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


def _extract_axis_features(
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
        raise ValueError("rpm must be positive for coupling-related shaft fault detection.")
    source = _as_float_array(waveform)
    if source.size < 128:
        raise ValueError("Need at least 128 samples for coupling-related shaft fault detection.")
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
    orders = {"05x": 0.5, "1x": 1.0, "15x": 1.5, "2x": 2.0, "25x": 2.5, "3x": 3.0, "35x": 3.5, "4x": 4.0, "5x": 5.0, "6x": 6.0}
    order_peaks: Dict[str, Dict[str, float]] = {}
    for name, order_value in orders.items():
        peak_hz, amp = _peak_at(freqs, amps, target_hz=order_value * shaft_hz, tolerance_hz=tolerance_hz)
        order_peaks[name] = {"order": float(order_value), "target_hz": float(order_value * shaft_hz), "peak_hz": float(peak_hz), "amp": float(amp)}
    rms_spectrum = max(_rms(amps), _EPS)
    noise_floor = float(np.median(np.abs(amps))) if amps.size else 0.0
    dominant_idx = int(np.argmax(amps))
    dominant_freq_hz = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])
    dominant_order = _safe_ratio(dominant_freq_hz, shaft_hz)
    amp = lambda name: float(order_peaks[name]["amp"])
    ratio = lambda value: _safe_ratio(value, rms_spectrum)
    fractional = amp("05x") + amp("15x") + amp("25x") + amp("35x")
    harmonic_2_to_5 = amp("2x") + amp("3x") + amp("4x") + amp("5x")
    severe_harmonics = amp("3x") + amp("4x") + amp("5x")
    high_order_harmonics = amp("4x") + amp("5x") + amp("6x")
    pulse_series = np.abs(velocity - float(np.mean(velocity)))
    wf_1x_pulse = _cached_best_autocorr_near_lag(pulse_series, int(round(fs_hz / shaft_hz))) if shaft_hz > 0.0 else 0.0
    wf_2x_pulse = _cached_best_autocorr_near_lag(pulse_series, int(round(fs_hz / (2.0 * shaft_hz)))) if shaft_hz > 0.0 else 0.0
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
        "dominant_freq_hz": dominant_freq_hz,
        "dominant_amp": dominant_amp,
        "dominant_order": float(dominant_order),
        "wf_1x_pulse": float(wf_1x_pulse),
        "wf_2x_pulse": float(wf_2x_pulse),
        "order_peaks": order_peaks,
        "ratio_05x": ratio(amp("05x")),
        "ratio_1x": ratio(amp("1x")),
        "ratio_15x": ratio(amp("15x")),
        "ratio_2x": ratio(amp("2x")),
        "ratio_25x": ratio(amp("25x")),
        "ratio_3x": ratio(amp("3x")),
        "ratio_35x": ratio(amp("35x")),
        "ratio_4x": ratio(amp("4x")),
        "ratio_5x": ratio(amp("5x")),
        "ratio_6x": ratio(amp("6x")),
        "ratio_fractional": ratio(fractional),
        "ratio_harmonic_2_to_5": ratio(harmonic_2_to_5),
        "ratio_severe_harmonics": ratio(severe_harmonics),
        "ratio_high_order_harmonics": ratio(high_order_harmonics),
        "ratio_2x_over_1x": _safe_ratio(amp("2x"), max(amp("1x"), _EPS)),
        "ratio_1x_over_2x": _safe_ratio(amp("1x"), max(amp("2x"), _EPS), default=99.0),
        "ratio_1x_over_3x": _safe_ratio(amp("1x"), max(amp("3x"), _EPS), default=99.0),
    }


def _coupling_location_factor(meta: Mapping[str, Any]) -> Tuple[float, List[str]]:
    endpoint_role = str(meta.get("endpoint_role", "unknown")).upper()
    is_coupling_end = bool(meta.get("is_coupling_end", False))
    installed_on = str(meta.get("installed_on", "unknown")).lower()
    limitations: List[str] = []
    if endpoint_role == "DE" or is_coupling_end:
        base = 1.22
    elif endpoint_role == "NDE":
        base = 0.58
        limitations.append("Reduced because this endpoint is NDE, not the coupling/drive end.")
    else:
        base = 0.78
        limitations.append("Endpoint DE/NDE role is unknown; coupling-location confidence is reduced.")
    if installed_on in {"base", "foundation"}:
        base *= 0.72
        limitations.append("Reduced because this endpoint is on base/foundation rather than coupling-end bearing housing/casing.")
    return float(base), limitations


def _axis_weight_for_coupling(axis: str, meta: Mapping[str, Any], subtype: str) -> float:
    axis = _norm_axis_name(axis)
    if subtype in {"coupling_angular_misalignment", "coupling_mixed_misalignment"}:
        base = 1.0 if _axis_is_axial(axis) else 0.68
    elif subtype == "coupling_parallel_offset_misalignment":
        base = 1.0 if not _axis_is_axial(axis) else 0.75
    elif subtype == "coupling_runout_or_eccentricity_like":
        base = 1.0 if not _axis_is_axial(axis) else 0.45
    else:
        base = 1.0 if not _axis_is_axial(axis) else 0.85
    if bool(meta.get("is_coupling_end", False)):
        base *= 1.10
    return float(base)


def _classify_coupling_pattern(axis: str, features: Mapping[str, Any]) -> Tuple[str, Dict[str, float]]:
    ratio1 = float(features["ratio_1x"])
    ratio2 = float(features["ratio_2x"])
    ratio3 = float(features["ratio_3x"])
    ratio_2x_over_1x = float(features["ratio_2x_over_1x"])
    axial_1x = ratio1 if _axis_is_axial(axis) else 0.0
    axial_2x = ratio2 if _axis_is_axial(axis) else 0.0
    radial_2x = ratio2 if not _axis_is_axial(axis) else 0.0
    severe_harmonics = float(features["ratio_severe_harmonics"])
    harmonic_2_to_5 = float(features["ratio_harmonic_2_to_5"])
    fractional = float(features["ratio_fractional"])
    noise_ratio = float(features["noise_floor_ratio"])
    wf_1x_pulse = float(features["wf_1x_pulse"])
    wf_2x_pulse = float(features["wf_2x_pulse"])
    dominant_order = float(features["dominant_order"])
    dominant_near_1x = 1.0 - min(abs(dominant_order - 1.0), 1.0)
    angular_score = 100.0 * (0.62 * _score_linear(axial_1x, 0.8, 3.0) + 0.25 * _score_linear(axial_2x, 0.4, 2.2) + 0.13 * _score_linear(ratio_2x_over_1x, 0.45, 1.30))
    parallel_score = 100.0 * (0.52 * _score_linear(ratio_2x_over_1x, 0.50, 1.50) + 0.34 * _score_linear(radial_2x, 0.6, 2.6) + 0.14 * _score_linear(severe_harmonics, 0.7, 2.8))
    wear_looseness_score = 100.0 * (
        0.34 * _score_linear(harmonic_2_to_5, 1.0, 4.2)
        + 0.22 * _score_linear(wf_2x_pulse, 0.10, 0.42)
        + 0.18 * _score_linear(ratio_2x_over_1x, 0.35, 1.20)
        + 0.14 * _score_linear(fractional, 0.35, 1.8)
        + 0.12 * _score_linear(noise_ratio, 0.06, 0.22)
    )
    if fractional > 2.8:
        wear_looseness_score *= 0.72
    runout_score = 100.0 * (
        0.42 * _score_linear(ratio1, 1.6, 4.8)
        + 0.24 * _score_linear(float(features["ratio_1x_over_2x"]), 1.2, 3.5)
        + 0.16 * _score_linear(float(features["ratio_1x_over_3x"]), 1.2, 3.0)
        + 0.12 * max(0.0, dominant_near_1x)
        + 0.06 * _score_linear(wf_1x_pulse, 0.10, 0.40)
    )
    if ratio2 + ratio3 > 4.0 or fractional > 2.2:
        runout_score *= 0.70
    scores = {
        "coupling_angular_misalignment": float(angular_score),
        "coupling_parallel_offset_misalignment": float(parallel_score),
        "coupling_wear_or_looseness_like": float(wear_looseness_score),
        "coupling_runout_or_eccentricity_like": float(runout_score),
    }
    if angular_score >= 35.0 and parallel_score >= 35.0:
        scores["coupling_mixed_misalignment"] = max(angular_score, parallel_score) + 8.0
    subtype = max(scores, key=lambda key: scores[key])
    return subtype, scores


def _score_coupling_axis(*, endpoint_id: str, axis: str, features: Mapping[str, Any], meta: Mapping[str, Any]) -> Dict[str, Any]:
    subtype, subtype_scores = _classify_coupling_pattern(axis, features)
    raw_score = float(subtype_scores[subtype])
    ratio1 = float(features["ratio_1x"])
    ratio2 = float(features["ratio_2x"])
    ratio3 = float(features["ratio_3x"])
    amp2_over_1 = float(features["ratio_2x_over_1x"])
    axial_1x = ratio1 if _axis_is_axial(axis) else 0.0
    axial_2x = ratio2 if _axis_is_axial(axis) else 0.0
    radial_2x = ratio2 if not _axis_is_axial(axis) else 0.0
    severe_harmonics = float(features["ratio_severe_harmonics"])
    harmonic_2_to_5 = float(features["ratio_harmonic_2_to_5"])
    fractional = float(features["ratio_fractional"])
    limitations: List[str] = []
    if subtype != "coupling_runout_or_eccentricity_like":
        if amp2_over_1 < 0.50 and axial_1x < 0.80:
            raw_score *= 0.55
            limitations.append("Reduced because 2X/1X and axial 1X are both weak for a coupling/misalignment call.")
        if amp2_over_1 < 0.35:
            raw_score *= 0.70
            limitations.append("Reduced because 2X/1X is well below the usual coupling/misalignment range.")
        if not _axis_is_axial(axis) and radial_2x < 0.45 and subtype != "coupling_wear_or_looseness_like":
            raw_score *= 0.78
            limitations.append("Reduced because radial 2X is weak on this non-axial axis.")
    location_factor, location_limits = _coupling_location_factor(meta)
    axis_weight = _axis_weight_for_coupling(axis, meta, subtype)
    limitations.extend(location_limits)
    score = _clamp(raw_score * location_factor * axis_weight, 0.0, 100.0)
    return {
        "fault": "coupling_related_shaft_fault",
        "label": "Coupling-related shaft fault",
        "subtype": subtype,
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "possible": bool(score >= 20.0),
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "is_coupling_end": bool(meta.get("is_coupling_end", False)),
        "shaft_group_id": str(meta.get("shaft_group_id", "")),
        "coupling_id": str(meta.get("coupling_id", "")),
        "local_rpm": float(meta.get("local_rpm") or 0.0),
        "metrics": {
            "ratio_1x": ratio1, "ratio_2x": ratio2, "ratio_3x": ratio3, "ratio_4x": float(features["ratio_4x"]), "ratio_5x": float(features["ratio_5x"]),
            "ratio_2x_over_1x": amp2_over_1, "ratio_1x_over_2x": float(features["ratio_1x_over_2x"]), "ratio_fractional": fractional,
            "radial_2x": radial_2x, "axial_1x": axial_1x, "axial_2x": axial_2x, "severe_harmonics": severe_harmonics,
            "harmonic_2_to_5": harmonic_2_to_5, "dominant_order": float(features["dominant_order"]), "waveform_1x_pulse": float(features["wf_1x_pulse"]),
            "waveform_2x_pulse": float(features["wf_2x_pulse"]), "noise_floor_ratio": float(features["noise_floor_ratio"]),
            "axis_weight": float(axis_weight), "location_factor": float(location_factor),
            "subtype_score_angular": float(subtype_scores.get("coupling_angular_misalignment", 0.0)),
            "subtype_score_parallel": float(subtype_scores.get("coupling_parallel_offset_misalignment", 0.0)),
            "subtype_score_wear_looseness": float(subtype_scores.get("coupling_wear_or_looseness_like", 0.0)),
            "subtype_score_runout": float(subtype_scores.get("coupling_runout_or_eccentricity_like", 0.0)),
            "subtype_score_mixed": float(subtype_scores.get("coupling_mixed_misalignment", 0.0)),
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: coupling score={score:.1f}, subtype={subtype}, "
            f"2X/1X={amp2_over_1:.2f}, radial_2X={radial_2x:.2f}xRMS, "
            f"axial_1X={axial_1x:.2f}xRMS, axial_2X={axial_2x:.2f}xRMS, "
            f"harmonic_2_to_5={harmonic_2_to_5:.2f}xRMS, frac={fractional:.2f}xRMS, "
            f"role={meta.get('endpoint_role', 'unknown')}"
        ),
    }


def _score_unbalance_like_axis(*, endpoint_id: str, axis: str, features: Mapping[str, Any], meta: Mapping[str, Any]) -> Dict[str, Any]:
    ratio1 = float(features["ratio_1x"])
    ratio2 = float(features["ratio_2x"])
    ratio3 = float(features["ratio_3x"])
    one_over_two = float(features["ratio_1x_over_2x"])
    one_over_three = float(features["ratio_1x_over_3x"])
    dominant_near_1x = 1.0 - min(abs(float(features["dominant_order"]) - 1.0), 1.0)
    fractional = float(features["ratio_fractional"])
    raw_score = (
        35.0 * _score_linear(ratio1, 1.8, 5.0)
        + 20.0 * _score_linear(one_over_two, 1.2, 3.5)
        + 15.0 * _score_linear(one_over_three, 1.2, 3.0)
        + 15.0 * max(0.0, dominant_near_1x)
        + 10.0 * (1.0 - _score_linear(ratio2 + ratio3, 2.5, 6.0))
        + 5.0 * (1.0 - _score_linear(fractional, 1.0, 3.0))
    )
    axis_weight = 0.35 if _axis_is_axial(axis) else 1.0
    if str(meta.get("installed_on", "unknown")).lower() in {"base", "foundation"}:
        axis_weight *= 0.70
    return {
        "fault": "unbalance_like_1x_competing_pattern",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(_clamp(raw_score * axis_weight, 0.0, 100.0)),
        "metrics": {
            "ratio_1x": ratio1, "ratio_2x": ratio2, "ratio_3x": ratio3, "ratio_1x_over_2x": one_over_two,
            "ratio_1x_over_3x": one_over_three, "dominant_order": float(features["dominant_order"]), "fractional_ratio": fractional,
        },
    }


def _aggregate_global(scores: List[float], endpoint_ids: List[str]) -> float:
    if not scores:
        return 0.0
    return float(_clamp(0.68 * _top_mean(scores, n=4) + 18.0 * _score_linear(_distinct_count(endpoint_ids), 1.0, 4.0) + 14.0 * _score_linear(sum(1 for s in scores if s >= 45.0), 1.0, 4.0), 0.0, 100.0))


def _summarize_endpoint(endpoint_id: str, meta: Mapping[str, Any], axis_rows: List[Dict[str, Any]], endpoint_rpm: float) -> Dict[str, Any]:
    scores = [float(row["score"]) for row in axis_rows]
    high_rows = [row for row in axis_rows if float(row["score"]) >= 45.0]
    best_axis_row = max(axis_rows, key=lambda row: float(row["score"])) if axis_rows else None
    metrics = lambda key: max((float(row["metrics"].get(key, 0.0)) for row in axis_rows), default=0.0)
    subtype_votes: Dict[str, float] = {}
    for row in axis_rows:
        subtype = str(row.get("subtype", "unknown"))
        subtype_votes[subtype] = max(subtype_votes.get(subtype, 0.0), float(row.get("score", 0.0)))
    dominant_subtype = max(subtype_votes, key=subtype_votes.get) if subtype_votes else "unknown"
    has_axial_axis = any(_axis_is_axial(str(row.get("axis", ""))) for row in axis_rows)
    has_radial_axis = any(not _axis_is_axial(str(row.get("axis", ""))) for row in axis_rows)
    endpoint_score = _clamp(0.78 * _top_mean(scores, n=3) + 12.0 * _score_linear(len(high_rows), 1.0, 3.0) + 10.0 * _score_linear(float(has_axial_axis and has_radial_axis), 0.0, 1.0), 0.0, 100.0) if scores else 0.0
    return {
        "endpoint_id": endpoint_id,
        "score": float(endpoint_score),
        "possible": bool(endpoint_score >= 20.0),
        "dominant_subtype": dominant_subtype,
        "best_axis": best_axis_row["axis"] if best_axis_row else None,
        "best_axis_score": float(best_axis_row["score"]) if best_axis_row else 0.0,
        "best_axis_evidence": best_axis_row["evidence"] if best_axis_row else "",
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "is_coupling_end": bool(meta.get("is_coupling_end", False)),
        "shaft_group_id": str(meta.get("shaft_group_id", "")),
        "coupling_id": str(meta.get("coupling_id", "")),
        "local_rpm": float(endpoint_rpm),
        "supporting_axes": [row["axis"] for row in high_rows],
        "axis_count": int(len(axis_rows)),
        "high_axis_count": int(len(high_rows)),
        "has_axial_axis": bool(has_axial_axis),
        "has_radial_axis": bool(has_radial_axis),
        "metrics": {
            "max_axial_1x": float(metrics("axial_1x")),
            "max_axial_2x": float(metrics("axial_2x")),
            "max_radial_2x": float(metrics("radial_2x")),
            "max_2x_over_1x": float(metrics("ratio_2x_over_1x")),
            "max_1x": float(metrics("ratio_1x")),
            "max_harmonic_2_to_5": float(metrics("harmonic_2_to_5")),
            "max_fractional_ratio": float(metrics("ratio_fractional")),
            "max_waveform_2x_pulse": float(metrics("waveform_2x_pulse")),
            "mean_axis_score": _mean_or_zero(scores),
            "top_axis_score": max(scores) if scores else 0.0,
        },
    }


def _endpoint_is_de_candidate(row: Mapping[str, Any]) -> bool:
    return str(row.get("endpoint_role", "unknown")).upper() == "DE" or bool(row.get("is_coupling_end", False))


def _endpoints_are_same_shaft_compatible(left: Mapping[str, Any], right: Mapping[str, Any], *, rpm_tolerance_pct: float = 5.0) -> bool:
    if str(left.get("endpoint_id")) == str(right.get("endpoint_id")):
        return False
    left_group = str(left.get("shaft_group_id", "") or "").strip().lower()
    right_group = str(right.get("shaft_group_id", "") or "").strip().lower()
    if left_group and right_group and left_group != right_group:
        return False
    left_coupling = str(left.get("coupling_id", "") or "").strip().lower()
    right_coupling = str(right.get("coupling_id", "") or "").strip().lower()
    if left_coupling and right_coupling and left_coupling != right_coupling:
        return False
    left_rpm = _float_or_none(left.get("local_rpm"))
    right_rpm = _float_or_none(right.get("local_rpm"))
    if left_rpm and right_rpm and left_rpm > 0.0 and right_rpm > 0.0:
        avg_rpm = 0.5 * (left_rpm + right_rpm)
        if 100.0 * abs(left_rpm - right_rpm) / max(avg_rpm, _EPS) > rpm_tolerance_pct:
            return False
    return True


def _endpoint_pair_vector(row: Mapping[str, Any]) -> np.ndarray:
    metrics = row.get("metrics", {}) or {}
    value = lambda key: float(metrics.get(key, 0.0)) if np.isfinite(float(metrics.get(key, 0.0) or 0.0)) else 0.0
    return np.asarray([
        value("max_2x_over_1x"),
        value("max_radial_2x"),
        value("max_axial_1x"),
        value("max_axial_2x"),
        value("max_harmonic_2_to_5"),
        value("max_fractional_ratio"),
        value("max_waveform_2x_pulse"),
    ], dtype=float)


def _log_vector_similarity(left_vector: np.ndarray, right_vector: np.ndarray) -> float:
    left = np.asarray(left_vector, dtype=float)
    right = np.asarray(right_vector, dtype=float)
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    left = np.maximum(left, 0.0)
    right = np.maximum(right, 0.0)
    return _clamp(float(np.exp(-float(np.mean(np.abs(np.log1p(left) - np.log1p(right)))))), 0.0, 1.0)


def _de_pair_preference_multiplier(left: Mapping[str, Any], right: Mapping[str, Any]) -> Tuple[float, str]:
    left_side = str(left.get("component_side", "unknown"))
    right_side = str(right.get("component_side", "unknown"))
    sides = {left_side, right_side}
    if sides == {"driver", "driven"}:
        return 1.18, "driver_driven_de_pair"
    if left_side != "unknown" and right_side != "unknown" and left_side != right_side:
        return 1.08, "different_component_de_pair"
    if left_side == right_side and left_side != "unknown":
        return 0.88, "same_component_side_de_pair"
    return 1.0, "generic_de_pair"


def _best_de_pair_support(endpoint_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    de_rows = [row for row in endpoint_summaries if _endpoint_is_de_candidate(row)]
    if len(de_rows) < 2:
        return {"available": False, "used": False, "reason": "Less than two DE/coupling-end endpoints are available.", "pair_score": 0.0, "similarity": 0.0}
    best: Optional[Dict[str, Any]] = None
    for i in range(len(de_rows)):
        for j in range(i + 1, len(de_rows)):
            left = de_rows[i]
            right = de_rows[j]
            if not _endpoints_are_same_shaft_compatible(left, right):
                continue
            similarity = _log_vector_similarity(_endpoint_pair_vector(left), _endpoint_pair_vector(right))
            left_score = float(left.get("score", 0.0))
            right_score = float(right.get("score", 0.0))
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            pair_score = _clamp((0.75 * min(left_score, right_score) + 0.25 * (0.5 * (left_score + right_score))) * (0.55 + 0.45 * similarity) * pair_multiplier, 0.0, 100.0)
            dominant_subtype_match = str(left.get("dominant_subtype")) == str(right.get("dominant_subtype"))
            if dominant_subtype_match:
                pair_score = _clamp(pair_score + 4.0, 0.0, 100.0)
            candidate = {
                "available": True,
                "used": bool(pair_score >= 35.0),
                "pair_class": pair_class,
                "pair_score": float(pair_score),
                "similarity": float(similarity),
                "dominant_subtype_match": bool(dominant_subtype_match),
                "endpoint_a": str(left.get("endpoint_id")),
                "score_a": float(left_score),
                "best_axis_a": str(left.get("best_axis")),
                "dominant_subtype_a": str(left.get("dominant_subtype")),
                "component_type_a": str(left.get("component_type", "unknown")),
                "component_side_a": str(left.get("component_side", "unknown")),
                "endpoint_b": str(right.get("endpoint_id")),
                "score_b": float(right_score),
                "best_axis_b": str(right.get("best_axis")),
                "dominant_subtype_b": str(right.get("dominant_subtype")),
                "component_type_b": str(right.get("component_type", "unknown")),
                "component_side_b": str(right.get("component_side", "unknown")),
                "shaft_group_id": str(left.get("shaft_group_id") or right.get("shaft_group_id") or ""),
                "coupling_id": str(left.get("coupling_id") or right.get("coupling_id") or ""),
                "local_rpm_a": float(left.get("local_rpm", 0.0) or 0.0),
                "local_rpm_b": float(right.get("local_rpm", 0.0) or 0.0),
                "metrics_a": dict(left.get("metrics", {}) or {}),
                "metrics_b": dict(right.get("metrics", {}) or {}),
            }
            if best is None or candidate["pair_score"] > best["pair_score"]:
                best = candidate
    if best is None:
        return {"available": False, "used": False, "reason": "DE endpoints exist, but no compatible same-shaft/same-speed/coupling pair was found.", "pair_score": 0.0, "similarity": 0.0}
    return best


def _coupling_recommendations(score: float, confidence: str) -> List[str]:
    severity_action = {
        "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
        "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
        "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
    }[_fault_urgency(score, confidence)]
    return [
        severity_action,
        "Inspect coupling condition, flexible element/spider/grid/disc pack, hub fit, keyway, guard rub marks, end float and coupling-hub runout.",
        "Perform laser alignment with thermal targets and re-measure DE axial/radial vibration after correction.",
        "Check pipe strain, base distortion and soft foot before replacing coupling parts only.",
    ]


def detect_coupling_related_shaft_faults(
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
    phase_data_available: bool = False,
    alignment_confirmation_available: bool = False,
    competing_unbalance_score: Optional[float] = None,
    competing_looseness_score: Optional[float] = None,
    competing_hydraulic_pass_score: Optional[float] = None,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for coupling-related shaft fault detection.")
    endpoints = _normalize_triaxial_twf(vibration_twf, axes=axes)
    shaft_hz = rpm / 60.0
    confidence_cap = "high" if (phase_data_available or alignment_confirmation_available) else "medium"
    endpoint_results: Dict[str, Any] = {}
    all_axis_rows: List[Dict[str, Any]] = []
    all_unbalance_like_rows: List[Dict[str, Any]] = []
    endpoint_summaries: List[Dict[str, Any]] = []
    for endpoint_id, axis_map in endpoints.items():
        meta = _endpoint_metadata(endpoint_metadata, endpoint_id)
        endpoint_rpm = float(meta.get("local_rpm") or rpm)
        meta["local_rpm"] = endpoint_rpm
        endpoint_axis_rows: List[Dict[str, Any]] = []
        endpoint_results[endpoint_id] = {"metadata": meta, "rpm_used": float(endpoint_rpm), "axes": {}, "fault_summary": None}
        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "features": {}, "fault": None, "competing_unbalance_like": None, "error": None}
            try:
                features = _extract_axis_features(waveform=axis_values, fs_hz=fs_hz, rpm=endpoint_rpm, signal_type=signal_type, acceleration_unit=acceleration_unit, integration_low_cut_hz=integration_low_cut_hz, target_tolerance_pct=target_tolerance_pct)
                fault_row = _score_coupling_axis(endpoint_id=endpoint_id, axis=axis, features=features, meta=meta)
                unbalance_like_row = _score_unbalance_like_axis(endpoint_id=endpoint_id, axis=axis, features=features, meta=meta)
                endpoint_axis_rows.append(fault_row)
                all_axis_rows.append(fault_row)
                all_unbalance_like_rows.append(unbalance_like_row)
                axis_result["valid"] = True
                axis_result["features"] = {
                    "samples": features["samples"], "duration_s": features["duration_s"], "shaft_hz": features["shaft_hz"], "rpm_used": float(endpoint_rpm),
                    "freq_resolution_hz": features["freq_resolution_hz"], "tolerance_hz": features["tolerance_hz"], "dominant_freq_hz": features["dominant_freq_hz"],
                    "dominant_order": features["dominant_order"], "rms_spectrum": features["rms_spectrum"], "noise_floor_ratio": features["noise_floor_ratio"],
                    "ratio_1x": features["ratio_1x"], "ratio_2x": features["ratio_2x"], "ratio_3x": features["ratio_3x"], "ratio_4x": features["ratio_4x"],
                    "ratio_5x": features["ratio_5x"], "ratio_2x_over_1x": features["ratio_2x_over_1x"], "ratio_fractional": features["ratio_fractional"],
                    "ratio_harmonic_2_to_5": features["ratio_harmonic_2_to_5"], "ratio_severe_harmonics": features["ratio_severe_harmonics"],
                    "waveform_1x_pulse": features["wf_1x_pulse"], "waveform_2x_pulse": features["wf_2x_pulse"],
                }
                axis_result["fault"] = fault_row
                axis_result["competing_unbalance_like"] = unbalance_like_row
            except Exception as exc:
                axis_result["error"] = str(exc)
            endpoint_results[endpoint_id]["axes"][axis] = axis_result
        endpoint_summary = _summarize_endpoint(endpoint_id=endpoint_id, meta=meta, axis_rows=endpoint_axis_rows, endpoint_rpm=endpoint_rpm)
        endpoint_results[endpoint_id]["fault_summary"] = endpoint_summary
        endpoint_summaries.append(endpoint_summary)
    local_scores = [float(row["score"]) for row in all_axis_rows]
    endpoint_ids_for_scores = [str(row["endpoint_id"]) for row in all_axis_rows]
    base_score = _aggregate_global(local_scores, endpoint_ids_for_scores)
    de_pair_support = _best_de_pair_support(endpoint_summaries)
    de_pair_boost = 0.0
    de_pair_text = ""
    if bool(de_pair_support.get("available", False)):
        pair_score = float(de_pair_support.get("pair_score", 0.0))
        de_pair_boost = 25.0 * _score_linear(pair_score, 35.0, 78.0)
        if de_pair_boost > 0.0:
            de_pair_text = (
                f"DE-pair support {de_pair_support.get('endpoint_a')} <-> {de_pair_support.get('endpoint_b')}: "
                f"pair_score={pair_score:.1f}, similarity={float(de_pair_support.get('similarity', 0.0)):.2f}, "
                f"class={de_pair_support.get('pair_class')}, subtypes={de_pair_support.get('dominant_subtype_a')} / {de_pair_support.get('dominant_subtype_b')}"
            )
    score = _clamp(base_score + de_pair_boost, 0.0, 100.0)
    high_rows = [row for row in all_axis_rows if float(row["score"]) >= 45.0]
    axial_support_rows = [row for row in high_rows if _axis_is_axial(str(row.get("axis", "")))]
    radial_support_rows = [row for row in high_rows if not _axis_is_axial(str(row.get("axis", "")))]
    coupling_support_endpoints = sorted({
        str(row["endpoint_id"]) for row in high_rows if bool(row.get("is_coupling_end", False)) or str(row.get("endpoint_role", "unknown")).upper() == "DE"
    } | {
        str(row["endpoint_id"]) for row in endpoint_summaries if (bool(row.get("is_coupling_end", False)) or str(row.get("endpoint_role", "unknown")).upper() == "DE") and float(row.get("score", 0.0)) >= 35.0
    })
    metric_list = lambda key, rows=all_axis_rows: [float(row["metrics"].get(key, 0.0)) for row in rows]
    ratio_1x_values = metric_list("ratio_1x")
    ratio_2x_values = metric_list("ratio_2x")
    ratio_3x_values = metric_list("ratio_3x")
    ratio_frac_values = metric_list("ratio_fractional")
    ratio_2x_over_1x_values = metric_list("ratio_2x_over_1x")
    axial_1x_values = [float(row["metrics"].get("axial_1x", 0.0)) for row in all_axis_rows if _axis_is_axial(str(row.get("axis", "")))]
    axial_2x_values = [float(row["metrics"].get("axial_2x", 0.0)) for row in all_axis_rows if _axis_is_axial(str(row.get("axis", "")))]
    radial_2x_values = [float(row["metrics"].get("radial_2x", 0.0)) for row in all_axis_rows if not _axis_is_axial(str(row.get("axis", "")))]
    harmonic_values = metric_list("harmonic_2_to_5")
    severe_harmonic_values = metric_list("severe_harmonics")
    waveform_2x_values = metric_list("waveform_2x_pulse")
    limitations: List[str] = []
    evidence_items: List[str] = []
    if not (phase_data_available or alignment_confirmation_available):
        limitations.append("Confidence capped at medium because phase/alignment confirmation is not available.")
    limitations.append("Use alignment, coupling inspection, soft-foot, pipe-strain and runout checks to separate overlapping shaft/support faults.")
    mean_2x_over_1x = _mean_or_zero(ratio_2x_over_1x_values)
    mean_radial_2x = _mean_or_zero(radial_2x_values)
    mean_axial_1x = _mean_or_zero(axial_1x_values)
    mean_axial_2x = _mean_or_zero(axial_2x_values)
    mean_harmonic_2_to_5 = _mean_or_zero(harmonic_values)
    mean_fractional = _mean_or_zero(ratio_frac_values)
    mean_waveform_2x = _mean_or_zero(waveform_2x_values)
    if len(coupling_support_endpoints) < 1 and not bool(de_pair_support.get("used", False)):
        score *= 0.55
        limitations.append("Reduced because coupling-end/DE support is weak for a coupling-related shaft fault call.")
    if mean_2x_over_1x < 0.40 and mean_axial_1x < 0.70 and mean_harmonic_2_to_5 < 1.25 and not bool(de_pair_support.get("used", False)):
        score *= 0.58
        limitations.append("Reduced because 2X/1X, axial 1X and coupling harmonic support are all weak.")
    if mean_radial_2x < 0.45 and mean_axial_1x < 0.70 and mean_waveform_2x < 0.12:
        score *= 0.70
        limitations.append("Reduced because neither radial 2X, axial 1X nor 2X waveform pulse supports a coupling-end fault strongly.")
    internal_unbalance_like_score = _aggregate_global([float(row["score"]) for row in all_unbalance_like_rows], [str(row["endpoint_id"]) for row in all_unbalance_like_rows])
    external_unbalance_score = float(competing_unbalance_score) if competing_unbalance_score is not None else 0.0
    unbalance_like_score = max(internal_unbalance_like_score, external_unbalance_score)
    if unbalance_like_score >= 45.0 and mean_2x_over_1x < 0.60 and not bool(de_pair_support.get("used", False)):
        score *= 0.68
        limitations.append("Reduced because simpler 1X/unbalance-like behavior explains the pattern better than a coupling fault.")
    if competing_looseness_score is not None and float(competing_looseness_score) >= 60.0 and mean_harmonic_2_to_5 >= 2.0 and len(coupling_support_endpoints) < 2:
        score *= 0.72
        limitations.append("Reduced because looseness can explain the harmonic pattern and DE-pair coupling support is limited.")
    if competing_hydraulic_pass_score is not None and float(competing_hydraulic_pass_score) >= 60.0 and mean_2x_over_1x < 1.20:
        score *= 0.72
        limitations.append("Reduced because hydraulic pass-frequency forcing can mimic 2X/axial coupling symptoms on pumps unless 2X/1X is clearly strong.")
    score = _clamp(score, 0.0, 100.0)
    confidence = _confidence_from_score(score, cap=confidence_cap)
    best_axis_row = max(all_axis_rows, key=lambda row: float(row["score"])) if all_axis_rows else None
    best_endpoint_summary = max(endpoint_summaries, key=lambda row: float(row["score"])) if endpoint_summaries else None
    if best_axis_row:
        evidence_items.append(str(best_axis_row.get("evidence", "")))
    if de_pair_text:
        evidence_items.append(de_pair_text)
    if not bool(de_pair_support.get("available", False)):
        limitations.append("No usable DE-to-DE same-shaft/coupling pair was available; result falls back to endpoint/axis aggregation.")
    if not any(_axis_is_axial(str(row.get("axis", ""))) for row in all_axis_rows):
        limitations.append("No explicit axial axis label was found; angular coupling fault confidence is limited. Pass axes=['horizontal','vertical','axial'] when orientation is known.")
    subtype_buckets: Dict[str, List[float]] = {}
    for row in all_axis_rows:
        subtype_buckets.setdefault(str(row.get("subtype", "unknown")), []).append(float(row.get("score", 0.0)))
    subtype_scores_asset = {key: _top_mean(vals, n=4) for key, vals in subtype_buckets.items()}
    dominant_subtype = max(subtype_scores_asset, key=subtype_scores_asset.get) if subtype_scores_asset else "unknown"
    primary_fault = None
    possible_faults: List[Dict[str, Any]] = []
    if score >= min_score:
        primary_fault = {
            "fault": "coupling_related_shaft_fault",
            "label": "Coupling-related shaft fault",
            "scope": "asset_wide",
            "subtype": dominant_subtype,
            "score": float(score),
            "base_score_before_de_pair": float(base_score),
            "de_pair_boost": float(de_pair_boost),
            "confidence": confidence,
            "possible": True,
            "urgency": _fault_urgency(score, confidence),
            "best_endpoint": best_endpoint_summary["endpoint_id"] if best_endpoint_summary else None,
            "best_axis": best_axis_row["axis"] if best_axis_row else None,
            "best_axis_score": float(best_axis_row["score"]) if best_axis_row else 0.0,
            "supporting_endpoints": sorted({str(row["endpoint_id"]) for row in high_rows}),
            "supporting_axis_count": int(len(high_rows)),
            "coupling_support_endpoints": coupling_support_endpoints,
            "evidence": " | ".join(item for item in evidence_items if item),
            "limitations": limitations,
            "recommendations": _coupling_recommendations(score, confidence),
            "metrics": {
                "num_supporting_axes": float(len(all_axis_rows)),
                "num_supporting_endpoints": float(_distinct_count(endpoint_ids_for_scores)),
                "num_high_support_axes": float(len(high_rows)),
                "num_axial_support_axes": float(len(axial_support_rows)),
                "num_radial_support_axes": float(len(radial_support_rows)),
                "num_coupling_support_endpoints": float(len(coupling_support_endpoints)),
                "mean_1x_ratio": _mean_or_zero(ratio_1x_values),
                "mean_2x_ratio": _mean_or_zero(ratio_2x_values),
                "mean_3x_ratio": _mean_or_zero(ratio_3x_values),
                "mean_fractional_ratio": mean_fractional,
                "mean_2x_over_1x": mean_2x_over_1x,
                "mean_axial_1x_ratio": mean_axial_1x,
                "mean_axial_2x_ratio": mean_axial_2x,
                "mean_radial_2x_ratio": mean_radial_2x,
                "mean_harmonic_2_to_5_ratio": mean_harmonic_2_to_5,
                "mean_severe_harmonics_ratio": _mean_or_zero(severe_harmonic_values),
                "mean_waveform_2x_pulse": mean_waveform_2x,
                "competing_unbalance_like_score": float(unbalance_like_score),
                "competing_looseness_score": float(competing_looseness_score) if competing_looseness_score is not None else 0.0,
                "competing_hydraulic_pass_score": float(competing_hydraulic_pass_score) if competing_hydraulic_pass_score is not None else 0.0,
                "de_pair_score": float(de_pair_support.get("pair_score", 0.0)),
                "de_pair_similarity": float(de_pair_support.get("similarity", 0.0)),
                "subtype_scores": subtype_scores_asset,
            },
        }
        possible_faults.append(primary_fault)
    return {
        "asset_id": asset_id,
        "rpm": float(rpm),
        "shaft_hz": float(shaft_hz),
        "sampling_frequency_hz": float(fs_hz),
        "signal_type": str(signal_type).lower(),
        "velocity_basis": "direct_velocity_twf" if str(signal_type).lower() in {"velocity", "vel", "mm/s", "mmps"} else "derived_velocity_from_acceleration_twf",
        "de_pair_logic": {
            "enabled": True,
            "description": "Compatible DE/coupling-end endpoints are compared first. If a same-shaft same-coupling DE pair supports the same coupling-related pattern, the score receives a bounded boost. Otherwise the detector falls back to endpoint/axis aggregation.",
            "support": de_pair_support,
        },
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "endpoint_summaries": endpoint_summaries,
        "endpoint_results": endpoint_results,
        "limitations": [
            "Coupling-related shaft faults are evaluated asset-wide using velocity-domain shaft-order evidence.",
            "Velocity TWF is preferred. If acceleration TWF is supplied, velocity is derived by frequency-domain integration.",
            "DE-to-DE comparison is only used when compatible same-shaft/same-speed/coupling endpoints are available.",
            "NDE endpoints still contribute to fallback aggregation, but they do not drive the special DE-pair boost.",
            "Confidence is capped at medium unless phase_data_available or alignment_confirmation_available is True.",
            "This detector does not replace direct coupling inspection, laser alignment, hub runout checks, or phase analysis.",
        ],
    }


__all__ = ["detect_coupling_related_shaft_faults"]
