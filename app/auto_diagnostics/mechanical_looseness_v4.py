from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Tuple

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


def _mean_or_zero(values: List[float]) -> float:
    clean = [float(v) for v in values if np.isfinite(v)]
    return float(mean(clean)) if clean else 0.0


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


def _float_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


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


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return _AXIS_ALIASES.get(text, text or "axis")


def _axis_is_axial(axis: str) -> bool:
    return _norm_axis_name(axis) == "axial"


def _axis_is_radial(axis: str) -> bool:
    return _norm_axis_name(axis) in {"horizontal", "vertical", "radial", "x", "y", "z"}


def _axis_names_for_triaxial(axes: Optional[List[str]]) -> List[str]:
    axis_names = list(axes or ["x", "y", "z"])
    while len(axis_names) < 3:
        axis_names.append(f"axis_{len(axis_names) + 1}")
    return axis_names[:3]


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)
    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}
    if data.ndim != 2:
        raise ValueError("Vibration TWF array must be 1-D or 2-D.")

    axis_names = _axis_names_for_triaxial(axes)
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


def _normalize_triaxial_twf(
    vibration_twf: Any,
    axes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, np.ndarray]]:
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


def _attach_endpoint_context(
    row: Dict[str, Any],
    endpoint_id: str,
    meta: Mapping[str, Any],
    endpoint_rpm: float,
) -> Dict[str, Any]:
    row["endpoint_id"] = endpoint_id
    row["endpoint_role"] = str(meta.get("endpoint_role", "unknown"))
    row["component_type"] = str(meta.get("component_type", "unknown"))
    row["component_side"] = str(meta.get("component_side", "unknown"))
    row["installed_on"] = str(meta.get("installed_on", "unknown"))
    row["is_coupling_end"] = bool(meta.get("is_coupling_end", False))
    row["shaft_group_id"] = str(meta.get("shaft_group_id", ""))
    row["local_rpm"] = float(endpoint_rpm)
    return row


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


def _extract_looseness_axis_features(
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
        raise ValueError("rpm must be positive for mechanical looseness detection.")

    source = _as_float_array(waveform)
    if source.size < 128:
        raise ValueError("Need at least 128 samples for mechanical looseness detection.")

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

    orders = {
        "05x": 0.5, "1x": 1.0, "15x": 1.5, "2x": 2.0, "25x": 2.5,
        "3x": 3.0, "35x": 3.5, "4x": 4.0, "5x": 5.0, "6x": 6.0,
        "7x": 7.0, "8x": 8.0, "9x": 9.0, "10x": 10.0,
    }
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

    harmonic_string = sum(amp(name) for name in ["2x", "3x", "4x", "5x", "6x", "7x", "8x", "9x", "10x"])
    moderate_harmonics = amp("2x") + amp("3x") + amp("4x")
    support_string = amp("2x") + amp("3x") + amp("4x") + amp("5x")
    high_harmonics = amp("6x") + amp("7x") + amp("8x") + amp("9x") + amp("10x")
    fractional = amp("05x") + amp("15x") + amp("25x") + amp("35x")

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
        "dominant_freq_hz": float(dominant_freq_hz),
        "dominant_amp": float(dominant_amp),
        "dominant_order": float(dominant_order),
        "crest_factor": float(_crest_factor(velocity)),
        "kurtosis_excess": float(_kurtosis_excess(velocity)),
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
        "ratio_7x": ratio(amp("7x")),
        "ratio_8x": ratio(amp("8x")),
        "ratio_9x": ratio(amp("9x")),
        "ratio_10x": ratio(amp("10x")),
        "harmonic_string_ratio": ratio(harmonic_string),
        "moderate_harmonics_ratio": ratio(moderate_harmonics),
        "support_string_ratio": ratio(support_string),
        "high_harmonics_ratio": ratio(high_harmonics),
        "fractional_ratio": ratio(fractional),
        "ratio_2x_over_1x": _safe_ratio(amp("2x"), max(amp("1x"), _EPS)),
    }


