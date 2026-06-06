from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
from app.auto_diagnostics.signal_feature_cache_v4 import (
    one_sided_spectrum as _cached_one_sided_spectrum,
)


EPS = 1e-12
CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
HYDRAULIC_COMPONENT_TYPES = {"pump", "fan", "blower", "compressor", "chiller", "hydraulic", "aero", "driven"}
DRIVER_COMPONENT_TYPES = {"motor", "engine", "turbine", "driver"}
AXIS_ALIASES = {
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

NumericOrMap = Union[float, int, Mapping[str, Union[float, int]]]


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    return float(num) / float(den) if abs(float(den)) > EPS else float(default)


def _score_linear(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    return _clamp((float(value) - low) / (high - low), 0.0, 1.0)


def _rms(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(arr))))


def _top_mean(values: Sequence[float], n: int = 3) -> float:
    clean = sorted([float(v) for v in values if v is not None and np.isfinite(v)], reverse=True)
    if not clean:
        return 0.0
    return float(mean(clean[: min(n, len(clean))]))


def _mean_or_zero(values: Iterable[float]) -> float:
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(mean(clean)) if clean else 0.0


def _confidence_from_score(score: float, cap: str = "high") -> str:
    if score >= 70.0:
        confidence = "high"
    elif score >= 45.0:
        confidence = "medium"
    elif score >= 20.0:
        confidence = "low"
    else:
        confidence = "none"
    cap = str(cap or "high").lower()
    if cap not in CONFIDENCE_ORDER:
        cap = "high"
    return cap if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[cap] else confidence


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
    r = _rms(x)
    return float(np.max(np.abs(x)) / r) if r > EPS else 0.0


def _kurtosis_excess(x: np.ndarray) -> float:
    x = _as_float_array(x)
    if x.size < 4:
        return 0.0
    std = float(np.std(x))
    if std <= EPS:
        return 0.0
    z = (x - float(np.mean(x))) / std
    return float(np.mean(np.power(z, 4)) - 3.0)


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return AXIS_ALIASES.get(text, text or "axis")


def _axis_is_radial(axis: str) -> bool:
    return _norm_axis_name(axis) in {"horizontal", "vertical", "radial", "x", "y", "z"}


def _axis_is_axial(axis: str) -> bool:
    return _norm_axis_name(axis) == "axial"


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)
    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}
    if data.ndim != 2:
        raise ValueError("Acceleration TWF array must be 1-D or 2-D.")
    axis_names = axes or ["x", "y", "z"]
    if data.shape[1] == 3:
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[:, i]) for i in range(3)}
    if data.shape[0] == 3:
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[i, :]) for i in range(3)}
    raise ValueError("2-D acceleration TWF must have one dimension of size 3 for tri-axial data.")


def _looks_like_axis_map(obj: Mapping[str, Any]) -> bool:
    if not obj:
        return False
    keys = {_norm_axis_name(k) for k in obj.keys()}
    axis_like = bool(keys & {"x", "y", "z", "horizontal", "vertical", "axial", "radial"})
    values_are_not_nested_maps = all(not isinstance(v, Mapping) for v in obj.values())
    return axis_like and values_are_not_nested_maps


def _normalize_triaxial_twf(acceleration_twf: Any, axes: Optional[List[str]] = None) -> Dict[str, Dict[str, np.ndarray]]:
    if isinstance(acceleration_twf, Mapping):
        if _looks_like_axis_map(acceleration_twf):
            return {"endpoint_1": {_norm_axis_name(axis): _as_float_array(values) for axis, values in acceleration_twf.items()}}
        endpoints: Dict[str, Dict[str, np.ndarray]] = {}
        for endpoint_id, endpoint_data in acceleration_twf.items():
            endpoint_key = str(endpoint_id)
            if isinstance(endpoint_data, Mapping):
                endpoints[endpoint_key] = {_norm_axis_name(axis): _as_float_array(values) for axis, values in endpoint_data.items()}
            else:
                endpoints[endpoint_key] = _array_to_axis_map(endpoint_data, axes=axes)
        return endpoints
    return {"endpoint_1": _array_to_axis_map(acceleration_twf, axes=axes)}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "de", "drive_end", "drive-end", "coupling", "coupling_end", "coupling-end", "present", "available",
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
    fields = ["endpoint_role", "end_role", "end_type", "end", "endpoint_flag", "de_nde", "drive_end_flag", "bearing_end", "location_end", "position"]
    for field in fields:
        if field in raw_meta and raw_meta.get(field) not in {None, ""}:
            role = _endpoint_role_from_text(raw_meta.get(field))
            if role != "unknown":
                return role
    if _truthy(raw_meta.get("is_nde")):
        return "NDE"
    if _truthy(raw_meta.get("is_de")) or _truthy(raw_meta.get("is_drive_end")) or _truthy(raw_meta.get("is_coupling_end")):
        return "DE"
    for candidate in [endpoint_id, raw_meta.get("location_tag"), raw_meta.get("endpoint_tag"), raw_meta.get("name"), raw_meta.get("mount_name"), raw_meta.get("composite_id"), raw_meta.get("composite_key")]:
        role = _endpoint_role_from_text(candidate)
        if role != "unknown":
            return role
    return "unknown"


