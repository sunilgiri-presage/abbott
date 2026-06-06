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
    if _CONFIDENCE_ORDER[confidence] > _CONFIDENCE_ORDER[cap]:
        return cap
    return confidence


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
    axis = _norm_axis_name(axis)
    return axis in {"horizontal", "vertical", "radial", "x", "y", "z", "axis_1"}


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
    axis_like = bool(keys & {"x", "y", "z", "horizontal", "vertical", "axial", "radial"})
    values_are_not_nested_maps = all(not isinstance(v, Mapping) for v in obj.values())
    return axis_like and values_are_not_nested_maps


def _normalize_triaxial_twf(vibration_twf: Any, axes: Optional[List[str]] = None) -> Dict[str, Dict[str, np.ndarray]]:
    if isinstance(vibration_twf, Mapping):
        if _looks_like_axis_map(vibration_twf):
            return {
                "endpoint_1": {
                    _norm_axis_name(axis): _as_float_array(values)
                    for axis, values in vibration_twf.items()
                }
            }

        endpoints: Dict[str, Dict[str, np.ndarray]] = {}
        for endpoint_id, endpoint_data in vibration_twf.items():
            endpoint_key = str(endpoint_id)
            if isinstance(endpoint_data, Mapping):
                endpoints[endpoint_key] = {
                    _norm_axis_name(axis): _as_float_array(values)
                    for axis, values in endpoint_data.items()
                }
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
    if "nde" in tokens:
        return "NDE"
    if "non" in tokens and "drive" in tokens:
        return "NDE"
    if "non_drive_end" in joined:
        return "NDE"
    if "de" in tokens:
        return "DE"
    if "drive" in tokens and "end" in tokens:
        return "DE"
    if "coupling" in tokens and "end" in tokens:
        return "DE"
    return "unknown"