def _axis_weight_for_looseness(fault_key: str, axis: str, installed_on: str) -> float:
    axis = _norm_axis_name(axis)
    installed_on = str(installed_on or "unknown").lower()
    if fault_key == "looseness_type_a_base_structure":
        base = 1.0 if _axis_is_radial(axis) else 0.55
    elif fault_key == "looseness_type_b_pedestal_support":
        base = 1.0 if _axis_is_radial(axis) else 0.75
    elif fault_key == "looseness_type_c_rotating_fit":
        base = 1.0 if _axis_is_radial(axis) else 0.70
    else:
        base = 1.0

    if installed_on in {"base", "foundation"}:
        if fault_key == "looseness_type_a_base_structure":
            base *= 1.15
        elif fault_key in {"looseness_type_b_pedestal_support", "looseness_type_c_rotating_fit"}:
            base *= 0.82
    return float(base)


def _mount_relevance_for_looseness(fault_key: str, installed_on: str) -> Tuple[float, List[str]]:
    installed_on = str(installed_on or "unknown").lower()
    limitations: List[str] = []
    if installed_on in {"", "unknown", "none", "nan"}:
        limitations.append("Endpoint mount metadata is missing; looseness subtype confidence is reduced.")
        return 0.85, limitations

    if fault_key == "looseness_type_a_base_structure":
        if installed_on in {"base", "foundation", "pedestal"}:
            return 1.0, limitations
        limitations.append("Type A base/structure looseness is weaker because this endpoint is not marked as base, foundation, or pedestal mounted.")
        return 0.32, limitations

    if fault_key == "looseness_type_b_pedestal_support":
        if installed_on in {"pedestal", "bearing_housing", "casing"}:
            return 1.0, limitations
        if installed_on in {"base", "foundation"}:
            limitations.append("Type B support looseness is reduced because the endpoint appears to be on the base/foundation.")
            return 0.70, limitations
        limitations.append("Type B support looseness is weaker because this endpoint is not marked as pedestal, bearing housing, or casing mounted.")
        return 0.42, limitations

    if fault_key == "looseness_type_c_rotating_fit":
        if installed_on in {"bearing_housing", "casing", "pedestal"}:
            return 1.0, limitations
        if installed_on in {"base", "foundation"}:
            limitations.append("Type C rotating-fit looseness is reduced because the endpoint appears to be on the base/foundation.")
            return 0.55, limitations
        limitations.append("Type C rotating-fit looseness is weaker because this endpoint is not marked as bearing housing, casing, or pedestal mounted.")
        return 0.45, limitations

    return 1.0, limitations


def _component_weight_for_looseness(fault_key: str, installed_on: str) -> float:
    installed_on = str(installed_on or "unknown").lower()
    if fault_key == "looseness_type_a_base_structure" and installed_on in {"base", "foundation"}:
        return 1.10
    if fault_key == "looseness_type_b_pedestal_support" and installed_on in {"pedestal", "bearing_housing", "casing"}:
        return 1.08
    if fault_key == "looseness_type_c_rotating_fit" and installed_on in {"bearing_housing", "casing", "pedestal"}:
        return 1.10
    return 1.0


def _score_looseness_type_a(endpoint_id: str, axis: str, installed_on: str, features: Dict[str, Any]) -> Dict[str, Any]:
    one_x = float(features["ratio_1x"])
    two_x = float(features["ratio_2x"])
    harmonic_string = float(features["harmonic_string_ratio"])
    fractional = float(features["fractional_ratio"])
    moderate_harmonics = float(features["moderate_harmonics_ratio"])
    wf_1x_pulse = float(features["wf_1x_pulse"])
    raw_score = (
        32.0 * _score_linear(one_x, 1.2, 4.8)
        + 12.0 * _score_linear(two_x, 0.2, 1.5)
        + 12.0 * (1.0 - _score_linear(harmonic_string, 2.0, 6.5))
        + 10.0 * (1.0 - _score_linear(fractional, 0.6, 2.0))
        + 10.0 * (1.0 - _score_linear(moderate_harmonics, 2.5, 6.5))
        + 24.0 * _score_linear(wf_1x_pulse, 0.10, 0.45)
    )
    fault_key = "looseness_type_a_base_structure"
    mount_factor, limitations = _mount_relevance_for_looseness(fault_key, installed_on)
    axis_weight = _axis_weight_for_looseness(fault_key, axis, installed_on)
    component_weight = _component_weight_for_looseness(fault_key, installed_on)
    score = _clamp(raw_score * mount_factor * axis_weight * component_weight, 0.0, 100.0)
    return {
        "fault": "mechanical_looseness",
        "subtype": fault_key,
        "label": "Type A - base / structure looseness",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "installed_on": installed_on,
        "score": float(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "ratio_1x": one_x,
            "ratio_2x": two_x,
            "harmonic_string_ratio": harmonic_string,
            "fractional_ratio": fractional,
            "moderate_harmonics_ratio": moderate_harmonics,
            "waveform_1x_pulse": wf_1x_pulse,
            "dominant_order": float(features["dominant_order"]),
            "axis_weight": float(axis_weight),
            "mount_factor": float(mount_factor),
            "component_weight": float(component_weight),
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: Type A score={score:.1f}, "
            f"1x={one_x:.2f}xRMS, 2x={two_x:.2f}xRMS, "
            f"harmonic_string={harmonic_string:.2f}xRMS, fractional={fractional:.2f}xRMS, "
            f"1x_pulse={wf_1x_pulse:.2f}, mount={installed_on}"
        ),
    }