def _component_side(component_type: str, endpoint_id: str = "") -> str:
    ctype = str(component_type or "").strip().lower()
    text = str(endpoint_id or "").strip().lower()
    if ctype in DRIVER_COMPONENT_TYPES:
        return "driver"
    if ctype in HYDRAULIC_COMPONENT_TYPES:
        return "driven_hydraulic"
    if "motor" in text:
        return "driver"
    if any(word in text for word in ["pump", "fan", "blower", "compressor", "chiller"]):
        return "driven_hydraulic"
    return "unknown"


def _endpoint_metadata(endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]], endpoint_id: str) -> Dict[str, Any]:
    raw_meta: Mapping[str, Any] = endpoint_metadata.get(endpoint_id, {}) if endpoint_metadata and endpoint_id in endpoint_metadata else {}
    installed_on = str(raw_meta.get("installed_on") or raw_meta.get("mount_type") or raw_meta.get("mounted_on") or "unknown").strip().lower()
    component_type = str(raw_meta.get("component_type") or raw_meta.get("component") or "unknown").strip().lower()
    component_id = str(raw_meta.get("component_id") or raw_meta.get("component") or "").strip().lower()
    endpoint_role = _resolve_endpoint_role(endpoint_id, raw_meta)
    shaft_group_id = str(raw_meta.get("shaft_group_id") or raw_meta.get("shaft_id") or raw_meta.get("train_id") or raw_meta.get("coupling_group_id") or "").strip().lower()
    hydraulic_id = str(raw_meta.get("hydraulic_id") or raw_meta.get("hydraulic_element_id") or raw_meta.get("pump_id") or raw_meta.get("fan_id") or "").strip().lower()
    local_rpm = _float_or_none(raw_meta.get("local_rpm") or raw_meta.get("rpm") or raw_meta.get("running_rpm"))
    is_coupling_end = bool(_truthy(raw_meta.get("is_coupling_end")) or _truthy(raw_meta.get("coupling_end")) or endpoint_role == "DE")
    return {
        "installed_on": installed_on,
        "component_type": component_type,
        "component_id": component_id,
        "endpoint_role": endpoint_role,
        "is_coupling_end": is_coupling_end,
        "shaft_group_id": shaft_group_id,
        "hydraulic_id": hydraulic_id,
        "local_rpm": local_rpm,
        "component_side": _component_side(component_type, endpoint_id),
    }