def _resolve_endpoint_role(endpoint_id: str, raw_meta: Mapping[str, Any]) -> str:
    explicit_fields = [
        "endpoint_role", "end_role", "end_type", "end", "endpoint_flag",
        "de_nde", "drive_end_flag", "bearing_end", "location_end", "position",
    ]
    for field in explicit_fields:
        if field in raw_meta and raw_meta.get(field) not in {None, ""}:
            role = _endpoint_role_from_text(raw_meta.get(field))
            if role != "unknown":
                return role

    if _truthy(raw_meta.get("is_nde")):
        return "NDE"
    if _truthy(raw_meta.get("is_de")) or _truthy(raw_meta.get("is_drive_end")):
        return "DE"
    if _truthy(raw_meta.get("is_coupling_end")):
        return "DE"

    for candidate in [
        endpoint_id,
        raw_meta.get("location_tag"),
        raw_meta.get("endpoint_tag"),
        raw_meta.get("name"),
        raw_meta.get("mount_name"),
        raw_meta.get("composite_id"),
        raw_meta.get("composite_key"),
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


def _endpoint_metadata(
    endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]],
    endpoint_id: str,
) -> Dict[str, Any]:
    raw_meta: Mapping[str, Any] = {}
    if endpoint_metadata and endpoint_id in endpoint_metadata:
        raw_meta = endpoint_metadata[endpoint_id] or {}

    installed_on = str(
        raw_meta.get("installed_on")
        or raw_meta.get("mount_type")
        or raw_meta.get("mounted_on")
        or "unknown"
    ).strip().lower()
    component_type = str(
        raw_meta.get("component_type")
        or raw_meta.get("component")
        or "unknown"
    ).strip().lower()
    endpoint_role = _resolve_endpoint_role(endpoint_id, raw_meta)
    shaft_group_id = str(
        raw_meta.get("shaft_group_id")
        or raw_meta.get("shaft_id")
        or raw_meta.get("train_id")
        or raw_meta.get("coupling_group_id")
        or ""
    ).strip().lower()
    local_rpm = _float_or_none(
        raw_meta.get("local_rpm")
        or raw_meta.get("rpm")
        or raw_meta.get("running_rpm")
    )
    is_coupling_end = bool(
        _truthy(raw_meta.get("is_coupling_end"))
        or _truthy(raw_meta.get("coupling_end"))
        or endpoint_role == "DE"
    )
    component_side = _component_side(component_type, endpoint_id)

    return {
        "installed_on": installed_on,
        "component_type": component_type,
        "endpoint_role": endpoint_role,
        "is_coupling_end": is_coupling_end,
        "shaft_group_id": shaft_group_id,
        "local_rpm": local_rpm,
        "component_side": component_side,
    }


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
        raise ValueError("rpm must be positive for misalignment detection.")

    source = _as_float_array(waveform)
    if source.size < 128:
        raise ValueError("Need at least 128 samples for misalignment detection.")

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
    orders = {"05x": 0.5, "1x": 1.0, "15x": 1.5, "2x": 2.0, "25x": 2.5, "3x": 3.0, "4x": 4.0, "5x": 5.0}

    order_peaks: Dict[str, Dict[str, float]] = {}
    for name, order_value in orders.items():
        peak_hz, amp = _peak_at(freqs, amps, order_value * shaft_hz, tolerance_hz)
        order_peaks[name] = {
            "order": float(order_value),
            "target_hz": float(order_value * shaft_hz),
            "peak_hz": float(peak_hz),
            "amp": float(amp),
        }

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
    harmonic_2_to_5 = amp("2x") + amp("3x") + amp("4x") + amp("5x")
    severe_harmonics = amp("3x") + amp("4x") + amp("5x")
    pulse_series = np.abs(velocity - float(np.mean(velocity)))
    wf_1x_pulse = 0.0
    wf_2x_pulse = 0.0
    if shaft_hz > 0.0:
        wf_1x_pulse = _cached_best_autocorr_near_lag(pulse_series, int(round(fs_hz / shaft_hz)))
        wf_2x_pulse = _cached_best_autocorr_near_lag(pulse_series, int(round(fs_hz / (2.0 * shaft_hz))))

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
        "ratio_4x": ratio(amp("4x")),
        "ratio_5x": ratio(amp("5x")),
        "ratio_fractional": ratio(fractional),
        "ratio_harmonic_2_to_5": ratio(harmonic_2_to_5),
        "ratio_severe_harmonics": ratio(severe_harmonics),
        "ratio_2x_over_1x": _safe_ratio(amp("2x"), max(amp("1x"), _EPS)),
        "ratio_1x_over_2x": _safe_ratio(amp("1x"), max(amp("2x"), _EPS), default=99.0),
        "ratio_1x_over_3x": _safe_ratio(amp("1x"), max(amp("3x"), _EPS), default=99.0),
    }


def _axis_weight_for_misalignment(axis: str, meta: Mapping[str, Any]) -> float:
    axis = _norm_axis_name(axis)
    installed_on = str(meta.get("installed_on", "unknown")).lower()
    is_coupling_end = bool(meta.get("is_coupling_end", False))
    base = 1.0 if _axis_is_axial(axis) else 0.65
    if installed_on in {"base", "foundation"}:
        base *= 0.70
    if is_coupling_end:
        base *= 1.15
    return float(base)


def _axis_weight_for_unbalance_like(axis: str, meta: Mapping[str, Any]) -> float:
    axis = _norm_axis_name(axis)
    installed_on = str(meta.get("installed_on", "unknown")).lower()
    base = 1.0 if _axis_is_radial_like(axis) and not _axis_is_axial(axis) else 0.35
    if installed_on in {"base", "foundation"}:
        base *= 0.70
    return float(base)


def _component_weight_for_misalignment(meta: Mapping[str, Any]) -> float:
    return 1.0