def _score_looseness_type_b(endpoint_id: str, axis: str, installed_on: str, features: Dict[str, Any]) -> Dict[str, Any]:
    two_x = float(features["ratio_2x"])
    ratio_2x_over_1x = float(features["ratio_2x_over_1x"])
    support_string = float(features["support_string_ratio"])
    fractional = float(features["fractional_ratio"])
    high_harmonics = float(features["high_harmonics_ratio"])
    wf_2x_pulse = float(features["wf_2x_pulse"])
    raw_score = (
        24.0 * _score_linear(two_x, 0.35, 2.2)
        + 24.0 * _score_linear(ratio_2x_over_1x, 0.45, 1.30)
        + 14.0 * _score_linear(support_string, 1.0, 4.5)
        + 8.0 * (1.0 - _score_linear(fractional, 0.8, 2.5))
        + 6.0 * (1.0 - _score_linear(high_harmonics, 1.5, 4.5))
        + 24.0 * _score_linear(wf_2x_pulse, 0.10, 0.45)
    )
    fault_key = "looseness_type_b_pedestal_support"
    mount_factor, limitations = _mount_relevance_for_looseness(fault_key, installed_on)
    axis_weight = _axis_weight_for_looseness(fault_key, axis, installed_on)
    component_weight = _component_weight_for_looseness(fault_key, installed_on)
    score = _clamp(raw_score * mount_factor * axis_weight * component_weight, 0.0, 100.0)
    return {
        "fault": "mechanical_looseness",
        "subtype": fault_key,
        "label": "Type B - pedestal / support looseness",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "installed_on": installed_on,
        "score": float(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "ratio_2x": two_x,
            "ratio_2x_over_1x": ratio_2x_over_1x,
            "support_string_ratio": support_string,
            "fractional_ratio": fractional,
            "high_harmonics_ratio": high_harmonics,
            "waveform_2x_pulse": wf_2x_pulse,
            "dominant_order": float(features["dominant_order"]),
            "axis_weight": float(axis_weight),
            "mount_factor": float(mount_factor),
            "component_weight": float(component_weight),
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: Type B score={score:.1f}, "
            f"2x={two_x:.2f}xRMS, 2x/1x={ratio_2x_over_1x:.2f}, "
            f"support_string={support_string:.2f}xRMS, fractional={fractional:.2f}xRMS, "
            f"2x_pulse={wf_2x_pulse:.2f}, mount={installed_on}"
        ),
    }