def _lookup_endpoint_numeric(value: Optional[NumericOrMap], endpoint_id: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        if endpoint_id not in value:
            return None
        return _float_or_none(value[endpoint_id])
    return _float_or_none(value)


def _resolve_temperature_delta_c(endpoint_id: str, surface_temperature_c: Optional[NumericOrMap] = None, baseline_temperature_c: Optional[NumericOrMap] = None, temperature_delta_c: Optional[NumericOrMap] = None) -> float:
    direct_delta = _lookup_endpoint_numeric(temperature_delta_c, endpoint_id)
    if direct_delta is not None:
        return float(direct_delta)
    surface = _lookup_endpoint_numeric(surface_temperature_c, endpoint_id)
    baseline = _lookup_endpoint_numeric(baseline_temperature_c, endpoint_id)
    if surface is not None and baseline is not None:
        return float(surface - baseline)
    if surface is not None and isinstance(surface_temperature_c, Mapping):
        peers: List[float] = []
        for key, raw_value in surface_temperature_c.items():
            if str(key) == str(endpoint_id):
                continue
            value = _float_or_none(raw_value)
            if value is not None:
                peers.append(value)
        if peers:
            return float(surface - float(np.median(peers)))
    return 0.0


def _peak_at(freqs_hz: np.ndarray, amplitudes: np.ndarray, target_hz: float, tolerance_hz: float) -> Tuple[float, float]:
    if target_hz <= 0.0 or tolerance_hz <= 0.0 or freqs_hz.size == 0 or amplitudes.size == 0:
        return 0.0, 0.0
    lo = int(np.searchsorted(freqs_hz, target_hz - tolerance_hz, side="left"))
    hi = int(np.searchsorted(freqs_hz, target_hz + tolerance_hz, side="right"))
    if hi <= lo:
        return 0.0, 0.0
    local = amplitudes[lo:hi]
    if local.size == 0:
        return 0.0, 0.0
    idx = int(np.argmax(local))
    return float(freqs_hz[lo + idx]), float(local[idx])


def _extract_axis_features(x: np.ndarray, fs_hz: float, rpm: float) -> Dict[str, Any]:
    x = _as_float_array(x)
    if x.size < 128:
        raise ValueError("Need at least 128 samples for hydraulic pass-frequency detection.")
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive.")
    shaft_hz = float(rpm) / 60.0
    freqs, amps = _cached_one_sided_spectrum(_as_float_array(x), fs_hz)
    if freqs.size == 0 or amps.size == 0:
        raise ValueError("Could not compute a valid acceleration spectrum.")
    freq_resolution_hz = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(shaft_hz * 0.03, 0.1)
    tolerance_hz = max(abs(shaft_hz) * 0.03, 1.5 * freq_resolution_hz)
    spectrum_rms = max(_rms(amps), EPS)
    noise_floor = float(np.median(np.abs(amps))) if amps.size else 0.0
    dominant_idx = int(np.argmax(amps))
    dominant_freq_hz = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])
    dominant_order = _safe_ratio(dominant_freq_hz, shaft_hz)
    hf_start_hz = max(5.0 * shaft_hz, 50.0 if freqs[-1] >= 100.0 else 3.0 * shaft_hz)
    hf_mask = freqs >= hf_start_hz
    hf_rms_ratio = _safe_ratio(_rms(amps[hf_mask]) if np.any(hf_mask) else 0.0, spectrum_rms)
    _, amp_1x = _peak_at(freqs, amps, shaft_hz, tolerance_hz)
    _, amp_2x = _peak_at(freqs, amps, 2.0 * shaft_hz, tolerance_hz)
    _, amp_3x = _peak_at(freqs, amps, 3.0 * shaft_hz, tolerance_hz)
    _, subsync_amp = _peak_at(freqs, amps, 0.5 * shaft_hz, tolerance_hz)
    return {
        "samples": int(x.size),
        "duration_s": float(x.size / fs_hz),
        "shaft_hz": float(shaft_hz),
        "freqs_hz": freqs,
        "spectrum": amps,
        "freq_resolution_hz": float(freq_resolution_hz),
        "tolerance_hz": float(tolerance_hz),
        "spectrum_rms": float(spectrum_rms),
        "noise_floor": float(noise_floor),
        "noise_floor_ratio": _safe_ratio(noise_floor, spectrum_rms),
        "dominant_freq_hz": float(dominant_freq_hz),
        "dominant_amp": float(dominant_amp),
        "dominant_order": float(dominant_order),
        "dominant_ratio": _safe_ratio(dominant_amp, spectrum_rms),
        "hf_start_hz": float(hf_start_hz),
        "hf_rms_ratio": float(hf_rms_ratio),
        "crest_factor": float(_crest_factor(x)),
        "kurtosis_excess": float(_kurtosis_excess(x)),
        "amp_1x_ratio": _safe_ratio(amp_1x, spectrum_rms),
        "amp_2x_ratio": _safe_ratio(amp_2x, spectrum_rms),
        "amp_3x_ratio": _safe_ratio(amp_3x, spectrum_rms),
        "subsync_ratio": _safe_ratio(subsync_amp, spectrum_rms),
    }