def _classify_misalignment_pattern(axis: str, features: Mapping[str, Any]) -> str:
    axial_1x = float(features["ratio_1x"]) if _axis_is_axial(axis) else 0.0
    axial_2x = float(features["ratio_2x"]) if _axis_is_axial(axis) else 0.0
    radial_2x = float(features["ratio_2x"]) if not _axis_is_axial(axis) else 0.0
    ratio_2x_over_1x = float(features["ratio_2x_over_1x"])
    severe_harmonics = float(features["ratio_severe_harmonics"])
    angular_score = 0.60 * _score_linear(axial_1x, 0.8, 3.0) + 0.40 * _score_linear(axial_2x, 0.4, 2.2)
    parallel_score = 0.60 * _score_linear(ratio_2x_over_1x, 0.5, 1.5) + 0.40 * _score_linear(radial_2x, 0.6, 2.6)
    severe_score = _score_linear(severe_harmonics, 0.7, 2.8)
    if severe_score >= 0.75 and max(angular_score, parallel_score) >= 0.35:
        return "severe_or_mixed_misalignment"
    if angular_score >= 0.45 and parallel_score >= 0.45:
        return "mixed_angular_parallel_misalignment"
    if angular_score > parallel_score:
        return "angular_misalignment_pattern"
    if parallel_score > angular_score:
        return "parallel_or_offset_misalignment_pattern"
    return "weak_or_indeterminate_misalignment_pattern"