def _score_looseness_type_c(endpoint_id: str, axis: str, installed_on: str, features: Dict[str, Any]) -> Dict[str, Any]:
    harmonic_string = float(features["harmonic_string_ratio"])
    high_harmonics = float(features["high_harmonics_ratio"])
    fractional = float(features["fractional_ratio"])
    noise_ratio = float(features["noise_floor_ratio"])
    kurtosis_excess = float(features["kurtosis_excess"])
    crest_factor = float(features["crest_factor"])
    irregularity = (
        0.5 * _score_linear(max(kurtosis_excess, 0.0), 0.6, 3.2)
        + 0.5 * _score_linear(crest_factor, 3.2, 6.8)
    )
    raw_score = (
        28.0 * _score_linear(harmonic_string, 1.6, 7.0)
        + 24.0 * _score_linear(fractional, 0.7, 3.4)
        + 18.0 * _score_linear(high_harmonics, 0.8, 3.5)
        + 14.0 * _score_linear(noise_ratio, 0.10, 0.30)
        + 16.0 * irregularity
    )
    fault_key = "looseness_type_c_rotating_fit"
    mount_factor, limitations = _mount_relevance_for_looseness(fault_key, installed_on)
    axis_weight = _axis_weight_for_looseness(fault_key, axis, installed_on)
    component_weight = _component_weight_for_looseness(fault_key, installed_on)
    score = _clamp(raw_score * mount_factor * axis_weight * component_weight, 0.0, 100.0)
    return {
        "fault": "mechanical_looseness",
        "subtype": fault_key,
        "label": "Type C - rotating fit / internal clearance looseness",
        "endpoint_id": endpoint_id,
        "axis": axis,
        "installed_on": installed_on,
        "score": float(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "harmonic_string_ratio": harmonic_string,
            "fractional_ratio": fractional,
            "high_harmonics_ratio": high_harmonics,
            "noise_floor_ratio": noise_ratio,
            "kurtosis_excess": kurtosis_excess,
            "crest_factor": crest_factor,
            "irregularity_score_0_1": float(irregularity),
            "dominant_order": float(features["dominant_order"]),
            "axis_weight": float(axis_weight),
            "mount_factor": float(mount_factor),
            "component_weight": float(component_weight),
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: Type C score={score:.1f}, "
            f"harmonic_string={harmonic_string:.2f}xRMS, fractional={fractional:.2f}xRMS, "
            f"high_harmonics={high_harmonics:.2f}xRMS, noise_floor={noise_ratio:.2f}xRMS, "
            f"kurtosis={kurtosis_excess:.2f}, crest={crest_factor:.2f}, mount={installed_on}"
        ),
    }