def _normalize_hydraulic_elements(*, pass_count: Optional[int] = None, hydraulic_elements: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None, rpm: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if hydraulic_elements is None:
        if pass_count is None:
            raise ValueError("Provide either pass_count or hydraulic_elements.")
        rows.append({"hydraulic_id": "hydraulic_1", "pass_count": int(pass_count), "component_id": "", "component_type": "", "local_rpm": float(rpm)})
    elif isinstance(hydraulic_elements, Mapping):
        if "pass_count" in hydraulic_elements or "blade_count" in hydraulic_elements or "vane_count" in hydraulic_elements:
            items = [hydraulic_elements]
        else:
            items = []
            for key, value in hydraulic_elements.items():
                if isinstance(value, Mapping):
                    item = dict(value)
                    item.setdefault("hydraulic_id", str(key))
                    items.append(item)
                else:
                    items.append({"hydraulic_id": str(key), "pass_count": value})
        for item in items:
            pc = item.get("pass_count") or item.get("blade_count") or item.get("vane_count") or item.get("count")
            pc_float = _float_or_none(pc)
            if pc_float is None or pc_float <= 0:
                continue
            rows.append({
                "hydraulic_id": str(item.get("hydraulic_id") or item.get("id") or f"hydraulic_{len(rows) + 1}"),
                "pass_count": int(round(pc_float)),
                "component_id": str(item.get("component_id") or "").strip().lower(),
                "component_type": str(item.get("component_type") or "").strip().lower(),
                "local_rpm": _float_or_none(item.get("local_rpm") or item.get("rpm") or item.get("running_rpm")) or float(rpm),
            })
    else:
        for item in hydraulic_elements:
            pc = item.get("pass_count") or item.get("blade_count") or item.get("vane_count") or item.get("count")
            pc_float = _float_or_none(pc)
            if pc_float is None or pc_float <= 0:
                continue
            rows.append({
                "hydraulic_id": str(item.get("hydraulic_id") or item.get("id") or f"hydraulic_{len(rows) + 1}"),
                "pass_count": int(round(pc_float)),
                "component_id": str(item.get("component_id") or "").strip().lower(),
                "component_type": str(item.get("component_type") or "").strip().lower(),
                "local_rpm": _float_or_none(item.get("local_rpm") or item.get("rpm") or item.get("running_rpm")) or float(rpm),
            })
    if not rows:
        raise ValueError("No valid hydraulic pass count was provided.")
    return rows


def _hydraulic_pass_frequency_hz(local_rpm: float, pass_count: int) -> float:
    return float(local_rpm) / 60.0 * float(pass_count)


def _axis_weight_hydraulic(axis: str, installed_on: str) -> float:
    base = 1.0 if _axis_is_radial(axis) else 0.55
    if str(installed_on or "unknown").lower() in {"base", "foundation"}:
        base *= 0.70
    return float(base)


def _component_weight_hydraulic(meta: Mapping[str, Any], hydraulic: Mapping[str, Any]) -> float:
    ctype = str(meta.get("component_type", "unknown") or "unknown").lower()
    installed = str(meta.get("installed_on", "unknown") or "unknown").lower()
    component_id = str(meta.get("component_id", "") or "").lower()
    hydraulic_component_id = str(hydraulic.get("component_id", "") or "").lower()
    hydraulic_id = str(hydraulic.get("hydraulic_id", "") or "").lower()
    endpoint_hydraulic_id = str(meta.get("hydraulic_id", "") or "").lower()
    if hydraulic_id and endpoint_hydraulic_id and hydraulic_id == endpoint_hydraulic_id:
        return 1.18
    if hydraulic_component_id and component_id and hydraulic_component_id == component_id:
        return 1.15
    if ctype in HYDRAULIC_COMPONENT_TYPES:
        return 1.10
    if installed in {"casing", "bearing_housing", "pedestal"} and str(meta.get("component_side")) == "driven_hydraulic":
        return 1.05
    if ctype in DRIVER_COMPONENT_TYPES:
        return 0.42
    return 0.35


def _score_hydraulic_axis(*, endpoint_id: str, axis: str, features: Dict[str, Any], meta: Mapping[str, Any], hydraulic: Mapping[str, Any], temp_delta_c: float, target_tolerance_pct: float) -> Dict[str, Any]:
    local_rpm = float(hydraulic.get("local_rpm") or 0.0)
    pass_count = int(hydraulic["pass_count"])
    pass_hz = _hydraulic_pass_frequency_hz(local_rpm, pass_count)
    freqs = features["freqs_hz"]
    amps = features["spectrum"]
    shaft_hz = float(features["shaft_hz"])
    df = float(features["freq_resolution_hz"])
    tol = max(float(features["tolerance_hz"]), pass_hz * float(target_tolerance_pct) / 100.0, 1.5 * df)
    _, pass_amp = _peak_at(freqs, amps, pass_hz, tol)
    _, left_amp = _peak_at(freqs, amps, max(pass_hz - shaft_hz, 0.0), tol)
    _, right_amp = _peak_at(freqs, amps, pass_hz + shaft_hz, tol)
    _, pass_2_amp = _peak_at(freqs, amps, 2.0 * pass_hz, tol)
    spectrum_rms = max(float(features["spectrum_rms"]), EPS)
    pass_ratio = _safe_ratio(pass_amp, spectrum_rms)
    pass_2_ratio = _safe_ratio(pass_2_amp, spectrum_rms)
    sideband_ratio = _safe_ratio(left_amp + right_amp, max(pass_amp, EPS))
    sideband_energy_ratio = _safe_ratio(left_amp + right_amp, spectrum_rms)
    dominant_order = float(features["dominant_order"])
    dominant_order_match = 1.0 - min(abs(dominant_order - float(pass_count)) / max(float(pass_count), 1.0), 1.0)
    hf = float(features["hf_rms_ratio"])
    kurt = float(features["kurtosis_excess"])
    crest = float(features["crest_factor"])
    raw_score = (
        36.0 * _score_linear(pass_ratio, 0.5, 3.0)
        + 18.0 * dominant_order_match
        + 18.0 * _score_linear(sideband_ratio, 0.10, 0.80)
        + 10.0 * _score_linear(hf, 0.6, 2.0)
        + 10.0 * _score_linear(temp_delta_c, 4.0, 16.0)
        + 8.0 * _score_linear(max(kurt, 0.0), 0.4, 2.5)
    )
    raw_score += 5.0 * _score_linear(pass_2_ratio, 0.20, 1.50)
    limitations: List[str] = []
    if pass_ratio < 0.35 and sideband_ratio < 0.10:
        raw_score *= 0.55
        limitations.append("Reduced because both pass-frequency amplitude and pass sidebands are weak.")
    if str(meta.get("component_side")) != "driven_hydraulic":
        limitations.append("Endpoint is not marked as pump/fan/blower/compressor; treating this as transmitted support, not primary hydraulic evidence.")
    if pass_hz >= 0.45 * float(features["freqs_hz"][-1]):
        raw_score *= 0.70
        limitations.append("Reduced because pass frequency is close to the usable Nyquist limit.")
    axis_weight = _axis_weight_hydraulic(axis, str(meta.get("installed_on", "unknown")))
    component_weight = _component_weight_hydraulic(meta, hydraulic)
    score = _clamp(raw_score * axis_weight * component_weight, 0.0, 100.0)
    return {
        "fault": "hydraulic_vane_or_blade_pass",
        "label": "Hydraulic vane/blade-pass forcing",
        "hydraulic_id": str(hydraulic.get("hydraulic_id") or "hydraulic_1"),
        "pass_count": int(pass_count),
        "pass_hz": float(pass_hz),
        "endpoint_id": endpoint_id,
        "axis": axis,
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "local_rpm": float(local_rpm),
        "score": float(score),
        "confidence": _confidence_from_score(score),
        "possible": bool(score >= 20.0),
        "metrics": {
            "pass_hz": float(pass_hz),
            "pass_ratio": float(pass_ratio),
            "pass_2_ratio": float(pass_2_ratio),
            "sideband_ratio": float(sideband_ratio),
            "sideband_energy_ratio": float(sideband_energy_ratio),
            "left_sideband_amp": float(left_amp),
            "right_sideband_amp": float(right_amp),
            "dominant_order": float(dominant_order),
            "dominant_order_match": float(dominant_order_match),
            "hf_rms_ratio": float(hf),
            "kurtosis_excess": float(kurt),
            "crest_factor": float(crest),
            "temperature_delta_c": float(temp_delta_c),
            "axis_weight": float(axis_weight),
            "component_weight": float(component_weight),
            "spectrum_rms": float(spectrum_rms),
            "freq_resolution_hz": float(df),
            "tolerance_hz": float(tol),
        },
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: pass_freq={pass_hz:.2f}Hz, pass={pass_ratio:.2f}xRMS, "
            f"sidebands={sideband_ratio:.2f}, dominant_order={dominant_order:.2f}x, "
            f"HF={hf:.2f}, kurtosis={kurt:.2f}, temp_delta={temp_delta_c:.1f}C"
        ),
    }