def _score_misalignment_axis(
    *,
    endpoint_id: str,
    axis: str,
    features: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> Dict[str, Any]:
    ratio1 = float(features["ratio_1x"])
    ratio2 = float(features["ratio_2x"])
    amp2_over_1 = float(features["ratio_2x_over_1x"])
    axial_1x = ratio1 if _axis_is_axial(axis) else 0.0
    axial_2x = ratio2 if _axis_is_axial(axis) else 0.0
    radial_2x = ratio2 if not _axis_is_axial(axis) else 0.0
    severe_harmonics = float(features["ratio_severe_harmonics"])
    raw_score = (
        42.0 * _score_linear(amp2_over_1, 0.50, 1.50)
        + 28.0 * _score_linear(radial_2x, 0.6, 2.6)
        + 18.0 * _score_linear(axial_1x, 0.8, 3.0)
        + 8.0 * _score_linear(axial_2x, 0.4, 2.2)
        + 4.0 * _score_linear(severe_harmonics, 0.7, 2.8)
    )
    reductions: List[str] = []
    if amp2_over_1 < 0.50 and axial_1x < 0.80:
        raw_score *= 0.45
        reductions.append("Reduced because 2X/1X and axial 1X are both weak.")
    if amp2_over_1 < 0.35:
        raw_score *= 0.55
        reductions.append("Reduced again because 2X/1X is well below the usual misalignment range.")
    if not _axis_is_axial(axis) and ratio2 < 0.45:
        raw_score *= 0.74
        reductions.append("Reduced because radial 2X is weak on this non-axial axis.")

    axis_weight = _axis_weight_for_misalignment(axis, meta)
    component_weight = _component_weight_for_misalignment(meta)
    score = _clamp(raw_score * axis_weight * component_weight, 0.0, 100.0)
    pattern = _classify_misalignment_pattern(axis, features)
    return {
        "fault": "misalignment",
        "label": "Misalignment",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "possible": bool(score >= 20.0),
        "pattern": pattern,
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "is_coupling_end": bool(meta.get("is_coupling_end", False)),
        "shaft_group_id": str(meta.get("shaft_group_id", "")),
        "local_rpm": float(meta.get("local_rpm") or 0.0),
        "metrics": {
            "ratio_1x": ratio1,
            "ratio_2x": ratio2,
            "ratio_3x": float(features["ratio_3x"]),
            "ratio_4x": float(features["ratio_4x"]),
            "ratio_5x": float(features["ratio_5x"]),
            "ratio_2x_over_1x": amp2_over_1,
            "ratio_fractional": float(features["ratio_fractional"]),
            "radial_2x": radial_2x,
            "axial_1x": axial_1x,
            "axial_2x": axial_2x,
            "severe_harmonics": severe_harmonics,
            "harmonic_2_to_5": float(features["ratio_harmonic_2_to_5"]),
            "dominant_order": float(features["dominant_order"]),
            "waveform_1x_pulse": float(features["wf_1x_pulse"]),
            "waveform_2x_pulse": float(features["wf_2x_pulse"]),
            "axis_weight": float(axis_weight),
            "component_weight": float(component_weight),
        },
        "limitations": reductions,
        "evidence": (
            f"{endpoint_id}/{axis}: misalignment score={score:.1f}, "
            f"2X/1X={amp2_over_1:.2f}, radial_2X={radial_2x:.2f}xRMS, "
            f"axial_1X={axial_1x:.2f}xRMS, axial_2X={axial_2x:.2f}xRMS, "
            f"3X-5X={severe_harmonics:.2f}xRMS, pattern={pattern}"
        ),
    }


def _score_unbalance_like_axis(
    *,
    endpoint_id: str,
    axis: str,
    features: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> Dict[str, Any]:
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
    score = _clamp(raw_score * _axis_weight_for_unbalance_like(axis, meta), 0.0, 100.0)
    return {
        "fault": "unbalance_like_1x_competing_pattern",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "metrics": {
            "ratio_1x": ratio1,
            "ratio_2x": ratio2,
            "ratio_3x": ratio3,
            "ratio_1x_over_2x": one_over_two,
            "ratio_1x_over_3x": one_over_three,
            "dominant_order": float(features["dominant_order"]),
            "fractional_ratio": fractional,
        },
    }


def _aggregate_global(scores: List[float], endpoint_ids: List[str]) -> float:
    if not scores:
        return 0.0
    top = _top_mean(scores, n=4)
    coverage = 20.0 * _score_linear(_distinct_count(endpoint_ids), 1.0, 4.0)
    repeatability = 15.0 * _score_linear(sum(1 for s in scores if s >= 45.0), 1.0, 4.0)
    return float(_clamp(0.65 * top + coverage + repeatability, 0.0, 100.0))


def _summarize_endpoint(
    endpoint_id: str,
    meta: Mapping[str, Any],
    axis_rows: List[Dict[str, Any]],
    endpoint_rpm: float,
) -> Dict[str, Any]:
    scores = [float(row["score"]) for row in axis_rows]
    high_rows = [row for row in axis_rows if float(row["score"]) >= 45.0]
    best_axis_row = max(axis_rows, key=lambda row: float(row["score"])) if axis_rows else None
    max_axial_1x = max((float(row["metrics"].get("axial_1x", 0.0)) for row in axis_rows), default=0.0)
    max_axial_2x = max((float(row["metrics"].get("axial_2x", 0.0)) for row in axis_rows), default=0.0)
    max_radial_2x = max((float(row["metrics"].get("radial_2x", 0.0)) for row in axis_rows), default=0.0)
    max_2x_over_1x = max((float(row["metrics"].get("ratio_2x_over_1x", 0.0)) for row in axis_rows), default=0.0)
    max_severe_harmonics = max((float(row["metrics"].get("severe_harmonics", 0.0)) for row in axis_rows), default=0.0)
    max_fractional = max((float(row["metrics"].get("ratio_fractional", 0.0)) for row in axis_rows), default=0.0)
    has_axial_axis = any(_axis_is_axial(str(row.get("axis", ""))) for row in axis_rows)
    has_radial_axis = any(not _axis_is_axial(str(row.get("axis", ""))) for row in axis_rows)
    if scores:
        endpoint_score = _clamp(
            0.78 * _top_mean(scores, n=3)
            + 12.0 * _score_linear(len(high_rows), 1.0, 3.0)
            + 10.0 * _score_linear(float(has_axial_axis and has_radial_axis), 0.0, 1.0),
            0.0,
            100.0,
        )
    else:
        endpoint_score = 0.0
    return {
        "endpoint_id": endpoint_id,
        "score": float(endpoint_score),
        "possible": bool(endpoint_score >= 20.0),
        "best_axis": best_axis_row["axis"] if best_axis_row else None,
        "best_axis_score": float(best_axis_row["score"]) if best_axis_row else 0.0,
        "best_axis_evidence": best_axis_row["evidence"] if best_axis_row else "",
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "is_coupling_end": bool(meta.get("is_coupling_end", False)),
        "shaft_group_id": str(meta.get("shaft_group_id", "")),
        "local_rpm": float(endpoint_rpm),
        "supporting_axes": [row["axis"] for row in high_rows],
        "axis_count": int(len(axis_rows)),
        "high_axis_count": int(len(high_rows)),
        "has_axial_axis": bool(has_axial_axis),
        "has_radial_axis": bool(has_radial_axis),
        "metrics": {
            "max_axial_1x": float(max_axial_1x),
            "max_axial_2x": float(max_axial_2x),
            "max_radial_2x": float(max_radial_2x),
            "max_2x_over_1x": float(max_2x_over_1x),
            "max_severe_harmonics": float(max_severe_harmonics),
            "max_fractional_ratio": float(max_fractional),
            "mean_axis_score": _mean_or_zero(scores),
            "top_axis_score": max(scores) if scores else 0.0,
        },
    }


def _endpoint_is_de_candidate(row: Mapping[str, Any]) -> bool:
    endpoint_role = str(row.get("endpoint_role", "unknown")).upper()
    return endpoint_role == "DE" or bool(row.get("is_coupling_end", False))


def _endpoints_are_same_shaft_compatible(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    rpm_tolerance_pct: float = 5.0,
) -> bool:
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
        rpm_delta_pct = 100.0 * abs(left_rpm - right_rpm) / max(avg_rpm, _EPS)
        if rpm_delta_pct > rpm_tolerance_pct:
            return False
    return True


def _endpoint_pair_vector(row: Mapping[str, Any]) -> np.ndarray:
    metrics = row.get("metrics", {}) or {}

    def value(key: str) -> float:
        try:
            number = float(metrics.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return number if np.isfinite(number) else 0.0

    return np.asarray(
        [
            value("max_2x_over_1x"),
            value("max_radial_2x"),
            value("max_axial_1x"),
            value("max_axial_2x"),
            value("max_severe_harmonics"),
            value("max_fractional_ratio"),
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
    left_side = str(left.get("component_side", "unknown"))
    right_side = str(right.get("component_side", "unknown"))
    sides = {left_side, right_side}
    if sides == {"driver", "driven"}:
        return 1.15, "driver_driven_de_pair"
    if left_side != "unknown" and right_side != "unknown" and left_side != right_side:
        return 1.08, "different_component_de_pair"
    if left_side == right_side and left_side != "unknown":
        return 0.92, "same_component_side_de_pair"
    return 1.0, "generic_de_pair"


def _best_de_pair_support(endpoint_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    de_rows = [row for row in endpoint_summaries if _endpoint_is_de_candidate(row)]
    if len(de_rows) < 2:
        return {
            "available": False,
            "used": False,
            "reason": "Less than two DE/coupling-end endpoints are available.",
            "pair_score": 0.0,
            "similarity": 0.0,
        }

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
            min_score = min(left_score, right_score)
            avg_score = 0.5 * (left_score + right_score)
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            pair_score = (0.72 * min_score + 0.28 * avg_score) * (0.55 + 0.45 * similarity) * pair_multiplier
            pair_score = _clamp(pair_score, 0.0, 100.0)
            candidate = {
                "available": True,
                "used": bool(pair_score >= 35.0),
                "pair_class": pair_class,
                "pair_score": float(pair_score),
                "similarity": float(similarity),
                "endpoint_a": str(left.get("endpoint_id")),
                "score_a": float(left_score),
                "best_axis_a": str(left.get("best_axis")),
                "component_type_a": str(left.get("component_type", "unknown")),
                "component_side_a": str(left.get("component_side", "unknown")),
                "endpoint_b": str(right.get("endpoint_id")),
                "score_b": float(right_score),
                "best_axis_b": str(right.get("best_axis")),
                "component_type_b": str(right.get("component_type", "unknown")),
                "component_side_b": str(right.get("component_side", "unknown")),
                "shaft_group_id": str(left.get("shaft_group_id") or right.get("shaft_group_id") or ""),
                "local_rpm_a": float(left.get("local_rpm", 0.0) or 0.0),
                "local_rpm_b": float(right.get("local_rpm", 0.0) or 0.0),
                "metrics_a": dict(left.get("metrics", {}) or {}),
                "metrics_b": dict(right.get("metrics", {}) or {}),
            }
            if best is None or candidate["pair_score"] > best["pair_score"]:
                best = candidate

    if best is None:
        return {
            "available": False,
            "used": False,
            "reason": "DE endpoints exist, but no compatible same-shaft/same-speed pair was found.",
            "pair_score": 0.0,
            "similarity": 0.0,
        }
    return best


def _misalignment_recommendations(score: float, confidence: str) -> List[str]:
    severity_action = {
        "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
        "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
        "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
    }[_fault_urgency(score, confidence)]
    return [
        severity_action,
        "Perform laser alignment with thermal targets where applicable and inspect coupling condition, pipe strain and base distortion.",
        "Re-measure axial and coupling-end vibration after correction to verify the diagnosis.",
    ]


def detect_misalignment(
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
    competing_hydraulic_pass_score: Optional[float] = None,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for misalignment detection.")

    endpoints = _normalize_triaxial_twf(vibration_twf, axes=axes)
    shaft_hz = rpm / 60.0
    confidence_cap = "high" if phase_data_available else "medium"
    endpoint_results: Dict[str, Any] = {}
    all_axis_rows: List[Dict[str, Any]] = []
    all_unbalance_like_rows: List[Dict[str, Any]] = []
    endpoint_summaries: List[Dict[str, Any]] = []

    for endpoint_id, axis_map in endpoints.items():
        meta = _endpoint_metadata(endpoint_metadata, endpoint_id)
        endpoint_rpm = float(meta.get("local_rpm") or rpm)
        meta["local_rpm"] = endpoint_rpm
        endpoint_axis_rows: List[Dict[str, Any]] = []
        endpoint_results[endpoint_id] = {
            "metadata": meta,
            "rpm_used": float(endpoint_rpm),
            "axes": {},
            "fault_summary": None,
        }

        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {
                "valid": False,
                "features": {},
                "fault": None,
                "competing_unbalance_like": None,
                "error": None,
            }
            try:
                features = _extract_axis_features(
                    waveform=axis_values,
                    fs_hz=fs_hz,
                    rpm=endpoint_rpm,
                    signal_type=signal_type,
                    acceleration_unit=acceleration_unit,
                    integration_low_cut_hz=integration_low_cut_hz,
                    target_tolerance_pct=target_tolerance_pct,
                )
                fault_row = _score_misalignment_axis(
                    endpoint_id=endpoint_id,
                    axis=axis,
                    features=features,
                    meta=meta,
                )
                unbalance_like_row = _score_unbalance_like_axis(
                    endpoint_id=endpoint_id,
                    axis=axis,
                    features=features,
                    meta=meta,
                )
                endpoint_axis_rows.append(fault_row)
                all_axis_rows.append(fault_row)
                all_unbalance_like_rows.append(unbalance_like_row)
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
                    "noise_floor_ratio": features["noise_floor_ratio"],
                    "ratio_1x": features["ratio_1x"],
                    "ratio_2x": features["ratio_2x"],
                    "ratio_3x": features["ratio_3x"],
                    "ratio_4x": features["ratio_4x"],
                    "ratio_5x": features["ratio_5x"],
                    "ratio_2x_over_1x": features["ratio_2x_over_1x"],
                    "ratio_fractional": features["ratio_fractional"],
                    "ratio_severe_harmonics": features["ratio_severe_harmonics"],
                    "waveform_1x_pulse": features["wf_1x_pulse"],
                    "waveform_2x_pulse": features["wf_2x_pulse"],
                }
                axis_result["fault"] = fault_row
                axis_result["competing_unbalance_like"] = unbalance_like_row
            except Exception as exc:
                axis_result["error"] = str(exc)
            endpoint_results[endpoint_id]["axes"][axis] = axis_result

        endpoint_summary = _summarize_endpoint(endpoint_id, meta, endpoint_axis_rows, endpoint_rpm)
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
        de_pair_boost = 20.0 * _score_linear(pair_score, 35.0, 75.0)
        if de_pair_boost > 0.0:
            de_pair_text = (
                f"DE-pair support {de_pair_support.get('endpoint_a')} "
                f"<-> {de_pair_support.get('endpoint_b')}: "
                f"pair_score={pair_score:.1f}, "
                f"similarity={float(de_pair_support.get('similarity', 0.0)):.2f}, "
                f"class={de_pair_support.get('pair_class')}"
            )

    score = _clamp(base_score + de_pair_boost, 0.0, 100.0)
    high_rows = [row for row in all_axis_rows if float(row["score"]) >= 45.0]
    axial_support_rows = [row for row in high_rows if _axis_is_axial(str(row.get("axis", "")))]
    radial_support_rows = [row for row in high_rows if not _axis_is_axial(str(row.get("axis", "")))]
    coupling_support_endpoints_from_axes = {
        str(row["endpoint_id"])
        for row in high_rows
        if bool(row.get("is_coupling_end", False)) or str(row.get("endpoint_role", "unknown")).upper() == "DE"
    }
    coupling_support_endpoints_from_summaries = {
        str(row["endpoint_id"])
        for row in endpoint_summaries
        if (
            bool(row.get("is_coupling_end", False))
            or str(row.get("endpoint_role", "unknown")).upper() == "DE"
        )
        and float(row.get("score", 0.0)) >= 35.0
    }
    coupling_support_endpoints = sorted(coupling_support_endpoints_from_axes | coupling_support_endpoints_from_summaries)

    ratio_1x_values = [float(row["metrics"].get("ratio_1x", 0.0)) for row in all_axis_rows]
    ratio_2x_values = [float(row["metrics"].get("ratio_2x", 0.0)) for row in all_axis_rows]
    ratio_3x_values = [float(row["metrics"].get("ratio_3x", 0.0)) for row in all_axis_rows]
    ratio_frac_values = [float(row["metrics"].get("ratio_fractional", 0.0)) for row in all_axis_rows]
    ratio_2x_over_1x_values = [float(row["metrics"].get("ratio_2x_over_1x", 0.0)) for row in all_axis_rows]
    axial_1x_values = [float(row["metrics"].get("axial_1x", 0.0)) for row in all_axis_rows if _axis_is_axial(str(row.get("axis", "")))]
    radial_2x_values = [float(row["metrics"].get("radial_2x", 0.0)) for row in all_axis_rows if not _axis_is_axial(str(row.get("axis", "")))]
    severe_harmonic_values = [float(row["metrics"].get("severe_harmonics", 0.0)) for row in all_axis_rows]

    limitations: List[str] = []
    evidence_items: List[str] = []
    if not phase_data_available:
        limitations.append("Confidence capped at medium because phase data is not available.")
    limitations.append("Use alignment, soft-foot, pipe-strain and coupling checks to separate overlapping shaft/support faults.")

    if len(coupling_support_endpoints) < 1 and not bool(de_pair_support.get("used", False)):
        score *= 0.80
        limitations.append("Reduced because coupling-end/DE support is weak for a misalignment call.")

    mean_2x_over_1x = _mean_or_zero(ratio_2x_over_1x_values)
    mean_radial_2x = _mean_or_zero(radial_2x_values)
    mean_axial_1x = _mean_or_zero(axial_1x_values)

    if mean_2x_over_1x < 0.50:
        score *= 0.50
        limitations.append("Reduced because 2X is too small relative to 1X for a strong misalignment call.")
    if mean_2x_over_1x < 0.35:
        score *= 0.55
        limitations.append("Reduced again because 2X/1X is well below the range usually expected for strong misalignment.")
    if mean_radial_2x < 0.60 and mean_axial_1x < 0.90:
        score *= 0.60
        limitations.append("Reduced because neither radial 2X nor axial 1X is strong enough to support a confident misalignment call.")
    if len(axial_support_rows) < 1 and mean_2x_over_1x < 0.60:
        score *= 0.60
        limitations.append("Reduced because axial 1X support and 2X evidence are both weak for misalignment.")

    unbalance_like_scores = [float(row["score"]) for row in all_unbalance_like_rows]
    unbalance_like_score = _aggregate_global(
        unbalance_like_scores,
        [str(row["endpoint_id"]) for row in all_unbalance_like_rows],
    )
    if unbalance_like_score >= 45.0 and mean_2x_over_1x < 0.60:
        score *= 0.70
        limitations.append("Reduced because the pattern is dominated by simpler 1X/unbalance-like behavior.")

    if competing_hydraulic_pass_score is not None:
        hydraulic_score = float(competing_hydraulic_pass_score)
        if hydraulic_score >= 60.0 and mean_2x_over_1x < 1.20:
            score *= 0.70
            limitations.append("Reduced because strong hydraulic pass-frequency evidence can mimic 2X/axial misalignment on pumps unless 2X/1X is clearly strong.")

    score = _clamp(score, 0.0, 100.0)
    confidence = _confidence_from_score(score, cap=confidence_cap)
    best_axis_row = max(all_axis_rows, key=lambda row: float(row["score"])) if all_axis_rows else None
    best_endpoint_summary = max(endpoint_summaries, key=lambda row: float(row["score"])) if endpoint_summaries else None
    if best_axis_row:
        evidence_items.append(str(best_axis_row.get("evidence", "")))
    if de_pair_text:
        evidence_items.append(de_pair_text)
    if not bool(de_pair_support.get("available", False)):
        limitations.append("No usable DE-to-DE same-shaft pair was available; result falls back to endpoint/axis aggregation.")

    has_explicit_axial_axis = any(_axis_is_axial(str(row.get("axis", ""))) for row in all_axis_rows)
    if not has_explicit_axial_axis:
        limitations.append("No explicit axial axis label was found; angular misalignment confidence is limited. Pass axes=['horizontal','vertical','axial'] when orientation is known.")

    primary_fault = None
    possible_faults: List[Dict[str, Any]] = []
    if score >= min_score:
        primary_fault = {
            "fault": "misalignment",
            "label": "Coupling / shaft misalignment",
            "scope": "asset_wide",
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
            "recommendations": _misalignment_recommendations(score, confidence),
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
                "mean_fractional_ratio": _mean_or_zero(ratio_frac_values),
                "mean_2x_over_1x": mean_2x_over_1x,
                "mean_axial_1x_ratio": mean_axial_1x,
                "mean_radial_2x_ratio": mean_radial_2x,
                "mean_severe_harmonics_ratio": _mean_or_zero(severe_harmonic_values),
                "competing_unbalance_like_score": float(unbalance_like_score),
                "de_pair_score": float(de_pair_support.get("pair_score", 0.0)),
                "de_pair_similarity": float(de_pair_support.get("similarity", 0.0)),
            },
        }
        possible_faults.append(primary_fault)

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
            "enabled": True,
            "description": (
                "Compatible DE/coupling-end endpoints are compared first. If a same-shaft DE pair supports "
                "the same misalignment pattern, the score receives a bounded boost. Otherwise the detector "
                "falls back to endpoint/axis aggregation."
            ),
            "support": de_pair_support,
        },
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "endpoint_summaries": endpoint_summaries,
        "endpoint_results": endpoint_results,
        "limitations": [
            "Misalignment is a shaft/train/coupling diagnosis, so evidence is evaluated asset-wide.",
            "Velocity TWF is preferred. If acceleration TWF is supplied, velocity is derived by frequency-domain integration.",
            "DE-to-DE comparison is only used when compatible same-shaft/same-speed DE endpoints are available.",
            "NDE endpoints still contribute to normal asset-wide aggregation, but they do not drive the special DE-pair boost.",
            "Confidence is capped at medium unless phase_data_available=True.",
        ],
    }


__all__ = ["detect_misalignment"]
