"""
Standalone cavitation / aeration detector for rotating hydraulic assets.

This module adapts the cavitation_or_aeration logic from the uploaded Presage
rotating-machine diagnostics script into a standalone function that does not
require the original AssetDefinition, SensorMeasurement, AxisSignal, or
FaultResult classes.

Main public function:
    detect_cavitation_or_aeration(...)

Expected use:
    - input: acceleration time waveform, tri-axial, one or more endpoints
    - metadata: RPM, optional hydraulic element/pass count, optional endpoint metadata
    - output: structured score, evidence, endpoint/axis details, and DE-pair support

Design notes:
    - Cavitation/aeration is treated as a hydraulic-local fault.
    - Acceleration TWF -> acceleration spectrum is used as the main signal domain.
    - The strongest evidence should normally come from pump/fan/blower/compressor
      endpoints. Motor/driver endpoints can provide transmitted/coupled support.
    - DE-to-DE comparison is a bounded support boost, not the primary proof.
    - Pass count is optional. If supplied, it helps separate cavitation/aeration
      from clean vane/blade-pass forcing. If omitted, the detector works as a
      broadband hydraulic distress screen and returns a limitation.
"""

from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
from app.auto_diagnostics.signal_feature_cache_v4 import (
    one_sided_spectrum as _cached_one_sided_spectrum,
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

EPS = 1e-12
CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
HYDRAULIC_COMPONENT_TYPES = {"pump", "fan", "blower", "compressor", "chiller", "hydraulic", "aero", "driven"}
DRIVER_COMPONENT_TYPES = {"motor", "engine", "turbine", "driver"}

NumericOrMap = Union[float, int, Mapping[str, Union[float, int]]]


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    if abs(float(den)) <= EPS:
        return float(default)
    return float(num) / float(den)


def _score_linear(value: float, low: float, high: float) -> float:
    """Linear 0..1 ramp."""
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
    score = float(score)
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

    if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[cap]:
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


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

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


def _norm_axis_name(axis: Any) -> str:
    text = str(axis).strip().lower()
    return AXIS_ALIASES.get(text, text or "axis")


def _axis_is_radial(axis: str) -> bool:
    return _norm_axis_name(axis) in {"horizontal", "vertical", "radial", "x", "y", "z"}


def _array_to_axis_map(arr: Any, axes: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    data = np.asarray(arr, dtype=float)

    if data.ndim == 1:
        return {"axis_1": _as_float_array(data)}

    if data.ndim != 2:
        raise ValueError("Acceleration TWF array must be 1-D or 2-D.")

    if data.shape[1] == 3:
        axis_names = axes or ["x", "y", "z"]
        return {_norm_axis_name(axis_names[i]): _as_float_array(data[:, i]) for i in range(3)}

    if data.shape[0] == 3:
        axis_names = axes or ["x", "y", "z"]
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
    """
    Returns:
        {
          "endpoint_id": {"x": np.ndarray, "y": np.ndarray, "z": np.ndarray}
        }

    Accepted input shapes:
        1) {"endpoint_1": {"x": [...], "y": [...], "z": [...]}, ...}
        2) {"x": [...], "y": [...], "z": [...]}       # single endpoint
        3) np.ndarray shape [samples, 3]
        4) np.ndarray shape [3, samples]
        5) np.ndarray shape [samples]
    """
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


# ---------------------------------------------------------------------------
# Endpoint metadata and DE/NDE helpers
# ---------------------------------------------------------------------------


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "de", "drive_end", "drive-end",
        "coupling", "coupling_end", "coupling-end", "present", "available",
    }


def _float_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _endpoint_role_from_text(text: Any) -> str:
    """Resolve DE/NDE. NDE must be checked before DE."""
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
    fields = [
        "endpoint_role", "end_role", "end_type", "end", "endpoint_flag",
        "de_nde", "drive_end_flag", "bearing_end", "location_end", "position",
    ]
    for field in fields:
        if field in raw_meta and raw_meta.get(field) not in {None, ""}:
            role = _endpoint_role_from_text(raw_meta.get(field))
            if role != "unknown":
                return role

    if _truthy(raw_meta.get("is_nde")):
        return "NDE"
    if _truthy(raw_meta.get("is_de")):
        return "DE"
    if _truthy(raw_meta.get("is_drive_end")):
        return "DE"
    if _truthy(raw_meta.get("is_coupling_end")):
        return "DE"

    text_candidates = [
        endpoint_id,
        raw_meta.get("location_tag"),
        raw_meta.get("endpoint_tag"),
        raw_meta.get("name"),
        raw_meta.get("mount_name"),
        raw_meta.get("composite_id"),
        raw_meta.get("composite_key"),
    ]
    for candidate in text_candidates:
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

    component_id = str(
        raw_meta.get("component_id")
        or raw_meta.get("component")
        or ""
    ).strip().lower()

    endpoint_role = _resolve_endpoint_role(endpoint_id, raw_meta)

    shaft_group_id = str(
        raw_meta.get("shaft_group_id")
        or raw_meta.get("shaft_id")
        or raw_meta.get("train_id")
        or raw_meta.get("coupling_group_id")
        or ""
    ).strip().lower()

    hydraulic_id = str(
        raw_meta.get("hydraulic_id")
        or raw_meta.get("hydraulic_element_id")
        or raw_meta.get("pump_id")
        or raw_meta.get("fan_id")
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

    side = _component_side(component_type, endpoint_id)

    return {
        "installed_on": installed_on,
        "component_type": component_type,
        "component_id": component_id,
        "endpoint_role": endpoint_role,
        "is_coupling_end": is_coupling_end,
        "shaft_group_id": shaft_group_id,
        "hydraulic_id": hydraulic_id,
        "local_rpm": local_rpm,
        "component_side": side,
    }


# ---------------------------------------------------------------------------
# Temperature and process-evidence helpers
# ---------------------------------------------------------------------------


def _lookup_endpoint_numeric(value: Optional[NumericOrMap], endpoint_id: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        if endpoint_id not in value:
            return None
        return _float_or_none(value[endpoint_id])
    return _float_or_none(value)


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


def _process_evidence_score(process_evidence: Optional[Mapping[str, Any]]) -> Tuple[float, List[str]]:
    """
    Optional process corroboration for cavitation/aeration.

    Supported truthy keys include:
        low_npsh, npsh_margin_low, suction_pressure_low, suction_pressure_drop,
        air_entrainment, entrained_air, suction_leak, strainer_blocked,
        valve_throttled, recirculation, minimum_flow_violation, off_design_flow.
    """
    if not process_evidence:
        return 0.0, []

    key_labels = {
        "low_npsh": "low NPSH margin",
        "npsh_margin_low": "low NPSH margin",
        "suction_pressure_low": "low suction pressure",
        "suction_pressure_drop": "suction pressure drop",
        "air_entrainment": "entrained air",
        "entrained_air": "entrained air",
        "suction_leak": "possible suction leak",
        "strainer_blocked": "blocked/dirty suction strainer",
        "valve_throttled": "throttled/incorrect valve position",
        "recirculation": "recirculation/off-design operation",
        "minimum_flow_violation": "minimum-flow violation",
        "off_design_flow": "off-design flow",
    }

    hits: List[str] = []
    for key, label in key_labels.items():
        if _truthy(process_evidence.get(key)):
            hits.append(label)

    score = _score_linear(len(hits), 1.0, 4.0)
    return float(score), hits


# ---------------------------------------------------------------------------
# Spectrum and feature extraction
# ---------------------------------------------------------------------------


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


def _band_rms(freqs_hz: np.ndarray, amplitudes: np.ndarray, low_hz: float, high_hz: float) -> float:
    if high_hz <= low_hz or freqs_hz.size == 0 or amplitudes.size == 0:
        return 0.0
    mask = (freqs_hz >= low_hz) & (freqs_hz <= high_hz)
    if not np.any(mask):
        return 0.0
    return _rms(amplitudes[mask])


def _extract_axis_features(x: np.ndarray, fs_hz: float, rpm: float) -> Dict[str, Any]:
    x = _as_float_array(x)
    if x.size < 128:
        raise ValueError("Need at least 128 samples for cavitation/aeration detection.")
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
    hf_rms = _rms(amps[hf_mask]) if np.any(hf_mask) else 0.0
    hf_rms_ratio = _safe_ratio(hf_rms, spectrum_rms)

    # A broad high-frequency indicator. Cavitation often lifts a wide band rather
    # than only a single exact pass-frequency line.
    upper = float(freqs[-1])
    broad_low = max(hf_start_hz, 0.10 * upper)
    broad_high = max(broad_low, 0.90 * upper)
    broad_hf_ratio = _safe_ratio(_band_rms(freqs, amps, broad_low, broad_high), spectrum_rms)

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
        "broad_hf_ratio": float(broad_hf_ratio),
        "crest_factor": float(_crest_factor(x)),
        "kurtosis_excess": float(_kurtosis_excess(x)),
        "amp_1x_ratio": _safe_ratio(amp_1x, spectrum_rms),
        "amp_2x_ratio": _safe_ratio(amp_2x, spectrum_rms),
        "amp_3x_ratio": _safe_ratio(amp_3x, spectrum_rms),
        "subsync_ratio": _safe_ratio(subsync_amp, spectrum_rms),
    }


# ---------------------------------------------------------------------------
# Hydraulic element normalization
# ---------------------------------------------------------------------------


def _normalize_hydraulic_elements(
    *,
    pass_count: Optional[int] = None,
    hydraulic_elements: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
    rpm: float,
) -> List[Dict[str, Any]]:
    """
    Output rows:
        {"hydraulic_id": str, "pass_count": Optional[int], "component_id": str, "local_rpm": float}

    For cavitation/aeration, pass_count is helpful but optional.
    """
    rows: List[Dict[str, Any]] = []

    def _append_item(item: Mapping[str, Any], default_id: str) -> None:
        pc = item.get("pass_count") or item.get("blade_count") or item.get("vane_count") or item.get("count")
        pc_float = _float_or_none(pc)
        pc_int = int(round(pc_float)) if pc_float is not None and pc_float > 0 else None
        rows.append({
            "hydraulic_id": str(item.get("hydraulic_id") or item.get("id") or default_id),
            "pass_count": pc_int,
            "component_id": str(item.get("component_id") or "").strip().lower(),
            "component_type": str(item.get("component_type") or "").strip().lower(),
            "local_rpm": _float_or_none(item.get("local_rpm") or item.get("rpm") or item.get("running_rpm")) or float(rpm),
        })

    if hydraulic_elements is None:
        item: Dict[str, Any] = {"hydraulic_id": "hydraulic_1", "local_rpm": float(rpm)}
        if pass_count is not None:
            item["pass_count"] = pass_count
        _append_item(item, "hydraulic_1")
    elif isinstance(hydraulic_elements, Mapping):
        if any(k in hydraulic_elements for k in ["pass_count", "blade_count", "vane_count", "count", "hydraulic_id"]):
            _append_item(hydraulic_elements, "hydraulic_1")
        else:
            for key, value in hydraulic_elements.items():
                if isinstance(value, Mapping):
                    item = dict(value)
                    item.setdefault("hydraulic_id", str(key))
                    _append_item(item, str(key))
                else:
                    _append_item({"hydraulic_id": str(key), "pass_count": value}, str(key))
    else:
        for idx, item in enumerate(hydraulic_elements, start=1):
            _append_item(item, f"hydraulic_{idx}")

    if not rows:
        rows.append({
            "hydraulic_id": "hydraulic_1",
            "pass_count": None,
            "component_id": "",
            "component_type": "",
            "local_rpm": float(rpm),
        })

    return rows


def _hydraulic_pass_frequency_hz(local_rpm: float, pass_count: Optional[int]) -> float:
    if pass_count is None or int(pass_count) <= 0:
        return 0.0
    return float(local_rpm) / 60.0 * float(pass_count)


# ---------------------------------------------------------------------------
# Axis-level scoring
# ---------------------------------------------------------------------------


def _axis_weight_cavitation(axis: str, installed_on: str) -> float:
    base = 1.0 if _axis_is_radial(axis) else 0.60
    installed_on = str(installed_on or "unknown").lower()
    if installed_on in {"base", "foundation"}:
        base *= 0.70
    return float(base)


def _component_weight_cavitation(meta: Mapping[str, Any], hydraulic: Mapping[str, Any]) -> float:
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
        return 0.35
    return 0.40


def _score_cavitation_axis(
    *,
    endpoint_id: str,
    axis: str,
    features: Dict[str, Any],
    meta: Mapping[str, Any],
    hydraulic: Mapping[str, Any],
    temp_delta_c: float,
    target_tolerance_pct: float,
    process_score: float,
    process_hits: List[str],
) -> Dict[str, Any]:
    local_rpm = float(hydraulic.get("local_rpm") or 0.0)
    pass_count = hydraulic.get("pass_count")
    pass_hz = _hydraulic_pass_frequency_hz(local_rpm, pass_count)

    freqs = features["freqs_hz"]
    amps = features["spectrum"]
    shaft_hz = float(features["shaft_hz"])
    df = float(features["freq_resolution_hz"])
    spectrum_rms = max(float(features["spectrum_rms"]), EPS)

    pass_available = pass_hz > 0.0
    tol = max(float(features["tolerance_hz"]), 1.5 * df)
    if pass_available:
        tol = max(tol, pass_hz * float(target_tolerance_pct) / 100.0)

    pass_peak_hz = 0.0
    pass_amp = 0.0
    left_amp = 0.0
    right_amp = 0.0
    pass_2_amp = 0.0
    pass_ratio = 0.0
    sideband_ratio = 0.0
    sideband_energy_ratio = 0.0
    pass_2_ratio = 0.0
    dominant_order_match = 0.0

    if pass_available:
        pass_peak_hz, pass_amp = _peak_at(freqs, amps, pass_hz, tol)
        _, left_amp = _peak_at(freqs, amps, max(pass_hz - shaft_hz, 0.0), tol)
        _, right_amp = _peak_at(freqs, amps, pass_hz + shaft_hz, tol)
        _, pass_2_amp = _peak_at(freqs, amps, 2.0 * pass_hz, tol)
        pass_ratio = _safe_ratio(pass_amp, spectrum_rms)
        sideband_ratio = _safe_ratio(left_amp + right_amp, max(pass_amp, EPS))
        sideband_energy_ratio = _safe_ratio(left_amp + right_amp, spectrum_rms)
        pass_2_ratio = _safe_ratio(pass_2_amp, spectrum_rms)
        dominant_order_match = 1.0 - min(
            abs(float(features["dominant_order"]) - float(pass_count)) / max(float(pass_count), 1.0),
            1.0,
        )

    hf = float(features["hf_rms_ratio"])
    broad_hf = float(features.get("broad_hf_ratio", 0.0))
    kurt = float(features["kurtosis_excess"])
    crest = float(features["crest_factor"])
    amp_1x_ratio = float(features["amp_1x_ratio"])
    subsync_ratio = float(features["subsync_ratio"])
    noise_floor_ratio = float(features["noise_floor_ratio"])

    hf_score = _score_linear(hf, 0.8, 3.2)
    broad_hf_score = _score_linear(broad_hf, 0.25, 1.15)
    kurtosis_score = _score_linear(max(kurt, 0.0), 0.5, 3.2)
    crest_score = _score_linear(crest, 3.6, 7.2)
    low_1x_score = 1.0 - _score_linear(amp_1x_ratio, 1.6, 5.0)
    subsync_score = _score_linear(subsync_ratio, 0.3, 1.5)
    temp_score = _score_linear(temp_delta_c, 4.0, 16.0)
    noise_score = _score_linear(noise_floor_ratio, 0.10, 0.34)

    if pass_available:
        low_pass_score = 1.0 - _score_linear(pass_ratio, 0.7, 3.0)
        sideband_energy_score = _score_linear(sideband_energy_ratio, 0.2, 1.5)
        sideband_ratio_score = _score_linear(sideband_ratio, 0.10, 0.85)
    else:
        low_pass_score = 0.55
        sideband_energy_score = 0.0
        sideband_ratio_score = 0.0

    # Adapted from the original script's cavitation_or_aeration scoring:
    # HF acceleration is primary; kurtosis and crest factor support; clean 1x
    # or clean pass-frequency dominance suppresses a pure cavitation call;
    # pass sideband/broadband energy and temperature/process clues are supporting.
    raw_score = (
        30.0 * hf_score
        + 10.0 * broad_hf_score
        + 18.0 * kurtosis_score
        + 16.0 * crest_score
        + 10.0 * low_1x_score
        + 7.0 * low_pass_score
        + 8.0 * sideband_energy_score
        + 5.0 * sideband_ratio_score
        + 6.0 * subsync_score
        + 8.0 * temp_score
        + 6.0 * process_score
        + 4.0 * noise_score
    )

    limitations: List[str] = []

    if not pass_available:
        raw_score *= 0.92
        limitations.append(
            "Pass count was not provided, so pass-frequency separation from clean vane/blade-pass forcing is limited."
        )

    if max(hf_score, kurtosis_score, crest_score) < 0.18:
        raw_score *= 0.50
        limitations.append(
            "Reduced because broadband/high-frequency and impulsive evidence is weak for cavitation/aeration."
        )

    clean_pass_indicator = 0.0
    if pass_available:
        clean_pass_indicator = (
            0.45 * _score_linear(pass_ratio, 0.8, 3.0)
            + 0.25 * _score_linear(dominant_order_match, 0.55, 0.95)
            + 0.20 * (1.0 - _score_linear(hf, 0.8, 2.0))
            + 0.10 * (1.0 - _score_linear(max(kurt, 0.0), 0.5, 2.0))
        )
        if clean_pass_indicator >= 0.70:
            raw_score *= 0.70
            limitations.append(
                "Reduced because the pattern looks more like clean vane/blade-pass forcing than broadband cavitation/aeration."
            )

    if amp_1x_ratio >= 5.0 and hf_score < 0.35:
        raw_score *= 0.72
        limitations.append(
            "Reduced because strong 1X synchronous energy with weak broadband evidence is more consistent with a shaft-order fault."
        )

    axis_weight = _axis_weight_cavitation(axis, str(meta.get("installed_on", "unknown")))
    component_weight = _component_weight_cavitation(meta, hydraulic)
    score = _clamp(raw_score * axis_weight * component_weight, 0.0, 100.0)

    process_text = ", ".join(process_hits[:4]) if process_hits else "none"
    pass_text = f", pass_freq={pass_hz:.2f}Hz, pass={pass_ratio:.2f}xRMS, sideband_energy={sideband_energy_ratio:.2f}xRMS" if pass_available else ""

    return {
        "fault": "cavitation_or_aeration",
        "label": "Cavitation / aeration hydraulic broadband distress",
        "scope": "hydraulic_local",
        "hydraulic_id": str(hydraulic["hydraulic_id"]),
        "pass_count": int(pass_count) if pass_count is not None else None,
        "pass_hz": float(pass_hz),
        "endpoint_id": endpoint_id,
        "axis": axis,
        "score": float(score),
        "confidence": _confidence_from_score(score),
        "possible": bool(score >= 20.0),
        "endpoint_role": str(meta.get("endpoint_role", "unknown")),
        "component_type": str(meta.get("component_type", "unknown")),
        "component_side": str(meta.get("component_side", "unknown")),
        "installed_on": str(meta.get("installed_on", "unknown")),
        "local_rpm": float(local_rpm),
        "metrics": {
            "hf_rms_ratio": hf,
            "broad_hf_ratio": broad_hf,
            "kurtosis_excess": kurt,
            "crest_factor": crest,
            "noise_floor_ratio": noise_floor_ratio,
            "amp_1x_ratio": amp_1x_ratio,
            "subsync_ratio": subsync_ratio,
            "temperature_delta_c": float(temp_delta_c),
            "process_evidence_score_0_1": float(process_score),
            "pass_ratio": float(pass_ratio),
            "pass_peak_hz": float(pass_peak_hz),
            "pass_2_ratio": float(pass_2_ratio),
            "sideband_ratio": float(sideband_ratio),
            "sideband_energy_ratio": float(sideband_energy_ratio),
            "dominant_order": float(features["dominant_order"]),
            "dominant_order_match_to_pass_count": float(dominant_order_match),
            "clean_pass_indicator_0_1": float(clean_pass_indicator),
            "hf_score_0_1": float(hf_score),
            "kurtosis_score_0_1": float(kurtosis_score),
            "crest_score_0_1": float(crest_score),
            "low_1x_score_0_1": float(low_1x_score),
            "low_pass_score_0_1": float(low_pass_score),
            "sideband_energy_score_0_1": float(sideband_energy_score),
            "axis_weight": float(axis_weight),
            "component_weight": float(component_weight),
        },
        "process_evidence_hits": process_hits,
        "limitations": limitations,
        "evidence": (
            f"{endpoint_id}/{axis}: cavitation score={score:.1f}, "
            f"HF={hf:.2f}, broadHF={broad_hf:.2f}, kurtosis={kurt:.2f}, "
            f"crest={crest:.2f}, 1x={amp_1x_ratio:.2f}xRMS{pass_text}, "
            f"temp_delta={temp_delta_c:.1f}C, process={process_text}"
        ),
    }


# ---------------------------------------------------------------------------
# DE-to-DE pair comparison
# ---------------------------------------------------------------------------


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

    return np.asarray(
        [
            v("hf_rms_ratio"),
            v("broad_hf_ratio"),
            max(v("kurtosis_excess"), 0.0),
            v("crest_factor"),
            v("sideband_energy_ratio"),
            v("noise_floor_ratio"),
            v("subsync_ratio"),
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
    if sides == {"driver", "driven_hydraulic"}:
        return 1.08, "driver_to_driven_hydraulic_de_pair"
    if "driven_hydraulic" in sides and "unknown" in sides:
        return 1.02, "hydraulic_to_unknown_de_pair"
    if sides == {"driven_hydraulic"}:
        return 1.07, "hydraulic_to_hydraulic_de_pair"
    return 0.88, "generic_de_pair"


def _best_de_pair_support(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            if not _same_shaft_compatible(left, right):
                continue

            similarity = _log_vector_similarity(_pair_vector(left), _pair_vector(right))
            left_score = float(left.get("score", 0.0))
            right_score = float(right.get("score", 0.0))
            min_score = min(left_score, right_score)
            avg_score = 0.5 * (left_score + right_score)
            pair_multiplier, pair_class = _de_pair_preference_multiplier(left, right)
            axis_factor = 1.0 if str(left.get("axis")) == str(right.get("axis")) else 0.94

            # For cavitation, similarity across DE points is useful, but the
            # driven hydraulic DE should still carry the diagnosis. Hence a
            # conservative pair score.
            pair_score = (0.60 * min_score + 0.40 * avg_score) * (0.55 + 0.45 * similarity) * pair_multiplier * axis_factor
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
        return {
            "available": False,
            "used": False,
            "reason": "DE endpoints exist, but no compatible same-shaft/same-speed pair was found.",
            "pair_score": 0.0,
            "similarity": 0.0,
        }
    return best


# ---------------------------------------------------------------------------
# Public detector
# ---------------------------------------------------------------------------


def detect_cavitation_or_aeration(
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
    process_evidence: Optional[Mapping[str, Any]] = None,
    competing_hydraulic_pass_score: Optional[float] = None,
    min_score: float = 20.0,
    target_tolerance_pct: float = 3.0,
    compare_de_endpoints: bool = True,
) -> Dict[str, Any]:
    """
    Detect possible cavitation/aeration from acceleration TWF.

    Parameters
    ----------
    acceleration_twf:
        Tri-axial acceleration time waveform.

        Supported shapes:
            {
              "motor_de": {"x": [...], "y": [...], "z": [...]},
              "pump_de": {"x": [...], "y": [...], "z": [...]}
            }

            or single endpoint:
            {"x": [...], "y": [...], "z": [...]}

            or numpy array shape [samples, 3], [3, samples], or [samples].

    sampling_frequency_hz:
        Sampling frequency of the acceleration TWF.

    rpm:
        Default running RPM. Endpoint or hydraulic local_rpm can override this.

    pass_count:
        Optional vane/blade count. This is not mandatory for cavitation/aeration,
        but improves separation from clean vane/blade-pass forcing.

    hydraulic_elements:
        Optional richer metadata for one or more hydraulic elements.

        Example:
            {"hydraulic_id": "pump_impeller", "pass_count": 6, "component_id": "pump", "local_rpm": 1485}

    endpoint_metadata:
        Optional endpoint metadata. Useful keys:
            endpoint_role: DE / NDE
            installed_on: bearing_housing / casing / pedestal / base / foundation
            component_type: motor / pump / fan / blower / compressor
            component_id
            hydraulic_id
            shaft_group_id
            is_coupling_end
            local_rpm

    process_evidence:
        Optional process corroboration, e.g.:
            {
              "low_npsh": True,
              "suction_pressure_low": True,
              "air_entrainment": False,
              "strainer_blocked": True,
              "off_design_flow": True,
            }

    competing_hydraulic_pass_score:
        Optional output score from the vane/blade-pass detector. If this is high
        and cavitation broadband evidence is weak, this function keeps the
        cavitation call conservative.

    Returns
    -------
    Dictionary with primary_fault, possible_faults, hydraulic_results,
    endpoint_results, and DE-pair support details.
    """
    fs_hz = float(sampling_frequency_hz)
    rpm = float(rpm)
    if fs_hz <= 0.0:
        raise ValueError("sampling_frequency_hz must be positive.")
    if rpm <= 0.0:
        raise ValueError("rpm must be positive.")

    endpoints = _normalize_triaxial_twf(acceleration_twf, axes=axes)
    hydraulics = _normalize_hydraulic_elements(pass_count=pass_count, hydraulic_elements=hydraulic_elements, rpm=rpm)
    process_score, process_hits = _process_evidence_score(process_evidence)

    endpoint_meta: Dict[str, Dict[str, Any]] = {
        endpoint_id: _endpoint_metadata(endpoint_metadata, endpoint_id)
        for endpoint_id in endpoints
    }

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
                    "broad_hf_ratio": features["broad_hf_ratio"],
                    "kurtosis_excess": features["kurtosis_excess"],
                    "crest_factor": features["crest_factor"],
                    "noise_floor_ratio": features["noise_floor_ratio"],
                    "amp_1x_ratio": features["amp_1x_ratio"],
                    "subsync_ratio": features["subsync_ratio"],
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
            temp_delta = _resolve_temperature_delta_c(
                endpoint_id=endpoint_id,
                surface_temperature_c=surface_temperature_c,
                baseline_temperature_c=baseline_temperature_c,
                temperature_delta_c=temperature_delta_c,
            )

            for axis_name in axis_map.keys():
                axis = _norm_axis_name(axis_name)
                features = feature_cache.get((endpoint_id, axis))
                if not features:
                    continue

                row = _score_cavitation_axis(
                    endpoint_id=endpoint_id,
                    axis=axis,
                    features=features,
                    meta=meta,
                    hydraulic=hydraulic,
                    temp_delta_c=temp_delta,
                    target_tolerance_pct=target_tolerance_pct,
                    process_score=process_score,
                    process_hits=process_hits,
                )
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
            endpoint_score = _clamp(
                0.74 * _top_mean(scores, n=3)
                + 10.0 * _score_linear(len(rows), 1.0, 3.0)
                + 8.0 * _score_linear(len(supporting_rows), 1.0, 3.0),
                0.0,
                100.0,
            )
            endpoint_summaries[endpoint_id] = {
                "fault": "cavitation_or_aeration",
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
        hydraulic_endpoint_support = [
            row for row in axis_rows
            if row.get("component_side") == "driven_hydraulic" and float(row.get("score", 0.0)) >= 35.0
        ]

        de_pair_support = _best_de_pair_support(axis_rows) if compare_de_endpoints else {
            "available": False,
            "used": False,
            "reason": "DE endpoint comparison disabled.",
            "pair_score": 0.0,
            "similarity": 0.0,
        }

        if axis_rows:
            best_axis_row = max(axis_rows, key=lambda row: float(row["score"]))
            base_score = _clamp(
                0.76 * _top_mean(axis_scores, n=3)
                + 14.0 * _score_linear(len(set(row["endpoint_id"] for row in axis_rows)), 1.0, 3.0)
                + 10.0 * _score_linear(len(supporting_axis_rows), 1.0, 4.0),
                0.0,
                100.0,
            )
        else:
            best_axis_row = None
            base_score = 0.0

        de_pair_boost = 0.0
        if de_pair_support.get("available"):
            boost_cap = 8.0
            de_pair_boost = boost_cap * _score_linear(float(de_pair_support.get("pair_score", 0.0)), 35.0, 75.0)

        process_boost = 4.0 * process_score
        score = _clamp(base_score + de_pair_boost + process_boost, 0.0, 100.0)

        mean_hf = _mean_or_zero([row["metrics"]["hf_rms_ratio"] for row in axis_rows])
        mean_kurt = _mean_or_zero([row["metrics"]["kurtosis_excess"] for row in axis_rows])
        mean_clean_pass = _mean_or_zero([row["metrics"]["clean_pass_indicator_0_1"] for row in axis_rows])
        mean_pass_ratio = _mean_or_zero([row["metrics"]["pass_ratio"] for row in axis_rows])
        mean_sideband_energy = _mean_or_zero([row["metrics"]["sideband_energy_ratio"] for row in axis_rows])

        limitations: List[str] = [
            "Best used together with process variables such as suction pressure, flow, NPSH margin, valve position and entrained-air checks.",
            "This detector identifies a cavitation/aeration vibration pattern; it does not directly prove the hydraulic root cause.",
        ]

        if hydraulic.get("pass_count") is None:
            limitations.append("No vane/blade count was supplied; separation from clean pass-frequency forcing is limited.")

        if not hydraulic_endpoint_support:
            score *= 0.68
            limitations.append("Reduced because no pump/fan/blower/compressor endpoint strongly supports the cavitation/aeration call.")

        if competing_hydraulic_pass_score is not None:
            pass_score = float(competing_hydraulic_pass_score)
            if pass_score >= 60.0 and mean_hf < 1.15 and mean_kurt < 0.9:
                score *= 0.72
                limitations.append(
                    "Reduced because a strong vane/blade-pass result is present while broadband cavitation evidence is limited."
                )

        if mean_clean_pass >= 0.70 and mean_sideband_energy < 0.45:
            score *= 0.76
            limitations.append(
                "Reduced because the mean pattern is closer to clean pass-frequency forcing than broadband cavitation/aeration."
            )

        if not de_pair_support.get("available"):
            limitations.append("No usable DE-to-DE same-shaft pair was available; result falls back to endpoint/axis aggregation.")

        score = _clamp(score, 0.0, 100.0)
        confidence_cap = "high"
        if hydraulic.get("pass_count") is None and not process_hits:
            confidence_cap = "medium"
        if not hydraulic_endpoint_support:
            confidence_cap = "medium"

        summary = {
            "fault": "cavitation_or_aeration",
            "label": "Cavitation / aeration hydraulic broadband distress",
            "scope": "hydraulic_local",
            "hydraulic_id": hydraulic_id,
            "pass_count": int(hydraulic["pass_count"]) if hydraulic.get("pass_count") is not None else None,
            "pass_hz": _hydraulic_pass_frequency_hz(float(hydraulic["local_rpm"]), hydraulic.get("pass_count")),
            "score": float(score),
            "base_score_before_de_pair": float(base_score),
            "de_pair_boost": float(de_pair_boost),
            "process_boost": float(process_boost),
            "confidence": _confidence_from_score(score, cap=confidence_cap),
            "possible": bool(score >= min_score),
            "best_endpoint": best_axis_row["endpoint_id"] if best_axis_row else None,
            "best_axis": best_axis_row["axis"] if best_axis_row else None,
            "best_axis_score": float(best_axis_row["score"]) if best_axis_row else 0.0,
            "supporting_endpoints": supporting_endpoint_ids,
            "supporting_axis_count": int(len(supporting_axis_rows)),
            "evidence": best_axis_row["evidence"] if best_axis_row else "",
            "limitations": limitations,
            "recommendations": [
                "Review suction pressure, NPSH margin, entrained air, suction leaks, strainers, valve position and minimum-flow protection.",
                "Inspect impeller, casing and wear-ring surfaces for pitting or erosion if the pattern persists.",
                "Trend the result against operating point because cavitation/aeration can appear or disappear with flow and suction conditions.",
            ],
            "de_pair_support": de_pair_support,
            "process_evidence_hits": process_hits,
            "metrics": {
                "mean_axis_score": _mean_or_zero(axis_scores),
                "top_axis_score": float(max(axis_scores)) if axis_scores else 0.0,
                "num_evaluated_axes": float(len(axis_rows)),
                "num_evaluated_endpoints": float(len(set(row["endpoint_id"] for row in axis_rows))),
                "num_supporting_axes": float(len(supporting_axis_rows)),
                "num_supporting_endpoints": float(len(supporting_endpoint_ids)),
                "num_hydraulic_endpoint_support_axes": float(len(hydraulic_endpoint_support)),
                "mean_hf_rms_ratio": float(mean_hf),
                "mean_kurtosis_excess": float(mean_kurt),
                "mean_crest_factor": _mean_or_zero([row["metrics"]["crest_factor"] for row in axis_rows]),
                "mean_broad_hf_ratio": _mean_or_zero([row["metrics"]["broad_hf_ratio"] for row in axis_rows]),
                "mean_noise_floor_ratio": _mean_or_zero([row["metrics"]["noise_floor_ratio"] for row in axis_rows]),
                "mean_1x_ratio": _mean_or_zero([row["metrics"]["amp_1x_ratio"] for row in axis_rows]),
                "mean_subsync_ratio": _mean_or_zero([row["metrics"]["subsync_ratio"] for row in axis_rows]),
                "mean_pass_ratio": float(mean_pass_ratio),
                "mean_sideband_energy_ratio": float(mean_sideband_energy),
                "mean_clean_pass_indicator": float(mean_clean_pass),
                "process_evidence_score_0_1": float(process_score),
                "de_pair_score": float(de_pair_support.get("pair_score", 0.0)),
                "de_pair_similarity": float(de_pair_support.get("similarity", 0.0)),
            },
        }

        hydraulic_results[hydraulic_id] = {
            "summary": summary,
            "endpoint_summaries": endpoint_summaries,
            "axis_rows": axis_rows,
        }
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
            "description": (
                "Compatible DE/coupling-end endpoints are compared as supporting evidence. "
                "For cavitation/aeration, the strongest evidence should normally come from the driven hydraulic endpoint; "
                "Motor DE or other DE points are treated as transmitted/coupled support."
            ),
        },
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "hydraulic_results": hydraulic_results,
        "endpoint_results": endpoint_results,
        "limitations": [
            "Cavitation/aeration is hydraulic-local and should be confirmed with process variables, not vibration alone.",
            "Acceleration broadband/high-frequency content, kurtosis and crest factor are the primary vibration evidence.",
            "If pass_count is supplied, clean pass-frequency dominance is used to keep cavitation separate from vane/blade-pass forcing.",
            "DE-to-DE comparison is a bounded support boost and is not required for detection.",
        ],
    }


__all__ = ["detect_cavitation_or_aeration"]