def _best_de_row_per_endpoint(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        endpoint_role = str(row.get("endpoint_role", "unknown")).upper()
        is_coupling_end = bool(row.get("is_coupling_end", False))
        if endpoint_role != "DE" and not is_coupling_end:
            continue
        endpoint_id = str(row.get("endpoint_id", ""))
        if not endpoint_id:
            continue
        current = best.get(endpoint_id)
        if current is None or float(row.get("score", 0.0)) > float(current.get("score", 0.0)):
            best[endpoint_id] = row
    return best


def _rows_are_same_shaft_compatible(
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


def _subtype_pair_vector(row: Mapping[str, Any], subtype: str) -> np.ndarray:
    metrics = row.get("metrics", {}) or {}

    def value(key: str) -> float:
        try:
            number = float(metrics.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return number if np.isfinite(number) else 0.0

    if subtype == "looseness_type_a_base_structure":
        return np.asarray(
            [value("ratio_1x"), value("ratio_2x"), value("harmonic_string_ratio"), value("fractional_ratio"), value("waveform_1x_pulse")],
            dtype=float,
        )
    if subtype == "looseness_type_b_pedestal_support":
        return np.asarray(
            [value("ratio_2x"), value("ratio_2x_over_1x"), value("support_string_ratio"), value("fractional_ratio"), value("high_harmonics_ratio"), value("waveform_2x_pulse")],
            dtype=float,
        )
    return np.asarray(
        [value("harmonic_string_ratio"), value("fractional_ratio"), value("high_harmonics_ratio"), value("noise_floor_ratio"), value("kurtosis_excess"), value("crest_factor")],
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
        return 1.12, "driver_driven_de_pair"
    if left_side != "unknown" and right_side != "unknown" and left_side != right_side:
        return 1.05, "different_component_de_pair"
    if left_side == right_side and left_side != "unknown":
        return 0.94, "same_component_side_de_pair"
    return 1.0, "generic_de_pair"


def _best_de_pair_support(subtype: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    de_rows = list(_best_de_row_per_endpoint(rows).values())
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
            if not _rows_are_same_shaft_compatible(left, right):
                continue

            similarity = _log_vector_similarity(
                _subtype_pair_vector(left, subtype),
                _subtype_pair_vector(right, subtype),
            )
            left_score = float(left.get("score", 0.0))
            right_score = float(right.get("score", 0.0))
            min_score = min(left_score, right_score)
            avg_score = 0.5 * (left_score + right_score)
            axis_factor = 1.0 if str(left.get("axis")) == str(right.get("axis")) else 0.93
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            pair_score = (0.65 * min_score + 0.35 * avg_score) * (0.55 + 0.45 * similarity) * axis_factor * pair_multiplier
            pair_score = _clamp(pair_score, 0.0, 100.0)

            candidate = {
                "available": True,
                "used": bool(pair_score >= 35.0),
                "subtype": subtype,
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
        return {
            "available": False,
            "used": False,
            "reason": "DE endpoints exist, but no compatible same-shaft/same-speed pair was found.",
            "pair_score": 0.0,
            "similarity": 0.0,
        }
    return best


def _compute_de_pair_support_by_subtype(
    subtype_axis_rows: Mapping[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    return {subtype: _best_de_pair_support(subtype, rows) for subtype, rows in subtype_axis_rows.items()}


def _aggregate_looseness_subtype(
    subtype: str,
    rows: List[Dict[str, Any]],
    *,
    min_score: float,
    confidence_cap: str,
    de_pair_support: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    scores = [float(row["score"]) for row in rows]
    high_rows = [row for row in rows if float(row["score"]) >= 45.0]
    endpoint_ids = sorted({str(row["endpoint_id"]) for row in rows})
    high_endpoint_ids = sorted({str(row["endpoint_id"]) for row in high_rows})
    best_row = max(rows, key=lambda row: float(row["score"]))
    base_score = _clamp(
        0.65 * _top_mean(scores, n=4)
        + 20.0 * _score_linear(float(len(endpoint_ids)), 1.0, 4.0)
        + 15.0 * _score_linear(float(len(high_rows)), 1.0, 4.0),
        0.0,
        100.0,
    )

    de_pair_score = 0.0
    de_pair_similarity = 0.0
    de_pair_boost = 0.0
    de_pair_used = False
    de_pair_text = ""
    if de_pair_support and bool(de_pair_support.get("available", False)):
        de_pair_score = float(de_pair_support.get("pair_score", 0.0))
        de_pair_similarity = float(de_pair_support.get("similarity", 0.0))
        de_pair_used = bool(de_pair_support.get("used", False))
        if subtype == "looseness_type_a_base_structure":
            boost_cap = 6.0
        elif subtype == "looseness_type_b_pedestal_support":
            boost_cap = 14.0
        else:
            boost_cap = 16.0
        de_pair_boost = boost_cap * _score_linear(de_pair_score, 35.0, 75.0)
        de_pair_text = (
            f"DE-pair support {de_pair_support.get('endpoint_a')}/{de_pair_support.get('axis_a')} "
            f"<-> {de_pair_support.get('endpoint_b')}/{de_pair_support.get('axis_b')}: "
            f"pair_score={de_pair_score:.1f}, similarity={de_pair_similarity:.2f}, "
            f"class={de_pair_support.get('pair_class')}"
        )

    score = _clamp(base_score + de_pair_boost, 0.0, 100.0)
    limitations = list(best_row.get("limitations", []))
    if confidence_cap != "high":
        limitations.append(f"Confidence capped at {confidence_cap} because phase data is not available.")
    if not de_pair_support or not bool(de_pair_support.get("available", False)):
        limitations.append("No usable DE-to-DE same-shaft pair was available; result falls back to endpoint/axis aggregation.")

    evidence = best_row["evidence"]
    if de_pair_text:
        evidence = f"{evidence} | {de_pair_text}"

    return {
        "fault": "mechanical_looseness",
        "subtype": subtype,
        "label": best_row["label"],
        "score": float(score),
        "base_score_before_de_pair": float(base_score),
        "de_pair_boost": float(de_pair_boost),
        "confidence": _confidence_from_score(score, cap=confidence_cap),
        "possible": bool(score >= min_score),
        "best_endpoint": best_row["endpoint_id"],
        "best_axis": best_row["axis"],
        "best_axis_score": float(best_row["score"]),
        "supporting_endpoints": high_endpoint_ids,
        "supporting_axis_count": int(len(high_rows)),
        "evidence": evidence,
        "limitations": limitations,
        "de_pair_support": dict(de_pair_support or {}),
        "metrics": {
            "mean_axis_score": _mean_or_zero(scores),
            "top_axis_score": float(max(scores)),
            "num_evaluated_axes": float(len(rows)),
            "num_evaluated_endpoints": float(len(endpoint_ids)),
            "num_supporting_axes": float(len(high_rows)),
            "num_supporting_endpoints": float(len(high_endpoint_ids)),
            "de_pair_score": float(de_pair_score),
            "de_pair_similarity": float(de_pair_similarity),
            "de_pair_used": 1.0 if de_pair_used else 0.0,
            "de_pair_boost": float(de_pair_boost),
        },
    }


def detect_mechanical_looseness(
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
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive for mechanical looseness detection.")

    endpoints = _normalize_triaxial_twf(vibration_twf, axes=axes)
    shaft_hz = rpm / 60.0
    confidence_cap = "high" if phase_data_available else "medium"
    endpoint_results: Dict[str, Any] = {}
    subtype_axis_rows: Dict[str, List[Dict[str, Any]]] = {
        "looseness_type_a_base_structure": [],
        "looseness_type_b_pedestal_support": [],
        "looseness_type_c_rotating_fit": [],
    }

    for endpoint_id, axis_map in endpoints.items():
        meta = _endpoint_metadata(endpoint_metadata, endpoint_id)
        endpoint_rpm = float(meta.get("local_rpm") or rpm)
        endpoint_results[endpoint_id] = {"metadata": meta, "rpm_used": float(endpoint_rpm), "axes": {}}

        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "features": {}, "faults": {}, "error": None}
            try:
                features = _extract_looseness_axis_features(
                    waveform=axis_values,
                    fs_hz=fs_hz,
                    rpm=endpoint_rpm,
                    signal_type=signal_type,
                    acceleration_unit=acceleration_unit,
                    integration_low_cut_hz=integration_low_cut_hz,
                    target_tolerance_pct=target_tolerance_pct,
                )
                type_a = _score_looseness_type_a(endpoint_id, axis, str(meta.get("installed_on", "unknown")), features)
                type_b = _score_looseness_type_b(endpoint_id, axis, str(meta.get("installed_on", "unknown")), features)
                type_c = _score_looseness_type_c(endpoint_id, axis, str(meta.get("installed_on", "unknown")), features)

                for row in (type_a, type_b, type_c):
                    _attach_endpoint_context(row, endpoint_id, meta, endpoint_rpm)
                    subtype_axis_rows[row["subtype"]].append(row)

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
                    "ratio_2x_over_1x": features["ratio_2x_over_1x"],
                    "fractional_ratio": features["fractional_ratio"],
                    "harmonic_string_ratio": features["harmonic_string_ratio"],
                    "high_harmonics_ratio": features["high_harmonics_ratio"],
                    "waveform_1x_pulse": features["wf_1x_pulse"],
                    "waveform_2x_pulse": features["wf_2x_pulse"],
                    "kurtosis_excess": features["kurtosis_excess"],
                    "crest_factor": features["crest_factor"],
                }
                axis_result["faults"] = {
                    "looseness_type_a_base_structure": type_a,
                    "looseness_type_b_pedestal_support": type_b,
                    "looseness_type_c_rotating_fit": type_c,
                }
            except Exception as exc:
                axis_result["error"] = str(exc)
            endpoint_results[endpoint_id]["axes"][axis] = axis_result

    de_pair_support_by_subtype = _compute_de_pair_support_by_subtype(subtype_axis_rows)
    subtype_summaries: List[Dict[str, Any]] = []
    for subtype, rows in subtype_axis_rows.items():
        summary = _aggregate_looseness_subtype(
            subtype,
            rows,
            min_score=min_score,
            confidence_cap=confidence_cap,
            de_pair_support=de_pair_support_by_subtype.get(subtype),
        )
        if summary is not None:
            subtype_summaries.append(summary)

    subtype_summaries.sort(key=lambda row: row["score"], reverse=True)
    possible_faults = [row for row in subtype_summaries if float(row["score"]) >= float(min_score)]
    primary_fault = possible_faults[0] if possible_faults else None

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
                "the same looseness subtype, the subtype score receives a bounded boost. Otherwise the detector "
                "falls back to endpoint/axis aggregation."
            ),
            "support_by_subtype": de_pair_support_by_subtype,
        },
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "all_subtype_summaries": subtype_summaries,
        "endpoint_results": endpoint_results,
        "limitations": [
            "Mechanical looseness is a shaft/train/structure diagnosis, so evidence is evaluated asset-wide.",
            "Velocity TWF is preferred. If acceleration TWF is supplied, velocity is derived by frequency-domain integration.",
            "DE-to-DE comparison is only used when compatible same-shaft/same-speed DE endpoints are available.",
            "NDE endpoints still contribute to normal asset-wide aggregation, but they do not drive the special DE-pair boost.",
            "Confidence is capped at medium unless phase_data_available=True.",
            "Confirm subtype with physical checks: base/anchor/foot checks for Type A, pedestal/support checks for Type B, and fit/clearance checks for Type C.",
        ],
    }