def _best_de_row_per_endpoint(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        role = str(row.get("endpoint_role", "unknown")).upper()
        if role != "DE" and not _truthy(row.get("is_coupling_end")):
            continue
        endpoint_id = str(row.get("endpoint_id", ""))
        if not endpoint_id:
            continue
        current = best.get(endpoint_id)
        if current is None or float(row.get("score", 0.0)) > float(current.get("score", 0.0)):
            best[endpoint_id] = row
    return best


def _same_shaft_compatible(left: Mapping[str, Any], right: Mapping[str, Any], rpm_tolerance_pct: float = 5.0) -> bool:
    if str(left.get("endpoint_id")) == str(right.get("endpoint_id")):
        return False
    left_group = str(left.get("shaft_group_id", "") or "").strip().lower()
    right_group = str(right.get("shaft_group_id", "") or "").strip().lower()
    if left_group and right_group and left_group != right_group:
        return False
    left_rpm = _float_or_none(left.get("local_rpm"))
    right_rpm = _float_or_none(right.get("local_rpm"))
    if left_rpm and right_rpm and left_rpm > 0.0 and right_rpm > 0.0:
        avg = 0.5 * (left_rpm + right_rpm)
        delta_pct = 100.0 * abs(left_rpm - right_rpm) / max(avg, EPS)
        if delta_pct > rpm_tolerance_pct:
            return False
    return True


def _pair_vector(row: Mapping[str, Any]) -> np.ndarray:
    metrics = row.get("metrics", {}) or {}
    def v(key: str) -> float:
        try:
            number = float(metrics.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0
        return number if np.isfinite(number) else 0.0
    return np.asarray([v("pass_ratio"), v("sideband_ratio"), v("sideband_energy_ratio"), v("dominant_order_match"), v("hf_rms_ratio"), max(v("kurtosis_excess"), 0.0)], dtype=float)


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
    if sides == {"driver", "driven_hydraulic"}:
        return 1.12, "driver_to_driven_hydraulic_de_pair"
    if "driven_hydraulic" in sides and "unknown" in sides:
        return 1.02, "hydraulic_to_unknown_de_pair"
    if sides == {"driven_hydraulic"}:
        return 1.05, "hydraulic_to_hydraulic_de_pair"
    return 0.90, "generic_de_pair"


def _best_de_pair_support(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    de_rows = list(_best_de_row_per_endpoint(rows).values())
    if len(de_rows) < 2:
        return {"available": False, "used": False, "reason": "Less than two DE/coupling-end endpoints are available.", "pair_score": 0.0, "similarity": 0.0}
    best: Optional[Dict[str, Any]] = None
    for i in range(len(de_rows)):
        for j in range(i + 1, len(de_rows)):
            left = de_rows[i]
            right = de_rows[j]
            if not _same_shaft_compatible(left, right):
                continue
            similarity = _log_vector_similarity(_pair_vector(left), _pair_vector(right))
            left_score = float(left.get("score", 0.0))
            right_score = float(right.get("score", 0.0))
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            axis_factor = 1.0 if str(left.get("axis")) == str(right.get("axis")) else 0.94
            pair_score = (0.62 * min(left_score, right_score) + 0.38 * (0.5 * (left_score + right_score))) * (0.55 + 0.45 * similarity) * pair_multiplier * axis_factor
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


def detect_hydraulic_vane_blade_pass(
    acceleration_twf: Any,
    sampling_frequency_hz: float,
    rpm: float,
    *,
    pass_count: Optional[int] = None,
    hydraulic_elements: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
    asset_id: Optional[str] = None,
    endpoint_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
    axes: Optional[List[str]] = None,
    surface_temperature_c: Optional[NumericOrMap] = None,
    baseline_temperature_c: Optional[NumericOrMap] = None,
    temperature_delta_c: Optional[NumericOrMap] = None,
    min_score: float = 20.0,
    target_tolerance_pct: float = 3.0,
    compare_de_endpoints: bool = True,
) -> Dict[str, Any]:
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive.")
    endpoints = _normalize_triaxial_twf(acceleration_twf, axes=axes)
    hydraulics = _normalize_hydraulic_elements(pass_count=pass_count, hydraulic_elements=hydraulic_elements, rpm=rpm)
    endpoint_meta: Dict[str, Dict[str, Any]] = {endpoint_id: _endpoint_metadata(endpoint_metadata, endpoint_id) for endpoint_id in endpoints}
    endpoint_results: Dict[str, Any] = {}
    feature_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for endpoint_id, axis_map in endpoints.items():
        meta = endpoint_meta[endpoint_id]
        endpoint_rpm = float(meta.get("local_rpm") or rpm)
        endpoint_results[endpoint_id] = {"metadata": dict(meta), "rpm_used": float(endpoint_rpm), "axes": {}}
        for axis_name, axis_values in axis_map.items():
            axis = _norm_axis_name(axis_name)
            axis_result: Dict[str, Any] = {"valid": False, "features": {}, "faults_by_hydraulic": {}, "error": None}
            try:
                features = _extract_axis_features(axis_values, fs_hz, endpoint_rpm)
                feature_cache[(endpoint_id, axis)] = features
                axis_result["valid"] = True
                axis_result["features"] = {
                    "samples": features["samples"],
                    "duration_s": features["duration_s"],
                    "shaft_hz": features["shaft_hz"],
                    "rpm_used": float(endpoint_rpm),
                    "dominant_freq_hz": features["dominant_freq_hz"],
                    "dominant_order": features["dominant_order"],
                    "dominant_ratio": features["dominant_ratio"],
                    "hf_rms_ratio": features["hf_rms_ratio"],
                    "kurtosis_excess": features["kurtosis_excess"],
                    "crest_factor": features["crest_factor"],
                    "noise_floor_ratio": features["noise_floor_ratio"],
                    "freq_resolution_hz": features["freq_resolution_hz"],
                }
            except Exception as exc:
                axis_result["error"] = str(exc)
            endpoint_results[endpoint_id]["axes"][axis] = axis_result
    hydraulic_results: Dict[str, Any] = {}
    possible_faults: List[Dict[str, Any]] = []
    for hydraulic in hydraulics:
        hydraulic_id = str(hydraulic["hydraulic_id"])
        axis_rows: List[Dict[str, Any]] = []
        rows_by_endpoint: Dict[str, List[Dict[str, Any]]] = {}
        for endpoint_id, axis_map in endpoints.items():
            meta = endpoint_meta[endpoint_id]
            temp_delta = _resolve_temperature_delta_c(endpoint_id=endpoint_id, surface_temperature_c=surface_temperature_c, baseline_temperature_c=baseline_temperature_c, temperature_delta_c=temperature_delta_c)
            for axis_name in axis_map.keys():
                axis = _norm_axis_name(axis_name)
                features = feature_cache.get((endpoint_id, axis))
                if not features:
                    continue
                row = _score_hydraulic_axis(endpoint_id=endpoint_id, axis=axis, features=features, meta=meta, hydraulic=hydraulic, temp_delta_c=temp_delta, target_tolerance_pct=target_tolerance_pct)
                row["shaft_group_id"] = str(meta.get("shaft_group_id", ""))
                row["is_coupling_end"] = bool(meta.get("is_coupling_end", False))
                row["hydraulic_component_id"] = str(hydraulic.get("component_id", ""))
                axis_rows.append(row)
                rows_by_endpoint.setdefault(endpoint_id, []).append(row)
                endpoint_results[endpoint_id]["axes"][axis]["faults_by_hydraulic"][hydraulic_id] = row
        endpoint_summaries: Dict[str, Any] = {}
        for endpoint_id, rows in rows_by_endpoint.items():
            scores = [float(row["score"]) for row in rows]
            supporting_rows = [row for row in rows if float(row["score"]) >= 40.0]
            best_row = max(rows, key=lambda row: float(row["score"]))
            endpoint_score = _clamp(0.74 * _top_mean(scores, n=3) + 10.0 * _score_linear(len(rows), 1.0, 3.0) + 8.0 * _score_linear(len(supporting_rows), 1.0, 3.0), 0.0, 100.0)
            endpoint_summaries[endpoint_id] = {
                "fault": "hydraulic_vane_or_blade_pass",
                "hydraulic_id": hydraulic_id,
                "score": float(endpoint_score),
                "confidence": _confidence_from_score(endpoint_score),
                "possible": bool(endpoint_score >= min_score),
                "best_axis": best_row["axis"],
                "best_axis_score": float(best_row["score"]),
                "supporting_axes": [row["axis"] for row in supporting_rows],
                "component_type": str(best_row.get("component_type", "unknown")),
                "endpoint_role": str(best_row.get("endpoint_role", "unknown")),
                "evidence": best_row["evidence"],
            }
        axis_scores = [float(row["score"]) for row in axis_rows]
        supporting_axis_rows = [row for row in axis_rows if float(row["score"]) >= 40.0]
        supporting_endpoint_ids = sorted({row["endpoint_id"] for row in supporting_axis_rows})
        hydraulic_endpoint_support = [row for row in axis_rows if row.get("component_side") == "driven_hydraulic" and float(row.get("score", 0.0)) >= 35.0]
        de_pair_support = _best_de_pair_support(axis_rows) if compare_de_endpoints else {"available": False, "used": False, "reason": "DE endpoint comparison disabled.", "pair_score": 0.0, "similarity": 0.0}
        if axis_rows:
            best_axis_row = max(axis_rows, key=lambda row: float(row["score"]))
            base_score = _clamp(0.76 * _top_mean(axis_scores, n=3) + 14.0 * _score_linear(len(set(row["endpoint_id"] for row in axis_rows)), 1.0, 3.0) + 10.0 * _score_linear(len(supporting_axis_rows), 1.0, 4.0), 0.0, 100.0)
        else:
            best_axis_row = None
            base_score = 0.0
        de_pair_boost = 10.0 * _score_linear(float(de_pair_support.get("pair_score", 0.0)), 35.0, 75.0) if de_pair_support.get("available") else 0.0
        score = _clamp(base_score + de_pair_boost, 0.0, 100.0)
        limitations: List[str] = [
            "Pass count and local RPM must be correct, especially on speed-changing equipment.",
            "Hydraulic pass-frequency forcing should be confirmed with operating point, flow, valve position, and process condition when available.",
        ]
        if not hydraulic_endpoint_support:
            score *= 0.72
            limitations.append("Reduced because no pump/fan/blower/compressor endpoint strongly supports the hydraulic pass-frequency call.")
        if not de_pair_support.get("available"):
            limitations.append("No usable DE-to-DE same-shaft pair was available; result falls back to endpoint/axis aggregation.")
        score = _clamp(score, 0.0, 100.0)
        summary = {
            "fault": "hydraulic_vane_or_blade_pass",
            "label": "Hydraulic vane/blade-pass forcing",
            "scope": "hydraulic_local",
            "hydraulic_id": hydraulic_id,
            "pass_count": int(hydraulic["pass_count"]),
            "pass_hz": _hydraulic_pass_frequency_hz(float(hydraulic["local_rpm"]), int(hydraulic["pass_count"])),
            "score": float(score),
            "base_score_before_de_pair": float(base_score),
            "de_pair_boost": float(de_pair_boost),
            "confidence": _confidence_from_score(score),
            "possible": bool(score >= min_score),
            "best_endpoint": best_axis_row["endpoint_id"] if best_axis_row else None,
            "best_axis": best_axis_row["axis"] if best_axis_row else None,
            "best_axis_score": float(best_axis_row["score"]) if best_axis_row else 0.0,
            "supporting_endpoints": supporting_endpoint_ids,
            "supporting_axis_count": int(len(supporting_axis_rows)),
            "evidence": best_axis_row["evidence"] if best_axis_row else "",
            "limitations": limitations,
            "de_pair_support": de_pair_support,
            "metrics": {
                "mean_axis_score": _mean_or_zero(axis_scores),
                "top_axis_score": float(max(axis_scores)) if axis_scores else 0.0,
                "num_evaluated_axes": float(len(axis_rows)),
                "num_evaluated_endpoints": float(len(set(row["endpoint_id"] for row in axis_rows))),
                "num_supporting_axes": float(len(supporting_axis_rows)),
                "num_supporting_endpoints": float(len(supporting_endpoint_ids)),
                "num_hydraulic_endpoint_support_axes": float(len(hydraulic_endpoint_support)),
                "mean_pass_ratio": _mean_or_zero([row["metrics"]["pass_ratio"] for row in axis_rows]),
                "mean_sideband_ratio": _mean_or_zero([row["metrics"]["sideband_ratio"] for row in axis_rows]),
                "mean_hf_rms_ratio": _mean_or_zero([row["metrics"]["hf_rms_ratio"] for row in axis_rows]),
                "mean_kurtosis_excess": _mean_or_zero([row["metrics"]["kurtosis_excess"] for row in axis_rows]),
                "de_pair_score": float(de_pair_support.get("pair_score", 0.0)),
                "de_pair_similarity": float(de_pair_support.get("similarity", 0.0)),
            },
        }
        hydraulic_results[hydraulic_id] = {"summary": summary, "endpoint_summaries": endpoint_summaries, "axis_rows": axis_rows}
        if summary["score"] >= min_score:
            possible_faults.append(summary)
    possible_faults.sort(key=lambda row: float(row["score"]), reverse=True)
    primary_fault = possible_faults[0] if possible_faults else None
    return {
        "asset_id": asset_id,
        "rpm": float(rpm),
        "shaft_hz": float(rpm / 60.0),
        "sampling_frequency_hz": float(fs_hz),
        "signal_domain": "acceleration_twf_to_acceleration_spectrum",
        "de_pair_logic": {
            "enabled": bool(compare_de_endpoints),
            "description": "Compatible DE/coupling-end endpoints are compared as supporting evidence. For hydraulic faults, the strongest evidence should normally come from the driven hydraulic endpoint; Motor DE or other DE points are treated as transmitted/coupled support.",
        },
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "hydraulic_results": hydraulic_results,
        "endpoint_results": endpoint_results,
        "limitations": [
            "This detector identifies hydraulic vane/blade-pass forcing from acceleration vibration; it does not directly prove the hydraulic root cause.",
            "Correct pass count and real local RPM are required.",
            "DE-to-DE comparison is a bounded support boost and is not required for detection.",
            "Use process variables such as flow, suction/discharge pressure, valve position, recirculation state, and NPSH margin to separate pass-frequency forcing from cavitation or off-design operation.",
        ],
    }


__all__ = ["detect_hydraulic_vane_blade_pass"]
