
"""
Asset-wise rotating-machine diagnostics for triaxial vibration + surface temperature.

Design intent
-------------
This module is built for practical condition monitoring when you have:
- triaxial vibration sensors with surface temperature
- running RPM
- bearing geometry / bearing IDs
- gear tooth counts / stage metadata
- motor nameplate metadata
- no phase data

Core principles
---------------
1) Train / shaft faults are evaluated asset-wide using all relevant sensors.
2) Bearing, lubrication, gear and hydraulic faults are evaluated locally using only
   the most relevant nearby sensors.
3) Direction and mounting location matter. The same spectrum gets scored differently
   depending on axis and installation context.
4) Diagnoses that normally rely on phase are confidence-capped when phase is absent.

The module is intentionally rule-based and transparent. It is designed to be edited
and adapted plant-by-plant rather than treated as a black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import numpy as np
from scipy.signal import butter, detrend, filtfilt, hilbert
from scipy.stats import kurtosis
from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    if abs(den) <= 1e-12:
        return default
    return float(num / den)


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _score_linear(value: float, low: float, high: float) -> float:
    """Map value onto 0..1 with a simple linear ramp."""
    if high <= low:
        return 1.0 if value >= high else 0.0
    return _clamp((value - low) / (high - low), 0.0, 1.0)


def _peak_at(freqs_hz: np.ndarray, amplitudes: np.ndarray, target_hz: float, tolerance_hz: float) -> Tuple[float, float]:
    if target_hz <= 0.0 or freqs_hz.size == 0 or amplitudes.size == 0:
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


def _peak_amplitudes_at_targets(
    freqs_hz: np.ndarray,
    amplitudes: np.ndarray,
    targets_hz: Mapping[str, float],
    tolerance_hz: float,
) -> Dict[str, float]:
    peaks: Dict[str, float] = {}
    if freqs_hz.size == 0 or amplitudes.size == 0:
        return {name: 0.0 for name in targets_hz}
    for name, target_hz in targets_hz.items():
        if target_hz <= 0.0:
            peaks[name] = 0.0
            continue
        lo = int(np.searchsorted(freqs_hz, target_hz - tolerance_hz, side="left"))
        hi = int(np.searchsorted(freqs_hz, target_hz + tolerance_hz, side="right"))
        peaks[name] = float(np.max(amplitudes[lo:hi])) if hi > lo else 0.0
    return peaks


def _peak_in_band(freqs_hz: np.ndarray, amplitudes: np.ndarray, low_hz: float, high_hz: float) -> Tuple[float, float]:
    if high_hz <= low_hz:
        return 0.0, 0.0
    mask = (freqs_hz >= low_hz) & (freqs_hz <= high_hz)
    if not np.any(mask):
        return 0.0, 0.0
    local_freqs = freqs_hz[mask]
    local_amps = amplitudes[mask]
    idx = int(np.argmax(local_amps))
    return float(local_freqs[idx]), float(local_amps[idx])


def _rms(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(values ** 2)))


def _crest_factor(time_waveform: Optional[np.ndarray]) -> float:
    if time_waveform is None or time_waveform.size == 0:
        return 0.0
    rms = _rms(time_waveform)
    return float(np.max(np.abs(time_waveform)) / rms) if rms > 0 else 0.0


def _kurtosis_excess(time_waveform: Optional[np.ndarray]) -> float:
    if time_waveform is None or time_waveform.size == 0:
        return 0.0
    std = float(np.std(time_waveform))
    if std <= 0.0:
        return 0.0
    norm = (time_waveform - np.mean(time_waveform)) / std
    return float(np.mean(norm ** 4) - 3.0)


def _waveform_sample_rate_hz(signal: "AxisSignal") -> float:
    if getattr(signal, "waveform_sample_rate_hz", None):
        return float(signal.waveform_sample_rate_hz)
    freqs = np.asarray(signal.freqs_hz, dtype=float).reshape(-1)
    positive = freqs[freqs > 0.0]
    if positive.size >= 2:
        return float(2.0 * np.max(positive))
    return 0.0


def _waveform_array(signal: "AxisSignal", kind: str) -> Optional[np.ndarray]:
    if kind == "velocity":
        source = signal.velocity_waveform if signal.velocity_waveform is not None else signal.waveform
    elif kind == "acceleration":
        source = signal.acceleration_waveform if signal.acceleration_waveform is not None else signal.waveform
    else:
        source = signal.waveform
    if source is None:
        return None
    arr = np.asarray(source, dtype=float).reshape(-1)
    return arr if arr.size >= 16 else None


def _best_autocorr_near_lag(x: np.ndarray, lag: int, window_pct: float = 0.18) -> float:
    if lag < 1 or x.size < lag + 8:
        return 0.0
    centered = x - np.mean(x)
    std = float(np.std(centered))
    if std <= 1e-12:
        return 0.0
    centered = centered / std
    ac = np.correlate(centered, centered, mode="full")[centered.size - 1 :]
    if ac.size == 0 or ac[0] <= 1e-12:
        return 0.0
    ac = ac / ac[0]
    lo = max(1, int(lag * (1.0 - window_pct)))
    hi = min(ac.size, int(lag * (1.0 + window_pct)) + 1)
    if hi <= lo:
        return 0.0
    return _clamp(float(np.max(ac[lo:hi])), 0.0, 1.0)


def _waveform_shape_metrics(signal: "AxisSignal", shaft_hz: float) -> Tuple[float, float, float]:
    fs = _waveform_sample_rate_hz(signal)
    wf_1x_pulse = 0.0
    wf_2x_pulse = 0.0
    wf_impact_periodicity = 0.0

    velocity_waveform = _waveform_array(signal, "velocity")
    if velocity_waveform is not None and fs > 0.0 and shaft_hz > 0.0:
        pulse_series = np.abs(velocity_waveform - np.mean(velocity_waveform))
        wf_1x_pulse = _best_autocorr_near_lag(pulse_series, int(round(fs / shaft_hz)))
        wf_2x_pulse = _best_autocorr_near_lag(pulse_series, int(round(fs / (2.0 * shaft_hz))))

    accel_waveform = _waveform_array(signal, "acceleration")
    if accel_waveform is not None:
        impact_series = np.abs(np.diff(accel_waveform, prepend=accel_waveform[0]))
        centered = impact_series - np.mean(impact_series)
        std = float(np.std(centered))
        if std > 1e-12:
            centered = centered / std
            ac = np.correlate(centered, centered, mode="full")[centered.size - 1 :]
            if ac.size > 1 and ac[0] > 1e-12:
                ac = ac / ac[0]
                start = max(1, int(0.03 * ac.size))
                if start < ac.size:
                    wf_impact_periodicity = _clamp(float(math.sqrt(max(0.0, np.max(ac[start:])))), 0.0, 1.0)

    return wf_1x_pulse, wf_2x_pulse, wf_impact_periodicity


def _distinct_count(items: Iterable[str]) -> int:
    return len({x for x in items if x})


def _top_mean(values: List[float], n: int = 3) -> float:
    good = sorted([float(v) for v in values if v is not None], reverse=True)
    if not good:
        return 0.0
    return float(mean(good[: min(n, len(good))]))


def _mean_or_zero(values: List[float]) -> float:
    good = [float(v) for v in values if v is not None]
    return float(mean(good)) if good else 0.0


def _cap_confidence(confidence: str, cap: str) -> str:
    if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[cap]:
        return cap
    return confidence


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AxisSignal:
    axis: str  # "horizontal", "vertical", "axial"
    # Backward-compatible default spectrum. After the domain-separated patch runs,
    # this is normalized to the velocity spectrum for shaft/order diagnostics.
    freqs_hz: List[float]
    spectrum: List[float]
    spectrum_kind: str = "auto"  # auto / velocity / acceleration

    # Optional explicit spectra. Use these when available.
    velocity_freqs_hz: Optional[List[float]] = None
    velocity_spectrum: Optional[List[float]] = None
    acceleration_freqs_hz: Optional[List[float]] = None
    acceleration_spectrum: Optional[List[float]] = None

    waveform: Optional[List[float]] = None
    velocity_waveform: Optional[List[float]] = None
    acceleration_waveform: Optional[List[float]] = None
    waveform_sample_rate_hz: Optional[float] = None
    envelope_freqs_hz: Optional[List[float]] = None
    envelope_spectrum: Optional[List[float]] = None
    overall_velocity_mm_s: Optional[float] = None
    overall_acceleration_g: Optional[float] = None


@dataclass
class SensorMeasurement:
    sensor_id: str
    component_id: str
    component_type: str  # motor / pump / fan / gearbox / bearing_housing / base / foundation / driven
    location_tag: str    # e.g. motor_de, motor_nde, pump_de, gearbox_inboard
    installed_on: str    # bearing_housing / casing / pedestal / base / foundation
    directions: Dict[str, AxisSignal]
    surface_temperature_c: Optional[float] = None
    bearing_id: Optional[str] = None
    gear_stage_id: Optional[str] = None
    coupling_id: Optional[str] = None
    rotor_id: Optional[str] = None
    local_rpm: Optional[float] = None
    is_coupling_end: bool = False
    is_local_to_thrust: bool = False
    notes: str = ""


@dataclass
class BearingDefinition:
    bearing_id: str
    component_id: str
    bearing_type: str = "rolling"   # rolling / fluid_film / thrust
    fault_frequencies_hz: Dict[str, float] = field(default_factory=dict)
    bpfo_hz: Optional[float] = None
    bpfi_hz: Optional[float] = None
    bsf_hz: Optional[float] = None
    ftf_hz: Optional[float] = None
    fault_frequency_orders: Dict[str, float] = field(default_factory=dict)
    bpfo: Optional[float] = None
    bpfi: Optional[float] = None
    bsf: Optional[float] = None
    ftf: Optional[float] = None
    rolling_elements: Optional[int] = None
    ball_diameter_mm: Optional[float] = None
    pitch_diameter_mm: Optional[float] = None
    contact_angle_deg: float = 0.0
    is_thrust_bearing: bool = False


@dataclass
class GearStageDefinition:
    gear_stage_id: str
    component_id: str
    driver_teeth: int
    driven_teeth: int
    stage_input_rpm: Optional[float] = None
    stage_output_rpm: Optional[float] = None


@dataclass
class HydraulicElementDefinition:
    hydraulic_id: str
    component_id: str
    pass_count: int           # vane count / blade count
    kind: str = "vane_pass"
    local_rpm: Optional[float] = None


@dataclass
class MotorDefinition:
    component_id: str
    line_frequency_hz: float = 50.0
    poles: int = 4
    slip_pct: float = 0.0


@dataclass
class AssetDefinition:
    asset_id: str
    asset_type: str
    running_rpm: float
    sensors: List[SensorMeasurement]
    bearings: List[BearingDefinition] = field(default_factory=list)
    gear_stages: List[GearStageDefinition] = field(default_factory=list)
    belt_drives: List['BeltDriveDefinition'] = field(default_factory=list)
    hydraulic_elements: List[HydraulicElementDefinition] = field(default_factory=list)
    motors: List[MotorDefinition] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class AxisFeatures:
    axis: str
    shaft_hz: float
    tolerance_hz: float
    amp_05x: float
    amp_1x: float
    amp_2x: float
    amp_3x: float
    amp_35x: float
    amp_4x: float
    amp_5x: float
    amp_6x: float
    amp_7x: float
    amp_8x: float
    amp_9x: float
    amp_10x: float
    amp_15x: float
    amp_25x: float
    dominant_freq_hz: float
    dominant_amp: float
    subsync_freq_hz: float
    subsync_amp: float
    rms_spectrum: float
    crest_factor: float
    kurtosis: float
    hf_rms_ratio: float
    noise_floor: float
    wf_1x_pulse: float
    wf_2x_pulse: float
    wf_impact_periodicity: float
    envelope_rms: float = 0.0

    @property
    def dominant_order(self) -> float:
        return _safe_ratio(self.dominant_freq_hz, self.shaft_hz)

    def amp_ratio(self, amp: float) -> float:
        return _safe_ratio(amp, self.rms_spectrum)


@dataclass
class FaultResult:
    fault_key: str
    target: str
    scope: str
    score: float
    confidence: str
    sensors_used: List[str]
    evidence: List[str]
    limitations: List[str]
    supporting_metrics: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    urgency: str = "monitor"
    diagnostic_segment: str = "secondary"
    condition_health: Optional[float] = None
    condition_abnormality: Optional[float] = None
    condition_alarm: Optional[str] = None
    condition_confidence: Optional[float] = None
    family_subscore: Optional[float] = None
    fault_severity_score: Optional[float] = None
    fault_severity_label: Optional[str] = None
    fault_explanation: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternFamilyProfile:
    synchronous_score: float
    harmonic_score: float
    subsynchronous_score: float
    modulation_score: float
    broadband_score: float
    radial_bias: float
    axial_bias: float
    mixed_bias: float
    dominant_family: str
    dominant_direction: str
    evidence: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "synchronous_score": self.synchronous_score,
            "harmonic_score": self.harmonic_score,
            "subsynchronous_score": self.subsynchronous_score,
            "modulation_score": self.modulation_score,
            "broadband_score": self.broadband_score,
            "radial_bias": self.radial_bias,
            "axial_bias": self.axial_bias,
            "mixed_bias": self.mixed_bias,
            "dominant_family": self.dominant_family,
            "dominant_direction": self.dominant_direction,
            "evidence": list(self.evidence),
            "metrics": dict(self.metrics),
        }


# ---------------------------------------------------------------------------
# Fault library and scope rules
# ---------------------------------------------------------------------------


FAULT_LIBRARY: Dict[str, Dict[str, object]] = {
    "unbalance": {"scope": "asset_wide", "phase_cap": "high"},
    "misalignment": {"scope": "asset_wide", "phase_cap": "medium"},
    "looseness_type_a_base_structure": {"scope": "asset_wide", "phase_cap": "medium"},
    "looseness_type_b_pedestal_support": {"scope": "asset_wide", "phase_cap": "medium"},
    "looseness_type_c_rotating_fit": {"scope": "asset_wide", "phase_cap": "medium"},
    "soft_foot_or_frame_distortion": {"scope": "asset_wide", "phase_cap": "medium"},
    "bent_shaft_or_bow": {"scope": "asset_wide", "phase_cap": "medium"},
    "resonance_or_structural_amplification": {"scope": "asset_wide", "phase_cap": "medium"},
    "rotor_rub": {"scope": "asset_wide", "phase_cap": "medium"},
    "motor_electrical_forcing": {"scope": "asset_wide", "phase_cap": "low"},
    "lubrication_distress": {"scope": "bearing_local", "phase_cap": "high"},
    "bearing_bpfo": {"scope": "bearing_local", "phase_cap": "high"},
    "bearing_bpfi": {"scope": "bearing_local", "phase_cap": "high"},
    "bearing_bsf": {"scope": "bearing_local", "phase_cap": "high"},
    "bearing_ftf": {"scope": "bearing_local", "phase_cap": "high"},
    "fluid_film_instability": {"scope": "bearing_local", "phase_cap": "high"},
    "thrust_bearing_or_axial_overload": {"scope": "bearing_local", "phase_cap": "medium"},
    "gear_mesh_fault": {"scope": "gear_local", "phase_cap": "high"},
    "hydraulic_vane_or_blade_pass": {"scope": "hydraulic_local", "phase_cap": "high"},
    "cavitation_or_aeration": {"scope": "hydraulic_local", "phase_cap": "high"},
}

CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# Frequency calculators
# ---------------------------------------------------------------------------


def shaft_hz_from_rpm(rpm: float) -> float:
    return float(rpm) / 60.0


def bearing_fault_frequencies_hz(rpm: float, bearing: BearingDefinition) -> Dict[str, float]:
    """
    Rolling-element bearing defect frequencies.
    Uses directly supplied Hz values when available. Otherwise it accepts the
    application's BearingDetailMaster-style order values (bpfo/bpfi/bsf/ftf)
    and converts them with RPM. Geometry remains a final fallback.
    """
    if bearing.bearing_type != "rolling":
        return {}

    def _valid_positive_float(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0.0 else None

    direct_freqs: Dict[str, float] = {}
    for key in ("bpfo", "bpfi", "bsf", "ftf"):
        direct_value = _valid_positive_float(getattr(bearing, f"{key}_hz", None))
        if direct_value is not None:
            direct_freqs[key] = direct_value
    for raw_key, raw_value in (bearing.fault_frequencies_hz or {}).items():
        key = str(raw_key).strip().lower()
        direct_value = _valid_positive_float(raw_value)
        if key in {"bpfo", "bpfi", "bsf", "ftf"} and direct_value is not None:
            direct_freqs[key] = direct_value
    if direct_freqs:
        return {key: direct_freqs[key] for key in ("ftf", "bpfo", "bpfi", "bsf") if key in direct_freqs}

    order_freqs: Dict[str, float] = {}
    shaft_hz = shaft_hz_from_rpm(rpm)
    if shaft_hz > 0.0:
        for key in ("bpfo", "bpfi", "bsf", "ftf"):
            order_value = _valid_positive_float(getattr(bearing, key, None))
            if order_value is not None:
                multiplier = 2.0 if key == "bsf" else 1.0
                order_freqs[key] = order_value * shaft_hz * multiplier
        for raw_key, raw_value in (bearing.fault_frequency_orders or {}).items():
            key = str(raw_key).strip().lower()
            order_value = _valid_positive_float(raw_value)
            if key in {"bpfo", "bpfi", "bsf", "ftf"} and order_value is not None:
                multiplier = 2.0 if key == "bsf" else 1.0
                order_freqs[key] = order_value * shaft_hz * multiplier
    if order_freqs:
        return {key: order_freqs[key] for key in ("ftf", "bpfo", "bpfi", "bsf") if key in order_freqs}

    if not all([bearing.rolling_elements, bearing.ball_diameter_mm, bearing.pitch_diameter_mm]):
        return {}
    n = float(bearing.rolling_elements)
    bd = float(bearing.ball_diameter_mm)
    pd = float(bearing.pitch_diameter_mm)
    theta = math.radians(float(bearing.contact_angle_deg or 0.0))
    fr = shaft_hz_from_rpm(rpm)
    ratio = (bd / pd) * math.cos(theta)
    ftf = 0.5 * fr * (1.0 - ratio)
    bpfo = 0.5 * n * fr * (1.0 - ratio)
    bpfi = 0.5 * n * fr * (1.0 + ratio)
    bsf = 0.5 * (pd / bd) * fr * (1.0 - ratio ** 2)
    return {"ftf": ftf, "bpfo": bpfo, "bpfi": bpfi, "bsf": bsf}


def gear_mesh_frequency_hz(input_rpm: float, stage: GearStageDefinition) -> float:
    return shaft_hz_from_rpm(input_rpm) * float(stage.driver_teeth)


def hydraulic_pass_frequency_hz(rpm: float, hydraulic: HydraulicElementDefinition) -> float:
    return shaft_hz_from_rpm(rpm) * float(hydraulic.pass_count)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_axis_features(signal: AxisSignal, rpm: float, tolerance_pct: float = 3.0) -> AxisFeatures:
    freqs = np.asarray(signal.freqs_hz, dtype=float).reshape(-1)
    amps = np.asarray(signal.spectrum, dtype=float).reshape(-1)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        raise ValueError(f"Bad spectrum for axis {signal.axis!r}")
    positive = freqs > 0.0
    freqs = freqs[positive]
    amps = amps[positive]
    if freqs.size == 0:
        raise ValueError(f"No positive frequencies for axis {signal.axis!r}")
    if freqs.size > 1 and np.any(np.diff(freqs) < 0.0):
        order = np.argsort(freqs)
        freqs = freqs[order]
        amps = amps[order]

    shaft_hz = shaft_hz_from_rpm(rpm)
    freq_res = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(shaft_hz * 0.03, 0.1)
    tolerance_hz = max(abs(shaft_hz) * tolerance_pct / 100.0, 1.5 * freq_res)
    noise_floor = float(np.median(np.abs(amps)))
    dominant_idx = int(np.argmax(amps))
    dominant_freq_hz = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])

    hf_start = max(5.0 * shaft_hz, 50.0 if freqs[-1] >= 100.0 else 3.0 * shaft_hz)
    hf_mask = freqs >= hf_start
    rms_spectrum = _rms(amps)
    hf_rms_ratio = _safe_ratio(_rms(amps[hf_mask]) if np.any(hf_mask) else 0.0, rms_spectrum)

    harmonic_peaks = _peak_amplitudes_at_targets(
        freqs,
        amps,
        {
            "amp_05x": 0.5 * shaft_hz,
            "amp_1x": 1.0 * shaft_hz,
            "amp_15x": 1.5 * shaft_hz,
            "amp_2x": 2.0 * shaft_hz,
            "amp_25x": 2.5 * shaft_hz,
            "amp_3x": 3.0 * shaft_hz,
            "amp_35x": 3.5 * shaft_hz,
            "amp_4x": 4.0 * shaft_hz,
            "amp_5x": 5.0 * shaft_hz,
            "amp_6x": 6.0 * shaft_hz,
            "amp_7x": 7.0 * shaft_hz,
            "amp_8x": 8.0 * shaft_hz,
            "amp_9x": 9.0 * shaft_hz,
            "amp_10x": 10.0 * shaft_hz,
        },
        tolerance_hz,
    )

    subsync_freq_hz, subsync_amp = _peak_in_band(freqs, amps, 0.42 * shaft_hz, 0.48 * shaft_hz)
    waveform_for_impacts = _waveform_array(signal, "acceleration")
    if waveform_for_impacts is None:
        waveform_for_impacts = _waveform_array(signal, "generic")
    wf_1x_pulse, wf_2x_pulse, wf_impact_periodicity = _waveform_shape_metrics(signal, shaft_hz)
    envelope_rms = _rms(np.asarray(signal.envelope_spectrum, dtype=float)) if signal.envelope_spectrum is not None else 0.0

    return AxisFeatures(
        axis=signal.axis.lower(),
        shaft_hz=shaft_hz,
        tolerance_hz=tolerance_hz,
        amp_05x=harmonic_peaks["amp_05x"],
        amp_1x=harmonic_peaks["amp_1x"],
        amp_2x=harmonic_peaks["amp_2x"],
        amp_3x=harmonic_peaks["amp_3x"],
        amp_35x=harmonic_peaks["amp_35x"],
        amp_4x=harmonic_peaks["amp_4x"],
        amp_5x=harmonic_peaks["amp_5x"],
        amp_6x=harmonic_peaks["amp_6x"],
        amp_7x=harmonic_peaks["amp_7x"],
        amp_8x=harmonic_peaks["amp_8x"],
        amp_9x=harmonic_peaks["amp_9x"],
        amp_10x=harmonic_peaks["amp_10x"],
        amp_15x=harmonic_peaks["amp_15x"],
        amp_25x=harmonic_peaks["amp_25x"],
        dominant_freq_hz=dominant_freq_hz,
        dominant_amp=dominant_amp,
        subsync_freq_hz=subsync_freq_hz,
        subsync_amp=subsync_amp,
        rms_spectrum=rms_spectrum,
        crest_factor=_crest_factor(waveform_for_impacts),
        kurtosis=_kurtosis_excess(waveform_for_impacts),
        hf_rms_ratio=hf_rms_ratio,
        noise_floor=noise_floor,
        wf_1x_pulse=wf_1x_pulse,
        wf_2x_pulse=wf_2x_pulse,
        wf_impact_periodicity=wf_impact_periodicity,
        envelope_rms=envelope_rms,
    )


def envelope_harmonic_hit_score(
    signal: AxisSignal,
    target_hz: float,
    tolerance_hz: float,
    harmonics: int = 4,
) -> Tuple[float, int]:
    if target_hz <= 0.0 or signal.envelope_freqs_hz is None or signal.envelope_spectrum is None:
        return 0.0, 0
    freqs = np.asarray(signal.envelope_freqs_hz, dtype=float).reshape(-1)
    amps = np.asarray(signal.envelope_spectrum, dtype=float).reshape(-1)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        return 0.0, 0

    rms = _rms(amps)
    hits = 0
    strengths: List[float] = []
    for order in range(1, harmonics + 1):
        _, amp = _peak_at(freqs, amps, order * target_hz, tolerance_hz)
        score = _score_linear(_safe_ratio(amp, rms), 1.1, 4.0)
        if score > 0.2:
            hits += 1
        strengths.append(score)
    total = 100.0 * (0.65 * (_top_mean(strengths, n=3)) + 0.35 * _score_linear(hits, 1.0, float(harmonics)))
    return float(total), hits


# ---------------------------------------------------------------------------
# Sensor / axis weighting
# ---------------------------------------------------------------------------


def _axis_weight(fault_key: str, sensor: SensorMeasurement, axis_name: str) -> float:
    axis = axis_name.lower()
    is_axial = axis == "axial"
    is_radial = axis in {"horizontal", "vertical", "radial"}

    base = 1.0
    if fault_key == "unbalance":
        base = 1.0 if is_radial else 0.35
    elif fault_key == "misalignment":
        base = 1.0 if is_axial else 0.65
    elif fault_key == "looseness_type_a_base_structure":
        base = 1.0 if is_radial else 0.55
    elif fault_key == "looseness_type_b_pedestal_support":
        base = 1.0 if is_radial else 0.75
    elif fault_key == "looseness_type_c_rotating_fit":
        base = 1.0 if is_radial else 0.70
    elif fault_key == "soft_foot_or_frame_distortion":
        base = 0.9 if is_radial else 0.45
    elif fault_key == "bent_shaft_or_bow":
        base = 1.0 if is_axial else 0.5
    elif fault_key == "resonance_or_structural_amplification":
        base = 1.0
    elif fault_key == "rotor_rub":
        base = 1.0 if is_radial else 0.8
    elif fault_key == "motor_electrical_forcing":
        base = 0.9 if is_radial else 0.7
    elif fault_key in {"lubrication_distress", "bearing_bpfo", "bearing_bpfi", "bearing_bsf", "bearing_ftf", "fluid_film_instability"}:
        base = 1.0 if is_radial else 0.75
    elif fault_key == "thrust_bearing_or_axial_overload":
        base = 1.0 if is_axial else 0.45
    elif fault_key == "gear_mesh_fault":
        base = 1.0 if is_radial else 0.6
    elif fault_key == "hydraulic_vane_or_blade_pass":
        base = 1.0 if is_radial else 0.55
    elif fault_key == "cavitation_or_aeration":
        base = 1.0 if is_radial else 0.6

    if sensor.installed_on in {"base", "foundation"}:
        if fault_key in {"looseness_type_a_base_structure", "soft_foot_or_frame_distortion", "resonance_or_structural_amplification"}:
            base *= 1.15
        elif fault_key in {"looseness_type_b_pedestal_support", "looseness_type_c_rotating_fit"}:
            base *= 0.82
        else:
            base *= 0.7

    if sensor.is_coupling_end and fault_key in {"misalignment", "coupling_problem"}:
        base *= 1.15

    if sensor.is_local_to_thrust and fault_key == "thrust_bearing_or_axial_overload":
        base *= 1.2

    return float(base)


def _component_weight(fault_key: str, sensor: SensorMeasurement) -> float:
    ctype = sensor.component_type.lower()
    installed = sensor.installed_on.lower()
    if fault_key == "motor_electrical_forcing":
        return 1.1 if ctype == "motor" else 0.2
    if fault_key == "gear_mesh_fault":
        return 1.1 if ctype == "gearbox" or sensor.gear_stage_id else 0.2
    if fault_key in {"hydraulic_vane_or_blade_pass", "cavitation_or_aeration"}:
        return 1.1 if ctype in {"pump", "fan", "blower", "compressor"} else 0.35
    if fault_key in {"lubrication_distress", "bearing_bpfo", "bearing_bpfi", "bearing_bsf", "bearing_ftf", "fluid_film_instability", "thrust_bearing_or_axial_overload"}:
        return 1.1 if installed == "bearing_housing" or sensor.bearing_id else 0.35
    if fault_key in {"soft_foot_or_frame_distortion", "looseness_type_a_base_structure", "resonance_or_structural_amplification"} and installed in {"base", "foundation"}:
        return 1.1
    if fault_key == "looseness_type_b_pedestal_support" and installed in {"pedestal", "bearing_housing", "casing"}:
        return 1.08
    if fault_key == "looseness_type_c_rotating_fit" and installed in {"bearing_housing", "casing", "pedestal"}:
        return 1.10
    return 1.0


def _selected_scope_sensors(asset: AssetDefinition, fault_key: str, bearing_id: Optional[str] = None, gear_stage_id: Optional[str] = None, hydraulic_id: Optional[str] = None) -> List[SensorMeasurement]:
    scope = FAULT_LIBRARY[fault_key]["scope"]

    if scope == "asset_wide":
        selected: List[SensorMeasurement] = []
        for s in asset.sensors:
            if fault_key == "motor_electrical_forcing" and s.component_type.lower() != "motor":
                continue
            selected.append(s)
        return selected

    if scope == "bearing_local":
        component_id = next((b.component_id for b in asset.bearings if b.bearing_id == bearing_id), "")
        direct = [s for s in asset.sensors if bearing_id and s.bearing_id == bearing_id]
        if direct:
            anchor_tags = {s.location_tag for s in direct if s.location_tag}
            selected = list(direct)
            for s in asset.sensors:
                if s in selected or s.component_id != component_id:
                    continue
                if s.installed_on.lower() not in {"bearing_housing", "pedestal", "casing"}:
                    continue
                if not anchor_tags or s.location_tag in anchor_tags:
                    selected.append(s)
            return selected
        return [
            s for s in asset.sensors
            if s.component_id == component_id and s.installed_on.lower() in {"bearing_housing", "pedestal", "casing"}
        ]

    if scope == "gear_local":
        component_id = next((g.component_id for g in asset.gear_stages if g.gear_stage_id == gear_stage_id), None)
        selected = []
        for s in asset.sensors:
            if gear_stage_id and s.gear_stage_id == gear_stage_id:
                selected.append(s)
            elif component_id and s.component_id == component_id:
                selected.append(s)
        if selected:
            return selected
        return [s for s in asset.sensors if s.component_type.lower() == "gearbox"]

    if scope == "hydraulic_local":
        component_id = next((h.component_id for h in asset.hydraulic_elements if h.hydraulic_id == hydraulic_id), None)
        selected = [s for s in asset.sensors if component_id and s.component_id == component_id]
        if selected:
            return selected
        return [s for s in asset.sensors if s.component_type.lower() in {"pump", "fan", "blower", "compressor"}]

    return list(asset.sensors)


def _temperature_delta_c(asset: AssetDefinition, sensor: SensorMeasurement) -> float:
    if sensor.surface_temperature_c is None:
        return 0.0

    local_peers = [
        s.surface_temperature_c
        for s in asset.sensors
        if s.sensor_id != sensor.sensor_id
        and s.surface_temperature_c is not None
        and s.component_id == sensor.component_id
    ]
    same_mount_peers = [
        s.surface_temperature_c
        for s in asset.sensors
        if s.sensor_id != sensor.sensor_id
        and s.surface_temperature_c is not None
        and s.component_id == sensor.component_id
        and s.installed_on.lower() == sensor.installed_on.lower()
    ]
    asset_peers = [s.surface_temperature_c for s in asset.sensors if s.surface_temperature_c is not None]

    if same_mount_peers:
        base = float(median(same_mount_peers))
    elif local_peers:
        base = float(median(local_peers))
    elif asset_peers:
        base = float(median(asset_peers))
    else:
        return 0.0
    return float(sensor.surface_temperature_c - base)


@dataclass
class AnalysisContext:
    axis_features_by_sensor: Dict[str, Dict[str, AxisFeatures]]


def _build_analysis_context(asset: AssetDefinition) -> AnalysisContext:
    axis_features_by_sensor: Dict[str, Dict[str, AxisFeatures]] = {}
    for sensor in asset.sensors:
        local_rpm = sensor.local_rpm or asset.running_rpm
        axis_features_by_sensor[sensor.sensor_id] = {
            axis_name.lower(): extract_axis_features(signal, local_rpm)
            for axis_name, signal in sensor.directions.items()
        }
    return AnalysisContext(axis_features_by_sensor=axis_features_by_sensor)


def _get_analysis_context(asset: AssetDefinition, refresh: bool = False) -> AnalysisContext:
    key = "_analysis_context"
    if refresh or key not in asset.metadata:
        asset.metadata[key] = _build_analysis_context(asset)
    ctx = asset.metadata[key]
    if not isinstance(ctx, AnalysisContext):
        ctx = _build_analysis_context(asset)
        asset.metadata[key] = ctx
    return ctx


def _axis_features_for_sensor(sensor: SensorMeasurement, default_rpm: float) -> Dict[str, AxisFeatures]:
    local_rpm = sensor.local_rpm or default_rpm
    result: Dict[str, AxisFeatures] = {}
    for axis_name, signal in sensor.directions.items():
        result[axis_name.lower()] = extract_axis_features(signal, local_rpm)
    return result


def _axis_features_for_sensor_cached(asset: AssetDefinition, sensor: SensorMeasurement) -> Dict[str, AxisFeatures]:
    ctx = _get_analysis_context(asset)
    return ctx.axis_features_by_sensor.get(sensor.sensor_id, {})


def _aggregate_global(scores: List[float], sensor_ids: List[str]) -> float:
    if not scores:
        return 0.0
    top = _top_mean(scores, n=4)
    coverage = 20.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 4.0)
    repeatability = 15.0 * _score_linear(sum(1 for s in scores if s >= 45.0), 1.0, 4.0)
    return float(_clamp(0.65 * top + coverage + repeatability, 0.0, 100.0))


def _confidence_from_score(score: float, cap: str) -> str:
    conf = "none"
    if score >= 70.0:
        conf = "high"
    elif score >= 45.0:
        conf = "medium"
    elif score >= 20.0:
        conf = "low"
    if CONFIDENCE_ORDER[conf] > CONFIDENCE_ORDER[cap]:
        return cap
    return conf



def _order_lock_score(order: float) -> float:
    if order <= 0.0:
        return 0.0
    candidates = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    min_delta = min(abs(order - c) for c in candidates)
    return 1.0 - _clamp(min_delta / 0.18, 0.0, 1.0)


def _sideband_pair_ratio(signal: AxisSignal, center_hz: float, spacing_hz: float, tolerance_hz: float) -> float:
    if center_hz <= 0.0 or spacing_hz <= 0.0:
        return 0.0
    freqs = np.asarray(signal.freqs_hz, dtype=float).reshape(-1)
    amps = np.asarray(signal.spectrum, dtype=float).reshape(-1)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        return 0.0
    positive = freqs > 0.0
    freqs = freqs[positive]
    amps = amps[positive]
    if freqs.size == 0:
        return 0.0
    _, center_amp = _peak_at(freqs, amps, center_hz, tolerance_hz)
    if center_amp <= 1e-12:
        return 0.0
    _, left_amp = _peak_at(freqs, amps, center_hz - spacing_hz, tolerance_hz)
    _, right_amp = _peak_at(freqs, amps, center_hz + spacing_hz, tolerance_hz)
    return _safe_ratio(0.5 * (left_amp + right_amp), center_amp)


def _pattern_classifier_axis_scores(
    asset: AssetDefinition,
    sensor: SensorMeasurement,
    axis_name: str,
    feat: AxisFeatures,
) -> Dict[str, float]:
    signal = sensor.directions[axis_name]
    shaft_hz = feat.shaft_hz
    one_x_ratio = feat.amp_ratio(feat.amp_1x)
    harmonic_ratio = feat.amp_ratio(
        feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x + feat.amp_6x + feat.amp_7x + feat.amp_8x + feat.amp_9x + feat.amp_10x
    )
    fractional_ratio = feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x + feat.amp_35x)
    order_lock = _order_lock_score(feat.dominant_order)
    synchronous = 100.0 * (
        0.45 * _score_linear(one_x_ratio, 0.7, 3.5) +
        0.25 * _score_linear(order_lock, 0.55, 0.95) +
        0.15 * (1.0 - _score_linear(fractional_ratio, 0.7, 2.8)) +
        0.15 * (1.0 - _score_linear(feat.hf_rms_ratio, 0.18, 0.75))
    )
    harmonic = 100.0 * (
        0.45 * _score_linear(harmonic_ratio, 0.8, 5.8) +
        0.20 * _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x), 0.6, 4.0) +
        0.20 * _score_linear(order_lock, 0.55, 0.95) +
        0.15 * (1.0 - _score_linear(feat.hf_rms_ratio, 0.18, 0.75))
    )
    subsynchronous = 100.0 * (
        0.45 * _score_linear(feat.amp_ratio(feat.subsync_amp), 0.12, 1.2) +
        0.30 * _score_linear(feat.amp_ratio(feat.amp_05x), 0.15, 1.1) +
        0.25 * _score_linear(1.0 - abs(feat.dominant_order - 0.5), 0.25, 0.95)
    )

    modulation_candidates = [
        _sideband_pair_ratio(signal, feat.dominant_freq_hz, shaft_hz, feat.tolerance_hz) if feat.dominant_order >= 1.5 else 0.0,
        _sideband_pair_ratio(signal, 2.0 * shaft_hz, shaft_hz, feat.tolerance_hz),
        _sideband_pair_ratio(signal, 3.0 * shaft_hz, shaft_hz, feat.tolerance_hz),
    ]
    for stage in asset.gear_stages:
        if sensor.gear_stage_id and sensor.gear_stage_id != stage.gear_stage_id:
            continue
        if sensor.gear_stage_id or sensor.component_id == stage.component_id:
            input_rpm = stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm
            gmf = gear_mesh_frequency_hz(input_rpm, stage)
            modulation_candidates.append(_sideband_pair_ratio(signal, gmf, shaft_hz, feat.tolerance_hz))
    for hydraulic in asset.hydraulic_elements:
        if sensor.component_id == hydraulic.component_id:
            local_rpm = hydraulic.local_rpm or sensor.local_rpm or asset.running_rpm
            hpf = hydraulic_pass_frequency_hz(local_rpm, hydraulic)
            modulation_candidates.append(_sideband_pair_ratio(signal, hpf, shaft_hz, feat.tolerance_hz))
    max_sideband = max(modulation_candidates) if modulation_candidates else 0.0
    modulation = 100.0 * (
        0.60 * _score_linear(max_sideband, 0.08, 0.45) +
        0.20 * _score_linear(feat.dominant_order, 1.8, 12.0) +
        0.20 * _score_linear(order_lock, 0.30, 0.85)
    )

    broadband = 100.0 * (
        0.35 * _score_linear(feat.hf_rms_ratio, 0.15, 0.85) +
        0.25 * _score_linear(max(feat.kurtosis, 0.0), 0.8, 4.5) +
        0.20 * _score_linear(feat.crest_factor, 3.2, 7.2) +
        0.20 * (1.0 - _score_linear(order_lock, 0.45, 0.90))
    )
    direction_radial = 1.0 if feat.axis in {"horizontal", "vertical", "radial"} else 0.0
    direction_axial = 1.0 if feat.axis == "axial" else 0.0
    return {
        "synchronous": _clamp(synchronous, 0.0, 100.0),
        "harmonic": _clamp(harmonic, 0.0, 100.0),
        "subsynchronous": _clamp(subsynchronous, 0.0, 100.0),
        "modulation": _clamp(modulation, 0.0, 100.0),
        "broadband": _clamp(broadband, 0.0, 100.0),
        "sideband_ratio": max_sideband,
        "direction_radial": direction_radial,
        "direction_axial": direction_axial,
    }


def classify_asset_pattern(asset: AssetDefinition) -> PatternFamilyProfile:
    family_scores = {k: [] for k in ["synchronous", "harmonic", "subsynchronous", "modulation", "broadband"]}
    directional_accum = {"radial": 0.0, "axial": 0.0}
    sideband_ratios: List[float] = []
    avg_one_x: List[float] = []
    avg_harmonic: List[float] = []
    avg_fractional: List[float] = []
    avg_subsync: List[float] = []
    avg_broadband: List[float] = []

    for sensor in asset.sensors:
        feats_by_axis = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in feats_by_axis.items():
            scores = _pattern_classifier_axis_scores(asset, sensor, axis_name, feat)
            axis_energy = max(feat.rms_spectrum, 1e-12)
            weight = min(1.8, 0.8 + math.log10(1.0 + axis_energy * 10.0))
            for key in family_scores:
                family_scores[key].append(scores[key] * weight)
            directional_accum["radial"] += scores["direction_radial"] * max(scores["synchronous"], scores["harmonic"], scores["modulation"], 1.0) * weight
            directional_accum["axial"] += scores["direction_axial"] * max(scores["synchronous"], scores["harmonic"], scores["modulation"], 1.0) * weight
            sideband_ratios.append(scores["sideband_ratio"])
            avg_one_x.append(feat.amp_ratio(feat.amp_1x))
            avg_harmonic.append(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x))
            avg_fractional.append(feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x + feat.amp_35x))
            avg_subsync.append(feat.amp_ratio(feat.subsync_amp))
            avg_broadband.append(feat.hf_rms_ratio)

    if not any(family_scores.values()):
        return PatternFamilyProfile(
            synchronous_score=0.0,
            harmonic_score=0.0,
            subsynchronous_score=0.0,
            modulation_score=0.0,
            broadband_score=0.0,
            radial_bias=0.0,
            axial_bias=0.0,
            mixed_bias=0.0,
            dominant_family="unknown",
            dominant_direction="unknown",
            evidence=["No valid spectral axes were available for front-end classification."],
            metrics={},
        )

    agg = {k: _clamp(_top_mean(v, n=6), 0.0, 100.0) for k, v in family_scores.items()}
    total_dir = directional_accum["radial"] + directional_accum["axial"]
    radial_bias = _safe_ratio(directional_accum["radial"], total_dir)
    axial_bias = _safe_ratio(directional_accum["axial"], total_dir)
    mixed_bias = 1.0 - abs(radial_bias - axial_bias)
    dominant_family = max(agg, key=agg.get)
    if radial_bias >= 0.67:
        dominant_direction = "radial"
    elif axial_bias >= 0.67:
        dominant_direction = "axial"
    else:
        dominant_direction = "mixed"

    family_names = {
        "synchronous": "synchronous",
        "harmonic": "harmonic",
        "subsynchronous": "subharmonic/subsynchronous",
        "modulation": "modulation/sidebands",
        "broadband": "broadband/non-synchronous",
    }
    evidence: List[str] = [
        f"Front-end classifier sees a {family_names[dominant_family]} dominant response family.",
        f"Directional bias is {dominant_direction} (radial={radial_bias:.2f}, axial={axial_bias:.2f}).",
    ]
    if agg["modulation"] >= 55.0:
        evidence.append(f"1x-spaced sideband behaviour is meaningful (mean max sideband ratio={_mean_or_zero(sideband_ratios):.2f}).")
    if agg["harmonic"] >= 55.0:
        evidence.append(f"Repeated synchronous harmonic content is strong (mean harmonic ratio={_mean_or_zero(avg_harmonic):.2f}).")
    if agg["subsynchronous"] >= 45.0:
        evidence.append(f"Sub-synchronous content is present (mean subsynchronous ratio={_mean_or_zero(avg_subsync):.2f}).")
    if agg["broadband"] >= 45.0:
        evidence.append(f"Broadband/high-frequency content is elevated (mean HF RMS ratio={_mean_or_zero(avg_broadband):.2f}).")
    if agg["synchronous"] >= 55.0:
        evidence.append(f"1x-driven synchronous behaviour is strong (mean 1x ratio={_mean_or_zero(avg_one_x):.2f}).")

    return PatternFamilyProfile(
        synchronous_score=agg["synchronous"],
        harmonic_score=agg["harmonic"],
        subsynchronous_score=agg["subsynchronous"],
        modulation_score=agg["modulation"],
        broadband_score=agg["broadband"],
        radial_bias=radial_bias,
        axial_bias=axial_bias,
        mixed_bias=mixed_bias,
        dominant_family=dominant_family,
        dominant_direction=dominant_direction,
        evidence=evidence,
        metrics={
            "mean_sideband_ratio": _mean_or_zero(sideband_ratios),
            "mean_1x_ratio": _mean_or_zero(avg_one_x),
            "mean_harmonic_ratio": _mean_or_zero(avg_harmonic),
            "mean_fractional_ratio": _mean_or_zero(avg_fractional),
            "mean_subsync_ratio": _mean_or_zero(avg_subsync),
            "mean_hf_rms_ratio": _mean_or_zero(avg_broadband),
        },
    )


def summarize_pattern_profile(profile: PatternFamilyProfile) -> str:
    lines = [
        "Pattern-family classifier",
        "========================",
        f"Dominant family: {profile.dominant_family}",
        f"Dominant direction: {profile.dominant_direction}",
        f"Scores -> synchronous={profile.synchronous_score:.1f}, harmonic={profile.harmonic_score:.1f}, subsynchronous={profile.subsynchronous_score:.1f}, modulation={profile.modulation_score:.1f}, broadband={profile.broadband_score:.1f}",
    ]
    for ev in profile.evidence[:5]:
        lines.append(f"- {ev}")
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Asset-wide shaft / train faults
# ---------------------------------------------------------------------------


def _score_unbalance(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    ratio1 = feat.amp_ratio(feat.amp_1x)
    ratio2 = feat.amp_ratio(feat.amp_2x)
    ratio3 = feat.amp_ratio(feat.amp_3x)
    one_over_two = _safe_ratio(feat.amp_1x, max(feat.amp_2x, 1e-12), default=99.0)
    dominant_near_1x = 1.0 - min(abs(feat.dominant_order - 1.0), 1.0)
    score = (
        35.0 * _score_linear(ratio1, 1.8, 5.0) +
        20.0 * _score_linear(one_over_two, 1.2, 3.5) +
        15.0 * _score_linear(_safe_ratio(feat.amp_1x, max(feat.amp_3x, 1e-12), 99.0), 1.2, 3.0) +
        15.0 * max(0.0, dominant_near_1x) +
        10.0 * (1.0 - _score_linear(ratio2 + ratio3, 2.5, 6.0)) +
        5.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x), 1.0, 3.0))
    )
    return float(score * _axis_weight("unbalance", sensor, feat.axis) * _component_weight("unbalance", sensor))


def _score_misalignment(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """
    Vendor-aligned misalignment heuristic.

    Public SKF/Acoem guidance makes the 2x/1x relationship the strongest simple
    FFT clue for offset/parallel misalignment, with radial 2x next in importance
    and axial 1x supporting angular misalignment. Higher harmonics can appear in
    severe cases but should remain secondary.
    """
    ratio1 = feat.amp_ratio(feat.amp_1x)
    ratio2 = feat.amp_ratio(feat.amp_2x)
    amp2_over_1 = _safe_ratio(feat.amp_2x, max(feat.amp_1x, 1e-12))
    axial_1x = ratio1 if feat.axis == "axial" else 0.0
    axial_2x = ratio2 if feat.axis == "axial" else 0.0
    radial_2x = ratio2 if feat.axis != "axial" else 0.0
    severe_harmonics = feat.amp_ratio(feat.amp_3x + feat.amp_4x + feat.amp_5x)

    score = (
        42.0 * _score_linear(amp2_over_1, 0.50, 1.50) +
        28.0 * _score_linear(radial_2x, 0.6, 2.6) +
        18.0 * _score_linear(axial_1x, 0.8, 3.0) +
        8.0 * _score_linear(axial_2x, 0.4, 2.2) +
        4.0 * _score_linear(severe_harmonics, 0.7, 2.8)
    )

    if amp2_over_1 < 0.50 and axial_1x < 0.80:
        score *= 0.45
    if amp2_over_1 < 0.35:
        score *= 0.55
    if feat.axis != "axial" and ratio2 < 0.45:
        score *= 0.74

    return float(score * _axis_weight("misalignment", sensor, feat.axis) * _component_weight("misalignment", sensor))


def _looseness_harmonic_string(feat: AxisFeatures) -> float:
    return feat.amp_ratio(
        feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x + feat.amp_6x + feat.amp_7x + feat.amp_8x + feat.amp_9x + feat.amp_10x
    )


def _looseness_fractional_ratio(feat: AxisFeatures) -> float:
    return feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x + feat.amp_35x)


def _score_looseness_type_a(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """
    Acoem Type A looseness: structural looseness/weakness at feet, baseplate,
    or foundation, often associated with 1 pulse per rev and strong directional 1x.
    """
    structural_mount = sensor.installed_on.lower() in {"base", "foundation", "pedestal"}
    one_x = feat.amp_ratio(feat.amp_1x)
    two_x = feat.amp_ratio(feat.amp_2x)
    harmonic_string = _looseness_harmonic_string(feat)
    frac = _looseness_fractional_ratio(feat)
    moderate_harmonics = feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x)

    score = (
        32.0 * _score_linear(one_x, 1.2, 4.8) +
        12.0 * _score_linear(two_x, 0.2, 1.5) +
        12.0 * (1.0 - _score_linear(harmonic_string, 2.0, 6.5)) +
        10.0 * (1.0 - _score_linear(frac, 0.6, 2.0)) +
        10.0 * (1.0 - _score_linear(moderate_harmonics, 2.5, 6.5)) +
        24.0 * _score_linear(feat.wf_1x_pulse, 0.10, 0.45)
    )
    if not structural_mount:
        score *= 0.32
    if feat.axis == "axial":
        score *= 0.62
    return float(score * _axis_weight("looseness_type_a_base_structure", sensor, feat.axis) * _component_weight("looseness_type_a_base_structure", sensor))


def _score_looseness_type_b(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """
    Acoem Type B looseness: loose pillow-block / pedestal / frame support. Often
    trends toward two pulses per rev, so radial 2x and a modest harmonic ladder are
    emphasized, while highly cluttered half-order patterns are pushed away to Type C.
    """
    support_mount = sensor.installed_on.lower() in {"pedestal", "bearing_housing", "casing"}
    two_x = feat.amp_ratio(feat.amp_2x)
    amp2_over_1 = _safe_ratio(feat.amp_2x, max(feat.amp_1x, 1e-12))
    support_string = feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x)
    frac = _looseness_fractional_ratio(feat)
    clutter = feat.amp_ratio(feat.amp_5x + feat.amp_6x + feat.amp_7x + feat.amp_8x + feat.amp_9x + feat.amp_10x)

    score = (
        24.0 * _score_linear(two_x, 0.35, 2.2) +
        24.0 * _score_linear(amp2_over_1, 0.45, 1.30) +
        14.0 * _score_linear(support_string, 1.0, 4.5) +
        8.0 * (1.0 - _score_linear(frac, 0.8, 2.5)) +
        6.0 * (1.0 - _score_linear(clutter, 1.5, 4.5)) +
        24.0 * _score_linear(feat.wf_2x_pulse, 0.10, 0.45)
    )
    if not support_mount:
        score *= 0.42
    if sensor.installed_on.lower() in {"base", "foundation"}:
        score *= 0.70
    if feat.axis == "axial":
        score *= 0.78
    return float(score * _axis_weight("looseness_type_b_pedestal_support", sensor, feat.axis) * _component_weight("looseness_type_b_pedestal_support", sensor))


def _score_looseness_type_c(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """
    Acoem Type C looseness: rotating fit / internal clearance looseness. Expect a
    cluttered spectrum, raised noise floor, many harmonics, and half-order content.
    """
    rotating_fit_mount = sensor.installed_on.lower() in {"bearing_housing", "casing", "pedestal"}
    harmonic_string = _looseness_harmonic_string(feat)
    high_harmonics = feat.amp_ratio(feat.amp_6x + feat.amp_7x + feat.amp_8x + feat.amp_9x + feat.amp_10x)
    frac = _looseness_fractional_ratio(feat)
    noise_ratio = _safe_ratio(feat.noise_floor, max(feat.rms_spectrum, 1e-12))
    irregularity = 0.5 * _score_linear(max(feat.kurtosis, 0.0), 0.6, 3.2) + 0.5 * _score_linear(feat.crest_factor, 3.2, 6.8)

    score = (
        28.0 * _score_linear(harmonic_string, 1.6, 7.0) +
        24.0 * _score_linear(frac, 0.7, 3.4) +
        18.0 * _score_linear(high_harmonics, 0.8, 3.5) +
        14.0 * _score_linear(noise_ratio, 0.10, 0.30) +
        16.0 * irregularity
    )
    if not rotating_fit_mount:
        score *= 0.45
    if sensor.installed_on.lower() in {"base", "foundation"}:
        score *= 0.55
    return float(score * _axis_weight("looseness_type_c_rotating_fit", sensor, feat.axis) * _component_weight("looseness_type_c_rotating_fit", sensor))


def _score_soft_foot(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    score = (
        28.0 * _score_linear(feat.amp_ratio(feat.amp_1x + feat.amp_2x), 1.8, 6.0) +
        24.0 * _score_linear(feat.amp_ratio(feat.amp_2x), 0.4, 2.2) +
        18.0 * _score_linear(_safe_ratio(feat.amp_2x, max(feat.amp_1x, 1e-12)), 0.35, 1.0) +
        18.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_3x + feat.amp_4x + feat.amp_5x), 1.0, 3.5)) +
        12.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x), 0.7, 2.2))
    )
    if sensor.installed_on.lower() not in {"base", "foundation", "pedestal"}:
        score *= 0.55
    return float(score * _axis_weight("soft_foot_or_frame_distortion", sensor, feat.axis) * _component_weight("soft_foot_or_frame_distortion", sensor))


def _score_bent_shaft(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """Conservative, because SKF separates bent shaft from misalignment mainly with phase/runout."""
    ratio12 = _safe_ratio(feat.amp_2x, max(feat.amp_1x, 1e-12))
    axial_primary = feat.amp_ratio(feat.amp_1x) if feat.axis == "axial" else 0.0
    score = (
        34.0 * _score_linear(axial_primary, 0.8, 3.5) +
        24.0 * _score_linear(feat.amp_ratio(feat.amp_1x), 1.0, 4.0) +
        18.0 * _score_linear(ratio12, 0.30, 1.20) +
        14.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_3x + feat.amp_4x + feat.amp_5x), 0.8, 2.8)) +
        10.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x), 0.6, 2.5))
    )
    if feat.axis != "axial":
        score *= 0.72
    return float(score * _axis_weight("bent_shaft_or_bow", sensor, feat.axis) * _component_weight("bent_shaft_or_bow", sensor))


def _score_resonance(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    dominant_ratio = _safe_ratio(feat.dominant_amp, max(feat.rms_spectrum, 1e-12))
    pure_unbalance_like = _score_linear(feat.amp_ratio(feat.amp_1x), 2.0, 6.0) * _score_linear(
        _safe_ratio(feat.amp_1x, max(feat.amp_2x + feat.amp_3x, 1e-12)),
        1.5,
        4.0,
    )
    score = (
        24.0 * _score_linear(dominant_ratio, 2.0, 6.0) +
        16.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x + feat.amp_05x + feat.amp_15x), 2.0, 7.0)) +
        18.0 * _score_linear(max(feat.amp_ratio(feat.amp_1x), feat.amp_ratio(feat.amp_2x), feat.amp_ratio(feat.dominant_amp)), 2.0, 6.0) +
        18.0 * (1.0 - min(abs(feat.dominant_order - round(feat.dominant_order)) / 0.3, 1.0)) +
        24.0 * (1.0 - pure_unbalance_like)
    )
    if sensor.installed_on.lower() not in {"base", "foundation", "pedestal"}:
        score *= 0.78
    return float(score * _axis_weight("resonance_or_structural_amplification", sensor, feat.axis) * _component_weight("resonance_or_structural_amplification", sensor))


def _score_rub(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    frac = feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x)
    score = (
        22.0 * _score_linear(frac, 0.8, 3.0) +
        18.0 * _score_linear(feat.amp_ratio(feat.amp_05x), 0.4, 1.8) +
        12.0 * _score_linear(feat.amp_ratio(feat.amp_15x), 0.3, 1.5) +
        12.0 * _score_linear(feat.amp_ratio(feat.amp_25x), 0.2, 1.0) +
        16.0 * _score_linear(max(feat.kurtosis, 0.0), 0.5, 3.0) +
        12.0 * _score_linear(feat.crest_factor, 3.5, 6.5) +
        8.0 * _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x), 0.6, 2.5)
    )
    return float(score * _axis_weight("rotor_rub", sensor, feat.axis) * _component_weight("rotor_rub", sensor))


def _score_motor_electrical(sensor: SensorMeasurement, feat: AxisFeatures, asset: AssetDefinition) -> float:
    motor = next((m for m in asset.motors if m.component_id == sensor.component_id), None)
    if motor is None:
        return 0.0
    line = float(motor.line_frequency_hz)
    tol = max(feat.tolerance_hz, 1.0)
    freqs = np.asarray(sensor.directions[feat.axis].freqs_hz, dtype=float)
    amps = np.asarray(sensor.directions[feat.axis].spectrum, dtype=float)
    _, amp_1lf = _peak_at(freqs, amps, line, tol)
    _, amp_2lf = _peak_at(freqs, amps, 2.0 * line, tol)
    line_ratio = _safe_ratio(amp_1lf, max(feat.rms_spectrum, 1e-12))
    double_line_ratio = _safe_ratio(amp_2lf, max(feat.rms_spectrum, 1e-12))
    score = (
        38.0 * _score_linear(double_line_ratio, 0.5, 3.0) +
        18.0 * _score_linear(line_ratio, 0.4, 2.0) +
        14.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x), 0.8, 2.5)) +
        15.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x), 2.0, 6.0)) +
        15.0 * _score_linear(max(line_ratio, double_line_ratio), 0.7, 3.0)
    )
    return float(score * _axis_weight("motor_electrical_forcing", sensor, feat.axis) * _component_weight("motor_electrical_forcing", sensor))


def diagnose_asset_wide_fault(asset: AssetDefinition, fault_key: str) -> FaultResult:
    selected = _selected_scope_sensors(asset, fault_key)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []

    ratio_1x: List[float] = []
    ratio_2x: List[float] = []
    ratio_3x: List[float] = []
    ratio_frac: List[float] = []
    ratio_2x_over_1x: List[float] = []
    axial_1x_values: List[float] = []
    radial_2x_values: List[float] = []
    waveform_1x_pulse_values: List[float] = []
    waveform_2x_pulse_values: List[float] = []
    waveform_impact_periodicity_values: List[float] = []
    high_support_axes = 0
    axial_support_axes = 0
    radial_support_axes = 0
    coupling_support_sensors: set[str] = set()
    base_support_sensors: set[str] = set()
    pedestal_support_sensors: set[str] = set()
    bearing_support_sensors: set[str] = set()
    harmonic_string_values: List[float] = []

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            if fault_key == "unbalance":
                score = _score_unbalance(sensor, feat)
            elif fault_key == "misalignment":
                score = _score_misalignment(sensor, feat)
            elif fault_key == "looseness_type_a_base_structure":
                score = _score_looseness_type_a(sensor, feat)
            elif fault_key == "looseness_type_b_pedestal_support":
                score = _score_looseness_type_b(sensor, feat)
            elif fault_key == "looseness_type_c_rotating_fit":
                score = _score_looseness_type_c(sensor, feat)
            elif fault_key == "soft_foot_or_frame_distortion":
                score = _score_soft_foot(sensor, feat)
            elif fault_key == "bent_shaft_or_bow":
                score = _score_bent_shaft(sensor, feat)
            elif fault_key == "resonance_or_structural_amplification":
                score = _score_resonance(sensor, feat)
            elif fault_key == "rotor_rub":
                score = _score_rub(sensor, feat)
            elif fault_key == "motor_electrical_forcing":
                score = _score_motor_electrical(sensor, feat, asset)
            else:
                score = 0.0

            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                ratio_1x.append(feat.amp_ratio(feat.amp_1x))
                ratio_2x.append(feat.amp_ratio(feat.amp_2x))
                ratio_3x.append(feat.amp_ratio(feat.amp_3x))
                ratio_frac.append(feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x))
                ratio_2x_over_1x.append(_safe_ratio(feat.amp_2x, max(feat.amp_1x, 1e-12)))
                if axis_name.lower() == "axial":
                    axial_1x_values.append(feat.amp_ratio(feat.amp_1x))
                else:
                    radial_2x_values.append(feat.amp_ratio(feat.amp_2x))
                waveform_1x_pulse_values.append(feat.wf_1x_pulse)
                waveform_2x_pulse_values.append(feat.wf_2x_pulse)
                waveform_impact_periodicity_values.append(feat.wf_impact_periodicity)
                harmonic_string_values.append(_looseness_harmonic_string(feat))

                if score >= 45.0:
                    high_support_axes += 1
                    if axis_name.lower() == "axial":
                        axial_support_axes += 1
                    else:
                        radial_support_axes += 1
                    if sensor.is_coupling_end:
                        coupling_support_sensors.add(sensor.sensor_id)
                    if sensor.installed_on.lower() in {"base", "foundation"}:
                        base_support_sensors.add(sensor.sensor_id)
                    if sensor.installed_on.lower() == "pedestal":
                        pedestal_support_sensors.add(sensor.sensor_id)
                    if sensor.installed_on.lower() in {"pedestal", "bearing_housing", "casing"}:
                        bearing_support_sensors.add(sensor.sensor_id)
                    evidence.append(
                        f"{sensor.sensor_id}/{axis_name}: score={score:.1f}, 1x={feat.amp_ratio(feat.amp_1x):.2f}xRMS, "
                        f"2x={feat.amp_ratio(feat.amp_2x):.2f}xRMS, 3x={feat.amp_ratio(feat.amp_3x):.2f}xRMS, "
                        f"frac={feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x):.2f}xRMS, dom={feat.dominant_order:.2f}x"
                    )

    score = _aggregate_global(local_scores, sensor_ids)
    cap = str(FAULT_LIBRARY[fault_key]["phase_cap"])
    confidence = _confidence_from_score(score, cap)
    limitations: List[str] = []
    if cap != "high":
        limitations.append(f"Confidence capped at {cap} because phase data is not available.")
    if fault_key in {"misalignment", "soft_foot_or_frame_distortion", "bent_shaft_or_bow"}:
        limitations.append("Use alignment/soft-foot checks to separate overlapping shaft/support faults.")
    if fault_key in {"looseness_type_a_base_structure", "looseness_type_b_pedestal_support", "looseness_type_c_rotating_fit"}:
        limitations.append("Looseness subtype is inferred without phase; confirm with bolt/pedestal/fit inspection before final root-cause closure.")
    if fault_key == "motor_electrical_forcing":
        limitations.append("Without current signature, this diagnosis should remain advisory only.")
    if fault_key == "resonance_or_structural_amplification":
        limitations.append("Single-spectrum resonance calls are advisory; run-up/coast-down or impact data improves certainty.")

    supporting_metrics = {
        "num_supporting_axes": float(len(local_scores)),
        "num_supporting_sensors": float(_distinct_count(sensor_ids)),
        "num_high_support_axes": float(high_support_axes),
        "num_axial_support_axes": float(axial_support_axes),
        "num_radial_support_axes": float(radial_support_axes),
        "num_coupling_support_sensors": float(len(coupling_support_sensors)),
        "num_base_support_sensors": float(len(base_support_sensors)),
        "num_pedestal_support_sensors": float(len(pedestal_support_sensors)),
        "num_bearing_support_sensors": float(len(bearing_support_sensors)),
        "mean_1x_ratio": _mean_or_zero(ratio_1x),
        "mean_2x_ratio": _mean_or_zero(ratio_2x),
        "mean_3x_ratio": _mean_or_zero(ratio_3x),
        "mean_fractional_ratio": _mean_or_zero(ratio_frac),
        "mean_2x_over_1x": _mean_or_zero(ratio_2x_over_1x),
        "mean_axial_1x_ratio": _mean_or_zero(axial_1x_values),
        "mean_radial_2x_ratio": _mean_or_zero(radial_2x_values),
        "mean_waveform_1x_pulse": _mean_or_zero(waveform_1x_pulse_values),
        "mean_waveform_2x_pulse": _mean_or_zero(waveform_2x_pulse_values),
        "mean_waveform_impact_periodicity": _mean_or_zero(waveform_impact_periodicity_values),
        "mean_harmonic_string_ratio": _mean_or_zero(harmonic_string_values),
    }

    return FaultResult(
        fault_key=fault_key,
        target=asset.asset_id,
        scope="asset_wide",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics=supporting_metrics,
    )


# ---------------------------------------------------------------------------
# Bearing / lubrication / fluid-film local faults
# ---------------------------------------------------------------------------


def _bearing_local_score_from_axis(
    fault_key: str,
    asset: AssetDefinition,
    bearing: BearingDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Tuple[float, List[str], Dict[str, float]]:
    temp_delta = _temperature_delta_c(asset, sensor)
    evidence: List[str] = []
    metrics: Dict[str, float] = {"temp_delta_c": temp_delta}

    if fault_key == "lubrication_distress":
        random_impact = 1.0 - feat.wf_impact_periodicity
        score = (
            28.0 * _score_linear(feat.hf_rms_ratio, 0.6, 2.5) +
            14.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5) +
            12.0 * _score_linear(feat.crest_factor, 3.4, 6.5) +
            12.0 * _score_linear(temp_delta, 4.0, 18.0) +
            12.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_1x + feat.amp_2x + feat.amp_3x), 2.5, 7.0)) +
            22.0 * _score_linear(random_impact, 0.25, 0.80)
        )
        metrics["waveform_impact_periodicity"] = feat.wf_impact_periodicity
        evidence.append(
            f"{sensor.sensor_id}/{feat.axis}: HF={feat.hf_rms_ratio:.2f}, kurtosis={feat.kurtosis:.2f}, "
            f"crest={feat.crest_factor:.2f}, impact_periodicity={feat.wf_impact_periodicity:.2f}, temp_delta={temp_delta:.1f}C"
        )
    elif fault_key == "fluid_film_instability":
        if bearing.bearing_type != "fluid_film":
            return 0.0, [], {}
        score = (
            38.0 * (1.0 - min(abs(_safe_ratio(feat.subsync_freq_hz, feat.shaft_hz) - 0.45) / 0.08, 1.0)) if feat.subsync_freq_hz > 0 else 0.0 +
            28.0 * _score_linear(_safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)), 0.5, 2.0) +
            14.0 * _score_linear(_safe_ratio(feat.subsync_amp, max(feat.amp_1x, 1e-12)), 0.15, 0.8) +
            10.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x), 1.2, 4.0)) +
            10.0 * _score_linear(temp_delta, 4.0, 18.0)
        )
        evidence.append(
            f"{sensor.sensor_id}/{feat.axis}: subsync={_safe_ratio(feat.subsync_freq_hz, feat.shaft_hz):.2f}x, "
            f"subsync_amp={_safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)):.2f}xRMS"
        )
    elif fault_key == "thrust_bearing_or_axial_overload":
        score = (
            30.0 * (1.0 if feat.axis == "axial" else 0.0) +
            20.0 * _score_linear(feat.amp_ratio(feat.amp_1x + feat.amp_2x), 1.5, 5.5) +
            20.0 * _score_linear(temp_delta, 4.0, 18.0) +
            15.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5) +
            15.0 * _score_linear(feat.crest_factor, 3.5, 6.0)
        )
        evidence.append(
            f"{sensor.sensor_id}/{feat.axis}: axial score context, 1x+2x={feat.amp_ratio(feat.amp_1x + feat.amp_2x):.2f}xRMS, temp_delta={temp_delta:.1f}C"
        )
    else:
        freqs = bearing_fault_frequencies_hz(sensor.local_rpm or asset.running_rpm, bearing)
        if not freqs:
            return 0.0, [], {}
        family = fault_key.split("_", 1)[1]  # bpfo / bpfi / bsf / ftf
        target_hz = freqs.get(family, 0.0)
        env_score, hits = envelope_harmonic_hit_score(signal, target_hz, max(feat.tolerance_hz, target_hz * 0.03), harmonics=4)
        metrics["envelope_hits"] = float(hits)
        score = (
            52.0 * _score_linear(env_score, 18.0, 75.0) +
            16.0 * _score_linear(feat.hf_rms_ratio, 0.7, 2.5) +
            10.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.8) +
            6.0 * _score_linear(feat.crest_factor, 3.4, 6.5) +
            6.0 * _score_linear(temp_delta, 4.0, 18.0) +
            10.0 * _score_linear(feat.wf_impact_periodicity, 0.25, 0.80)
        )
        metrics["waveform_impact_periodicity"] = feat.wf_impact_periodicity
        evidence.append(
            f"{sensor.sensor_id}/{feat.axis}: {family.upper()}={target_hz:.1f}Hz, envelope_score={env_score:.1f}, hits={hits}, impact_periodicity={feat.wf_impact_periodicity:.2f}, temp_delta={temp_delta:.1f}C"
        )

    score *= _axis_weight(fault_key, sensor, feat.axis) * _component_weight(fault_key, sensor)
    return float(score), evidence, metrics


def diagnose_bearing_local_fault(asset: AssetDefinition, fault_key: str, bearing: BearingDefinition) -> FaultResult:
    selected = _selected_scope_sensors(asset, fault_key, bearing_id=bearing.bearing_id)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            signal = sensor.directions[axis_name]
            score, ev, metrics = _bearing_local_score_from_axis(fault_key, asset, bearing, sensor, feat, signal)
            if score > 0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    local_coverage = 18.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 2.0)
    repeatability = 12.0 * _score_linear(sum(1 for s in local_scores if s >= 45.0), 1.0, 3.0)
    score = _clamp(0.70 * top + local_coverage + repeatability, 0.0, 100.0)
    cap = str(FAULT_LIBRARY[fault_key]["phase_cap"])
    confidence = _confidence_from_score(score, cap)
    limitations: List[str] = []
    if fault_key.startswith("bearing_"):
        limitations.append("Bearing family confidence depends on correct geometry, speed and envelope processing.")
    if fault_key == "lubrication_distress":
        limitations.append("Surface temperature is a corroborator, not a standalone lubricant health measurement.")
    if fault_key == "thrust_bearing_or_axial_overload":
        limitations.append("Without axial position or process thrust data, keep this diagnosis conservative.")

    metrics_out = {k: float(mean(v)) for k, v in metrics_acc.items() if v}
    return FaultResult(
        fault_key=fault_key,
        target=bearing.bearing_id,
        scope="bearing_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics=metrics_out,
    )


# ---------------------------------------------------------------------------
# Gear local faults
# ---------------------------------------------------------------------------


def _gear_axis_score(asset: AssetDefinition, stage: GearStageDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Tuple[float, List[str], Dict[str, float]]:
    input_rpm = stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm
    gmf = gear_mesh_frequency_hz(input_rpm, stage)
    freqs = np.asarray(signal.freqs_hz, dtype=float)
    amps = np.asarray(signal.spectrum, dtype=float)
    tol = max(feat.tolerance_hz, gmf * 0.03)
    _, gmf_amp = _peak_at(freqs, amps, gmf, tol)
    _, gmf2_amp = _peak_at(freqs, amps, 2.0 * gmf, tol)
    _, left = _peak_at(freqs, amps, gmf - feat.shaft_hz, tol)
    _, right = _peak_at(freqs, amps, gmf + feat.shaft_hz, tol)
    symmetry = _safe_ratio(min(left, right), max(left, right, 1e-12))
    sideband_ratio = _safe_ratio(left + right, max(gmf_amp, 1e-12))
    env_score, env_hits = envelope_harmonic_hit_score(signal, gmf, tol, harmonics=3)
    score = (
        28.0 * _score_linear(_safe_ratio(gmf_amp, max(feat.rms_spectrum, 1e-12)), 0.6, 3.5) +
        12.0 * _score_linear(_safe_ratio(gmf2_amp, max(feat.rms_spectrum, 1e-12)), 0.3, 2.0) +
        22.0 * _score_linear(sideband_ratio, 0.2, 1.0) +
        10.0 * _score_linear(symmetry, 0.2, 0.8) +
        16.0 * _score_linear(env_score, 18.0, 75.0) +
        8.0 * _score_linear(feat.hf_rms_ratio, 0.7, 2.5) +
        4.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5)
    )
    score *= _axis_weight("gear_mesh_fault", sensor, feat.axis) * _component_weight("gear_mesh_fault", sensor)
    evidence = [f"{sensor.sensor_id}/{feat.axis}: GMF={gmf:.1f}Hz, GMF_amp={_safe_ratio(gmf_amp, max(feat.rms_spectrum, 1e-12)):.2f}xRMS, SB={sideband_ratio:.2f}, symmetry={symmetry:.2f}, env={env_score:.1f}, hits={env_hits}"]
    metrics = {"gmf_hz": gmf, "sideband_ratio": sideband_ratio, "symmetry": symmetry, "env_score": env_score}
    return float(score), evidence, metrics


def diagnose_gear_fault(asset: AssetDefinition, stage: GearStageDefinition) -> FaultResult:
    selected = _selected_scope_sensors(asset, "gear_mesh_fault", gear_stage_id=stage.gear_stage_id)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            score, ev, metrics = _gear_axis_score(asset, stage, sensor, feat, sensor.directions[axis_name])
            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    coverage = 16.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 3.0)
    repeatability = 12.0 * _score_linear(sum(1 for s in local_scores if s >= 40.0), 1.0, 4.0)
    score = _clamp(0.72 * top + coverage + repeatability, 0.0, 100.0)
    confidence = _confidence_from_score(score, str(FAULT_LIBRARY["gear_mesh_fault"]["phase_cap"]))
    return FaultResult(
        fault_key="gear_mesh_fault",
        target=stage.gear_stage_id,
        scope="gear_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=["Exact tooth counts and shaft speed are required for best accuracy."],
        supporting_metrics={k: float(mean(v)) for k, v in metrics_acc.items() if v},
    )


# ---------------------------------------------------------------------------
# Hydraulic local faults
# ---------------------------------------------------------------------------


def _hydraulic_axis_scores(
    asset: AssetDefinition,
    hydraulic: HydraulicElementDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, Tuple[float, List[str], Dict[str, float]]]:
    local_rpm = hydraulic.local_rpm or sensor.local_rpm or asset.running_rpm
    pass_hz = hydraulic_pass_frequency_hz(local_rpm, hydraulic)
    freqs = np.asarray(signal.freqs_hz, dtype=float)
    amps = np.asarray(signal.spectrum, dtype=float)
    tol = max(feat.tolerance_hz, pass_hz * 0.03)
    _, pass_amp = _peak_at(freqs, amps, pass_hz, tol)
    _, left = _peak_at(freqs, amps, max(pass_hz - feat.shaft_hz, 0.0), tol)
    _, right = _peak_at(freqs, amps, pass_hz + feat.shaft_hz, tol)
    pass_ratio = _safe_ratio(pass_amp, max(feat.rms_spectrum, 1e-12))
    sideband_ratio = _safe_ratio(left + right, max(pass_amp, 1e-12))
    dominant_order_match = 1.0 - min(abs(feat.dominant_order - float(hydraulic.pass_count)) / max(float(hydraulic.pass_count), 1.0), 1.0)
    score_pass = (
        36.0 * _score_linear(pass_ratio, 0.5, 3.0) +
        18.0 * dominant_order_match +
        18.0 * _score_linear(sideband_ratio, 0.10, 0.80) +
        10.0 * _score_linear(feat.hf_rms_ratio, 0.6, 2.0) +
        10.0 * _score_linear(_temperature_delta_c(asset, sensor), 4.0, 16.0) +
        8.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5)
    )
    score_pass *= _axis_weight("hydraulic_vane_or_blade_pass", sensor, feat.axis) * _component_weight("hydraulic_vane_or_blade_pass", sensor)

    score_cav = (
        38.0 * _score_linear(feat.hf_rms_ratio, 0.8, 3.2) +
        18.0 * _score_linear(max(feat.kurtosis, 0.0), 0.5, 3.0) +
        16.0 * _score_linear(feat.crest_factor, 3.6, 6.8) +
        12.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_1x), 1.6, 5.0)) +
        10.0 * (1.0 - _score_linear(pass_ratio, 0.7, 3.0)) +
        6.0 * _score_linear(_safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)), 0.3, 1.5)
    )
    score_cav *= _axis_weight("cavitation_or_aeration", sensor, feat.axis) * _component_weight("cavitation_or_aeration", sensor)

    return {
        "hydraulic_vane_or_blade_pass": (
            float(score_pass),
            [f"{sensor.sensor_id}/{feat.axis}: pass_freq={pass_hz:.1f}Hz, pass_amp={pass_ratio:.2f}xRMS, sidebands={sideband_ratio:.2f}, dominant_order={feat.dominant_order:.2f}x"],
            {"pass_hz": pass_hz, "pass_ratio": pass_ratio, "sideband_ratio": sideband_ratio},
        ),
        "cavitation_or_aeration": (
            float(score_cav),
            [f"{sensor.sensor_id}/{feat.axis}: HF={feat.hf_rms_ratio:.2f}, kurtosis={feat.kurtosis:.2f}, crest={feat.crest_factor:.2f}, 1x={feat.amp_ratio(feat.amp_1x):.2f}xRMS"],
            {"hf_rms_ratio": feat.hf_rms_ratio},
        ),
    }


def diagnose_hydraulic_fault(asset: AssetDefinition, fault_key: str, hydraulic: HydraulicElementDefinition) -> FaultResult:
    selected = _selected_scope_sensors(asset, fault_key, hydraulic_id=hydraulic.hydraulic_id)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            pack = _hydraulic_axis_scores(asset, hydraulic, sensor, feat, sensor.directions[axis_name])
            score, ev, metrics = pack[fault_key]
            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    coverage = 14.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 3.0)
    repeatability = 10.0 * _score_linear(sum(1 for s in local_scores if s >= 40.0), 1.0, 4.0)
    score = _clamp(0.76 * top + coverage + repeatability, 0.0, 100.0)
    confidence = _confidence_from_score(score, str(FAULT_LIBRARY[fault_key]["phase_cap"]))
    limitations = []
    if fault_key == "cavitation_or_aeration":
        limitations.append("Best used together with process variables such as suction pressure, flow and NPSH margin.")
    if fault_key == "hydraulic_vane_or_blade_pass":
        limitations.append("Pass count and local RPM must be correct, especially on speed-changing equipment.")
    return FaultResult(
        fault_key=fault_key,
        target=hydraulic.hydraulic_id,
        scope="hydraulic_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics={k: float(mean(v)) for k, v in metrics_acc.items() if v},
    )


# ---------------------------------------------------------------------------
# Result post-processing and recommendations
# ---------------------------------------------------------------------------


def _refresh_result_confidence(result: FaultResult) -> None:
    result.score = _clamp(result.score, 0.0, 100.0)
    cap = str(FAULT_LIBRARY.get(result.fault_key, {}).get("phase_cap", "high"))
    result.confidence = _confidence_from_score(result.score, cap)


def _postprocess_results(asset: AssetDefinition, results: List[FaultResult]) -> None:
    asset_wide = {r.fault_key: r for r in results if r.scope == "asset_wide"}
    pattern_profile = asset.metadata.get("_pattern_classifier")
    if isinstance(pattern_profile, dict):
        pattern_profile = PatternFamilyProfile(
            synchronous_score=float(pattern_profile.get("synchronous_score", 0.0)),
            harmonic_score=float(pattern_profile.get("harmonic_score", 0.0)),
            subsynchronous_score=float(pattern_profile.get("subsynchronous_score", 0.0)),
            modulation_score=float(pattern_profile.get("modulation_score", 0.0)),
            broadband_score=float(pattern_profile.get("broadband_score", 0.0)),
            radial_bias=float(pattern_profile.get("radial_bias", 0.0)),
            axial_bias=float(pattern_profile.get("axial_bias", 0.0)),
            mixed_bias=float(pattern_profile.get("mixed_bias", 0.0)),
            dominant_family=str(pattern_profile.get("dominant_family", "unknown")),
            dominant_direction=str(pattern_profile.get("dominant_direction", "unknown")),
            evidence=list(pattern_profile.get("evidence", [])),
            metrics=dict(pattern_profile.get("metrics", {})),
        )
    have_resonance_confirmation = bool(
        asset.metadata.get("speed_sweep_available")
        or asset.metadata.get("impact_test_available")
        or asset.metadata.get("resonance_confirmed")
    )

    unbalance = asset_wide.get("unbalance")
    misalignment = asset_wide.get("misalignment")
    looseness_a = asset_wide.get("looseness_type_a_base_structure")
    looseness_b = asset_wide.get("looseness_type_b_pedestal_support")
    looseness_c = asset_wide.get("looseness_type_c_rotating_fit")
    soft_foot = asset_wide.get("soft_foot_or_frame_distortion")
    bent_shaft = asset_wide.get("bent_shaft_or_bow")
    resonance = asset_wide.get("resonance_or_structural_amplification")
    hydraulic_pass_candidates = [r for r in results if r.fault_key == "hydraulic_vane_or_blade_pass"]
    hydraulic_pass = max(hydraulic_pass_candidates, key=lambda r: r.score) if hydraulic_pass_candidates else None
    lubrication_candidates = [r for r in results if r.fault_key == "lubrication_distress"]
    lubrication_distress = max(lubrication_candidates, key=lambda r: r.score) if lubrication_candidates else None

    if pattern_profile is not None:
        modulation_dominant = pattern_profile.modulation_score >= 55.0 or pattern_profile.dominant_family == "modulation"
        subsync_dominant = pattern_profile.subsynchronous_score >= 45.0 or pattern_profile.dominant_family == "subsynchronous"
        broadband_dominant = pattern_profile.broadband_score >= 50.0 or pattern_profile.dominant_family == "broadband"
        synchronous_radial = pattern_profile.synchronous_score >= 55.0 and pattern_profile.radial_bias >= 0.60

        for key in ["unbalance", "misalignment", "looseness_type_a_base_structure", "looseness_type_b_pedestal_support"]:
            result = asset_wide.get(key)
            if result is None:
                continue
            if modulation_dominant:
                factor = 0.80 if key == "unbalance" else 0.72
                result.score *= factor
                result.limitations.append("Reduced by the front-end pattern classifier because modulation/sidebands dominate ahead of a simple shaft-train response family.")
                _refresh_result_confidence(result)
            if broadband_dominant and key in {"unbalance", "misalignment"}:
                result.score *= 0.78
                result.limitations.append("Reduced by the front-end pattern classifier because broadband/non-synchronous content is stronger than a clean synchronous shaft-train pattern.")
                _refresh_result_confidence(result)
            if subsync_dominant and key == "misalignment":
                result.score *= 0.82
                result.limitations.append("Reduced by the front-end pattern classifier because subsynchronous behaviour is competing with the misalignment hypothesis.")
                _refresh_result_confidence(result)

        for key in ["hydraulic_vane_or_blade_pass", "gear_mesh_fault"]:
            for result in [r for r in results if r.fault_key == key]:
                if modulation_dominant:
                    result.score *= 1.08
                    result.evidence.append("Supported by the front-end pattern classifier: modulation/sideband family is dominant.")
                    _refresh_result_confidence(result)

        for key in ["cavitation_or_aeration", "lubrication_distress"]:
            for result in [r for r in results if r.fault_key == key]:
                if broadband_dominant:
                    result.score *= 1.08
                    result.evidence.append("Supported by the front-end pattern classifier: broadband/non-synchronous energy is elevated.")
                    _refresh_result_confidence(result)

        for key in ["rotor_rub", "fluid_film_instability", "resonance_or_structural_amplification"]:
            targets = [r for r in results if r.fault_key == key]
            for result in targets:
                if subsync_dominant:
                    result.score *= 1.06
                    result.evidence.append("Supported by the front-end pattern classifier: subsynchronous content is meaningful.")
                    _refresh_result_confidence(result)
                elif synchronous_radial and key == "resonance_or_structural_amplification":
                    result.score *= 0.94
                    result.limitations.append("Front-end classifier sees a predominantly synchronous radial family, so resonance is kept conservative until confirmed by speed sweep or impact test.")
                    _refresh_result_confidence(result)

    if misalignment is not None:
        mean_2x_over_1x = misalignment.supporting_metrics.get("mean_2x_over_1x", 0.0)
        mean_radial_2x = misalignment.supporting_metrics.get("mean_radial_2x_ratio", 0.0)
        mean_axial_1x = misalignment.supporting_metrics.get("mean_axial_1x_ratio", 0.0)
        if misalignment.supporting_metrics.get("num_coupling_support_sensors", 0.0) < 1.0:
            misalignment.score *= 0.80
            misalignment.limitations.append("Reduced because coupling-end support is weak for a misalignment call.")
        if mean_2x_over_1x < 0.50:
            misalignment.score *= 0.50
            misalignment.limitations.append("Reduced because 2x is too small relative to 1x for a strong misalignment call.")
        if mean_2x_over_1x < 0.35:
            misalignment.score *= 0.55
            misalignment.limitations.append("Reduced again because 2x/1x is well below the range usually expected for a strong misalignment diagnosis.")
        if mean_radial_2x < 0.60 and mean_axial_1x < 0.90:
            misalignment.score *= 0.60
            misalignment.limitations.append("Reduced because neither radial 2x nor axial 1x is strong enough to support a confident misalignment call.")
        if (
            misalignment.supporting_metrics.get("num_axial_support_axes", 0.0) < 1.0
            and mean_2x_over_1x < 0.60
        ):
            misalignment.score *= 0.60
            misalignment.limitations.append("Reduced because axial 1x support and 2x evidence are both weak for misalignment.")
        if unbalance is not None and unbalance.score >= 45.0 and mean_2x_over_1x < 0.60:
            misalignment.score *= 0.70
            misalignment.limitations.append("Reduced because the pattern is dominated by simpler 1x unbalance behaviour.")
        if hydraulic_pass is not None and hydraulic_pass.score >= 60.0 and mean_2x_over_1x < 1.20:
            misalignment.score *= 0.70
            misalignment.limitations.append("Reduced because strong hydraulic pass-frequency evidence can mimic a 2x/axial misalignment pattern on pumps unless 2x/1x is clearly strong.")
        _refresh_result_confidence(misalignment)


    if looseness_a is not None:
        if looseness_a.supporting_metrics.get("num_base_support_sensors", 0.0) < 1.0:
            looseness_a.score *= 0.45
            looseness_a.limitations.append("Reduced because Type A looseness should be supported at the base/foundation rather than only at bearing housings.")
        if looseness_a.supporting_metrics.get("mean_harmonic_string_ratio", 0.0) > 4.5:
            looseness_a.score *= 0.72
            looseness_a.limitations.append("Reduced because the harmonic ladder is too cluttered for a clean Type A structural looseness pattern.")
        if looseness_a.supporting_metrics.get("mean_waveform_1x_pulse", 0.0) < 0.14:
            looseness_a.score *= 0.68
            looseness_a.limitations.append("Reduced because the waveform does not show the expected 1-pulse-per-rev tendency for Type A looseness.")
        if hydraulic_pass is not None and hydraulic_pass.score >= 60.0:
            looseness_a.score *= 0.72
            looseness_a.limitations.append("Reduced because strong hydraulic pass-frequency forcing can mimic directional structural looseness on pumps.")
        _refresh_result_confidence(looseness_a)
        looseness_a.confidence = _cap_confidence(looseness_a.confidence, "low")

    if looseness_b is not None:
        if looseness_b.supporting_metrics.get("num_pedestal_support_sensors", 0.0) < 1.0:
            looseness_b.score *= 0.72
            looseness_b.limitations.append("Reduced because Type B looseness is strongest when a pedestal or support-frame location is directly involved.")
        if looseness_b.supporting_metrics.get("num_pedestal_support_sensors", 0.0) < 1.0 and looseness_b.supporting_metrics.get("num_bearing_support_sensors", 0.0) < 1.0:
            looseness_b.score *= 0.48
            looseness_b.limitations.append("Reduced because Type B looseness should be supported near a pedestal, bearing support, or frame crack location.")
        if looseness_b.supporting_metrics.get("mean_2x_over_1x", 0.0) < 0.45:
            looseness_b.score *= 0.62
            looseness_b.limitations.append("Reduced because 2x evidence is weak for a Type B support/pedestal looseness pattern.")
        if looseness_b.supporting_metrics.get("mean_waveform_2x_pulse", 0.0) < 0.14:
            looseness_b.score *= 0.68
            looseness_b.limitations.append("Reduced because the waveform does not show the expected 2-pulses-per-rev tendency for Type B looseness.")
        if hydraulic_pass is not None and hydraulic_pass.score >= 60.0 and looseness_b.supporting_metrics.get("mean_2x_over_1x", 0.0) < 0.80:
            looseness_b.score *= 0.65
            looseness_b.limitations.append("Reduced because strong hydraulic pass-frequency evidence can mimic a support-side harmonic ladder when 2x evidence is limited.")
        _refresh_result_confidence(looseness_b)
        looseness_b.confidence = _cap_confidence(looseness_b.confidence, "low")

    if looseness_c is not None:
        if looseness_c.supporting_metrics.get("num_bearing_support_sensors", 0.0) < 1.0:
            looseness_c.score *= 0.55
            looseness_c.limitations.append("Reduced because Type C looseness should be strongest at bearing-housing/casing support points.")
        if looseness_c.supporting_metrics.get("mean_harmonic_string_ratio", 0.0) < 2.5:
            looseness_c.score *= 0.68
            looseness_c.limitations.append("Reduced because the spectrum is not cluttered enough for a strong Type C rotating-fit looseness pattern.")
        if looseness_c.supporting_metrics.get("mean_fractional_ratio", 0.0) < 1.50:
            looseness_c.score *= 0.64
            looseness_c.limitations.append("Reduced because half-order content is not strong enough for a confident Type C rotating-fit looseness call.")
        if hydraulic_pass is not None and hydraulic_pass.score >= 60.0:
            if looseness_c.supporting_metrics.get("mean_fractional_ratio", 0.0) < 2.20:
                looseness_c.score *= 0.58
                looseness_c.limitations.append("Reduced because strong hydraulic pass-frequency evidence can create harmonics without the heavy half-order clutter expected from Type C looseness.")
            if lubrication_distress is None or lubrication_distress.score < 20.0:
                looseness_c.score *= 0.52
                looseness_c.limitations.append("Reduced because the pattern looks hydraulically driven and lacks corroborating local bearing/fit distress evidence.")
        _refresh_result_confidence(looseness_c)

    if soft_foot is not None:
        if soft_foot.supporting_metrics.get("num_base_support_sensors", 0.0) < 1.0:
            soft_foot.score *= 0.68
            soft_foot.limitations.append("Reduced because no base/foundation/pedestal measurements strongly support soft-foot or frame distortion.")
        if soft_foot.supporting_metrics.get("mean_2x_over_1x", 0.0) < 0.40:
            soft_foot.score *= 0.52
            soft_foot.limitations.append("Reduced because 2x content is weak for soft-foot/frame distortion.")
        if unbalance is not None and unbalance.score >= 45.0 and soft_foot.supporting_metrics.get("mean_2x_over_1x", 0.0) < 0.40:
            soft_foot.score *= 0.70
            soft_foot.limitations.append("Reduced because the pattern is dominated by simpler 1x unbalance behaviour.")
        _refresh_result_confidence(soft_foot)
        soft_foot.confidence = _cap_confidence(soft_foot.confidence, "low")

    if bent_shaft is not None:
        if bent_shaft.supporting_metrics.get("num_supporting_sensors", 0.0) < 2.0:
            bent_shaft.score *= 0.72
            bent_shaft.limitations.append("Reduced because bent-shaft diagnosis is weak when based on a single sensor location.")
        if bent_shaft.supporting_metrics.get("num_axial_support_axes", 0.0) < 1.0:
            bent_shaft.score *= 0.55
            bent_shaft.limitations.append("Reduced because axial dominance is weak for a bent-shaft/bow pattern.")
        if bent_shaft.supporting_metrics.get("mean_2x_over_1x", 0.0) < 0.30:
            bent_shaft.score *= 0.60
            bent_shaft.limitations.append("Reduced because 2x content is too weak for a bent-shaft/bow pattern.")
        if unbalance is not None and unbalance.score >= 45.0 and bent_shaft.supporting_metrics.get("mean_fractional_ratio", 0.0) < 0.60:
            bent_shaft.score *= 0.72
            bent_shaft.limitations.append("Reduced because the pattern overlaps more closely with simple 1x unbalance.")
        _refresh_result_confidence(bent_shaft)
        bent_shaft.confidence = _cap_confidence(bent_shaft.confidence, "low")

    if resonance is not None:
        if not have_resonance_confirmation:
            resonance.score *= 0.58
            resonance.limitations.append("Reduced because no run-up/coast-down, impact test or confirmed phase swing is provided.")
        if resonance.supporting_metrics.get("num_base_support_sensors", 0.0) < 1.0:
            resonance.score *= 0.72
            resonance.limitations.append("Reduced because support-structure measurements are limited.")
        if unbalance is not None and unbalance.score >= 45.0 and resonance.supporting_metrics.get("num_base_support_sensors", 0.0) < 1.0:
            resonance.score *= 0.78
            resonance.limitations.append("Reduced because a simpler 1x unbalance explanation is stronger than a structural-resonance explanation.")
        _refresh_result_confidence(resonance)
        if not have_resonance_confirmation:
            resonance.confidence = _cap_confidence(resonance.confidence, "low")


def _fault_urgency(score: float, confidence: str) -> str:
    if score >= 75.0 and confidence in {"medium", "high"}:
        return "urgent"
    if score >= 45.0 and confidence != "none":
        return "plan"
    return "monitor"


def _fault_recommendations(result: FaultResult) -> List[str]:
    severity_action = {
        "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
        "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
        "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
    }[_fault_urgency(result.score, result.confidence)]

    fault_key = result.fault_key
    mapping: Dict[str, List[str]] = {
        "unbalance": [
            severity_action,
            "Verify rotor cleanliness, product build-up, missing balance weights, eccentric sleeves and recent maintenance changes before balancing.",
            "If the pattern persists, trim-balance only after ruling out looseness, resonance and coupling problems.",
        ],
        "misalignment": [
            severity_action,
            "Perform laser alignment with thermal targets where applicable and inspect coupling condition, pipe strain and base distortion.",
            "Re-measure axial and coupling-end vibration after correction to verify the diagnosis.",
        ],
        "looseness_type_a_base_structure": [
            severity_action,
            "Inspect feet, grout, baseplate, anchor bolts and soft-foot condition first; Type A looseness is a structural/base problem, not a rotor-fit problem.",
            "Compare machine-foot, baseplate and floor vibration and confirm with torque checks and a soft-foot check before moving to rotor work.",
        ],
        "looseness_type_b_pedestal_support": [
            severity_action,
            "Inspect pillow-block bolts, bearing pedestal joints, support welds and frame cracks near the high-vibration support points.",
            "Use time waveform and local cross-point measurements around the support structure to confirm a two-pulse-per-rev support looseness pattern.",
        ],
        "looseness_type_c_rotating_fit": [
            severity_action,
            "Inspect bearing fits, sleeve clearances, housings, liners, impeller-to-shaft fit and other rotating/stationary fit interfaces for excessive play.",
            "Use waveform/envelope/high-frequency checks to confirm internal clearance or rotating-fit looseness before concluding a structural root cause.",
        ],
        "soft_foot_or_frame_distortion": [
            severity_action,
            "Run a formal soft-foot check foot-by-foot, correct shims/base flatness and relieve pipe strain before final alignment.",
            "If 2x line frequency or directional distortion remains on a motor, inspect for frame distortion or weak base conditions.",
        ],
        "bent_shaft_or_bow": [
            severity_action,
            "Check shaft and coupling-hub runout, thermal bow, sleeve eccentricity and rotor straightness during outage.",
            "Use phase, axial position/runout, or uncoupled measurements to confirm before major rotor work.",
        ],
        "resonance_or_structural_amplification": [
            severity_action,
            "Confirm with run-up/coast-down, bump/impact test, phase swing or ODS before changing hardware.",
            "If confirmed, shift stiffness/mass/damping or avoid the resonant operating range.",
        ],
        "rotor_rub": [
            severity_action,
            "Inspect internal clearances, seals, wear rings, impeller/casing contact marks and thermal growth margins.",
            "If rubbing is active and severe, do not rely on trending alone; inspect before damage escalates.",
        ],
        "motor_electrical_forcing": [
            severity_action,
            "Compare the vibration with current signature, voltage balance, air-gap checks and rotor/stator condition before concluding an electrical root cause.",
            "Inspect for weak base or frame distortion as these can amplify 2x line-frequency forcing.",
        ],
        "lubrication_distress": [
            severity_action,
            "Verify lubricant type, quantity, delivery method, relubrication interval and contamination control.",
            "Trend temperature and high-frequency acceleration together; do not use surface temperature alone as the decision point.",
        ],
        "bearing_bpfo": [
            severity_action,
            "Confirm bearing geometry, speed and envelope setup, then inspect lubrication, fits and contamination sources.",
            "Plan bearing replacement and correct the root cause rather than replacing the bearing only.",
        ],
        "bearing_bpfi": [
            severity_action,
            "Confirm bearing geometry, speed and envelope setup, then inspect lubrication, fits and contamination sources.",
            "Look for shaft-speed sidebands or repeated modulation and plan corrective work before secondary damage spreads.",
        ],
        "bearing_bsf": [
            severity_action,
            "Confirm bearing geometry, speed and envelope setup, then inspect lubrication, fits and contamination sources.",
            "Inspect rolling-element damage and cage condition when the machine is opened.",
        ],
        "bearing_ftf": [
            severity_action,
            "Confirm cage frequency against real running speed and inspect for cage distress, lubricant starvation or skidding.",
            "Check whether low-load or poor lubrication conditions are contributing to the cage-related pattern.",
        ],
        "fluid_film_instability": [
            severity_action,
            "Check oil condition, viscosity, supply temperature, bearing clearances and radial loading.",
            "Use shaft probes/orbits and process condition review where available to separate oil whirl from other subsynchronous phenomena.",
        ],
        "thrust_bearing_or_axial_overload": [
            severity_action,
            "Check process thrust, axial float/position, thrust pad temperatures and coupling end float.",
            "Use process data and machine design limits before concluding an overload condition.",
        ],
        "gear_mesh_fault": [
            severity_action,
            "Inspect tooth contact pattern, backlash, alignment, lubrication quality and debris generation.",
            "Trend GMF, harmonics and sidebands after correction to confirm the gear-root cause.",
        ],
        "hydraulic_vane_or_blade_pass": [
            severity_action,
            "Confirm vane/blade count and real running speed, then inspect impeller/rotor condition and hydraulic recirculation issues.",
            "Review process operating point because off-design flow can exaggerate pass-frequency symptoms.",
        ],
        "cavitation_or_aeration": [
            severity_action,
            "Review suction pressure, NPSH margin, entrained air, leaks, strainers, valve position and minimum-flow protection.",
            "Inspect impeller and wear-ring surfaces for pitting or erosion if the pattern persists.",
        ],
    }
    return mapping.get(fault_key, [severity_action])


def _annotate_results(results: List[FaultResult]) -> None:
    for result in results:
        result.urgency = _fault_urgency(result.score, result.confidence)
        result.recommendations = _fault_recommendations(result)



# ---------------------------------------------------------------------------
# Integrated condition-severity engine (patched from rotating_machine_health_score)
# ---------------------------------------------------------------------------

CONDITION_EPS = 1e-9

CONDITION_SEVERITY_FEATURE_WEIGHTS: Dict[str, float] = {
    "vel_rms": 0.50,
    "acc_rms": 0.20,
    "peak": 0.15,
    "crest_factor": 0.15,
}

CONDITION_SHAFT_FEATURE_WEIGHTS: Dict[str, float] = {
    "amp_1x": 0.30,
    "amp_2x": 0.22,
    "amp_3x": 0.12,
    "subharmonic_ratio": 0.14,
    "harmonic_energy_ratio": 0.12,
    "axial_radial_ratio": 0.10,
}

CONDITION_BEARING_FEATURE_WEIGHTS: Dict[str, float] = {
    "env_rms": 0.20,
    "env_kurtosis": 0.15,
    "hf_rms": 0.15,
    "bpfo_band_energy": 0.15,
    "bpfi_band_energy": 0.15,
    "bsf_band_energy": 0.10,
    "ftf_band_energy": 0.05,
    "env_entropy": 0.05,
}

CONDITION_GEAR_FEATURE_WEIGHTS: Dict[str, float] = {
    "gmf_amp": 0.20,
    "gmf_harmonics": 0.20,
    "gmf_sideband_ratio": 0.25,
    "residual_tsa_rms": 0.15,
    "residual_tsa_kurtosis": 0.10,
    "mesh_band_entropy": 0.10,
}

CONDITION_HYDRAULIC_FEATURE_WEIGHTS: Dict[str, float] = {
    "vpf_amp": 0.25,
    "vpf_harmonics": 0.20,
    "vpf_sideband_ratio": 0.20,
    "broadband_hf_energy": 0.20,
    "cavitation_band_energy": 0.15,
}

CONDITION_AERO_FEATURE_WEIGHTS: Dict[str, float] = {
    "bpf_amp": 0.35,
    "bpf_harmonics": 0.20,
    "bpf_sideband_ratio": 0.20,
    "broadband_aero_energy": 0.25,
}

CONDITION_ELECTRICAL_FEATURE_WEIGHTS: Dict[str, float] = {
    "line_freq_vib": 0.35,
    "twice_line_freq_vib": 0.35,
    "electrical_sideband_ratio": 0.30,
}

CONDITION_ASSET_BLOCK_WEIGHTS: Dict[str, Dict[str, float]] = {
    "motor": {"severity": 0.20, "shaft": 0.30, "bearing": 0.30, "electrical": 0.10, "trend": 0.10},
    "pump": {"severity": 0.20, "shaft": 0.20, "bearing": 0.25, "hydraulic": 0.25, "trend": 0.10},
    "gearbox": {"severity": 0.10, "shaft": 0.15, "bearing": 0.20, "gear": 0.45, "trend": 0.10},
    "blower": {"severity": 0.20, "shaft": 0.30, "bearing": 0.25, "aero": 0.15, "trend": 0.10},
    "fan": {"severity": 0.20, "shaft": 0.30, "bearing": 0.25, "aero": 0.15, "trend": 0.10},
    "bearing_only": {"severity": 0.10, "bearing": 0.70, "trend": 0.20},
}

CONDITION_SCORE_BANDS: List[Tuple[float, str]] = [
    (35.0, "critical"),
    (55.0, "high"),
    (75.0, "medium"),
    (90.0, "low"),
    (100.0, "normal"),
]

SEVERITY_FAMILY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "shaft": {"condition": 0.50, "diagnostic": 0.30, "family": 0.15, "trend": 0.05},
    "bearing": {"condition": 0.25, "diagnostic": 0.45, "family": 0.20, "trend": 0.10},
    "gear": {"condition": 0.20, "diagnostic": 0.45, "family": 0.25, "trend": 0.10},
    "hydraulic": {"condition": 0.25, "diagnostic": 0.45, "family": 0.20, "trend": 0.10},
    "aero": {"condition": 0.25, "diagnostic": 0.45, "family": 0.20, "trend": 0.10},
    "electrical": {"condition": 0.35, "diagnostic": 0.35, "family": 0.20, "trend": 0.10},
}

FAULT_TO_CONDITION_FAMILY: Dict[str, str] = {
    "unbalance": "shaft",
    "misalignment": "shaft",
    "looseness_type_a_base_structure": "shaft",
    "looseness_type_b_pedestal_support": "shaft",
    "looseness_type_c_rotating_fit": "shaft",
    "soft_foot_or_frame_distortion": "shaft",
    "bent_shaft_or_bow": "shaft",
    "resonance_or_structural_amplification": "shaft",
    "rotor_rub": "shaft",
    "motor_electrical_forcing": "electrical",
    "lubrication_distress": "bearing",
    "bearing_bpfo": "bearing",
    "bearing_bpfi": "bearing",
    "bearing_bsf": "bearing",
    "bearing_ftf": "bearing",
    "fluid_film_instability": "bearing",
    "thrust_bearing_or_axial_overload": "bearing",
    "gear_mesh_fault": "gear",
    "hydraulic_vane_or_blade_pass": "hydraulic",
    "cavitation_or_aeration": "hydraulic",
}

FAULT_RISK_BONUS: Dict[str, float] = {
    "rotor_rub": 0.08,
    "bearing_bpfo": 0.08,
    "bearing_bpfi": 0.08,
    "bearing_bsf": 0.07,
    "bearing_ftf": 0.05,
    "lubrication_distress": 0.05,
    "gear_mesh_fault": 0.08,
    "cavitation_or_aeration": 0.05,
    "fluid_film_instability": 0.06,
}

@dataclass
class ConditionMachineMetadata:
    asset_type: str
    asset_id: str = "default"
    rpm: Optional[float] = None
    load_pct: Optional[float] = None
    axis: str = "radial"
    line_freq_hz: float = 50.0
    bearing_freqs_hz: Dict[str, float] = field(default_factory=dict)
    gear_mesh_freq_hz: Optional[float] = None
    vane_pass_freq_hz: Optional[float] = None
    blade_pass_freq_hz: Optional[float] = None

    def normalized_asset_type(self) -> str:
        v = self.asset_type.strip().lower()
        if v in {"fan", "blower"}:
            return v
        if v in CONDITION_ASSET_BLOCK_WEIGHTS:
            return v
        return "pump"

    def running_freq_hz(self) -> Optional[float]:
        return None if self.rpm is None else self.rpm / 60.0

@dataclass
class ConditionFeatureStats:
    median: float
    iqr: float

class ConditionBaseline:
    def __init__(self) -> None:
        self.stats_by_regime: Dict[Tuple[Any, Any], Dict[str, ConditionFeatureStats]] = {}
        self.global_stats: Dict[str, ConditionFeatureStats] = {}

    @staticmethod
    def infer_regime_id(metadata: ConditionMachineMetadata, rpm_bin_size: int = 100, load_bin_size: int = 10) -> Tuple[Optional[int], Optional[int]]:
        rpm_bin = None if metadata.rpm is None else int(metadata.rpm // rpm_bin_size) * rpm_bin_size
        load_bin = None if metadata.load_pct is None else int(metadata.load_pct // load_bin_size) * load_bin_size
        return rpm_bin, load_bin

    @classmethod
    def fit(cls, records: Iterable[Tuple[Tuple[Any, Any], Mapping[str, float]]]) -> "ConditionBaseline":
        baseline = cls()
        grouped: Dict[Tuple[Any, Any], Dict[str, List[float]]] = {}
        global_grouped: Dict[str, List[float]] = {}
        for regime_id, features in records:
            grouped.setdefault(regime_id, {})
            for key, value in features.items():
                grouped[regime_id].setdefault(key, []).append(float(value))
                global_grouped.setdefault(key, []).append(float(value))
        for regime_id, feat_map in grouped.items():
            baseline.stats_by_regime[regime_id] = {}
            for key, values in feat_map.items():
                arr = np.asarray(values, dtype=float)
                q75, q25 = np.percentile(arr, [75, 25])
                baseline.stats_by_regime[regime_id][key] = ConditionFeatureStats(float(np.median(arr)), max(float(q75 - q25), CONDITION_EPS))
        for key, values in global_grouped.items():
            arr = np.asarray(values, dtype=float)
            q75, q25 = np.percentile(arr, [75, 25])
            baseline.global_stats[key] = ConditionFeatureStats(float(np.median(arr)), max(float(q75 - q25), CONDITION_EPS))
        return baseline

    def normalize(self, regime_id: Tuple[Any, Any], features: Mapping[str, float]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        regime_stats = self.stats_by_regime.get(regime_id)
        if regime_stats is None and self.stats_by_regime:
            def _dist(cand: Tuple[Any, Any]) -> float:
                rpm_d = abs(float((cand[0] or 0)) - float((regime_id[0] or 0)))
                load_d = abs(float((cand[1] or 0)) - float((regime_id[1] or 0)))
                return rpm_d + 0.2 * load_d
            nearest = min(self.stats_by_regime.keys(), key=_dist)
            regime_stats = self.stats_by_regime.get(nearest, {})
        regime_stats = regime_stats or {}
        for key, value in features.items():
            stats = regime_stats.get(key) or self.global_stats.get(key)
            if stats is None:
                out[key] = 0.0
                continue
            z = (float(value) - stats.median) / (stats.iqr + CONDITION_EPS)
            out[key] = float(np.clip(z, 0.0, 6.0) / 6.0)
        return out

def _condition_weighted_sum(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        total += weight * values.get(key, 0.0)
        weight_sum += weight
    return float(total / (weight_sum + CONDITION_EPS))

def _condition_rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0

def _condition_crest_factor(x: np.ndarray) -> float:
    return float(np.max(np.abs(x)) / (_condition_rms(x) + CONDITION_EPS)) if np.asarray(x).size else 0.0

def _condition_entropy(x: np.ndarray, bins: int = 64) -> float:
    hist, _ = np.histogram(x, bins=bins, density=True)
    p = hist / (np.sum(hist) + CONDITION_EPS)
    p = p[p > 0]
    return float(-np.sum(p * np.log(p + CONDITION_EPS))) if p.size else 0.0

def _condition_butter_filter(x: np.ndarray, fs: float, low: Optional[float] = None, high: Optional[float] = None, order: int = 4) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if fs <= 0.0:
        return x.copy()
    nyq = fs / 2.0
    if low is None and high is None:
        return x.copy()
    if low is not None and high is not None:
        low = max(0.1, float(low))
        high = min(float(high), nyq * 0.98)
        if high <= low:
            return x.copy()
        wn = [low / nyq, high / nyq]
        btype = "band"
    elif low is not None:
        wn = max(0.1, float(low)) / nyq
        btype = "high"
    else:
        wn = min(float(high), nyq * 0.98) / nyq
        btype = "low"
    b, a = butter(order, wn, btype=btype)
    return filtfilt(b, a, x)

def _condition_integrate_acc_to_velocity(acc: np.ndarray, fs: float, hp_hz: float = 2.0) -> np.ndarray:
    vel = np.cumsum(np.asarray(acc, dtype=float)) * (1.0 / fs)
    vel = vel - np.mean(vel)
    return _condition_butter_filter(vel, fs, low=hp_hz)

def _condition_one_sided_spectrum(x: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0 or fs <= 0.0:
        return np.array([]), np.array([])
    w = np.hanning(n)
    spec = np.fft.rfft(x * w)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = (2.0 / np.sum(w)) * np.abs(spec)
    return freqs, amp

def _condition_peak_near(freqs: np.ndarray, amp: np.ndarray, target_hz: float, tol_hz: float) -> float:
    if target_hz <= 0.0 or freqs.size == 0:
        return 0.0
    mask = (freqs >= target_hz - tol_hz) & (freqs <= target_hz + tol_hz)
    return float(np.max(amp[mask])) if np.any(mask) else 0.0

def _condition_sum_harmonics(freqs: np.ndarray, amp: np.ndarray, base_hz: float, harmonics: int = 3, tol_hz: float = 1.0) -> float:
    return float(sum(_condition_peak_near(freqs, amp, base_hz * i, tol_hz) for i in range(1, harmonics + 1)))

def _condition_sideband_ratio(freqs: np.ndarray, amp: np.ndarray, center_hz: float, mod_hz: float, n_sidebands: int = 2, tol_hz: float = 1.0) -> float:
    if center_hz <= 0.0 or mod_hz <= 0.0:
        return 0.0
    center = _condition_peak_near(freqs, amp, center_hz, tol_hz)
    if center <= CONDITION_EPS:
        return 0.0
    sidebands = 0.0
    for k in range(1, n_sidebands + 1):
        sidebands += _condition_peak_near(freqs, amp, center_hz - k * mod_hz, tol_hz)
        sidebands += _condition_peak_near(freqs, amp, center_hz + k * mod_hz, tol_hz)
    return float(sidebands / (center + CONDITION_EPS))

def _condition_band_energy_from_spectrum(freqs: np.ndarray, amp: np.ndarray, low_hz: float, high_hz: float) -> float:
    if freqs.size == 0:
        return 0.0
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    return float(np.sum(np.square(amp[mask]))) if np.any(mask) else 0.0

def _condition_band_rms(x: np.ndarray, fs: float, low_hz: float, high_hz: float) -> float:
    return _condition_rms(_condition_butter_filter(x, fs, low=low_hz, high=high_hz))

def _condition_residual_tsa(x: np.ndarray, fs: float, running_hz: float) -> np.ndarray:
    if running_hz <= 0.0:
        return np.asarray(x, dtype=float)
    period = int(round(fs / running_hz))
    if period < 8 or len(x) < 3 * period:
        return np.asarray(x, dtype=float)
    usable = (len(x) // period) * period
    trimmed = np.asarray(x[:usable], dtype=float)
    reshaped = trimmed.reshape(-1, period)
    template = np.mean(reshaped, axis=0)
    return (reshaped - template[None, :]).reshape(-1)

class ConditionTrendTracker:
    def __init__(self, alpha: float = 0.2, k: float = 0.05, persistence_window: int = 10, abnormal_threshold: float = 0.4) -> None:
        self.alpha = alpha
        self.k = k
        self.persistence_window = persistence_window
        self.abnormal_threshold = abnormal_threshold
        self.ewma = 0.0
        self.cusum = 0.0
        self.persistence_buffer: List[float] = []
    def update(self, f_score: float) -> float:
        self.ewma = self.alpha * f_score + (1.0 - self.alpha) * self.ewma
        self.cusum = max(0.0, self.cusum + (f_score - self.k))
        self.persistence_buffer.append(float(f_score > self.abnormal_threshold))
        self.persistence_buffer = self.persistence_buffer[-self.persistence_window :]
        persistence_ratio = float(np.mean(self.persistence_buffer)) if self.persistence_buffer else 0.0
        trend_score = 0.50 * min(self.ewma, 1.0) + 0.25 * min(self.cusum, 1.0) + 0.25 * persistence_ratio
        return float(min(trend_score, 1.0))

class ConditionFeatureExtractor:
    def preprocess(self, acc: np.ndarray, fs: float) -> np.ndarray:
        x = detrend(np.asarray(acc, dtype=float))
        x = x - np.mean(x)
        return _condition_butter_filter(x, fs, low=2.0)
    def envelope(self, x: np.ndarray) -> np.ndarray:
        return np.abs(hilbert(x))
    def extract_basic(self, acc: np.ndarray, vel: np.ndarray) -> Dict[str, float]:
        return {"acc_rms": _condition_rms(acc), "vel_rms": _condition_rms(vel), "peak": float(np.max(np.abs(acc))) if acc.size else 0.0, "crest_factor": _condition_crest_factor(acc)}
    def extract_shaft(self, vel: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        freqs, amp = _condition_one_sided_spectrum(vel, fs)
        running = metadata.running_freq_hz()
        if running is None or running <= 0.0:
            return {"amp_1x": 0.0, "amp_2x": 0.0, "amp_3x": 0.0, "subharmonic_ratio": 0.0, "harmonic_energy_ratio": 0.0, "axial_radial_ratio": 1.0 if metadata.axis == "axial" else 0.0}
        tol = max(0.3, 0.03 * running)
        a1 = _condition_peak_near(freqs, amp, running, tol)
        a2 = _condition_peak_near(freqs, amp, 2.0 * running, tol)
        a3 = _condition_peak_near(freqs, amp, 3.0 * running, tol)
        sub = _condition_peak_near(freqs, amp, 0.5 * running, tol)
        return {"amp_1x": a1, "amp_2x": a2, "amp_3x": a3, "subharmonic_ratio": float(sub / (a1 + CONDITION_EPS)), "harmonic_energy_ratio": float((a2 + a3) / (a1 + CONDITION_EPS)), "axial_radial_ratio": 1.0 if metadata.axis.lower() == "axial" else 0.0}
    def extract_bearing(self, acc: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        nyq = fs / 2.0
        env_band_low = min(500.0, nyq * 0.2)
        env_band_high = min(5000.0, nyq * 0.9)
        if env_band_high <= env_band_low:
            env_band_low = min(50.0, nyq * 0.2)
            env_band_high = min(1000.0, nyq * 0.9)
        env = self.envelope(_condition_butter_filter(acc, fs, low=env_band_low, high=env_band_high))
        env_freqs, env_amp = _condition_one_sided_spectrum(env - np.mean(env), fs)
        bearing_freqs = metadata.bearing_freqs_hz
        defect_tolerance = 1.0
        bpfo = _condition_peak_near(env_freqs, env_amp, bearing_freqs.get("BPFO", 0.0), defect_tolerance) if "BPFO" in bearing_freqs else 0.0
        bpfi = _condition_peak_near(env_freqs, env_amp, bearing_freqs.get("BPFI", 0.0), defect_tolerance) if "BPFI" in bearing_freqs else 0.0
        bsf = _condition_peak_near(env_freqs, env_amp, bearing_freqs.get("BSF", 0.0), defect_tolerance) if "BSF" in bearing_freqs else 0.0
        ftf = _condition_peak_near(env_freqs, env_amp, bearing_freqs.get("FTF", 0.0), defect_tolerance) if "FTF" in bearing_freqs else 0.0
        hf_low = min(1000.0, nyq * 0.3)
        hf_high = min(8000.0, nyq * 0.95)
        hf_rms_val = _condition_band_rms(acc, fs, hf_low, hf_high) if hf_high > hf_low else _condition_rms(acc)
        return {"env_rms": _condition_rms(env), "env_kurtosis": float(kurtosis(env, fisher=False, bias=False)) if env.size >= 4 else 0.0, "hf_rms": hf_rms_val, "bpfo_band_energy": bpfo, "bpfi_band_energy": bpfi, "bsf_band_energy": bsf, "ftf_band_energy": ftf, "env_entropy": _condition_entropy(env)}
    def extract_gear(self, acc: np.ndarray, vel: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        gmf = metadata.gear_mesh_freq_hz or 0.0
        if gmf <= 0.0:
            return {"gmf_amp": 0.0, "gmf_harmonics": 0.0, "gmf_sideband_ratio": 0.0, "residual_tsa_rms": 0.0, "residual_tsa_kurtosis": 0.0, "mesh_band_entropy": 0.0}
        freqs, amp = _condition_one_sided_spectrum(vel, fs)
        running = metadata.running_freq_hz() or 0.0
        residual = _condition_residual_tsa(acc, fs, running) if running > 0.0 else np.asarray(acc, dtype=float)
        mesh_band = _condition_butter_filter(acc, fs, low=max(10.0, gmf * 0.7), high=min(fs / 2.0 * 0.95, gmf * 1.3))
        tol = max(1.0, 0.02 * gmf)
        return {"gmf_amp": _condition_peak_near(freqs, amp, gmf, tol), "gmf_harmonics": _condition_sum_harmonics(freqs, amp, gmf, harmonics=3, tol_hz=tol), "gmf_sideband_ratio": _condition_sideband_ratio(freqs, amp, gmf, running, n_sidebands=2, tol_hz=tol) if running > 0.0 else 0.0, "residual_tsa_rms": _condition_rms(residual), "residual_tsa_kurtosis": float(kurtosis(residual, fisher=False, bias=False)) if residual.size >= 4 else 0.0, "mesh_band_entropy": _condition_entropy(mesh_band)}
    def extract_hydraulic(self, acc: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        vpf = metadata.vane_pass_freq_hz or 0.0
        freqs, amp = _condition_one_sided_spectrum(acc, fs)
        running = metadata.running_freq_hz() or 0.0
        broadband_hf_energy = _condition_band_energy_from_spectrum(freqs, amp, 1000.0, min(fs / 2.0 * 0.95, 8000.0))
        cavitation_band_energy = _condition_band_energy_from_spectrum(freqs, amp, 2000.0, min(fs / 2.0 * 0.95, 10000.0))
        if vpf <= 0.0:
            return {"vpf_amp": 0.0, "vpf_harmonics": 0.0, "vpf_sideband_ratio": 0.0, "broadband_hf_energy": broadband_hf_energy, "cavitation_band_energy": cavitation_band_energy}
        tol = max(1.0, 0.02 * vpf)
        return {"vpf_amp": _condition_peak_near(freqs, amp, vpf, tol), "vpf_harmonics": _condition_sum_harmonics(freqs, amp, vpf, harmonics=3, tol_hz=tol), "vpf_sideband_ratio": _condition_sideband_ratio(freqs, amp, vpf, running, n_sidebands=2, tol_hz=tol) if running > 0.0 else 0.0, "broadband_hf_energy": broadband_hf_energy, "cavitation_band_energy": cavitation_band_energy}
    def extract_aero(self, acc: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        bpf = metadata.blade_pass_freq_hz or 0.0
        freqs, amp = _condition_one_sided_spectrum(acc, fs)
        running = metadata.running_freq_hz() or 0.0
        broadband_aero_energy = _condition_band_energy_from_spectrum(freqs, amp, 300.0, min(fs / 2.0 * 0.95, 3000.0))
        if bpf <= 0.0:
            return {"bpf_amp": 0.0, "bpf_harmonics": 0.0, "bpf_sideband_ratio": 0.0, "broadband_aero_energy": broadband_aero_energy}
        tol = max(1.0, 0.02 * bpf)
        return {"bpf_amp": _condition_peak_near(freqs, amp, bpf, tol), "bpf_harmonics": _condition_sum_harmonics(freqs, amp, bpf, harmonics=3, tol_hz=tol), "bpf_sideband_ratio": _condition_sideband_ratio(freqs, amp, bpf, running, n_sidebands=2, tol_hz=tol) if running > 0.0 else 0.0, "broadband_aero_energy": broadband_aero_energy}
    def extract_electrical(self, vel: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, float]:
        freqs, amp = _condition_one_sided_spectrum(vel, fs)
        line = metadata.line_freq_hz
        running = metadata.running_freq_hz() or 0.0
        tol = max(0.5, 0.02 * line)
        return {"line_freq_vib": _condition_peak_near(freqs, amp, line, tol), "twice_line_freq_vib": _condition_peak_near(freqs, amp, 2.0 * line, tol), "electrical_sideband_ratio": _condition_sideband_ratio(freqs, amp, 2.0 * line, running, n_sidebands=2, tol_hz=tol) if running > 0.0 else 0.0}
    def extract_all(self, acc: np.ndarray, fs: float, metadata: ConditionMachineMetadata) -> Dict[str, Dict[str, float]]:
        acc_pp = self.preprocess(acc, fs)
        vel = _condition_integrate_acc_to_velocity(acc_pp, fs)
        out = {"severity": self.extract_basic(acc_pp, vel), "shaft": self.extract_shaft(vel, fs, metadata), "bearing": self.extract_bearing(acc_pp, fs, metadata)}
        asset_type = metadata.normalized_asset_type()
        if asset_type == "motor":
            out["electrical"] = self.extract_electrical(vel, fs, metadata)
        if asset_type == "pump":
            out["hydraulic"] = self.extract_hydraulic(acc_pp, fs, metadata)
        if asset_type == "gearbox":
            out["gear"] = self.extract_gear(acc_pp, vel, fs, metadata)
        if asset_type in {"fan", "blower"}:
            out["aero"] = self.extract_aero(acc_pp, fs, metadata)
        return out

class ConditionHealthScorer:
    def __init__(self, baseline: ConditionBaseline, trend_trackers: Optional[MutableMapping[str, ConditionTrendTracker]] = None) -> None:
        self.extractor = ConditionFeatureExtractor()
        self.baseline = baseline
        self.trend_trackers = trend_trackers if trend_trackers is not None else {}
    def _get_tracker(self, asset_id: str) -> ConditionTrendTracker:
        if asset_id not in self.trend_trackers:
            self.trend_trackers[asset_id] = ConditionTrendTracker()
        return self.trend_trackers[asset_id]
    def score_window(self, acc: np.ndarray, metadata: ConditionMachineMetadata, fs: float) -> Dict[str, Any]:
        asset_type = metadata.normalized_asset_type()
        regime_id = ConditionBaseline.infer_regime_id(metadata)
        raw_feature_families = self.extractor.extract_all(np.asarray(acc, dtype=float), fs, metadata)
        normalized_feature_families = {family: self.baseline.normalize(regime_id, features) for family, features in raw_feature_families.items()}
        subsystem_scores = {
            "severity": _condition_weighted_sum(normalized_feature_families.get("severity", {}), CONDITION_SEVERITY_FEATURE_WEIGHTS),
            "shaft": _condition_weighted_sum(normalized_feature_families.get("shaft", {}), CONDITION_SHAFT_FEATURE_WEIGHTS),
            "bearing": _condition_weighted_sum(normalized_feature_families.get("bearing", {}), CONDITION_BEARING_FEATURE_WEIGHTS),
        }
        if asset_type == "motor":
            subsystem_scores["electrical"] = _condition_weighted_sum(normalized_feature_families.get("electrical", {}), CONDITION_ELECTRICAL_FEATURE_WEIGHTS)
        if asset_type == "pump":
            subsystem_scores["hydraulic"] = _condition_weighted_sum(normalized_feature_families.get("hydraulic", {}), CONDITION_HYDRAULIC_FEATURE_WEIGHTS)
        if asset_type == "gearbox":
            subsystem_scores["gear"] = _condition_weighted_sum(normalized_feature_families.get("gear", {}), CONDITION_GEAR_FEATURE_WEIGHTS)
        if asset_type in {"fan", "blower"}:
            subsystem_scores["aero"] = _condition_weighted_sum(normalized_feature_families.get("aero", {}), CONDITION_AERO_FEATURE_WEIGHTS)
        tracker = self._get_tracker(metadata.asset_id)
        fault_blocks = {k: v for k, v in subsystem_scores.items() if k != "severity"}
        fused_fault_score = float(np.mean(list(fault_blocks.values()))) if fault_blocks else subsystem_scores.get("severity", 0.0)
        trend_score = tracker.update(fused_fault_score)
        weights = CONDITION_ASSET_BLOCK_WEIGHTS[asset_type]
        abnormality = sum(weights.get(k, 0.0) * (trend_score if k == "trend" else subsystem_scores.get(k, 0.0)) for k in weights) / (sum(weights.values()) + CONDITION_EPS)
        health = float(np.clip(100.0 * np.exp(-abnormality), 0.0, 100.0))
        alarm = next((label for threshold, label in CONDITION_SCORE_BANDS if health < threshold), "normal")
        total_features = sum(len(v) for v in normalized_feature_families.values())
        nonzero_features = sum(sum(1 for vv in v.values() if vv > 0.0) for v in normalized_feature_families.values())
        coverage = nonzero_features / (total_features + CONDITION_EPS)
        spread = float(np.std(list(subsystem_scores.values()))) if subsystem_scores else 0.0
        confidence = float(np.clip(0.6 * min(coverage * 2.0, 1.0) + 0.4 * min(spread * 2.0, 1.0), 0.0, 1.0))
        return {"asset_id": metadata.asset_id, "asset_type": asset_type, "regime_id": regime_id, "health": health, "abnormality": float(abnormality), "alarm": alarm, "dominant_fault_family": max(subsystem_scores, key=subsystem_scores.get) if subsystem_scores else "unknown", "confidence": confidence, "trend_score": trend_score, "subscores": subsystem_scores, "raw_features": raw_feature_families, "normalized_features": normalized_feature_families}

def _condition_waveform_and_fs(signal: AxisSignal) -> Tuple[Optional[np.ndarray], float]:
    source = signal.acceleration_waveform if signal.acceleration_waveform is not None else signal.waveform
    if source is None:
        return None, 0.0
    arr = np.asarray(source, dtype=float).reshape(-1)
    if arr.size < 64:
        return None, 0.0
    fs = float(signal.waveform_sample_rate_hz or 0.0)
    if fs <= 0.0 and signal.freqs_hz:
        fs = float(max(signal.freqs_hz) * 2.0)
    return (arr, fs) if fs > 0.0 else (None, 0.0)

def _condition_metadata_from_context(asset: AssetDefinition, sensor: SensorMeasurement, axis_name: str) -> ConditionMachineMetadata:
    rpm = sensor.local_rpm or asset.running_rpm
    line_freq = float(asset.motors[0].line_frequency_hz) if asset.motors else 50.0
    bearing_freqs: Dict[str, float] = {}
    if sensor.bearing_id:
        bearing = next((b for b in asset.bearings if b.bearing_id == sensor.bearing_id), None)
        if bearing and rpm:
            bearing_freqs = {k.upper(): float(v) for k, v in bearing_fault_frequencies_hz(rpm, bearing).items()}
    gear_mesh = None
    if sensor.gear_stage_id:
        stage = next((g for g in asset.gear_stages if g.gear_stage_id == sensor.gear_stage_id), None)
        if stage:
            gear_mesh = gear_mesh_frequency_hz(stage.stage_input_rpm or rpm or asset.running_rpm, stage)
    vane_pass = None
    if asset.hydraulic_elements:
        hyd = asset.hydraulic_elements[0]
        vane_pass = hydraulic_pass_frequency_hz(hyd.local_rpm or rpm or asset.running_rpm, hyd)
    return ConditionMachineMetadata(asset_type=asset.asset_type, asset_id=asset.asset_id, rpm=rpm, load_pct=float(asset.metadata.get("load_pct")) if isinstance(asset.metadata.get("load_pct"), (int, float)) else None, axis="axial" if axis_name.lower() == "axial" else "radial", line_freq_hz=line_freq, bearing_freqs_hz=bearing_freqs, gear_mesh_freq_hz=gear_mesh, vane_pass_freq_hz=vane_pass, blade_pass_freq_hz=vane_pass)

def build_condition_baseline_from_assets(assets: Iterable[AssetDefinition]) -> ConditionBaseline:
    extractor = ConditionFeatureExtractor()
    records: List[Tuple[Tuple[Any, Any], Dict[str, float]]] = []
    for asset in assets:
        for sensor in asset.sensors:
            for axis_name, signal in sensor.directions.items():
                arr, fs = _condition_waveform_and_fs(signal)
                if arr is None or fs <= 0.0:
                    continue
                md = _condition_metadata_from_context(asset, sensor, axis_name)
                regime_id = ConditionBaseline.infer_regime_id(md)
                families = extractor.extract_all(arr, fs, md)
                flat = {key: float(value) for features in families.values() for key, value in features.items()}
                records.append((regime_id, flat))
    return ConditionBaseline.fit(records)

def compute_asset_condition_summary(asset: AssetDefinition, condition_scorer: ConditionHealthScorer) -> Optional[Dict[str, Any]]:
    window_results: List[Dict[str, Any]] = []
    for sensor in asset.sensors:
        for axis_name, signal in sensor.directions.items():
            arr, fs = _condition_waveform_and_fs(signal)
            if arr is None or fs <= 0.0:
                continue
            md = _condition_metadata_from_context(asset, sensor, axis_name)
            scored = condition_scorer.score_window(arr, md, fs)
            scored["sensor_id"] = sensor.sensor_id
            scored["axis"] = axis_name
            window_results.append(scored)
    if not window_results:
        return None
    family_keys = {k for wr in window_results for k in wr.get("subscores", {}).keys()}
    aggregate_subscores = {key: float(np.mean([wr.get("subscores", {}).get(key, 0.0) for wr in window_results])) for key in family_keys}
    dominant_family = max(aggregate_subscores, key=aggregate_subscores.get) if aggregate_subscores else "unknown"
    worst = max(window_results, key=lambda x: x["abnormality"])
    return {"health": float(min(wr["health"] for wr in window_results)), "abnormality": float(worst["abnormality"]), "alarm": str(worst["alarm"]), "trend_score": float(max(wr["trend_score"] for wr in window_results)), "confidence": float(np.mean([wr["confidence"] for wr in window_results])), "dominant_fault_family": dominant_family, "subscores": aggregate_subscores, "window_results": window_results}

def _severity_label_from_score(score_0_1: float) -> str:
    if score_0_1 >= 0.75:
        return "critical"
    if score_0_1 >= 0.55:
        return "high"
    if score_0_1 >= 0.35:
        return "medium"
    return "low"

def _urgency_from_severity(score_0_1: float, condition_alarm: Optional[str], fault_key: str) -> str:
    urgent_faults = {"rotor_rub", "bearing_bpfo", "bearing_bpfi", "bearing_bsf", "gear_mesh_fault", "cavitation_or_aeration"}
    label = _severity_label_from_score(score_0_1)
    if label == "critical":
        return "immediate_review"
    if condition_alarm == "critical" or (fault_key in urgent_faults and label in {"high", "critical"}):
        return "urgent"
    if label == "high":
        return "urgent"
    if label == "medium":
        return "plan"
    return "monitor"

def _diagnostic_segment_for_result(r: FaultResult) -> str:
    if r.confidence in {"high", "medium"} and r.score >= 60.0:
        return "primary"
    if r.confidence != "none" and r.score >= 35.0:
        return "secondary"
    return "low_confidence"

def _condition_family_for_fault(fault_key: str) -> str:
    return FAULT_TO_CONDITION_FAMILY.get(fault_key, "shaft")

def _apply_condition_severity(asset: AssetDefinition, results: List[FaultResult], condition_scorer: Optional[ConditionHealthScorer]) -> Optional[Dict[str, Any]]:
    summary = compute_asset_condition_summary(asset, condition_scorer) if condition_scorer is not None else None
    for r in results:
        family = _condition_family_for_fault(r.fault_key)
        weights = SEVERITY_FAMILY_WEIGHTS.get(family, SEVERITY_FAMILY_WEIGHTS["shaft"])
        diag = _clamp(r.score / 100.0, 0.0, 1.0)
        cond = float(summary["abnormality"]) if summary is not None else 0.0
        fam = float(summary["subscores"].get(family, 0.0)) if summary is not None else 0.0
        trend = float(summary["trend_score"]) if summary is not None else 0.0
        risk_bonus = float(FAULT_RISK_BONUS.get(r.fault_key, 0.0))
        sev_before_conf = weights["condition"] * cond + weights["diagnostic"] * diag + weights["family"] * fam + weights["trend"] * trend + risk_bonus
        conf_factor = {"high": 1.0, "medium": 0.92, "low": 0.78, "none": 0.65}.get(r.confidence, 0.9)
        sev = _clamp(sev_before_conf * conf_factor, 0.0, 1.0)
        if summary is not None:
            r.condition_health = float(summary["health"])
            r.condition_abnormality = float(summary["abnormality"])
            r.condition_alarm = str(summary["alarm"])
            r.condition_confidence = float(summary["confidence"])
            r.family_subscore = fam
        r.fault_severity_score = float(round(100.0 * sev, 1))
        r.fault_severity_label = _severity_label_from_score(sev)
        r.urgency = _urgency_from_severity(sev, r.condition_alarm, r.fault_key)
        r.diagnostic_segment = _diagnostic_segment_for_result(r)
        r.fault_explanation = {
            "severity_components": {
                "weights": {key: float(value) for key, value in weights.items()},
                "condition_component": float(round(weights["condition"] * cond, 4)),
                "diagnostic_component": float(round(weights["diagnostic"] * diag, 4)),
                "family_component": float(round(weights["family"] * fam, 4)),
                "trend_component": float(round(weights["trend"] * trend, 4)),
                "risk_bonus": float(round(risk_bonus, 4)),
                "confidence_factor": float(round(conf_factor, 4)),
                "severity_before_confidence": float(round(sev_before_conf, 4)),
                "severity_after_confidence": float(round(sev, 4)),
            }
        }
    return summary


def _top_metric_items(metrics: Mapping[str, float], n: int = 5) -> List[Dict[str, float]]:
    items: List[Tuple[str, float]] = []
    for key, value in metrics.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        items.append((key, v))
    items.sort(key=lambda kv: (-abs(kv[1]), kv[0]))
    return [{"metric": key, "value": float(round(value, 4))} for key, value in items[:n]]


def _family_feature_weights(family: str) -> Mapping[str, float]:
    return {
        "severity": CONDITION_SEVERITY_FEATURE_WEIGHTS,
        "shaft": CONDITION_SHAFT_FEATURE_WEIGHTS,
        "bearing": CONDITION_BEARING_FEATURE_WEIGHTS,
        "gear": CONDITION_GEAR_FEATURE_WEIGHTS,
        "hydraulic": CONDITION_HYDRAULIC_FEATURE_WEIGHTS,
        "aero": CONDITION_AERO_FEATURE_WEIGHTS,
        "electrical": CONDITION_ELECTRICAL_FEATURE_WEIGHTS,
    }.get(family, CONDITION_SHAFT_FEATURE_WEIGHTS)


def _rank_diagnostic_features(metrics: Mapping[str, float], n: int = 5) -> List[Dict[str, float]]:
    scored: List[Tuple[str, float, float]] = []
    for key, value in metrics.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        scored.append((str(key), v, abs(v)))
    total = sum(s for _, _, s in scored) + EPS
    scored.sort(key=lambda row: (-row[2], row[0]))
    out: List[Dict[str, float]] = []
    for rank, (key, value, strength) in enumerate(scored[:n], start=1):
        out.append({
            "rank": rank,
            "feature": key,
            "value": float(round(value, 4)),
            "relative_contribution": float(round(strength / total, 4)),
        })
    return out


def _rank_condition_features(
    family: str,
    normalized_family_features: Mapping[str, float],
    raw_family_features: Mapping[str, float],
    n: int = 5,
) -> List[Dict[str, float]]:
    weights = _family_feature_weights(family)
    scored: List[Tuple[str, float, float, float, float]] = []
    for key, weight in weights.items():
        abnormality = float(normalized_family_features.get(key, 0.0) or 0.0)
        raw_value = float(raw_family_features.get(key, 0.0) or 0.0)
        contribution = max(0.0, abnormality) * float(weight)
        scored.append((str(key), raw_value, abnormality, float(weight), contribution))
    total = sum(row[4] for row in scored) + EPS
    scored.sort(key=lambda row: (-row[4], row[0]))
    out: List[Dict[str, float]] = []
    for rank, (key, raw_value, abnormality, weight, contribution) in enumerate(scored[:n], start=1):
        out.append({
            "rank": rank,
            "feature": key,
            "raw_value": float(round(raw_value, 4)),
            "abnormality": float(round(abnormality, 4)),
            "weight": float(round(weight, 4)),
            "weighted_contribution": float(round(contribution, 4)),
            "relative_contribution": float(round(contribution / total, 4)),
        })
    return out


def _rank_suppressors(result: FaultResult, n: int = 5) -> List[Dict[str, Any]]:
    suppressors: List[Dict[str, Any]] = []
    for rank, limitation in enumerate(result.limitations[:n], start=1):
        suppressors.append({"rank": rank, "reason": str(limitation)})
    return suppressors


def _mean_feature_map(window_results: List[Dict[str, Any]], family: str, feature_key: str) -> Dict[str, float]:
    acc: Dict[str, List[float]] = {}
    for wr in window_results:
        fam = wr.get(feature_key, {}).get(family, {})
        if not isinstance(fam, Mapping):
            continue
        for key, value in fam.items():
            try:
                acc.setdefault(str(key), []).append(float(value))
            except (TypeError, ValueError):
                continue
    return {key: float(np.mean(values)) for key, values in acc.items() if values}


def _build_fault_explanation(
    result: FaultResult,
    pattern_profile: Optional[PatternFamilyProfile],
    condition_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    family = _condition_family_for_fault(result.fault_key)
    window_results = condition_summary.get("window_results", []) if condition_summary else []
    normalized_family_features = _mean_feature_map(window_results, family, "normalized_features")
    raw_family_features = _mean_feature_map(window_results, family, "raw_features")
    explanation: Dict[str, Any] = {
        "summary": (
            f"{result.fault_key} on {result.target} scored {result.score:.1f} with {result.confidence} confidence"
            + (f" and fault severity {result.fault_severity_score:.1f} ({result.fault_severity_label})" if result.fault_severity_score is not None and result.fault_severity_label else "")
            + "."
        ),
        "diagnostic_segment": result.diagnostic_segment,
        "primary_evidence": list(result.evidence[:5]),
        "why_not_higher": list(result.limitations[:3]),
        "top_supporting_metrics": _top_metric_items(result.supporting_metrics, n=5),
        "top_diagnostic_features": _rank_diagnostic_features(result.supporting_metrics, n=5),
        "condition_family": family,
        "top_condition_feature_abnormalities": _top_metric_items(normalized_family_features, n=5),
        "top_condition_feature_raw_values": _top_metric_items(raw_family_features, n=5),
        "top_condition_features": _rank_condition_features(family, normalized_family_features, raw_family_features, n=5),
        "top_suppressors": _rank_suppressors(result, n=5),
        "next_checks": list(result.recommendations[:3]),
    }
    if pattern_profile is not None:
        explanation["pattern_context"] = {
            "dominant_family": pattern_profile.dominant_family,
            "dominant_direction": pattern_profile.dominant_direction,
            "evidence": list(pattern_profile.evidence[:4]),
            "metrics": {k: float(round(v, 4)) for k, v in pattern_profile.metrics.items()},
        }
    if result.fault_severity_score is not None:
        explanation.setdefault("severity_components", {})
    return explanation


def _apply_explainability(
    results: List[FaultResult],
    pattern_profile: Optional[PatternFamilyProfile],
    condition_summary: Optional[Dict[str, Any]],
) -> None:
    for result in results:
        explanation = _build_fault_explanation(result, pattern_profile, condition_summary)
        if result.condition_health is not None or result.fault_severity_score is not None:
            explanation["severity_components"] = {
                "condition_health": float(round(result.condition_health, 3)) if result.condition_health is not None else None,
                "condition_abnormality": float(round(result.condition_abnormality, 4)) if result.condition_abnormality is not None else None,
                "condition_alarm": result.condition_alarm,
                "family_subscore": float(round(result.family_subscore, 4)) if result.family_subscore is not None else None,
                "fault_severity_score": float(round(result.fault_severity_score, 3)) if result.fault_severity_score is not None else None,
                "fault_severity_label": result.fault_severity_label,
                "urgency": result.urgency,
            }
        result.fault_explanation = explanation


def explain_result(result: FaultResult) -> str:
    exp = result.fault_explanation or {}
    top_diag = exp.get("top_diagnostic_features", [])[:3]
    diag_text = ", ".join(
        f"{m['feature']}={m['value']:.3f} (share={m['relative_contribution']:.2f})" for m in top_diag
    ) if top_diag else "no top diagnostic features captured"
    top_cond = exp.get("top_condition_features", [])[:2]
    cond_text = ", ".join(
        f"{m['feature']}={m['abnormality']:.3f} abnormal" for m in top_cond
    ) if top_cond else ""
    sev = exp.get("severity_components", {})
    sev_text = ""
    if sev:
        cond_alarm = sev.get("condition_alarm")
        cond_health = sev.get("condition_health")
        fam = sev.get("family_subscore")
        sev_text = f" Condition backbone: alarm={cond_alarm}, health={cond_health}, family_subscore={fam}."
    pattern = exp.get("pattern_context", {})
    pattern_text = ""
    if pattern:
        pattern_text = f" Pattern context: {pattern.get('dominant_family')} / {pattern.get('dominant_direction')}."
    suppressors = exp.get("top_suppressors", [])[:2]
    suppressor_text = f" Suppressors: {'; '.join(s['reason'] for s in suppressors)}." if suppressors else ""
    extra_cond = f" Top condition features: {cond_text}." if cond_text else ""
    return f"Top diagnostic features: {diag_text}.{extra_cond}{sev_text}{pattern_text}{suppressor_text}"

def segment_diagnostic_results(results: List[FaultResult]) -> Dict[str, List[FaultResult]]:
    buckets = {"primary": [], "secondary": [], "low_confidence": []}
    for r in results:
        buckets.setdefault(r.diagnostic_segment, []).append(r)
    for key in buckets:
        buckets[key].sort(key=lambda rr: (-(rr.fault_severity_score or rr.score), -rr.score, rr.fault_key, rr.target))
    return buckets

# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------


def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
) -> List[FaultResult]:
    """Diagnose one rotating asset and optionally enrich it with condition severity."""
    results: List[FaultResult] = []
    pattern_profile = classify_asset_pattern(asset)
    asset.metadata["_pattern_classifier"] = pattern_profile.as_dict()

    for fault_key in [
        "unbalance",
        "misalignment",
        "looseness_type_a_base_structure",
        "looseness_type_b_pedestal_support",
        "looseness_type_c_rotating_fit",
        "soft_foot_or_frame_distortion",
        "bent_shaft_or_bow",
        "resonance_or_structural_amplification",
        "rotor_rub",
        "motor_electrical_forcing",
    ]:
        results.append(diagnose_asset_wide_fault(asset, fault_key))

    for bearing in asset.bearings:
        for fault_key in [
            "lubrication_distress",
            "fluid_film_instability" if bearing.bearing_type == "fluid_film" else None,
            "thrust_bearing_or_axial_overload" if (bearing.is_thrust_bearing or bearing.bearing_type == "thrust") else None,
            "bearing_bpfo" if bearing.bearing_type == "rolling" else None,
            "bearing_bpfi" if bearing.bearing_type == "rolling" else None,
            "bearing_bsf" if bearing.bearing_type == "rolling" else None,
            "bearing_ftf" if bearing.bearing_type == "rolling" else None,
        ]:
            if fault_key:
                results.append(diagnose_bearing_local_fault(asset, fault_key, bearing))

    for stage in asset.gear_stages:
        results.append(diagnose_gear_fault(asset, stage))

    for hydraulic in asset.hydraulic_elements:
        results.append(diagnose_hydraulic_fault(asset, "hydraulic_vane_or_blade_pass", hydraulic))
        results.append(diagnose_hydraulic_fault(asset, "cavitation_or_aeration", hydraulic))

    _postprocess_results(asset, results)
    _annotate_results(results)
    condition_summary = _apply_condition_severity(asset, results, condition_scorer)
    _apply_explainability(results, pattern_profile, condition_summary)

    filtered = [r for r in results if r.score >= minimum_score and r.confidence != "none"]
    filtered.sort(key=lambda r: (-(r.fault_severity_score or r.score), -r.score, r.fault_key, r.target))
    return filtered


def summarize_results(results: List[FaultResult]) -> str:
    if not results:
        return "No diagnosis crossed the minimum score threshold."
    buckets = segment_diagnostic_results(results)
    lines = ["Asset diagnosis summary", "======================", ""]
    for title, key in [("Primary", "primary"), ("Secondary", "secondary"), ("Low confidence", "low_confidence")]:
        lines.append(title)
        lines.append("-" * len(title))
        if not buckets.get(key):
            lines.append("  none")
            lines.append("")
            continue
        for idx, r in enumerate(buckets[key], start=1):
            sev = f" | fault_severity={r.fault_severity_score:.1f} ({r.fault_severity_label})" if r.fault_severity_score is not None else ""
            cond = f" | condition={r.condition_alarm}:{r.condition_health:.1f}" if r.condition_health is not None and r.condition_alarm is not None else ""
            fam = f" | family_subscore={r.family_subscore:.2f}" if r.family_subscore is not None else ""
            lines.append(
                f"{idx}. {r.fault_key} | target={r.target} | scope={r.scope} | score={r.score:.1f} | confidence={r.confidence}{sev} | urgency={r.urgency}{cond}{fam}"
            )
            if r.sensors_used:
                lines.append(f"   sensors: {', '.join(r.sensors_used)}")
            lines.append(f"   explain: {explain_result(r)}")
            for e in r.evidence[:4]:
                lines.append(f"   - {e}")
            for lim in r.limitations[:2]:
                lines.append(f"   ! {lim}")
            for rec in r.recommendations[:3]:
                lines.append(f"   > {rec}")
            lines.append("")
    return "\n".join(lines)


def result_to_dict(r: FaultResult) -> Dict[str, Any]:
    return {
        "fault_key": r.fault_key,
        "target": r.target,
        "scope": r.scope,
        "score": round(r.score, 1),
        "confidence": r.confidence,

        "fault_severity": {
            "score": round(r.fault_severity_score, 1) if r.fault_severity_score is not None else None,
            "label": r.fault_severity_label,
        },

        "urgency": r.urgency,

        "condition": {
            "alarm": r.condition_alarm,
            "health": round(r.condition_health, 1) if r.condition_health is not None else None,
        },

        "family_subscore": round(r.family_subscore, 2) if r.family_subscore is not None else None,

        "sensors_used": r.sensors_used or [],

        "explanation": explain_result(r),

        "evidence": r.evidence[:4] if r.evidence else [],

        "limitations": r.limitations[:2] if r.limitations else [],

        "recommendations": r.recommendations[:3] if r.recommendations else [],
    }


def summarize_results_structured(results: List[FaultResult]) -> Dict[str, Any]:
    if not results:
        return {
            "status": "no_diagnosis",
            "message": "No diagnosis crossed the minimum score threshold.",
            "summary": {
                "total_results": 0,
                "primary_count": 0,
                "secondary_count": 0,
                "low_confidence_count": 0,
            },
            "diagnostics": {
                "primary": [],
                "secondary": [],
                "low_confidence": [],
            },
        }

    buckets = segment_diagnostic_results(results)

    diagnostics = {
        "primary": [result_to_dict(r) for r in buckets.get("primary", [])],
        "secondary": [result_to_dict(r) for r in buckets.get("secondary", [])],
        "low_confidence": [result_to_dict(r) for r in buckets.get("low_confidence", [])],
    }

    return {
        "status": "diagnosis_available",
        "message": "Asset diagnosis summary generated successfully.",
        "summary": {
            "total_results": len(results),
            "primary_count": len(diagnostics["primary"]),
            "secondary_count": len(diagnostics["secondary"]),
            "low_confidence_count": len(diagnostics["low_confidence"]),
        },
        "diagnostics": diagnostics,
    }

# ---------------------------------------------------------------------------
# Example
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # Minimal synthetic example showing how to structure the input.
    freq = np.linspace(0, 500, 5001)
    shaft_hz = 30.0
    spectrum = 0.05 * np.ones_like(freq)
    spectrum += 1.8 * np.exp(-0.5 * ((freq - shaft_hz) / 0.7) ** 2)      # 1x
    spectrum += 0.30 * np.exp(-0.5 * ((freq - 2 * shaft_hz) / 0.7) ** 2)  # 2x
    waveform = np.sin(2 * np.pi * shaft_hz * np.linspace(0, 1, 4096))

    sensor = SensorMeasurement(
        sensor_id="MTR_DE_01",
        component_id="motor_1",
        component_type="motor",
        location_tag="motor_de",
        installed_on="bearing_housing",
        surface_temperature_c=66.0,
        bearing_id="BRG_MTR_DE",
        is_coupling_end=True,
        directions={
            "horizontal": AxisSignal("horizontal", freq.tolist(), spectrum.tolist(), waveform=waveform.tolist()),
            "vertical": AxisSignal("vertical", freq.tolist(), (0.8 * spectrum).tolist(), waveform=waveform.tolist()),
            "axial": AxisSignal("axial", freq.tolist(), (0.35 * spectrum).tolist(), waveform=waveform.tolist()),
        },
    )

    asset = AssetDefinition(
        asset_id="motor_pump_train_01",
        asset_type="motor_pump_train",
        running_rpm=1800.0,
        sensors=[sensor],
        bearings=[
            BearingDefinition(
                bearing_id="BRG_MTR_DE",
                component_id="motor_1",
                bearing_type="rolling",
                rolling_elements=8,
                ball_diameter_mm=9.5,
                pitch_diameter_mm=42.0,
                contact_angle_deg=0.0,
            )
        ],
        motors=[MotorDefinition(component_id="motor_1", line_frequency_hz=50.0, poles=4, slip_pct=1.5)],
    )

    out = diagnose_asset(asset, minimum_score=20.0)
    print(summarize_results_structured(out))

# ---------------------------------------------------------------------------
# Gearbox expansion patch (merged)
# ---------------------------------------------------------------------------

# Added gear-local sub-faults:
# - gear_misalignment
# - gear_eccentricity
# - gear_backlash
# - gear_tooth_wear
# - gear_tooth_damage_localized

FAULT_LIBRARY.update({
    "gear_misalignment": {"scope": "gear_local", "phase_cap": "medium"},
    "gear_eccentricity": {"scope": "gear_local", "phase_cap": "medium"},
    "gear_backlash": {"scope": "gear_local", "phase_cap": "medium"},
    "gear_tooth_wear": {"scope": "gear_local", "phase_cap": "high"},
    "gear_tooth_damage_localized": {"scope": "gear_local", "phase_cap": "high"},
})

FAULT_TO_CONDITION_FAMILY.update({
    "gear_misalignment": "gear",
    "gear_eccentricity": "gear",
    "gear_backlash": "gear",
    "gear_tooth_wear": "gear",
    "gear_tooth_damage_localized": "gear",
})

FAULT_RISK_BONUS.update({
    "gear_misalignment": 0.06,
    "gear_eccentricity": 0.05,
    "gear_backlash": 0.06,
    "gear_tooth_wear": 0.08,
    "gear_tooth_damage_localized": 0.10,
})

_original_axis_weight = _axis_weight
_original_component_weight = _component_weight
_original_fault_recommendations = _fault_recommendations
_original_diagnose_asset = diagnose_asset
_original_postprocess_results = _postprocess_results


def _axis_weight(fault_key: str, sensor: SensorMeasurement, axis_name: str) -> float:
    if fault_key in {"gear_misalignment", "gear_eccentricity", "gear_backlash", "gear_tooth_wear", "gear_tooth_damage_localized"}:
        return _original_axis_weight("gear_mesh_fault", sensor, axis_name)
    return _original_axis_weight(fault_key, sensor, axis_name)


def _component_weight(fault_key: str, sensor: SensorMeasurement) -> float:
    if fault_key in {"gear_misalignment", "gear_eccentricity", "gear_backlash", "gear_tooth_wear", "gear_tooth_damage_localized"}:
        return _original_component_weight("gear_mesh_fault", sensor)
    return _original_component_weight(fault_key, sensor)


def _mesh_sideband_pack(
    freqs: np.ndarray,
    amps: np.ndarray,
    center_hz: float,
    spacing_hz: float,
    tolerance_hz: float,
    sidebands: int = 3,
) -> Dict[str, float]:
    if center_hz <= 0.0 or spacing_hz <= 0.0:
        return {
            "center_amp": 0.0,
            "mean_pair_ratio": 0.0,
            "max_pair_ratio": 0.0,
            "pair_symmetry": 0.0,
            "count": 0.0,
            "sum_ratio": 0.0,
        }
    _, center_amp = _peak_at(freqs, amps, center_hz, tolerance_hz)
    if center_amp <= 1e-12:
        return {
            "center_amp": 0.0,
            "mean_pair_ratio": 0.0,
            "max_pair_ratio": 0.0,
            "pair_symmetry": 0.0,
            "count": 0.0,
            "sum_ratio": 0.0,
        }

    pair_ratios: List[float] = []
    symmetries: List[float] = []
    count = 0
    sum_ratio = 0.0
    for k in range(1, sidebands + 1):
        _, left = _peak_at(freqs, amps, center_hz - k * spacing_hz, tolerance_hz)
        _, right = _peak_at(freqs, amps, center_hz + k * spacing_hz, tolerance_hz)
        pair_ratio = _safe_ratio(0.5 * (left + right), center_amp)
        sym = _safe_ratio(min(left, right), max(left, right, 1e-12)) if (left > 0 or right > 0) else 0.0
        pair_ratios.append(pair_ratio)
        symmetries.append(sym)
        sum_ratio += left + right
        if pair_ratio >= 0.08:
            count += 1

    return {
        "center_amp": float(center_amp),
        "mean_pair_ratio": float(mean(pair_ratios)) if pair_ratios else 0.0,
        "max_pair_ratio": float(max(pair_ratios)) if pair_ratios else 0.0,
        "pair_symmetry": float(mean(symmetries)) if symmetries else 0.0,
        "count": float(count),
        "sum_ratio": _safe_ratio(sum_ratio, center_amp),
    }


def _mesh_harmonic_pack(
    freqs: np.ndarray,
    amps: np.ndarray,
    gmf: float,
    tolerance_hz: float,
    harmonics: int = 4,
) -> Dict[str, float]:
    vals = []
    for k in range(1, harmonics + 1):
        _, a = _peak_at(freqs, amps, k * gmf, tolerance_hz)
        vals.append(float(a))
    base = vals[0] if vals else 0.0
    return {
        "gmf1": vals[0] if len(vals) > 0 else 0.0,
        "gmf2": vals[1] if len(vals) > 1 else 0.0,
        "gmf3": vals[2] if len(vals) > 2 else 0.0,
        "gmf4": vals[3] if len(vals) > 3 else 0.0,
        "gmf23_over_gmf1": _safe_ratio((vals[1] if len(vals) > 1 else 0.0) + (vals[2] if len(vals) > 2 else 0.0), max(base, 1e-12)),
        "gmf234_over_rms": _safe_ratio(sum(vals[1:4]), max(_rms(amps), 1e-12)),
        "gmf123_over_rms": _safe_ratio(sum(vals[:3]), max(_rms(amps), 1e-12)),
    }


def _gear_mesh_resonance_band_energy(freqs: np.ndarray, amps: np.ndarray, gmf: float) -> float:
    if gmf <= 0.0 or freqs.size == 0:
        return 0.0
    low = max(2.5 * gmf, 300.0)
    high = min(float(freqs[-1]), max(4.5 * gmf, low + 50.0))
    if high <= low:
        return 0.0
    return _safe_ratio(_rms(amps[(freqs >= low) & (freqs <= high)]), max(_rms(amps), 1e-12))


def _mesh_band_waveform_metrics(signal: AxisSignal, gmf: float) -> Dict[str, float]:
    fs = _waveform_sample_rate_hz(signal)
    wf = _waveform_array(signal, "acceleration")
    if wf is None or fs <= 0.0 or gmf <= 0.0:
        return {
            "mesh_band_crest": 0.0,
            "mesh_band_kurtosis": 0.0,
            "mesh_env_rms": 0.0,
            "mesh_env_impact_periodicity": 0.0,
        }
    nyq = 0.5 * fs
    low = max(0.8 * gmf, 100.0)
    high = min(1.2 * gmf, 0.95 * nyq)
    if high <= low:
        return {
            "mesh_band_crest": 0.0,
            "mesh_band_kurtosis": 0.0,
            "mesh_env_rms": 0.0,
            "mesh_env_impact_periodicity": 0.0,
        }
    mesh_band = _condition_butter_filter(wf, fs, low=low, high=high)
    env = np.abs(hilbert(mesh_band))
    centered = env - np.mean(env)
    std = float(np.std(centered))
    periodicity = 0.0
    if std > 1e-12:
        centered = centered / std
        ac = np.correlate(centered, centered, mode="full")[centered.size - 1:]
        if ac.size > 1 and ac[0] > 1e-12:
            ac = ac / ac[0]
            start = max(1, int(0.02 * ac.size))
            if start < ac.size:
                periodicity = float(np.clip(np.max(ac[start:]) ** 0.5, 0.0, 1.0))
    return {
        "mesh_band_crest": float(_crest_factor(mesh_band)),
        "mesh_band_kurtosis": float(_kurtosis_excess(mesh_band)),
        "mesh_env_rms": float(_rms(env)),
        "mesh_env_impact_periodicity": periodicity,
    }


def _stage_shaft_speeds_hz(asset: AssetDefinition, stage: GearStageDefinition, sensor: SensorMeasurement) -> Tuple[float, float]:
    in_rpm = stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm
    out_rpm = stage.stage_output_rpm
    if out_rpm is None and stage.driven_teeth > 0:
        out_rpm = in_rpm * float(stage.driver_teeth) / float(stage.driven_teeth)
    return shaft_hz_from_rpm(in_rpm), shaft_hz_from_rpm(out_rpm or 0.0)


def _gear_subfault_features(
    asset: AssetDefinition,
    stage: GearStageDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, float]:
    freqs = np.asarray(signal.freqs_hz, dtype=float)
    amps = np.asarray(signal.spectrum, dtype=float)
    in_hz, out_hz = _stage_shaft_speeds_hz(asset, stage, sensor)
    gmf = gear_mesh_frequency_hz((stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm), stage)
    tol = max(feat.tolerance_hz, gmf * 0.03)

    harm = _mesh_harmonic_pack(freqs, amps, gmf, tol, harmonics=4)
    sb_in_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, in_hz, tol, sidebands=2)
    sb_out_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, out_hz, tol, sidebands=2)
    wave = _mesh_band_waveform_metrics(signal, gmf)

    spacing_owner = "input"
    if max(sb_out_1["mean_pair_ratio"], sb_out_2["mean_pair_ratio"], sb_out_3["mean_pair_ratio"]) > max(sb_in_1["mean_pair_ratio"], sb_in_2["mean_pair_ratio"], sb_in_3["mean_pair_ratio"]):
        spacing_owner = "output"

    gnf_ratio = _gear_mesh_resonance_band_energy(freqs, amps, gmf)
    _, in1_amp = _peak_at(freqs, amps, in_hz, max(feat.tolerance_hz, 0.03 * max(in_hz, 1.0)))
    _, out1_amp = _peak_at(freqs, amps, out_hz, max(feat.tolerance_hz, 0.03 * max(out_hz, 1.0))) if out_hz > 0 else (0.0, 0.0)

    return {
        "gmf_hz": gmf,
        "gmf1_ratio": _safe_ratio(harm["gmf1"], max(feat.rms_spectrum, 1e-12)),
        "gmf2_ratio": _safe_ratio(harm["gmf2"], max(feat.rms_spectrum, 1e-12)),
        "gmf3_ratio": _safe_ratio(harm["gmf3"], max(feat.rms_spectrum, 1e-12)),
        "gmf23_over_gmf1": harm["gmf23_over_gmf1"],
        "gmf234_over_rms": harm["gmf234_over_rms"],
        "gmf123_over_rms": harm["gmf123_over_rms"],
        "sb_in_1": sb_in_1["mean_pair_ratio"],
        "sb_in_2": sb_in_2["mean_pair_ratio"],
        "sb_in_3": sb_in_3["mean_pair_ratio"],
        "sb_out_1": sb_out_1["mean_pair_ratio"],
        "sb_out_2": sb_out_2["mean_pair_ratio"],
        "sb_out_3": sb_out_3["mean_pair_ratio"],
        "sb_in_count": sb_in_1["count"] + sb_in_2["count"] + sb_in_3["count"],
        "sb_out_count": sb_out_1["count"] + sb_out_2["count"] + sb_out_3["count"],
        "sb_in_sym": float(np.mean([sb_in_1["pair_symmetry"], sb_in_2["pair_symmetry"], sb_in_3["pair_symmetry"]])),
        "sb_out_sym": float(np.mean([sb_out_1["pair_symmetry"], sb_out_2["pair_symmetry"], sb_out_3["pair_symmetry"]])),
        "dominant_spacing_owner_input": 1.0 if spacing_owner == "input" else 0.0,
        "dominant_spacing_owner_output": 1.0 if spacing_owner == "output" else 0.0,
        "mesh_resonance_ratio": gnf_ratio,
        "input_1x_ratio": _safe_ratio(in1_amp, max(feat.rms_spectrum, 1e-12)),
        "output_1x_ratio": _safe_ratio(out1_amp, max(feat.rms_spectrum, 1e-12)),
        "mesh_band_crest": wave["mesh_band_crest"],
        "mesh_band_kurtosis": wave["mesh_band_kurtosis"],
        "mesh_env_rms": wave["mesh_env_rms"],
        "mesh_env_impact_periodicity": wave["mesh_env_impact_periodicity"],
        "hf_rms_ratio": feat.hf_rms_ratio,
        "kurtosis": feat.kurtosis,
        "crest_factor": feat.crest_factor,
        "axis_radial": 1.0 if feat.axis in {"horizontal", "vertical", "radial"} else 0.0,
        "axis_axial": 1.0 if feat.axis == "axial" else 0.0,
        "sideband_owner_hz": in_hz if spacing_owner == "input" else out_hz,
    }


def _score_gear_misalignment_from_features(values: Dict[str, float]) -> float:
    score = (
        28.0 * _score_linear(values["gmf23_over_gmf1"], 0.8, 2.5) +
        20.0 * _score_linear(values["gmf2_ratio"] + values["gmf3_ratio"], 0.5, 2.5) +
        16.0 * _score_linear(max(values["sb_in_2"], values["sb_out_2"]), 0.08, 0.45) +
        10.0 * _score_linear(max(values["sb_in_3"], values["sb_out_3"]), 0.05, 0.35) +
        10.0 * _score_linear(max(values["sb_in_sym"], values["sb_out_sym"]), 0.25, 0.80) +
        8.0 * _score_linear(values["gmf234_over_rms"], 0.6, 2.8) +
        8.0 * _score_linear(values["axis_radial"], 0.5, 1.0)
    )
    if values["gmf23_over_gmf1"] < 0.8:
        score *= 0.55
    return float(score)


def _score_gear_eccentricity_from_features(values: Dict[str, float]) -> float:
    spacing_ratio = max(values["sb_in_1"], values["sb_out_1"])
    owner_strength = max(values["input_1x_ratio"], values["output_1x_ratio"])
    score = (
        28.0 * _score_linear(spacing_ratio, 0.10, 0.50) +
        18.0 * _score_linear(owner_strength, 0.20, 1.50) +
        14.0 * _score_linear(max(values["sb_in_sym"], values["sb_out_sym"]), 0.30, 0.90) +
        14.0 * _score_linear(values["gmf1_ratio"], 0.4, 2.2) +
        10.0 * (1.0 - _score_linear(values["gmf23_over_gmf1"], 1.4, 3.0)) +
        8.0 * _score_linear(values["dominant_spacing_owner_input"] + values["dominant_spacing_owner_output"], 0.5, 1.0) +
        8.0 * (1.0 - _score_linear(values["mesh_band_kurtosis"], 1.8, 5.0))
    )
    return float(score)


def _score_gear_backlash_from_features(values: Dict[str, float]) -> float:
    score = (
        22.0 * _score_linear(max(values["sb_in_1"], values["sb_out_1"]), 0.10, 0.50) +
        16.0 * _score_linear(values["mesh_resonance_ratio"], 0.20, 0.90) +
        14.0 * _score_linear(values["mesh_band_crest"], 3.2, 6.5) +
        12.0 * _score_linear(max(values["mesh_band_kurtosis"], 0.0), 0.8, 4.0) +
        12.0 * _score_linear(values["mesh_env_impact_periodicity"], 0.15, 0.70) +
        12.0 * _score_linear(values["gmf123_over_rms"], 0.4, 2.2) +
        12.0 * _score_linear(max(values["sb_in_count"], values["sb_out_count"]), 2.0, 6.0)
    )
    return float(score)


def _score_gear_tooth_wear_from_features(values: Dict[str, float]) -> float:
    score = (
        24.0 * _score_linear(max(values["sb_in_1"], values["sb_out_1"]), 0.08, 0.40) +
        16.0 * _score_linear(max(values["sb_in_count"], values["sb_out_count"]), 2.0, 7.0) +
        16.0 * _score_linear(values["mesh_resonance_ratio"], 0.18, 0.85) +
        14.0 * _score_linear(values["gmf2_ratio"] + values["gmf3_ratio"], 0.4, 2.2) +
        12.0 * _score_linear(values["gmf123_over_rms"], 0.5, 2.5) +
        10.0 * _score_linear(values["mesh_env_rms"], 0.05, 0.40) +
        8.0 * (1.0 - _score_linear(max(values["mesh_band_kurtosis"], 0.0), 2.5, 6.0))
    )
    return float(score)


def _score_gear_tooth_damage_localized_from_features(values: Dict[str, float]) -> float:
    score = (
        20.0 * _score_linear(values["mesh_band_crest"], 3.6, 7.0) +
        18.0 * _score_linear(max(values["mesh_band_kurtosis"], 0.0), 1.0, 5.0) +
        14.0 * _score_linear(values["mesh_env_impact_periodicity"], 0.20, 0.80) +
        14.0 * _score_linear(max(values["sb_in_1"], values["sb_out_1"]), 0.10, 0.45) +
        12.0 * _score_linear(values["mesh_resonance_ratio"], 0.25, 1.0) +
        12.0 * _score_linear(values["hf_rms_ratio"], 0.25, 0.90) +
        10.0 * _score_linear(values["gmf123_over_rms"], 0.5, 2.5)
    )
    return float(score)


def _gear_subfault_axis_score(
    fault_key: str,
    asset: AssetDefinition,
    stage: GearStageDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Tuple[float, List[str], Dict[str, float]]:
    values = _gear_subfault_features(asset, stage, sensor, feat, signal)
    if fault_key == "gear_misalignment":
        score = _score_gear_misalignment_from_features(values)
    elif fault_key == "gear_eccentricity":
        score = _score_gear_eccentricity_from_features(values)
    elif fault_key == "gear_backlash":
        score = _score_gear_backlash_from_features(values)
    elif fault_key == "gear_tooth_wear":
        score = _score_gear_tooth_wear_from_features(values)
    elif fault_key == "gear_tooth_damage_localized":
        score = _score_gear_tooth_damage_localized_from_features(values)
    else:
        score = 0.0

    score *= _axis_weight(fault_key, sensor, feat.axis) * _component_weight(fault_key, sensor)
    ev = [
        (
            f"{sensor.sensor_id}/{feat.axis}: stage={stage.gear_stage_id}, teeth={stage.driver_teeth}:{stage.driven_teeth}, "
            f"GMF={values['gmf_hz']:.1f}Hz, GMF1={values['gmf1_ratio']:.2f}xRMS, "
            f"GMF2={values['gmf2_ratio']:.2f}xRMS, GMF3={values['gmf3_ratio']:.2f}xRMS, "
            f"SB1_in={values['sb_in_1']:.2f}, SB1_out={values['sb_out_1']:.2f}, "
            f"meshRes={values['mesh_resonance_ratio']:.2f}, meshCF={values['mesh_band_crest']:.2f}, "
            f"meshKurt={values['mesh_band_kurtosis']:.2f}"
        )
    ]
    metrics = {
        "gmf_hz": values["gmf_hz"],
        "gmf1_ratio": values["gmf1_ratio"],
        "gmf2_ratio": values["gmf2_ratio"],
        "gmf3_ratio": values["gmf3_ratio"],
        "gmf23_over_gmf1": values["gmf23_over_gmf1"],
        "sb_in_1": values["sb_in_1"],
        "sb_in_2": values["sb_in_2"],
        "sb_out_1": values["sb_out_1"],
        "sb_out_2": values["sb_out_2"],
        "sb_in_count": values["sb_in_count"],
        "sb_out_count": values["sb_out_count"],
        "sb_in_sym": values["sb_in_sym"],
        "sb_out_sym": values["sb_out_sym"],
        "mesh_resonance_ratio": values["mesh_resonance_ratio"],
        "input_1x_ratio": values["input_1x_ratio"],
        "output_1x_ratio": values["output_1x_ratio"],
        "mesh_band_crest": values["mesh_band_crest"],
        "mesh_band_kurtosis": values["mesh_band_kurtosis"],
        "mesh_env_impact_periodicity": values["mesh_env_impact_periodicity"],
        "sideband_owner_hz": values["sideband_owner_hz"],
    }
    return float(score), ev, metrics


def diagnose_gear_subfault(asset: AssetDefinition, fault_key: str, stage: GearStageDefinition) -> FaultResult:
    selected = _selected_scope_sensors(asset, fault_key, gear_stage_id=stage.gear_stage_id)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            score, ev, metrics = _gear_subfault_axis_score(fault_key, asset, stage, sensor, feat, sensor.directions[axis_name])
            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    coverage = 16.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 3.0)
    repeatability = 12.0 * _score_linear(sum(1 for s in local_scores if s >= 40.0), 1.0, 4.0)
    score = _clamp(0.72 * top + coverage + repeatability, 0.0, 100.0)
    cap = FAULT_LIBRARY[fault_key]["phase_cap"]
    confidence = _confidence_from_score(score, str(cap))

    limitations = [
        "Exact tooth counts and stage shaft speeds are required for best accuracy.",
        "Without load trend, separation between eccentricity, backlash and wear stays partly inferential.",
    ]
    if fault_key == "gear_backlash":
        limitations.append("Backlash confidence improves markedly when load or torque trend is available because backlash often changes with load.")
    if fault_key == "gear_misalignment":
        limitations.append("Gear misalignment and support-bearing looseness can coexist; check bearings, shaft deflection and contact pattern together.")

    return FaultResult(
        fault_key=fault_key,
        target=stage.gear_stage_id,
        scope="gear_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics={k: float(mean(v)) for k, v in metrics_acc.items() if v},
    )


def _postprocess_results(asset: AssetDefinition, results: List[FaultResult]) -> None:
    _original_postprocess_results(asset, results)
    by_key = {r.fault_key: r for r in results}

    gm = by_key.get("gear_misalignment")
    if gm is not None:
        if gm.supporting_metrics.get("gmf23_over_gmf1", 0.0) < 0.8:
            gm.score *= 0.60
            gm.limitations.append("Reduced because higher-order GMF support is weak for a gear-misalignment call.")
            _refresh_result_confidence(gm)

    ge = by_key.get("gear_eccentricity")
    if ge is not None:
        owner = max(ge.supporting_metrics.get("input_1x_ratio", 0.0), ge.supporting_metrics.get("output_1x_ratio", 0.0))
        sb = max(ge.supporting_metrics.get("sb_in_1", 0.0), ge.supporting_metrics.get("sb_out_1", 0.0))
        if owner < 0.2 or sb < 0.08:
            ge.score *= 0.62
            ge.limitations.append("Reduced because shaft-speed ownership of GMF sidebands is weak for a clean eccentricity call.")
            _refresh_result_confidence(ge)

    gb = by_key.get("gear_backlash")
    if gb is not None:
        if gb.supporting_metrics.get("mesh_band_crest", 0.0) < 3.2 and gb.supporting_metrics.get("mesh_band_kurtosis", 0.0) < 0.8:
            gb.score *= 0.65
            gb.limitations.append("Reduced because mesh-band impulsiveness is weak for backlash/clearance knock.")
            _refresh_result_confidence(gb)

    gw = by_key.get("gear_tooth_wear")
    if gw is not None:
        sideband_count = max(gw.supporting_metrics.get("sb_in_count", 0.0), gw.supporting_metrics.get("sb_out_count", 0.0))
        if sideband_count < 2.0 and gw.supporting_metrics.get("mesh_resonance_ratio", 0.0) < 0.18:
            gw.score *= 0.65
            gw.limitations.append("Reduced because sideband count and mesh-band energy are limited for a tooth-wear call.")
            _refresh_result_confidence(gw)

    gd = by_key.get("gear_tooth_damage_localized")
    if gd is not None:
        if gd.supporting_metrics.get("mesh_band_crest", 0.0) < 3.6 and gd.supporting_metrics.get("mesh_band_kurtosis", 0.0) < 1.0 and gd.supporting_metrics.get("mesh_env_impact_periodicity", 0.0) < 0.20:
            gd.score *= 0.58
            gd.limitations.append("Reduced because crest, kurtosis and periodic mesh impacts are not strong enough for localized tooth damage.")
            _refresh_result_confidence(gd)


def _fault_recommendations(result: FaultResult) -> List[str]:
    if result.fault_key == "gear_misalignment":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Check tooth contact pattern, shaft/bearing fits, housing distortion, axial setting and parallelism of the shafts.",
            "Correlate with bearing looseness, shaft deflection and coupling alignment before concluding a pure mesh-only misalignment root cause.",
        ]
    if result.fault_key == "gear_eccentricity":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Check gear runout, bore fit, mounting eccentricity, shaft eccentricity and sleeve/hub concentricity.",
            "Use sideband spacing to identify whether the input or output member is the most likely source.",
        ]
    if result.fault_key == "gear_backlash":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Verify backlash against design limits, inspect for excessive clearance, tooth knock, wear pattern and torsional reversals.",
            "Compare spectra across load if possible; backlash confidence rises when the symptom changes predictably with torque.",
        ]
    if result.fault_key == "gear_tooth_wear":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan corrective work and intensified trending.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Inspect tooth flanks, lubrication quality, debris, surface finish, scuffing and pitting progression.",
            "Trend sideband count and total sideband energy around 1x/2x/3x GMF, not GMF amplitude alone.",
        ]
    if result.fault_key == "gear_tooth_damage_localized":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan immediate confirmatory checks and a near-term outage inspection.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Look for chipped, cracked, spalled or broken teeth and correlate with impulsive time-waveform events.",
            "Confirm with mesh-band envelope, borescope or oil-debris inspection where possible.",
        ]
    return _original_fault_recommendations(result)


def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
) -> List[FaultResult]:
    results: List[FaultResult] = []
    pattern_profile = classify_asset_pattern(asset)
    asset.metadata["_pattern_classifier"] = pattern_profile.as_dict()

    for fault_key in [
        "unbalance",
        "misalignment",
        "looseness_type_a_base_structure",
        "looseness_type_b_pedestal_support",
        "looseness_type_c_rotating_fit",
        "soft_foot_or_frame_distortion",
        "bent_shaft_or_bow",
        "resonance_or_structural_amplification",
        "rotor_rub",
        "motor_electrical_forcing",
    ]:
        results.append(diagnose_asset_wide_fault(asset, fault_key))

    for bearing in asset.bearings:
        for fault_key in [
            "lubrication_distress",
            "fluid_film_instability" if bearing.bearing_type == "fluid_film" else None,
            "thrust_bearing_or_axial_overload" if (bearing.is_thrust_bearing or bearing.bearing_type == "thrust") else None,
            "bearing_bpfo" if bearing.bearing_type == "rolling" else None,
            "bearing_bpfi" if bearing.bearing_type == "rolling" else None,
            "bearing_bsf" if bearing.bearing_type == "rolling" else None,
            "bearing_ftf" if bearing.bearing_type == "rolling" else None,
        ]:
            if fault_key:
                results.append(diagnose_bearing_local_fault(asset, fault_key, bearing))

    for stage in asset.gear_stages:
        results.append(diagnose_gear_fault(asset, stage))
        for fk in [
            "gear_misalignment",
            "gear_eccentricity",
            "gear_backlash",
            "gear_tooth_wear",
            "gear_tooth_damage_localized",
        ]:
            results.append(diagnose_gear_subfault(asset, fk, stage))

    for hydraulic in asset.hydraulic_elements:
        results.append(diagnose_hydraulic_fault(asset, "hydraulic_vane_or_blade_pass", hydraulic))
        results.append(diagnose_hydraulic_fault(asset, "cavitation_or_aeration", hydraulic))

    _postprocess_results(asset, results)
    _annotate_results(results)
    condition_summary = _apply_condition_severity(asset, results, condition_scorer)
    _apply_explainability(results, pattern_profile, condition_summary)

    filtered = [r for r in results if r.score >= minimum_score and r.confidence != "none"]
    filtered.sort(key=lambda r: (-(r.fault_severity_score or r.score), -r.score, r.fault_key, r.target))
    return filtered


# ---------------------------------------------------------------------------
# Belt / sheave local faults patch
# ---------------------------------------------------------------------------

@dataclass
class BeltDriveDefinition:
    belt_id: str
    component_id: str
    driver_component_id: Optional[str] = None
    driven_component_id: Optional[str] = None
    driver_rpm: Optional[float] = None
    driven_rpm: Optional[float] = None
    driver_pitch_diameter_mm: Optional[float] = None
    driven_pitch_diameter_mm: Optional[float] = None
    belt_length_mm: Optional[float] = None
    center_distance_mm: Optional[float] = None
    belt_count: int = 1
    belt_type: str = "v_belt"
    is_timing_belt: bool = False
    notes: str = ""


FAULT_LIBRARY.update({
    "belt_sheave_misalignment": {"scope": "belt_local", "phase_cap": "medium"},
    "belt_sheave_eccentricity": {"scope": "belt_local", "phase_cap": "medium"},
    "belt_slip_or_tension_fault": {"scope": "belt_local", "phase_cap": "medium"},
    "belt_wear_or_damage": {"scope": "belt_local", "phase_cap": "high"},
    "belt_span_resonance": {"scope": "belt_local", "phase_cap": "low"},
})

FAULT_TO_CONDITION_FAMILY.update({
    "belt_sheave_misalignment": "shaft",
    "belt_sheave_eccentricity": "shaft",
    "belt_slip_or_tension_fault": "shaft",
    "belt_wear_or_damage": "shaft",
    "belt_span_resonance": "shaft",
})

FAULT_RISK_BONUS.update({
    "belt_sheave_misalignment": 0.04,
    "belt_sheave_eccentricity": 0.04,
    "belt_slip_or_tension_fault": 0.05,
    "belt_wear_or_damage": 0.06,
    "belt_span_resonance": 0.04,
})


def belt_length_from_geometry_mm(driver_pitch_diameter_mm: float, driven_pitch_diameter_mm: float, center_distance_mm: float) -> float:
    d = float(driver_pitch_diameter_mm)
    D = float(driven_pitch_diameter_mm)
    C = float(center_distance_mm)
    if min(d, D, C) <= 0.0:
        return 0.0
    return float(2.0 * C + (math.pi * (D + d) / 2.0) + (((D - d) ** 2) / (4.0 * C)))


def belt_speed_m_s(rpm: float, pitch_diameter_mm: float) -> float:
    if rpm is None or pitch_diameter_mm is None:
        return 0.0
    if rpm <= 0.0 or pitch_diameter_mm <= 0.0:
        return 0.0
    return float(math.pi * (pitch_diameter_mm / 1000.0) * (rpm / 60.0))


def belt_pass_frequency_hz(driver_rpm: float, driver_pitch_diameter_mm: float, belt_length_mm: float) -> float:
    if driver_rpm is None or driver_pitch_diameter_mm is None or belt_length_mm is None:
        return 0.0
    if driver_rpm <= 0.0 or driver_pitch_diameter_mm <= 0.0 or belt_length_mm <= 0.0:
        return 0.0
    return float((math.pi * driver_pitch_diameter_mm * driver_rpm) / (60.0 * belt_length_mm))


def _asset_belt_drives(asset: AssetDefinition) -> List[BeltDriveDefinition]:
    belts = getattr(asset, "belt_drives", None)
    if belts:
        return [b for b in belts if isinstance(b, BeltDriveDefinition)]
    meta_belts = asset.metadata.get("belt_drives", []) if isinstance(asset.metadata, dict) else []
    out = []
    for item in meta_belts:
        if isinstance(item, BeltDriveDefinition):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(BeltDriveDefinition(**item))
            except Exception:
                continue
    return out


def _belt_driver_hz(belt: BeltDriveDefinition, asset: AssetDefinition) -> float:
    return shaft_hz_from_rpm(belt.driver_rpm or asset.running_rpm)


def _belt_driven_hz(belt: BeltDriveDefinition, asset: AssetDefinition) -> float:
    rpm = belt.driven_rpm
    if rpm is None and belt.driver_rpm and belt.driver_pitch_diameter_mm and belt.driven_pitch_diameter_mm:
        rpm = float(belt.driver_rpm) * float(belt.driver_pitch_diameter_mm) / float(belt.driven_pitch_diameter_mm)
    return shaft_hz_from_rpm(rpm or 0.0)


def _belt_pass_hz(belt: BeltDriveDefinition, asset: AssetDefinition) -> float:
    length = belt.belt_length_mm
    if (length is None or length <= 0.0) and belt.driver_pitch_diameter_mm and belt.driven_pitch_diameter_mm and belt.center_distance_mm:
        length = belt_length_from_geometry_mm(belt.driver_pitch_diameter_mm, belt.driven_pitch_diameter_mm, belt.center_distance_mm)
    return belt_pass_frequency_hz(belt.driver_rpm or asset.running_rpm, belt.driver_pitch_diameter_mm or 0.0, length or 0.0)


def _belt_selected_sensors(asset: AssetDefinition, belt: BeltDriveDefinition) -> List[SensorMeasurement]:
    ids = {belt.component_id}
    if belt.driver_component_id:
        ids.add(belt.driver_component_id)
    if belt.driven_component_id:
        ids.add(belt.driven_component_id)
    selected = [s for s in asset.sensors if s.component_id in ids]
    if selected:
        return selected
    return [s for s in asset.sensors if s.component_type.lower() in {"motor", "fan", "blower", "pump", "driven", "gearbox"}]


def _belt_sideband_ratio(freqs: np.ndarray, amps: np.ndarray, center_hz: float, spacing_hz: float, tolerance_hz: float, n: int = 2) -> float:
    if center_hz <= 0.0 or spacing_hz <= 0.0:
        return 0.0
    _, center_amp = _peak_at(freqs, amps, center_hz, tolerance_hz)
    if center_amp <= 1e-12:
        return 0.0
    total = 0.0
    for k in range(1, n + 1):
        _, left = _peak_at(freqs, amps, center_hz - k * spacing_hz, tolerance_hz)
        _, right = _peak_at(freqs, amps, center_hz + k * spacing_hz, tolerance_hz)
        total += left + right
    return _safe_ratio(total, center_amp)


def _belt_low_band_broadness(freqs: np.ndarray, amps: np.ndarray, center_hz: float, width_hz: float) -> float:
    if center_hz <= 0.0:
        return 0.0
    low = max(0.0, center_hz - width_hz)
    high = center_hz + width_hz
    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return 0.0
    band = amps[mask]
    return _safe_ratio(_rms(band), max(np.max(band), 1e-12))


def _belt_waveform_impulsiveness(signal: AxisSignal, belt_hz: float) -> Dict[str, float]:
    fs = _waveform_sample_rate_hz(signal)
    wf = _waveform_array(signal, "acceleration")
    if wf is None or fs <= 0.0:
        return {"crest": 0.0, "kurtosis": 0.0, "belt_periodicity": 0.0}
    crest = _crest_factor(wf)
    kurt = _kurtosis_excess(wf)
    periodicity = 0.0
    if belt_hz > 0.0:
        periodicity = _best_autocorr_near_lag(np.abs(wf - np.mean(wf)), int(round(fs / belt_hz)))
    return {"crest": float(crest), "kurtosis": float(kurt), "belt_periodicity": float(periodicity)}


def _belt_axis_metrics(asset: AssetDefinition, belt: BeltDriveDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Dict[str, float]:
    freqs = np.asarray(signal.freqs_hz, dtype=float)
    amps = np.asarray(signal.spectrum, dtype=float)
    driver_hz = _belt_driver_hz(belt, asset)
    driven_hz = _belt_driven_hz(belt, asset)
    belt_hz = _belt_pass_hz(belt, asset)
    freq_res = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(feat.tolerance_hz, 0.1)
    tol_driver = max(feat.tolerance_hz, 0.03 * max(driver_hz, 1.0), 1.5 * freq_res)
    tol_driven = max(feat.tolerance_hz, 0.03 * max(driven_hz, 1.0), 1.5 * freq_res) if driven_hz > 0.0 else feat.tolerance_hz
    tol_belt = max(feat.tolerance_hz, 0.05 * max(belt_hz, 1.0), 1.5 * freq_res) if belt_hz > 0.0 else feat.tolerance_hz

    _, driver1 = _peak_at(freqs, amps, driver_hz, tol_driver)
    _, driver2 = _peak_at(freqs, amps, 2.0 * driver_hz, tol_driver)
    _, driven1 = _peak_at(freqs, amps, driven_hz, tol_driven)
    _, driven2 = _peak_at(freqs, amps, 2.0 * driven_hz, tol_driven)
    _, belt1 = _peak_at(freqs, amps, belt_hz, tol_belt)
    _, belt2 = _peak_at(freqs, amps, 2.0 * belt_hz, tol_belt)
    _, belt3 = _peak_at(freqs, amps, 3.0 * belt_hz, tol_belt)

    sb_driver = _belt_sideband_ratio(freqs, amps, driver_hz, belt_hz, max(tol_driver, tol_belt), n=2) if belt_hz > 0.0 else 0.0
    sb_driven = _belt_sideband_ratio(freqs, amps, driven_hz, belt_hz, max(tol_driven, tol_belt), n=2) if belt_hz > 0.0 and driven_hz > 0.0 else 0.0
    low_broad = _belt_low_band_broadness(freqs, amps, belt_hz if belt_hz > 0.0 else driver_hz, max(driver_hz, belt_hz, 1.0))
    wave = _belt_waveform_impulsiveness(signal, belt_hz)

    axis = feat.axis.lower()
    axial = 1.0 if axis == "axial" else 0.0
    radial = 1.0 if axis in {"horizontal", "vertical", "radial"} else 0.0
    belt_lt_driver = 1.0 if (belt_hz > 0.0 and driver_hz > 0.0 and belt_hz < driver_hz) else 0.0
    dominant_near_belt = 1.0 - min(abs(feat.dominant_freq_hz - belt_hz) / max(2.0 * tol_belt, 1e-12), 1.0) if belt_hz > 0.0 else 0.0

    return {
        "driver_hz": driver_hz,
        "driven_hz": driven_hz,
        "belt_hz": belt_hz,
        "driver1_ratio": _safe_ratio(driver1, max(feat.rms_spectrum, 1e-12)),
        "driver2_ratio": _safe_ratio(driver2, max(feat.rms_spectrum, 1e-12)),
        "driven1_ratio": _safe_ratio(driven1, max(feat.rms_spectrum, 1e-12)),
        "driven2_ratio": _safe_ratio(driven2, max(feat.rms_spectrum, 1e-12)),
        "belt1_ratio": _safe_ratio(belt1, max(feat.rms_spectrum, 1e-12)),
        "belt2_ratio": _safe_ratio(belt2, max(feat.rms_spectrum, 1e-12)),
        "belt3_ratio": _safe_ratio(belt3, max(feat.rms_spectrum, 1e-12)),
        "belt_harmonics_ratio": _safe_ratio(belt1 + belt2 + belt3, max(feat.rms_spectrum, 1e-12)),
        "driver_belt_sideband_ratio": sb_driver,
        "driven_belt_sideband_ratio": sb_driven,
        "low_band_broadness": low_broad,
        "crest_factor": wave["crest"],
        "kurtosis": wave["kurtosis"],
        "belt_periodicity": wave["belt_periodicity"],
        "axis_axial": axial,
        "axis_radial": radial,
        "belt_lt_driver": belt_lt_driver,
        "dominant_near_belt": dominant_near_belt,
        "hf_rms_ratio": feat.hf_rms_ratio,
        "subsync_ratio": _safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)),
    }


def _score_belt_sheave_misalignment(values: Dict[str, float]) -> float:
    score = (
        28.0 * _score_linear(max(values["driver1_ratio"], values["driven1_ratio"]), 0.5, 2.5) +
        22.0 * _score_linear(max(values["driver2_ratio"], values["driven2_ratio"]), 0.2, 1.5) +
        24.0 * _score_linear(values["axis_axial"], 0.5, 1.0) +
        12.0 * _score_linear(max(values["driver_belt_sideband_ratio"], values["driven_belt_sideband_ratio"]), 0.05, 0.30) +
        14.0 * (1.0 - _score_linear(values["belt_harmonics_ratio"], 1.2, 3.8))
    )
    if values["axis_axial"] < 0.5:
        score *= 0.68
    return float(score)


def _score_belt_sheave_eccentricity(values: Dict[str, float]) -> float:
    dominant_1x = max(values["driver1_ratio"], values["driven1_ratio"])
    secondary_1x = min(values["driver1_ratio"], values["driven1_ratio"])
    skew = _safe_ratio(dominant_1x, max(secondary_1x, 1e-12), default=99.0)
    score = (
        36.0 * _score_linear(dominant_1x, 0.6, 3.0) +
        18.0 * _score_linear(skew, 1.3, 4.0) +
        22.0 * _score_linear(values["axis_radial"], 0.5, 1.0) +
        12.0 * (1.0 - _score_linear(values["axis_axial"], 0.2, 0.8)) +
        12.0 * (1.0 - _score_linear(values["belt_harmonics_ratio"], 0.9, 3.2))
    )
    return float(score)


def _score_belt_slip_or_tension_fault(values: Dict[str, float]) -> float:
    score = (
        24.0 * _score_linear(values["belt2_ratio"], 0.10, 1.10) +
        18.0 * _score_linear(values["belt1_ratio"], 0.08, 0.90) +
        14.0 * _score_linear(values["belt3_ratio"], 0.05, 0.70) +
        16.0 * _score_linear(max(values["driver_belt_sideband_ratio"], values["driven_belt_sideband_ratio"]), 0.06, 0.35) +
        12.0 * _score_linear(values["belt_lt_driver"], 0.5, 1.0) +
        8.0 * _score_linear(values["crest_factor"], 3.2, 6.0) +
        8.0 * _score_linear(values["belt_periodicity"], 0.10, 0.45)
    )
    if values["belt_hz"] <= 0.0:
        score *= 0.35
    return float(score)


def _score_belt_wear_or_damage(values: Dict[str, float]) -> float:
    score = (
        28.0 * _score_linear(values["belt1_ratio"], 0.10, 1.00) +
        18.0 * _score_linear(values["belt_harmonics_ratio"], 0.20, 1.80) +
        14.0 * _score_linear(max(values["driver_belt_sideband_ratio"], values["driven_belt_sideband_ratio"]), 0.05, 0.30) +
        14.0 * _score_linear(values["crest_factor"], 3.2, 6.5) +
        10.0 * _score_linear(max(values["kurtosis"], 0.0), 0.5, 3.5) +
        10.0 * _score_linear(values["belt_periodicity"], 0.10, 0.60) +
        6.0 * _score_linear(values["dominant_near_belt"], 0.20, 0.90)
    )
    if values["belt_hz"] <= 0.0:
        score *= 0.40
    return float(score)


def _score_belt_span_resonance(values: Dict[str, float]) -> float:
    score = (
        24.0 * _score_linear(values["dominant_near_belt"], 0.20, 0.90) +
        20.0 * _score_linear(values["low_band_broadness"], 0.22, 0.60) +
        16.0 * _score_linear(values["belt_lt_driver"], 0.5, 1.0) +
        12.0 * _score_linear(values["axis_radial"], 0.5, 1.0) +
        14.0 * (1.0 - _score_linear(values["belt_harmonics_ratio"], 0.35, 1.40)) +
        14.0 * (1.0 - _score_linear(values["driver1_ratio"] + values["driven1_ratio"], 1.0, 3.5))
    )
    if values["belt_hz"] <= 0.0:
        score *= 0.35
    return float(score)


def _belt_axis_score(fault_key: str, asset: AssetDefinition, belt: BeltDriveDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Tuple[float, List[str], Dict[str, float]]:
    values = _belt_axis_metrics(asset, belt, sensor, feat, signal)
    if fault_key == "belt_sheave_misalignment":
        score = _score_belt_sheave_misalignment(values)
    elif fault_key == "belt_sheave_eccentricity":
        score = _score_belt_sheave_eccentricity(values)
    elif fault_key == "belt_slip_or_tension_fault":
        score = _score_belt_slip_or_tension_fault(values)
    elif fault_key == "belt_wear_or_damage":
        score = _score_belt_wear_or_damage(values)
    elif fault_key == "belt_span_resonance":
        score = _score_belt_span_resonance(values)
    else:
        score = 0.0

    axis_mult = 1.0
    if fault_key == "belt_sheave_misalignment":
        axis_mult = 1.10 if feat.axis == "axial" else 0.75
    elif fault_key == "belt_sheave_eccentricity":
        axis_mult = 1.08 if feat.axis in {"horizontal", "vertical", "radial"} else 0.72
    elif fault_key in {"belt_slip_or_tension_fault", "belt_wear_or_damage", "belt_span_resonance"}:
        axis_mult = 1.02 if feat.axis in {"horizontal", "vertical", "radial"} else 0.86

    score *= axis_mult

    evidence = [
        (
            f"{sensor.sensor_id}/{feat.axis}: belt={belt.belt_id}, driver={values['driver_hz']:.2f}Hz, driven={values['driven_hz']:.2f}Hz, "
            f"belt={values['belt_hz']:.2f}Hz, drv1={values['driver1_ratio']:.2f}xRMS, drv2={values['driver2_ratio']:.2f}xRMS, "
            f"drn1={values['driven1_ratio']:.2f}xRMS, belt1={values['belt1_ratio']:.2f}xRMS, belt2={values['belt2_ratio']:.2f}xRMS, "
            f"sb_drv={values['driver_belt_sideband_ratio']:.2f}, sb_drn={values['driven_belt_sideband_ratio']:.2f}"
        )
    ]
    metrics = {
        "driver_hz": values["driver_hz"],
        "driven_hz": values["driven_hz"],
        "belt_hz": values["belt_hz"],
        "driver1_ratio": values["driver1_ratio"],
        "driver2_ratio": values["driver2_ratio"],
        "driven1_ratio": values["driven1_ratio"],
        "driven2_ratio": values["driven2_ratio"],
        "belt1_ratio": values["belt1_ratio"],
        "belt2_ratio": values["belt2_ratio"],
        "belt3_ratio": values["belt3_ratio"],
        "belt_harmonics_ratio": values["belt_harmonics_ratio"],
        "driver_belt_sideband_ratio": values["driver_belt_sideband_ratio"],
        "driven_belt_sideband_ratio": values["driven_belt_sideband_ratio"],
        "low_band_broadness": values["low_band_broadness"],
        "belt_periodicity": values["belt_periodicity"],
        "crest_factor": values["crest_factor"],
        "kurtosis": values["kurtosis"],
        "axis_axial": values["axis_axial"],
        "axis_radial": values["axis_radial"],
        "dominant_near_belt": values["dominant_near_belt"],
    }
    return float(score), evidence, metrics


def diagnose_belt_fault(asset: AssetDefinition, fault_key: str, belt: BeltDriveDefinition) -> FaultResult:
    selected = _belt_selected_sensors(asset, belt)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            score, ev, metrics = _belt_axis_score(fault_key, asset, belt, sensor, feat, sensor.directions[axis_name])
            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    coverage = 14.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 4.0)
    repeatability = 12.0 * _score_linear(sum(1 for s in local_scores if s >= 35.0), 1.0, 4.0)
    score = _clamp(0.74 * top + coverage + repeatability, 0.0, 100.0)
    confidence = _confidence_from_score(score, str(FAULT_LIBRARY[fault_key]["phase_cap"]))

    limitations = [
        "Belt-drive confidence depends on correct driver/driven speed and pulley geometry.",
        "Belt pass frequency requires belt length or enough geometry to calculate it.",
    ]
    if fault_key == "belt_span_resonance":
        limitations.append("Belt-span resonance is most reliable when confirmed by tension change, run-up/coast-down or visual belt flutter.")
    if fault_key == "belt_sheave_eccentricity":
        limitations.append("Confirm sheave eccentricity by checking whether strong 1x remains after the belt is removed or tension is released.")

    metrics_out = {k: float(mean(v)) for k, v in metrics_acc.items() if v}
    return FaultResult(
        fault_key=fault_key,
        target=belt.belt_id,
        scope="belt_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics=metrics_out,
    )


def _postprocess_belt_results(asset: AssetDefinition, results: List[FaultResult]) -> None:
    by_key: Dict[str, List[FaultResult]] = {}
    for r in results:
        by_key.setdefault(r.fault_key, []).append(r)

    pattern_profile = asset.metadata.get("_pattern_classifier")
    if isinstance(pattern_profile, dict):
        modulation_dominant = float(pattern_profile.get("modulation_score", 0.0)) >= 55.0 or pattern_profile.get("dominant_family") == "modulation"
        subsync_dominant = float(pattern_profile.get("subsynchronous_score", 0.0)) >= 45.0 or pattern_profile.get("dominant_family") == "subsynchronous"
        synchronous_radial = float(pattern_profile.get("synchronous_score", 0.0)) >= 55.0 and float(pattern_profile.get("radial_bias", 0.0)) >= 0.60
    else:
        modulation_dominant = subsync_dominant = synchronous_radial = False

    for result in by_key.get("belt_sheave_misalignment", []):
        axial = result.supporting_metrics.get("axis_axial", 0.0)
        if axial < 0.30:
            result.score *= 0.70
            result.limitations.append("Reduced because axial 1x support is limited for a belt/sheave misalignment call.")
        if modulation_dominant:
            result.score *= 0.94
            result.limitations.append("Kept conservative because the front-end classifier sees a modulation-led response, not a clean axial 1x misalignment pattern.")
        _refresh_result_confidence(result)

    for result in by_key.get("belt_sheave_eccentricity", []):
        radial = result.supporting_metrics.get("axis_radial", 0.0)
        belt_harm = result.supporting_metrics.get("belt_harmonics_ratio", 0.0)
        if radial < 0.50:
            result.score *= 0.68
            result.limitations.append("Reduced because strong radial 1x support is limited for a sheave-eccentricity call.")
        if belt_harm > 1.2:
            result.score *= 0.80
            result.limitations.append("Reduced because belt-frequency harmonics are too strong for a clean sheave-eccentricity call.")
        _refresh_result_confidence(result)

    for result in by_key.get("belt_slip_or_tension_fault", []):
        belt2 = result.supporting_metrics.get("belt2_ratio", 0.0)
        belt1 = result.supporting_metrics.get("belt1_ratio", 0.0)
        if max(belt1, belt2) < 0.10:
            result.score *= 0.55
            result.limitations.append("Reduced because belt-pass components are weak for a slip/tension fault call.")
        if subsync_dominant:
            result.score *= 1.06
            result.evidence.append("Supported by the front-end pattern classifier: subsynchronous content is meaningful.")
        _refresh_result_confidence(result)

    for result in by_key.get("belt_wear_or_damage", []):
        belt1 = result.supporting_metrics.get("belt1_ratio", 0.0)
        harm = result.supporting_metrics.get("belt_harmonics_ratio", 0.0)
        if max(belt1, harm) < 0.15:
            result.score *= 0.58
            result.limitations.append("Reduced because belt-pass frequency content is weak for a wear/damage call.")
        if modulation_dominant or subsync_dominant:
            result.score *= 1.04
            result.evidence.append("Supported by the front-end pattern classifier: modulation/subsynchronous content fits a belt-frequency fault family.")
        _refresh_result_confidence(result)

    for result in by_key.get("belt_span_resonance", []):
        broad = result.supporting_metrics.get("low_band_broadness", 0.0)
        if broad < 0.20:
            result.score *= 0.60
            result.limitations.append("Reduced because the low-frequency response is not broad enough for a belt-span resonance call.")
        if not asset.metadata.get("belt_tension_changed") and not asset.metadata.get("speed_sweep_available"):
            result.score *= 0.70
            result.limitations.append("Reduced because there is no tension-change or speed-sweep confirmation for belt-span resonance.")
        _refresh_result_confidence(result)
        result.confidence = _cap_confidence(result.confidence, "low")


_belt_patch_previous_fault_recommendations = _fault_recommendations


def _fault_recommendations(result: FaultResult) -> List[str]:
    if result.fault_key == "belt_sheave_misalignment":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Check angular and parallel sheave alignment with a straight-edge or laser pulley-alignment tool and verify belt tracking in the grooves.",
            "Inspect belt edge wear, uneven groove contact and elevated axial bearing vibration on both driver and driven sides.",
        ]
    if result.fault_key == "belt_sheave_eccentricity":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Check sheave runout, groove wear, bush fit and shaft seating; eccentric sheaves usually create strong radial 1x in line with the belt.",
            "If practical, verify whether the 1x peak remains with the belt removed or tension released before balancing the sheave.",
        ]
    if result.fault_key == "belt_slip_or_tension_fault":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Check belt tension against the manufacturer method and verify speed ratio / slip with a tachometer rather than relying only on static deflection.",
            "Inspect for glazing, polishing, dusting, rubber buildup in the grooves and evidence of belt chirp or squeal during start-up and load changes.",
        ]
    if result.fault_key == "belt_wear_or_damage":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Inspect all belts as a matched set for cracks, frayed cords, glazing, seam/lump damage and uneven wear; do not replace a single belt in a matched multi-belt drive.",
            "Gauge the sheave grooves for wear because worn grooves often drive repeat belt damage and unstable belt-pass vibration.",
        ]
    if result.fault_key == "belt_span_resonance":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Confirm by changing belt tension or observing a run-up/coast-down; belt-span resonance should shift with span stiffness/tension.",
            "Inspect for visible belt flutter, guard contact and nearby structural flexibility before concluding a pure resonance root cause.",
        ]
    return _belt_patch_previous_fault_recommendations(result)


def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
) -> List[FaultResult]:
    results: List[FaultResult] = []
    pattern_profile = classify_asset_pattern(asset)
    asset.metadata["_pattern_classifier"] = pattern_profile.as_dict()

    for fault_key in [
        "unbalance",
        "misalignment",
        "looseness_type_a_base_structure",
        "looseness_type_b_pedestal_support",
        "looseness_type_c_rotating_fit",
        "soft_foot_or_frame_distortion",
        "bent_shaft_or_bow",
        "resonance_or_structural_amplification",
        "rotor_rub",
        "motor_electrical_forcing",
    ]:
        results.append(diagnose_asset_wide_fault(asset, fault_key))

    for bearing in asset.bearings:
        for fault_key in [
            "lubrication_distress",
            "fluid_film_instability" if bearing.bearing_type == "fluid_film" else None,
            "thrust_bearing_or_axial_overload" if (bearing.is_thrust_bearing or bearing.bearing_type == "thrust") else None,
            "bearing_bpfo" if bearing.bearing_type == "rolling" else None,
            "bearing_bpfi" if bearing.bearing_type == "rolling" else None,
            "bearing_bsf" if bearing.bearing_type == "rolling" else None,
            "bearing_ftf" if bearing.bearing_type == "rolling" else None,
        ]:
            if fault_key:
                results.append(diagnose_bearing_local_fault(asset, fault_key, bearing))

    for stage in asset.gear_stages:
        results.append(diagnose_gear_fault(asset, stage))
        for fk in [
            "gear_misalignment",
            "gear_eccentricity",
            "gear_backlash",
            "gear_tooth_wear",
            "gear_tooth_damage_localized",
        ]:
            results.append(diagnose_gear_subfault(asset, fk, stage))

    for belt in _asset_belt_drives(asset):
        for fk in [
            "belt_sheave_misalignment",
            "belt_sheave_eccentricity",
            "belt_slip_or_tension_fault",
            "belt_wear_or_damage",
            "belt_span_resonance",
        ]:
            results.append(diagnose_belt_fault(asset, fk, belt))

    for hydraulic in asset.hydraulic_elements:
        results.append(diagnose_hydraulic_fault(asset, "hydraulic_vane_or_blade_pass", hydraulic))
        results.append(diagnose_hydraulic_fault(asset, "cavitation_or_aeration", hydraulic))

    _postprocess_results(asset, results)
    _postprocess_belt_results(asset, results)
    _annotate_results(results)
    condition_summary = _apply_condition_severity(asset, results, condition_scorer)
    _apply_explainability(results, pattern_profile, condition_summary)

    filtered = [r for r in results if r.score >= minimum_score and r.confidence != "none"]
    filtered.sort(key=lambda r: (-(r.fault_severity_score or r.score), -r.score, r.fault_key, r.target))
    return filtered


# ---------------------------------------------------------------------------
# Bearing lubrication-vs-wear differentiation patch
# Grounded in Emerson PeakVue guidance and broader literature:
# - lubrication deficiency -> more random/non-periodic impact energy, often with
#   higher HF content and weaker defect periodicity
# - bearing wear / progressing surface damage -> stronger periodic envelope
#   content at bearing characteristic frequencies with repeated hits/harmonics
# ---------------------------------------------------------------------------

FAULT_LIBRARY["bearing_wear_progression"] = {"scope": "bearing_local", "phase_cap": "high"}
FAULT_TO_CONDITION_FAMILY["bearing_wear_progression"] = "bearing"
FAULT_RISK_BONUS["bearing_wear_progression"] = 0.07


def _bearing_envelope_centroid_ratio(signal: AxisSignal) -> float:
    if signal.envelope_freqs_hz is None or signal.envelope_spectrum is None:
        return 0.0
    freqs = np.asarray(signal.envelope_freqs_hz, dtype=float).reshape(-1)
    amps = np.asarray(signal.envelope_spectrum, dtype=float).reshape(-1)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        return 0.0
    weights = np.abs(amps)
    if np.sum(weights) <= 1e-12 or freqs[-1] <= 0.0:
        return 0.0
    centroid = float(np.sum(freqs * weights) / (np.sum(weights) + 1e-12))
    return _safe_ratio(centroid, max(float(freqs[-1]), 1e-12))



def _bearing_characteristic_evidence(
    asset: AssetDefinition,
    bearing: BearingDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, float]:
    if bearing.bearing_type != "rolling":
        return {
            "best_defect_env_score": 0.0,
            "best_defect_hits": 0.0,
            "raceway_env_score": 0.0,
            "cage_ball_env_score": 0.0,
            "raceway_fraction": 0.0,
            "cage_ball_fraction": 0.0,
            "defect_hit_total": 0.0,
            "envelope_centroid_ratio": _bearing_envelope_centroid_ratio(signal),
            "bpfo_env_score": 0.0,
            "bpfi_env_score": 0.0,
            "bsf_env_score": 0.0,
            "ftf_env_score": 0.0,
            "bpfo_hits": 0.0,
            "bpfi_hits": 0.0,
            "bsf_hits": 0.0,
            "ftf_hits": 0.0,
        }
    freqs = bearing_fault_frequencies_hz(sensor.local_rpm or asset.running_rpm, bearing)
    out: Dict[str, float] = {"envelope_centroid_ratio": _bearing_envelope_centroid_ratio(signal)}
    scores: Dict[str, float] = {}
    hits_map: Dict[str, int] = {}
    for family in ("bpfo", "bpfi", "bsf", "ftf"):
        target_hz = freqs.get(family, 0.0)
        env_score, hits = envelope_harmonic_hit_score(signal, target_hz, max(feat.tolerance_hz, target_hz * 0.03), harmonics=4)
        scores[family] = float(env_score)
        hits_map[family] = int(hits)
        out[f"{family}_env_score"] = float(env_score)
        out[f"{family}_hits"] = float(hits)
    raceway_score = max(scores.get("bpfo", 0.0), scores.get("bpfi", 0.0))
    cage_ball_score = max(scores.get("bsf", 0.0), scores.get("ftf", 0.0))
    best_family = max(scores, key=scores.get) if scores else "unknown"
    best_defect_score = scores.get(best_family, 0.0)
    best_hits = hits_map.get(best_family, 0)
    defect_hit_total = float(sum(hits_map.values()))
    total_family_score = raceway_score + cage_ball_score
    out.update({
        "best_defect_env_score": float(best_defect_score),
        "best_defect_hits": float(best_hits),
        "raceway_env_score": float(raceway_score),
        "cage_ball_env_score": float(cage_ball_score),
        "raceway_fraction": _safe_ratio(raceway_score, max(total_family_score, 1e-12)),
        "cage_ball_fraction": _safe_ratio(cage_ball_score, max(total_family_score, 1e-12)),
        "defect_hit_total": defect_hit_total,
    })
    if best_family == "unknown":
        out["best_family_code"] = 0.0
    else:
        out["best_family_code"] = float({"bpfo": 1.0, "bpfi": 2.0, "bsf": 3.0, "ftf": 4.0}[best_family])
    return out



def _bearing_like_weight(sensor: SensorMeasurement, axis_name: str) -> float:
    return _axis_weight("bearing_bpfo", sensor, axis_name) * _component_weight("bearing_bpfo", sensor)


_bearing_patch_previous_local_score = _bearing_local_score_from_axis


def _bearing_local_score_from_axis(
    fault_key: str,
    asset: AssetDefinition,
    bearing: BearingDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Tuple[float, List[str], Dict[str, float]]:
    temp_delta = _temperature_delta_c(asset, sensor)
    evidence_pack = _bearing_characteristic_evidence(asset, bearing, sensor, feat, signal)
    random_impact = 1.0 - feat.wf_impact_periodicity
    if fault_key == "lubrication_distress":
        # Emerson/PeakVue: lubrication tends to be random/non-periodic impact energy.
        # Literature also reports higher cage/ball-spin support and stronger HF randomness
        # under lubrication starvation than under localized raceway damage.
        best_defect = evidence_pack.get("best_defect_env_score", 0.0)
        raceway_fraction = evidence_pack.get("raceway_fraction", 0.0)
        cage_ball_fraction = evidence_pack.get("cage_ball_fraction", 0.0)
        score = (
            20.0 * _score_linear(feat.hf_rms_ratio, 0.55, 2.50) +
            10.0 * _score_linear(max(feat.kurtosis, 0.0), 0.40, 2.80) +
            8.0 * _score_linear(feat.crest_factor, 3.2, 6.2) +
            14.0 * _score_linear(temp_delta, 4.0, 18.0) +
            18.0 * _score_linear(random_impact, 0.30, 0.85) +
            12.0 * _score_linear(evidence_pack.get("envelope_centroid_ratio", 0.0), 0.18, 0.55) +
            10.0 * _score_linear(cage_ball_fraction, 0.40, 0.80) +
            8.0 * (1.0 - _score_linear(best_defect, 28.0, 70.0))
        )
        if best_defect >= 55.0 and feat.wf_impact_periodicity >= 0.35:
            score *= 0.58
        if raceway_fraction >= 0.60 and evidence_pack.get("defect_hit_total", 0.0) >= 3.0:
            score *= 0.72
        metrics = {
            "temp_delta_c": temp_delta,
            "waveform_impact_periodicity": feat.wf_impact_periodicity,
            "random_impact_ratio": random_impact,
            **evidence_pack,
        }
        evidence = [
            f"{sensor.sensor_id}/{feat.axis}: HF={feat.hf_rms_ratio:.2f}, kurtosis={feat.kurtosis:.2f}, crest={feat.crest_factor:.2f}, "
            f"impact_periodicity={feat.wf_impact_periodicity:.2f}, random_impact={random_impact:.2f}, best_defect_env={best_defect:.1f}, "
            f"cage_ball_fraction={cage_ball_fraction:.2f}, env_centroid={evidence_pack.get('envelope_centroid_ratio', 0.0):.2f}, temp_delta={temp_delta:.1f}C"
        ]
        score *= _bearing_like_weight(sensor, feat.axis)
        return float(score), evidence, metrics

    if fault_key == "bearing_wear_progression":
        if bearing.bearing_type != "rolling":
            return 0.0, [], {}
        best_defect = evidence_pack.get("best_defect_env_score", 0.0)
        best_hits = evidence_pack.get("best_defect_hits", 0.0)
        raceway_fraction = evidence_pack.get("raceway_fraction", 0.0)
        score = (
            34.0 * _score_linear(best_defect, 18.0, 78.0) +
            12.0 * _score_linear(best_hits, 1.0, 4.0) +
            12.0 * _score_linear(evidence_pack.get("defect_hit_total", 0.0), 2.0, 8.0) +
            16.0 * _score_linear(feat.wf_impact_periodicity, 0.22, 0.80) +
            10.0 * _score_linear(temp_delta, 4.0, 18.0) +
            8.0 * _score_linear(feat.hf_rms_ratio, 0.50, 2.20) +
            8.0 * _score_linear(max(feat.kurtosis, 0.0), 0.30, 2.80)
        )
        # Wear should favor periodic mechanical evidence over random starvation noise.
        score *= 0.85 + 0.30 * _score_linear(raceway_fraction, 0.35, 0.80)
        if best_defect < 24.0:
            score *= 0.55
        if random_impact >= 0.70 and feat.wf_impact_periodicity < 0.18:
            score *= 0.52
        metrics = {
            "temp_delta_c": temp_delta,
            "waveform_impact_periodicity": feat.wf_impact_periodicity,
            "random_impact_ratio": random_impact,
            **evidence_pack,
        }
        evidence = [
            f"{sensor.sensor_id}/{feat.axis}: best_defect_env={best_defect:.1f}, defect_hits={best_hits:.0f}, total_hits={evidence_pack.get('defect_hit_total', 0.0):.0f}, "
            f"periodicity={feat.wf_impact_periodicity:.2f}, raceway_fraction={raceway_fraction:.2f}, HF={feat.hf_rms_ratio:.2f}, temp_delta={temp_delta:.1f}C"
        ]
        score *= _bearing_like_weight(sensor, feat.axis)
        return float(score), evidence, metrics

    return _bearing_patch_previous_local_score(fault_key, asset, bearing, sensor, feat, signal)


_bearing_patch_previous_diagnose_bearing_local_fault = diagnose_bearing_local_fault


def diagnose_bearing_local_fault(asset: AssetDefinition, fault_key: str, bearing: BearingDefinition) -> FaultResult:
    selected = _selected_scope_sensors(asset, fault_key, bearing_id=bearing.bearing_id)
    local_scores: List[float] = []
    sensor_ids: List[str] = []
    evidence: List[str] = []
    metrics_acc: Dict[str, List[float]] = {}

    for sensor in selected:
        axis_feats = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in axis_feats.items():
            signal = sensor.directions[axis_name]
            score, ev, metrics = _bearing_local_score_from_axis(fault_key, asset, bearing, sensor, feat, signal)
            if score > 0.0:
                local_scores.append(score)
                sensor_ids.append(sensor.sensor_id)
                evidence.extend(ev)
                for k, v in metrics.items():
                    if isinstance(v, (int, float)):
                        metrics_acc.setdefault(k, []).append(float(v))

    top = _top_mean(local_scores, n=3)
    local_coverage = 18.0 * _score_linear(_distinct_count(sensor_ids), 1.0, 2.0)
    repeatability = 12.0 * _score_linear(sum(1 for s in local_scores if s >= 45.0), 1.0, 3.0)
    score = _clamp(0.70 * top + local_coverage + repeatability, 0.0, 100.0)
    cap = str(FAULT_LIBRARY[fault_key]["phase_cap"])
    confidence = _confidence_from_score(score, cap)
    limitations: List[str] = []
    if fault_key.startswith("bearing_") and fault_key != "bearing_wear_progression":
        limitations.append("Bearing family confidence depends on correct geometry, speed and envelope processing.")
    if fault_key == "lubrication_distress":
        limitations.append("Lubrication distress is strongest when random/non-periodic impact energy dominates over defect-frequency periodicity; surface temperature remains corroborative only.")
    if fault_key == "bearing_wear_progression":
        limitations.append("Bearing wear/progression is a generic mechanical-distress bucket; use BPFO/BPFI/BSF/FTF families to localize the wear mechanism when geometry is reliable.")
    if fault_key == "thrust_bearing_or_axial_overload":
        limitations.append("Without axial position or process thrust data, keep this diagnosis conservative.")

    metrics_out = {k: float(mean(v)) for k, v in metrics_acc.items() if v}
    return FaultResult(
        fault_key=fault_key,
        target=bearing.bearing_id,
        scope="bearing_local",
        score=score,
        confidence=confidence,
        sensors_used=sorted(set(sensor_ids)),
        evidence=evidence[:8],
        limitations=limitations,
        supporting_metrics=metrics_out,
    )



def _postprocess_bearing_lubrication_vs_wear(results: List[FaultResult]) -> None:
    by_target: Dict[str, Dict[str, FaultResult]] = {}
    for r in results:
        if r.scope != "bearing_local":
            continue
        by_target.setdefault(r.target, {})[r.fault_key] = r

    for target, pack in by_target.items():
        lub = pack.get("lubrication_distress")
        wear = pack.get("bearing_wear_progression")
        specifics = [pack.get(k) for k in ("bearing_bpfo", "bearing_bpfi", "bearing_bsf", "bearing_ftf") if pack.get(k) is not None]
        best_specific = max(specifics, key=lambda x: x.score) if specifics else None

        if lub is not None:
            if best_specific is not None and best_specific.score >= 55.0 and lub.supporting_metrics.get("waveform_impact_periodicity", 0.0) >= 0.30:
                lub.score *= 0.62
                lub.limitations.append("Reduced because periodic defect-frequency evidence is stronger than the random-impact pattern expected from pure lubrication deficiency.")
            if lub.supporting_metrics.get("raceway_fraction", 0.0) >= 0.62 and lub.supporting_metrics.get("best_defect_env_score", 0.0) >= 55.0:
                lub.score *= 0.70
                lub.limitations.append("Reduced because raceway-family envelope content is too strong for a clean lubrication-only diagnosis.")
            _refresh_result_confidence(lub)

        if wear is not None:
            if wear.supporting_metrics.get("best_defect_env_score", 0.0) < 28.0:
                wear.score *= 0.62
                wear.limitations.append("Reduced because defect-frequency envelope evidence is weak for a wear/progression call.")
            if wear.supporting_metrics.get("random_impact_ratio", 0.0) >= 0.70 and wear.supporting_metrics.get("waveform_impact_periodicity", 0.0) < 0.18:
                wear.score *= 0.55
                wear.limitations.append("Reduced because the signal is dominated by random non-periodic impacts, which is more characteristic of lubrication deficiency than bearing wear progression.")
            if lub is not None and lub.supporting_metrics.get("cage_ball_fraction", 0.0) >= 0.60 and wear.supporting_metrics.get("raceway_fraction", 0.0) < 0.45:
                wear.score *= 0.78
                wear.limitations.append("Reduced because cage/ball-spin evidence dominates without sufficient periodic raceway-family support.")
            _refresh_result_confidence(wear)


_bearing_patch_previous_fault_recommendations = _fault_recommendations


def _fault_recommendations(result: FaultResult) -> List[str]:
    if result.fault_key == "bearing_wear_progression":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Review envelope spectrum families first: strong periodic BPFO/BPFI/BSF/FTF content indicates mechanical bearing damage progression rather than pure lubrication deficiency.",
            "Inspect bearing fits, contamination history, load/alignment, and replacement strategy; correct the root cause instead of replacing the bearing only.",
        ]
    return _bearing_patch_previous_fault_recommendations(result)


_urgency_patch_previous_urgency_from_severity = _urgency_from_severity


def _urgency_from_severity(score_0_1: float, condition_alarm: Optional[str], fault_key: str) -> str:
    urgent_faults = {"rotor_rub", "bearing_bpfo", "bearing_bpfi", "bearing_bsf", "bearing_wear_progression", "gear_mesh_fault", "cavitation_or_aeration"}
    label = _severity_label_from_score(score_0_1)
    if label == "critical":
        return "immediate_review"
    if condition_alarm == "critical" or (fault_key in urgent_faults and label in {"high", "critical"}):
        return "urgent"
    if label == "high":
        return "urgent"
    if label == "medium":
        return "plan"
    return "monitor"



def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
) -> List[FaultResult]:
    asset.metadata.pop("_analysis_context", None)
    _get_analysis_context(asset, refresh=True)
    results: List[FaultResult] = []
    pattern_profile = classify_asset_pattern(asset)
    asset.metadata["_pattern_classifier"] = pattern_profile.as_dict()

    for fault_key in [
        "unbalance",
        "misalignment",
        "looseness_type_a_base_structure",
        "looseness_type_b_pedestal_support",
        "looseness_type_c_rotating_fit",
        "soft_foot_or_frame_distortion",
        "bent_shaft_or_bow",
        "resonance_or_structural_amplification",
        "rotor_rub",
        "motor_electrical_forcing",
    ]:
        results.append(diagnose_asset_wide_fault(asset, fault_key))

    for bearing in asset.bearings:
        for fault_key in [
            "lubrication_distress",
            "bearing_wear_progression" if bearing.bearing_type == "rolling" else None,
            "fluid_film_instability" if bearing.bearing_type == "fluid_film" else None,
            "thrust_bearing_or_axial_overload" if (bearing.is_thrust_bearing or bearing.bearing_type == "thrust") else None,
            "bearing_bpfo" if bearing.bearing_type == "rolling" else None,
            "bearing_bpfi" if bearing.bearing_type == "rolling" else None,
            "bearing_bsf" if bearing.bearing_type == "rolling" else None,
            "bearing_ftf" if bearing.bearing_type == "rolling" else None,
        ]:
            if fault_key:
                results.append(diagnose_bearing_local_fault(asset, fault_key, bearing))

    for stage in asset.gear_stages:
        results.append(diagnose_gear_fault(asset, stage))
        for fk in [
            "gear_misalignment",
            "gear_eccentricity",
            "gear_backlash",
            "gear_tooth_wear",
            "gear_tooth_damage_localized",
        ]:
            results.append(diagnose_gear_subfault(asset, fk, stage))

    for belt in _asset_belt_drives(asset):
        for fk in [
            "belt_sheave_misalignment",
            "belt_sheave_eccentricity",
            "belt_slip_or_tension_fault",
            "belt_wear_or_damage",
            "belt_span_resonance",
        ]:
            results.append(diagnose_belt_fault(asset, fk, belt))

    for hydraulic in asset.hydraulic_elements:
        results.append(diagnose_hydraulic_fault(asset, "hydraulic_vane_or_blade_pass", hydraulic))
        results.append(diagnose_hydraulic_fault(asset, "cavitation_or_aeration", hydraulic))

    _postprocess_results(asset, results)
    _postprocess_belt_results(asset, results)
    _postprocess_bearing_lubrication_vs_wear(results)
    _annotate_results(results)
    effective_condition_scorer = condition_scorer if compute_condition_summary else None
    condition_summary = _apply_condition_severity(asset, results, effective_condition_scorer)
    _apply_explainability(results, pattern_profile, condition_summary)

    filtered = [r for r in results if r.score >= minimum_score and r.confidence != "none"]
    filtered.sort(key=lambda r: (-(r.fault_severity_score or r.score), -r.score, r.fault_key, r.target))
    return filtered

# ---------------------------------------------------------------------------
# Performance cache patch (diagnostic-equivalent)
# ---------------------------------------------------------------------------

EPS = CONDITION_EPS

_EMPTY_FLOAT_ARRAY = np.asarray([], dtype=float)


def _runtime_cache_dict(obj: Any, attr: str) -> Dict[Any, Any]:
    cache = getattr(obj, attr, None)
    if cache is None:
        cache = {}
        setattr(obj, attr, cache)
    return cache


def _cached_signal_array(signal: AxisSignal, field_name: str) -> Optional[np.ndarray]:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    if field_name in cache:
        return cache[field_name]
    source = getattr(signal, field_name, None)
    if source is None:
        cache[field_name] = None
        return None
    arr = np.asarray(source, dtype=float).reshape(-1)
    cache[field_name] = arr
    return arr


def _cached_signal_spectrum_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    freqs = _cached_signal_array(signal, "freqs_hz")
    amps = _cached_signal_array(signal, "spectrum")
    if freqs is None or amps is None:
        return _EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY
    return freqs, amps


def _cached_signal_positive_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = "__positive_spectrum__"
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        out = (_EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY)
    else:
        positive = freqs > 0.0
        out = (freqs[positive], amps[positive]) if np.any(positive) else (_EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY)
    cache[key] = out
    return out


def _cached_signal_positive_sorted_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = "__positive_sorted_spectrum__"
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_positive_arrays(signal)
    if freqs.size > 1 and np.any(np.diff(freqs) < 0.0):
        order = np.argsort(freqs)
        out = (freqs[order], amps[order])
    else:
        out = (freqs, amps)
    cache[key] = out
    return out


def _cached_signal_envelope_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = "__envelope_arrays__"
    if key in cache:
        return cache[key]
    freqs = _cached_signal_array(signal, "envelope_freqs_hz")
    amps = _cached_signal_array(signal, "envelope_spectrum")
    out = (_EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY) if freqs is None or amps is None else (freqs, amps)
    cache[key] = out
    return out


def _clear_signal_runtime_caches(asset: AssetDefinition) -> None:
    for sensor in asset.sensors:
        for signal in sensor.directions.values():
            if hasattr(signal, "_runtime_np_cache"):
                getattr(signal, "_runtime_np_cache").clear()


def _waveform_sample_rate_hz(signal: "AxisSignal") -> float:
    if getattr(signal, "waveform_sample_rate_hz", None):
        return float(signal.waveform_sample_rate_hz)
    freqs = _cached_signal_array(signal, "freqs_hz")
    if freqs is None or freqs.size == 0:
        return 0.0
    positive = freqs[freqs > 0.0]
    if positive.size >= 2:
        return float(2.0 * np.max(positive))
    return 0.0


def _waveform_array(signal: "AxisSignal", kind: str) -> Optional[np.ndarray]:
    if kind == "velocity":
        field_name = "velocity_waveform" if signal.velocity_waveform is not None else "waveform"
    elif kind == "acceleration":
        field_name = "acceleration_waveform" if signal.acceleration_waveform is not None else "waveform"
    else:
        field_name = "waveform"
    arr = _cached_signal_array(signal, field_name)
    if arr is None:
        return None
    return arr if arr.size >= 16 else None


def extract_axis_features(signal: AxisSignal, rpm: float, tolerance_pct: float = 3.0) -> AxisFeatures:
    freqs, amps = _cached_signal_positive_sorted_arrays(signal)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        raise ValueError(f"Bad spectrum for axis {signal.axis!r}")
    if freqs.size == 0:
        raise ValueError(f"No positive frequencies for axis {signal.axis!r}")

    shaft_hz = shaft_hz_from_rpm(rpm)
    freq_res = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(shaft_hz * 0.03, 0.1)
    tolerance_hz = max(abs(shaft_hz) * tolerance_pct / 100.0, 1.5 * freq_res)
    noise_floor = float(np.median(np.abs(amps)))
    dominant_idx = int(np.argmax(amps))
    dominant_freq_hz = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])

    hf_start = max(5.0 * shaft_hz, 50.0 if freqs[-1] >= 100.0 else 3.0 * shaft_hz)
    hf_mask = freqs >= hf_start
    rms_spectrum = _rms(amps)
    hf_rms_ratio = _safe_ratio(_rms(amps[hf_mask]) if np.any(hf_mask) else 0.0, rms_spectrum)

    harmonic_peaks = _peak_amplitudes_at_targets(
        freqs,
        amps,
        {
            "amp_05x": 0.5 * shaft_hz,
            "amp_1x": 1.0 * shaft_hz,
            "amp_15x": 1.5 * shaft_hz,
            "amp_2x": 2.0 * shaft_hz,
            "amp_25x": 2.5 * shaft_hz,
            "amp_3x": 3.0 * shaft_hz,
            "amp_35x": 3.5 * shaft_hz,
            "amp_4x": 4.0 * shaft_hz,
            "amp_5x": 5.0 * shaft_hz,
            "amp_6x": 6.0 * shaft_hz,
            "amp_7x": 7.0 * shaft_hz,
            "amp_8x": 8.0 * shaft_hz,
            "amp_9x": 9.0 * shaft_hz,
            "amp_10x": 10.0 * shaft_hz,
        },
        tolerance_hz,
    )

    subsync_freq_hz, subsync_amp = _peak_in_band(freqs, amps, 0.42 * shaft_hz, 0.48 * shaft_hz)
    waveform_for_impacts = _waveform_array(signal, "acceleration")
    if waveform_for_impacts is None:
        waveform_for_impacts = _waveform_array(signal, "generic")
    wf_1x_pulse, wf_2x_pulse, wf_impact_periodicity = _waveform_shape_metrics(signal, shaft_hz)
    envelope_spectrum = _cached_signal_array(signal, "envelope_spectrum")
    envelope_rms = _rms(envelope_spectrum) if envelope_spectrum is not None else 0.0

    return AxisFeatures(
        axis=signal.axis.lower(),
        shaft_hz=shaft_hz,
        tolerance_hz=tolerance_hz,
        amp_05x=harmonic_peaks["amp_05x"],
        amp_1x=harmonic_peaks["amp_1x"],
        amp_2x=harmonic_peaks["amp_2x"],
        amp_3x=harmonic_peaks["amp_3x"],
        amp_35x=harmonic_peaks["amp_35x"],
        amp_4x=harmonic_peaks["amp_4x"],
        amp_5x=harmonic_peaks["amp_5x"],
        amp_6x=harmonic_peaks["amp_6x"],
        amp_7x=harmonic_peaks["amp_7x"],
        amp_8x=harmonic_peaks["amp_8x"],
        amp_9x=harmonic_peaks["amp_9x"],
        amp_10x=harmonic_peaks["amp_10x"],
        amp_15x=harmonic_peaks["amp_15x"],
        amp_25x=harmonic_peaks["amp_25x"],
        dominant_freq_hz=dominant_freq_hz,
        dominant_amp=dominant_amp,
        subsync_freq_hz=subsync_freq_hz,
        subsync_amp=subsync_amp,
        rms_spectrum=rms_spectrum,
        crest_factor=_crest_factor(waveform_for_impacts),
        kurtosis=_kurtosis_excess(waveform_for_impacts),
        hf_rms_ratio=hf_rms_ratio,
        noise_floor=noise_floor,
        wf_1x_pulse=wf_1x_pulse,
        wf_2x_pulse=wf_2x_pulse,
        wf_impact_periodicity=wf_impact_periodicity,
        envelope_rms=envelope_rms,
    )


def envelope_harmonic_hit_score(
    signal: AxisSignal,
    target_hz: float,
    tolerance_hz: float,
    harmonics: int = 4,
) -> Tuple[float, int]:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = ("__env_hit__", float(target_hz), float(tolerance_hz), int(harmonics))
    if key in cache:
        return cache[key]
    if target_hz <= 0.0 or signal.envelope_freqs_hz is None or signal.envelope_spectrum is None:
        out = (0.0, 0)
        cache[key] = out
        return out
    freqs, amps = _cached_signal_envelope_arrays(signal)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        out = (0.0, 0)
        cache[key] = out
        return out

    rms = _rms(amps)
    hits = 0
    strengths: List[float] = []
    for order in range(1, harmonics + 1):
        _, amp = _peak_at(freqs, amps, order * target_hz, tolerance_hz)
        score = _score_linear(_safe_ratio(amp, rms), 1.1, 4.0)
        if score > 0.2:
            hits += 1
        strengths.append(score)
    total = 100.0 * (0.65 * (_top_mean(strengths, n=3)) + 0.35 * _score_linear(hits, 1.0, float(harmonics)))
    out = (float(total), hits)
    cache[key] = out
    return out


_opt_prev_selected_scope_sensors = _selected_scope_sensors


def _selected_scope_sensors(
    asset: AssetDefinition,
    fault_key: str,
    bearing_id: Optional[str] = None,
    gear_stage_id: Optional[str] = None,
    hydraulic_id: Optional[str] = None,
) -> List[SensorMeasurement]:
    cache = asset.metadata.setdefault("_scope_sensor_cache", {})
    key = (fault_key, bearing_id, gear_stage_id, hydraulic_id)
    if key not in cache:
        cache[key] = _opt_prev_selected_scope_sensors(asset, fault_key, bearing_id=bearing_id, gear_stage_id=gear_stage_id, hydraulic_id=hydraulic_id)
    return cache[key]



def _temperature_delta_c(asset: AssetDefinition, sensor: SensorMeasurement) -> float:
    cache = asset.metadata.setdefault("_temperature_delta_cache", {})
    if sensor.sensor_id in cache:
        return cache[sensor.sensor_id]
    if sensor.surface_temperature_c is None:
        cache[sensor.sensor_id] = 0.0
        return 0.0

    local_peers = [
        s.surface_temperature_c
        for s in asset.sensors
        if s.sensor_id != sensor.sensor_id
        and s.surface_temperature_c is not None
        and s.component_id == sensor.component_id
    ]
    same_mount_peers = [
        s.surface_temperature_c
        for s in asset.sensors
        if s.sensor_id != sensor.sensor_id
        and s.surface_temperature_c is not None
        and s.component_id == sensor.component_id
        and s.installed_on.lower() == sensor.installed_on.lower()
    ]
    asset_peers = [s.surface_temperature_c for s in asset.sensors if s.surface_temperature_c is not None]

    if same_mount_peers:
        base = float(median(same_mount_peers))
    elif local_peers:
        base = float(median(local_peers))
    elif asset_peers:
        base = float(median(asset_peers))
    else:
        cache[sensor.sensor_id] = 0.0
        return 0.0
    delta = float(sensor.surface_temperature_c - base)
    cache[sensor.sensor_id] = delta
    return delta



def _sideband_pair_ratio(signal: AxisSignal, center_hz: float, spacing_hz: float, tolerance_hz: float) -> float:
    if center_hz <= 0.0 or spacing_hz <= 0.0:
        return 0.0
    freqs, amps = _cached_signal_positive_arrays(signal)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        return 0.0
    _, center_amp = _peak_at(freqs, amps, center_hz, tolerance_hz)
    if center_amp <= 1e-12:
        return 0.0
    _, left_amp = _peak_at(freqs, amps, center_hz - spacing_hz, tolerance_hz)
    _, right_amp = _peak_at(freqs, amps, center_hz + spacing_hz, tolerance_hz)
    return _safe_ratio(0.5 * (left_amp + right_amp), center_amp)



def _score_motor_electrical(sensor: SensorMeasurement, feat: AxisFeatures, asset: AssetDefinition) -> float:
    motor = next((m for m in asset.motors if m.component_id == sensor.component_id), None)
    if motor is None:
        return 0.0
    line = float(motor.line_frequency_hz)
    tol = max(feat.tolerance_hz, 1.0)
    signal = sensor.directions[feat.axis]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    _, amp_1lf = _peak_at(freqs, amps, line, tol)
    _, amp_2lf = _peak_at(freqs, amps, 2.0 * line, tol)
    line_ratio = _safe_ratio(amp_1lf, max(feat.rms_spectrum, 1e-12))
    double_line_ratio = _safe_ratio(amp_2lf, max(feat.rms_spectrum, 1e-12))
    score = (
        38.0 * _score_linear(double_line_ratio, 0.5, 3.0) +
        18.0 * _score_linear(line_ratio, 0.4, 2.0) +
        14.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x), 0.8, 2.5)) +
        15.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x), 2.0, 6.0)) +
        15.0 * _score_linear(max(line_ratio, double_line_ratio), 0.7, 3.0)
    )
    return float(score * _axis_weight("motor_electrical_forcing", sensor, feat.axis) * _component_weight("motor_electrical_forcing", sensor))



def _gear_axis_score(asset: AssetDefinition, stage: GearStageDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Tuple[float, List[str], Dict[str, float]]:
    input_rpm = stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm
    gmf = gear_mesh_frequency_hz(input_rpm, stage)
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    tol = max(feat.tolerance_hz, gmf * 0.03)
    _, gmf_amp = _peak_at(freqs, amps, gmf, tol)
    _, gmf2_amp = _peak_at(freqs, amps, 2.0 * gmf, tol)
    _, left = _peak_at(freqs, amps, gmf - feat.shaft_hz, tol)
    _, right = _peak_at(freqs, amps, gmf + feat.shaft_hz, tol)
    symmetry = _safe_ratio(min(left, right), max(left, right, 1e-12))
    sideband_ratio = _safe_ratio(left + right, max(gmf_amp, 1e-12))
    env_score, env_hits = envelope_harmonic_hit_score(signal, gmf, tol, harmonics=3)
    score = (
        28.0 * _score_linear(_safe_ratio(gmf_amp, max(feat.rms_spectrum, 1e-12)), 0.6, 3.5) +
        12.0 * _score_linear(_safe_ratio(gmf2_amp, max(feat.rms_spectrum, 1e-12)), 0.3, 2.0) +
        22.0 * _score_linear(sideband_ratio, 0.2, 1.0) +
        10.0 * _score_linear(symmetry, 0.2, 0.8) +
        16.0 * _score_linear(env_score, 18.0, 75.0) +
        8.0 * _score_linear(feat.hf_rms_ratio, 0.7, 2.5) +
        4.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5)
    )
    score *= _axis_weight("gear_mesh_fault", sensor, feat.axis) * _component_weight("gear_mesh_fault", sensor)
    evidence = [f"{sensor.sensor_id}/{feat.axis}: GMF={gmf:.1f}Hz, GMF_amp={_safe_ratio(gmf_amp, max(feat.rms_spectrum, 1e-12)):.2f}xRMS, SB={sideband_ratio:.2f}, symmetry={symmetry:.2f}, env={env_score:.1f}, hits={env_hits}"]
    metrics = {"gmf_hz": gmf, "sideband_ratio": sideband_ratio, "symmetry": symmetry, "env_score": env_score}
    return float(score), evidence, metrics



def _hydraulic_axis_scores(
    asset: AssetDefinition,
    hydraulic: HydraulicElementDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, Tuple[float, List[str], Dict[str, float]]]:
    cache = asset.metadata.setdefault("_hydraulic_axis_score_cache", {})
    key = (hydraulic.hydraulic_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    local_rpm = hydraulic.local_rpm or sensor.local_rpm or asset.running_rpm
    pass_hz = hydraulic_pass_frequency_hz(local_rpm, hydraulic)
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    tol = max(feat.tolerance_hz, pass_hz * 0.03)
    _, pass_amp = _peak_at(freqs, amps, pass_hz, tol)
    _, left = _peak_at(freqs, amps, max(pass_hz - feat.shaft_hz, 0.0), tol)
    _, right = _peak_at(freqs, amps, pass_hz + feat.shaft_hz, tol)
    pass_ratio = _safe_ratio(pass_amp, max(feat.rms_spectrum, 1e-12))
    sideband_ratio = _safe_ratio(left + right, max(pass_amp, 1e-12))
    dominant_order_match = 1.0 - min(abs(feat.dominant_order - float(hydraulic.pass_count)) / max(float(hydraulic.pass_count), 1.0), 1.0)
    score_pass = (
        36.0 * _score_linear(pass_ratio, 0.5, 3.0) +
        18.0 * dominant_order_match +
        18.0 * _score_linear(sideband_ratio, 0.10, 0.80) +
        10.0 * _score_linear(feat.hf_rms_ratio, 0.6, 2.0) +
        10.0 * _score_linear(_temperature_delta_c(asset, sensor), 4.0, 16.0) +
        8.0 * _score_linear(max(feat.kurtosis, 0.0), 0.4, 2.5)
    )
    score_pass *= _axis_weight("hydraulic_vane_or_blade_pass", sensor, feat.axis) * _component_weight("hydraulic_vane_or_blade_pass", sensor)

    score_cav = (
        38.0 * _score_linear(feat.hf_rms_ratio, 0.8, 3.2) +
        18.0 * _score_linear(max(feat.kurtosis, 0.0), 0.5, 3.0) +
        16.0 * _score_linear(feat.crest_factor, 3.6, 6.8) +
        12.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_1x), 1.6, 5.0)) +
        10.0 * (1.0 - _score_linear(pass_ratio, 0.7, 3.0)) +
        6.0 * _score_linear(_safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)), 0.3, 1.5)
    )
    score_cav *= _axis_weight("cavitation_or_aeration", sensor, feat.axis) * _component_weight("cavitation_or_aeration", sensor)

    out = {
        "hydraulic_vane_or_blade_pass": (
            float(score_pass),
            [f"{sensor.sensor_id}/{feat.axis}: pass_freq={pass_hz:.1f}Hz, pass_amp={pass_ratio:.2f}xRMS, sidebands={sideband_ratio:.2f}, dominant_order={feat.dominant_order:.2f}x"],
            {"pass_hz": pass_hz, "pass_ratio": pass_ratio, "sideband_ratio": sideband_ratio},
        ),
        "cavitation_or_aeration": (
            float(score_cav),
            [f"{sensor.sensor_id}/{feat.axis}: HF={feat.hf_rms_ratio:.2f}, kurtosis={feat.kurtosis:.2f}, crest={feat.crest_factor:.2f}, 1x={feat.amp_ratio(feat.amp_1x):.2f}xRMS"],
            {"hf_rms_ratio": feat.hf_rms_ratio},
        ),
    }
    cache[key] = out
    return out



def _gear_subfault_features(
    asset: AssetDefinition,
    stage: GearStageDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_gear_subfault_feature_cache", {})
    key = (stage.gear_stage_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    in_hz, out_hz = _stage_shaft_speeds_hz(asset, stage, sensor)
    gmf = gear_mesh_frequency_hz((stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm), stage)
    tol = max(feat.tolerance_hz, gmf * 0.03)

    harm = _mesh_harmonic_pack(freqs, amps, gmf, tol, harmonics=4)
    sb_in_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, in_hz, tol, sidebands=2)
    sb_out_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, out_hz, tol, sidebands=2)
    wave = _mesh_band_waveform_metrics(signal, gmf)

    spacing_owner = "input"
    if max(sb_out_1["mean_pair_ratio"], sb_out_2["mean_pair_ratio"], sb_out_3["mean_pair_ratio"]) > max(sb_in_1["mean_pair_ratio"], sb_in_2["mean_pair_ratio"], sb_in_3["mean_pair_ratio"]):
        spacing_owner = "output"

    gnf_ratio = _gear_mesh_resonance_band_energy(freqs, amps, gmf)
    _, in1_amp = _peak_at(freqs, amps, in_hz, max(feat.tolerance_hz, 0.03 * max(in_hz, 1.0)))
    _, out1_amp = _peak_at(freqs, amps, out_hz, max(feat.tolerance_hz, 0.03 * max(out_hz, 1.0))) if out_hz > 0 else (0.0, 0.0)

    out = {
        "gmf_hz": gmf,
        "gmf1_ratio": _safe_ratio(harm["gmf1"], max(feat.rms_spectrum, 1e-12)),
        "gmf2_ratio": _safe_ratio(harm["gmf2"], max(feat.rms_spectrum, 1e-12)),
        "gmf3_ratio": _safe_ratio(harm["gmf3"], max(feat.rms_spectrum, 1e-12)),
        "gmf23_over_gmf1": harm["gmf23_over_gmf1"],
        "gmf234_over_rms": harm["gmf234_over_rms"],
        "gmf123_over_rms": harm["gmf123_over_rms"],
        "sb_in_1": sb_in_1["mean_pair_ratio"],
        "sb_in_2": sb_in_2["mean_pair_ratio"],
        "sb_in_3": sb_in_3["mean_pair_ratio"],
        "sb_out_1": sb_out_1["mean_pair_ratio"],
        "sb_out_2": sb_out_2["mean_pair_ratio"],
        "sb_out_3": sb_out_3["mean_pair_ratio"],
        "sb_in_count": sb_in_1["count"] + sb_in_2["count"] + sb_in_3["count"],
        "sb_out_count": sb_out_1["count"] + sb_out_2["count"] + sb_out_3["count"],
        "sb_in_sym": float(np.mean([sb_in_1["pair_symmetry"], sb_in_2["pair_symmetry"], sb_in_3["pair_symmetry"]])),
        "sb_out_sym": float(np.mean([sb_out_1["pair_symmetry"], sb_out_2["pair_symmetry"], sb_out_3["pair_symmetry"]])),
        "dominant_spacing_owner_input": 1.0 if spacing_owner == "input" else 0.0,
        "dominant_spacing_owner_output": 1.0 if spacing_owner == "output" else 0.0,
        "mesh_resonance_ratio": gnf_ratio,
        "input_1x_ratio": _safe_ratio(in1_amp, max(feat.rms_spectrum, 1e-12)),
        "output_1x_ratio": _safe_ratio(out1_amp, max(feat.rms_spectrum, 1e-12)),
        "mesh_band_crest": wave["mesh_band_crest"],
        "mesh_band_kurtosis": wave["mesh_band_kurtosis"],
        "mesh_env_rms": wave["mesh_env_rms"],
        "mesh_env_impact_periodicity": wave["mesh_env_impact_periodicity"],
    }
    cache[key] = out
    return out



def _belt_axis_metrics(asset: AssetDefinition, belt: BeltDriveDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_belt_axis_metrics_cache", {})
    key = (belt.belt_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    driver_hz = _belt_driver_hz(belt, asset)
    driven_hz = _belt_driven_hz(belt, asset)
    belt_hz = _belt_pass_hz(belt, asset)
    freq_res = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(feat.tolerance_hz, 0.1)
    tol_driver = max(feat.tolerance_hz, 0.03 * max(driver_hz, 1.0), 1.5 * freq_res)
    tol_driven = max(feat.tolerance_hz, 0.03 * max(driven_hz, 1.0), 1.5 * freq_res) if driven_hz > 0.0 else feat.tolerance_hz
    tol_belt = max(feat.tolerance_hz, 0.05 * max(belt_hz, 1.0), 1.5 * freq_res) if belt_hz > 0.0 else feat.tolerance_hz

    _, driver1 = _peak_at(freqs, amps, driver_hz, tol_driver)
    _, driver2 = _peak_at(freqs, amps, 2.0 * driver_hz, tol_driver)
    _, driven1 = _peak_at(freqs, amps, driven_hz, tol_driven)
    _, driven2 = _peak_at(freqs, amps, 2.0 * driven_hz, tol_driven)
    _, belt1 = _peak_at(freqs, amps, belt_hz, tol_belt)
    _, belt2 = _peak_at(freqs, amps, 2.0 * belt_hz, tol_belt)
    _, belt3 = _peak_at(freqs, amps, 3.0 * belt_hz, tol_belt)

    sb_driver = _belt_sideband_ratio(freqs, amps, driver_hz, belt_hz, max(tol_driver, tol_belt), n=2) if belt_hz > 0.0 else 0.0
    sb_driven = _belt_sideband_ratio(freqs, amps, driven_hz, belt_hz, max(tol_driven, tol_belt), n=2) if belt_hz > 0.0 and driven_hz > 0.0 else 0.0
    low_broad = _belt_low_band_broadness(freqs, amps, belt_hz if belt_hz > 0.0 else driver_hz, max(driver_hz, belt_hz, 1.0))
    wave = _belt_waveform_impulsiveness(signal, belt_hz)

    axis = feat.axis.lower()
    axial = 1.0 if axis == "axial" else 0.0
    radial = 1.0 - axial
    out = {
        "driver_1x_ratio": _safe_ratio(driver1, max(feat.rms_spectrum, 1e-12)),
        "driver_2x_ratio": _safe_ratio(driver2, max(feat.rms_spectrum, 1e-12)),
        "driven_1x_ratio": _safe_ratio(driven1, max(feat.rms_spectrum, 1e-12)),
        "driven_2x_ratio": _safe_ratio(driven2, max(feat.rms_spectrum, 1e-12)),
        "belt_1x_ratio": _safe_ratio(belt1, max(feat.rms_spectrum, 1e-12)),
        "belt_2x_ratio": _safe_ratio(belt2, max(feat.rms_spectrum, 1e-12)),
        "belt_3x_ratio": _safe_ratio(belt3, max(feat.rms_spectrum, 1e-12)),
        "driver_belt_sideband_ratio": sb_driver,
        "driven_belt_sideband_ratio": sb_driven,
        "low_band_broadness": low_broad,
        "wave_crest": wave["crest"],
        "wave_kurtosis": wave["kurtosis"],
        "wave_belt_periodicity": wave["belt_periodicity"],
        "radial_weight": radial,
        "axial_weight": axial,
        "belt_hz": belt_hz,
        "driver_hz": driver_hz,
        "driven_hz": driven_hz,
    }
    cache[key] = out
    return out



def _bearing_envelope_centroid_ratio(signal: AxisSignal) -> float:
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = "__bearing_env_centroid_ratio__"
    if key in cache:
        return cache[key]
    if signal.envelope_freqs_hz is None or signal.envelope_spectrum is None:
        cache[key] = 0.0
        return 0.0
    freqs, amps = _cached_signal_envelope_arrays(signal)
    if freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        cache[key] = 0.0
        return 0.0
    weights = np.abs(amps)
    if np.sum(weights) <= 1e-12 or freqs[-1] <= 0.0:
        cache[key] = 0.0
        return 0.0
    centroid = float(np.sum(freqs * weights) / (np.sum(weights) + 1e-12))
    value = _safe_ratio(centroid, max(float(freqs[-1]), 1e-12))
    cache[key] = value
    return value


_opt_prev_bearing_characteristic_evidence = _bearing_characteristic_evidence


def _bearing_characteristic_evidence(
    asset: AssetDefinition,
    bearing: BearingDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_bearing_characteristic_cache", {})
    key = (bearing.bearing_id, sensor.sensor_id, feat.axis.lower(), float(sensor.local_rpm or asset.running_rpm))
    if key not in cache:
        cache[key] = _opt_prev_bearing_characteristic_evidence(asset, bearing, sensor, feat, signal)
    return cache[key]



def _condition_waveform_and_fs(signal: AxisSignal) -> Tuple[Optional[np.ndarray], float]:
    field_name = "acceleration_waveform" if signal.acceleration_waveform is not None else "waveform"
    arr = _cached_signal_array(signal, field_name)
    if arr is None or arr.size < 64:
        return None, 0.0
    fs = float(signal.waveform_sample_rate_hz or 0.0)
    if fs <= 0.0:
        freqs = _cached_signal_array(signal, "freqs_hz")
        if freqs is not None and freqs.size:
            fs = float(np.max(freqs) * 2.0)
    return (arr, fs) if fs > 0.0 else (None, 0.0)


_opt_prev_diagnose_asset = diagnose_asset


def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
) -> List[FaultResult]:
    asset.metadata.pop("_scope_sensor_cache", None)
    asset.metadata.pop("_temperature_delta_cache", None)
    asset.metadata.pop("_bearing_characteristic_cache", None)
    asset.metadata.pop("_gear_subfault_feature_cache", None)
    asset.metadata.pop("_hydraulic_axis_score_cache", None)
    asset.metadata.pop("_belt_axis_metrics_cache", None)
    _clear_signal_runtime_caches(asset)
    return _opt_prev_diagnose_asset(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
    )

# ---------------------------------------------------------------------------
# Performance cache patch fixups
# ---------------------------------------------------------------------------


def _gear_subfault_features(
    asset: AssetDefinition,
    stage: GearStageDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_gear_subfault_feature_cache", {})
    key = (stage.gear_stage_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    in_hz, out_hz = _stage_shaft_speeds_hz(asset, stage, sensor)
    gmf = gear_mesh_frequency_hz((stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm), stage)
    tol = max(feat.tolerance_hz, gmf * 0.03)

    harm = _mesh_harmonic_pack(freqs, amps, gmf, tol, harmonics=4)
    sb_in_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, in_hz, tol, sidebands=2)
    sb_out_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, out_hz, tol, sidebands=2)
    wave = _mesh_band_waveform_metrics(signal, gmf)

    spacing_owner = "input"
    if max(sb_out_1["mean_pair_ratio"], sb_out_2["mean_pair_ratio"], sb_out_3["mean_pair_ratio"]) > max(sb_in_1["mean_pair_ratio"], sb_in_2["mean_pair_ratio"], sb_in_3["mean_pair_ratio"]):
        spacing_owner = "output"

    gnf_ratio = _gear_mesh_resonance_band_energy(freqs, amps, gmf)
    _, in1_amp = _peak_at(freqs, amps, in_hz, max(feat.tolerance_hz, 0.03 * max(in_hz, 1.0)))
    _, out1_amp = _peak_at(freqs, amps, out_hz, max(feat.tolerance_hz, 0.03 * max(out_hz, 1.0))) if out_hz > 0 else (0.0, 0.0)

    out = {
        "gmf_hz": gmf,
        "gmf1_ratio": _safe_ratio(harm["gmf1"], max(feat.rms_spectrum, 1e-12)),
        "gmf2_ratio": _safe_ratio(harm["gmf2"], max(feat.rms_spectrum, 1e-12)),
        "gmf3_ratio": _safe_ratio(harm["gmf3"], max(feat.rms_spectrum, 1e-12)),
        "gmf23_over_gmf1": harm["gmf23_over_gmf1"],
        "gmf234_over_rms": harm["gmf234_over_rms"],
        "gmf123_over_rms": harm["gmf123_over_rms"],
        "sb_in_1": sb_in_1["mean_pair_ratio"],
        "sb_in_2": sb_in_2["mean_pair_ratio"],
        "sb_in_3": sb_in_3["mean_pair_ratio"],
        "sb_out_1": sb_out_1["mean_pair_ratio"],
        "sb_out_2": sb_out_2["mean_pair_ratio"],
        "sb_out_3": sb_out_3["mean_pair_ratio"],
        "sb_in_count": sb_in_1["count"] + sb_in_2["count"] + sb_in_3["count"],
        "sb_out_count": sb_out_1["count"] + sb_out_2["count"] + sb_out_3["count"],
        "sb_in_sym": float(np.mean([sb_in_1["pair_symmetry"], sb_in_2["pair_symmetry"], sb_in_3["pair_symmetry"]])),
        "sb_out_sym": float(np.mean([sb_out_1["pair_symmetry"], sb_out_2["pair_symmetry"], sb_out_3["pair_symmetry"]])),
        "dominant_spacing_owner_input": 1.0 if spacing_owner == "input" else 0.0,
        "dominant_spacing_owner_output": 1.0 if spacing_owner == "output" else 0.0,
        "mesh_resonance_ratio": gnf_ratio,
        "input_1x_ratio": _safe_ratio(in1_amp, max(feat.rms_spectrum, 1e-12)),
        "output_1x_ratio": _safe_ratio(out1_amp, max(feat.rms_spectrum, 1e-12)),
        "mesh_band_crest": wave["mesh_band_crest"],
        "mesh_band_kurtosis": wave["mesh_band_kurtosis"],
        "mesh_env_rms": wave["mesh_env_rms"],
        "mesh_env_impact_periodicity": wave["mesh_env_impact_periodicity"],
        "hf_rms_ratio": feat.hf_rms_ratio,
        "kurtosis": feat.kurtosis,
        "crest_factor": feat.crest_factor,
        "axis_radial": 1.0 if feat.axis in {"horizontal", "vertical", "radial"} else 0.0,
        "axis_axial": 1.0 if feat.axis == "axial" else 0.0,
        "sideband_owner_hz": in_hz if spacing_owner == "input" else out_hz,
    }
    cache[key] = out
    return out



def _belt_axis_metrics(asset: AssetDefinition, belt: BeltDriveDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_belt_axis_metrics_cache", {})
    key = (belt.belt_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    freqs, amps = _cached_signal_spectrum_arrays(signal)
    driver_hz = _belt_driver_hz(belt, asset)
    driven_hz = _belt_driven_hz(belt, asset)
    belt_hz = _belt_pass_hz(belt, asset)
    freq_res = float(np.median(np.diff(freqs))) if freqs.size > 1 else max(feat.tolerance_hz, 0.1)
    tol_driver = max(feat.tolerance_hz, 0.03 * max(driver_hz, 1.0), 1.5 * freq_res)
    tol_driven = max(feat.tolerance_hz, 0.03 * max(driven_hz, 1.0), 1.5 * freq_res) if driven_hz > 0.0 else feat.tolerance_hz
    tol_belt = max(feat.tolerance_hz, 0.05 * max(belt_hz, 1.0), 1.5 * freq_res) if belt_hz > 0.0 else feat.tolerance_hz

    _, driver1 = _peak_at(freqs, amps, driver_hz, tol_driver)
    _, driver2 = _peak_at(freqs, amps, 2.0 * driver_hz, tol_driver)
    _, driven1 = _peak_at(freqs, amps, driven_hz, tol_driven)
    _, driven2 = _peak_at(freqs, amps, 2.0 * driven_hz, tol_driven)
    _, belt1 = _peak_at(freqs, amps, belt_hz, tol_belt)
    _, belt2 = _peak_at(freqs, amps, 2.0 * belt_hz, tol_belt)
    _, belt3 = _peak_at(freqs, amps, 3.0 * belt_hz, tol_belt)

    sb_driver = _belt_sideband_ratio(freqs, amps, driver_hz, belt_hz, max(tol_driver, tol_belt), n=2) if belt_hz > 0.0 else 0.0
    sb_driven = _belt_sideband_ratio(freqs, amps, driven_hz, belt_hz, max(tol_driven, tol_belt), n=2) if belt_hz > 0.0 and driven_hz > 0.0 else 0.0
    low_broad = _belt_low_band_broadness(freqs, amps, belt_hz if belt_hz > 0.0 else driver_hz, max(driver_hz, belt_hz, 1.0))
    wave = _belt_waveform_impulsiveness(signal, belt_hz)

    axis = feat.axis.lower()
    axial = 1.0 if axis == "axial" else 0.0
    radial = 1.0 if axis in {"horizontal", "vertical", "radial"} else 0.0
    belt_lt_driver = 1.0 if (belt_hz > 0.0 and driver_hz > 0.0 and belt_hz < driver_hz) else 0.0
    dominant_near_belt = 1.0 - min(abs(feat.dominant_freq_hz - belt_hz) / max(2.0 * tol_belt, 1e-12), 1.0) if belt_hz > 0.0 else 0.0

    out = {
        "driver_hz": driver_hz,
        "driven_hz": driven_hz,
        "belt_hz": belt_hz,
        "driver1_ratio": _safe_ratio(driver1, max(feat.rms_spectrum, 1e-12)),
        "driver2_ratio": _safe_ratio(driver2, max(feat.rms_spectrum, 1e-12)),
        "driven1_ratio": _safe_ratio(driven1, max(feat.rms_spectrum, 1e-12)),
        "driven2_ratio": _safe_ratio(driven2, max(feat.rms_spectrum, 1e-12)),
        "belt1_ratio": _safe_ratio(belt1, max(feat.rms_spectrum, 1e-12)),
        "belt2_ratio": _safe_ratio(belt2, max(feat.rms_spectrum, 1e-12)),
        "belt3_ratio": _safe_ratio(belt3, max(feat.rms_spectrum, 1e-12)),
        "belt_harmonics_ratio": _safe_ratio(belt1 + belt2 + belt3, max(feat.rms_spectrum, 1e-12)),
        "driver_belt_sideband_ratio": sb_driver,
        "driven_belt_sideband_ratio": sb_driven,
        "low_band_broadness": low_broad,
        "crest_factor": wave["crest"],
        "kurtosis": wave["kurtosis"],
        "belt_periodicity": wave["belt_periodicity"],
        "axis_axial": axial,
        "axis_radial": radial,
        "belt_lt_driver": belt_lt_driver,
        "dominant_near_belt": dominant_near_belt,
        "hf_rms_ratio": feat.hf_rms_ratio,
        "subsync_ratio": _safe_ratio(feat.subsync_amp, max(feat.rms_spectrum, 1e-12)),
    }
    cache[key] = out
    return out


# ---------------------------------------------------------------------------
# Conservative rotor-rub false-positive guard patch
# ---------------------------------------------------------------------------
# Rationale
# ---------
# Fractional / sub-synchronous vibration is not unique to rotor rub. It can also
# come from belt / pulley defects, looseness, clearance, fluid-film instability,
# resonance, eccentricity, or structural amplification. The original rotor-rub
# score intentionally looked for fractional content, but in field data this can
# over-report rotor_rub. This patch keeps rotor rub available as a hypothesis,
# but makes it harder to show as a strong finding unless there is rub-like
# evidence beyond generic fractional content.

_ORIGINAL_SCORE_RUB_BEFORE_CONSERVATIVE_PATCH = _score_rub
_ORIGINAL_POSTPROCESS_RESULTS_BEFORE_CONSERVATIVE_PATCH = _postprocess_results
_ORIGINAL_FAULT_RECOMMENDATIONS_BEFORE_CONSERVATIVE_PATCH = _fault_recommendations


def _truthy_metadata(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "present", "available", "direct"}


def _asset_drive_type(asset: AssetDefinition) -> str:
    return str(asset.metadata.get("drive_type", asset.metadata.get("drive", ""))).strip().lower()


def _asset_has_belt_drive(asset: AssetDefinition) -> bool:
    return bool(getattr(asset, "belt_drives", None)) or _truthy_metadata(asset.metadata.get("belt_drive_present")) or _asset_drive_type(asset) in {"belt", "belt_drive", "belt-driven", "belt_driven"}


def _asset_is_direct_coupled(asset: AssetDefinition) -> bool:
    drive_type = _asset_drive_type(asset)
    if drive_type in {"direct", "direct_coupled", "direct-coupled", "coupled", "coupling"}:
        return True
    return _truthy_metadata(asset.metadata.get("direct_coupled")) or _truthy_metadata(asset.metadata.get("direct_drive"))


def _asset_drive_type_unknown(asset: AssetDefinition) -> bool:
    return not _asset_has_belt_drive(asset) and not _asset_is_direct_coupled(asset)


def _rub_fractional_ratio(feat: AxisFeatures) -> float:
    return feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x)


def _rub_impulse_score(feat: AxisFeatures) -> float:
    # Use the strongest available impulsiveness clue. Some deployments have FFT
    # only, so this returns 0 when waveform information is missing.
    return max(
        _score_linear(max(feat.kurtosis, 0.0), 1.5, 4.5),
        _score_linear(feat.crest_factor, 4.5, 8.0),
        _score_linear(feat.wf_impact_periodicity, 0.45, 0.75),
    )


def _rub_harmonic_support(feat: AxisFeatures) -> float:
    return _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x), 0.8, 3.0)


def _score_rub(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    """
    Conservative rotor-rub score.

    The original rub score is retained as the base score, but it now passes
    through a rub-specific gate. This prevents generic half-order/fractional
    vibration from being reported as rotor rub unless there is some combination
    of radial response, fractional content, and impulsive/contact-like waveform
    behaviour.
    """
    base_score = _ORIGINAL_SCORE_RUB_BEFORE_CONSERVATIVE_PATCH(sensor, feat)
    if base_score <= 0.0:
        return 0.0

    axis = str(feat.axis).lower()
    is_radial = axis in {"horizontal", "vertical", "radial"}
    frac = _rub_fractional_ratio(feat)
    half_x = feat.amp_ratio(feat.amp_05x)
    impulse = _rub_impulse_score(feat)
    harmonic = _rub_harmonic_support(feat)

    # No meaningful fractional/subharmonic evidence -> do not call rub.
    if frac < 1.25 and half_x < 0.75:
        return 0.0

    if is_radial:
        # Fractional content without impulsiveness/harmonic contact clues is
        # more safely treated as generic fractional vibration, not rotor rub.
        if impulse < 0.25 and harmonic < 0.40:
            return float(base_score * 0.35)
        if impulse < 0.25:
            return float(base_score * 0.60)
        return float(base_score)

    # Axial-only fractional content is weak rub evidence. Keep it as a small
    # contribution only when it is very strong and contact-like.
    if frac >= 2.20 and impulse >= 0.45:
        return float(base_score * 0.55)
    return float(base_score * 0.25)


def _conservative_rotor_rub_postprocess(asset: AssetDefinition, results: List[FaultResult]) -> None:
    rub_results = [r for r in results if r.fault_key == "rotor_rub"]
    if not rub_results:
        return

    competitor_keys = {
        "looseness_type_c_rotating_fit",
        "looseness_type_b_pedestal_support",
        "resonance_or_structural_amplification",
        "unbalance",
        "belt_sheave_misalignment",
        "belt_sheave_eccentricity",
        "belt_slip_or_tension_fault",
        "belt_wear_or_damage",
        "belt_span_resonance",
        "fluid_film_instability",
    }
    competitors = [r for r in results if r.fault_key in competitor_keys]

    for rub in rub_results:
        # Conservative drive-type handling. Belt/pulley faults can produce
        # fractional/subsynchronous content, and if drive type is unknown the
        # script should not aggressively name rotor rub.
        if _asset_has_belt_drive(asset):
            rub.score *= 0.45
            rub.limitations.append(
                "Reduced because belt/pulley faults can create fractional or sub-synchronous vibration similar to rub."
            )
        elif _asset_drive_type_unknown(asset):
            rub.score *= 0.70
            rub.limitations.append(
                "Reduced because drive type is unknown; belt/pulley and other fractional-vibration sources have not been ruled out."
            )

        frac = float(rub.supporting_metrics.get("mean_fractional_ratio", 0.0))
        impact = float(rub.supporting_metrics.get("mean_waveform_impact_periodicity", 0.0))
        radial_axes = float(rub.supporting_metrics.get("num_radial_support_axes", 0.0))

        # Rub should not be strong from generic fractional content alone.
        if frac < 1.50:
            rub.score *= 0.55
            rub.limitations.append(
                "Reduced because fractional/subharmonic content is not strong enough for a rub-specific call."
            )
        if impact < 0.30:
            rub.score *= 0.70
            rub.limitations.append(
                "Reduced because waveform impact/contact periodicity is weak for rotor rub."
            )
        if radial_axes < 1.0:
            rub.score *= 0.70
            rub.limitations.append(
                "Reduced because radial-axis support is weak for a rotor-rub call."
            )

        # Competing root-cause suppression. If looseness, belt, resonance or
        # unbalance explains nearly the same evidence, rub becomes an alternative
        # explanation rather than a main detected fault.
        nearest = None
        if competitors:
            near_competitors = [c for c in competitors if c.score >= rub.score - 8.0]
            if near_competitors:
                nearest = max(near_competitors, key=lambda c: c.score)
        if nearest is not None:
            rub.score *= 0.75
            rub.limitations.append(
                f"Reduced because {nearest.fault_key} explains similar fractional/harmonic evidence."
            )

        # Keep low/medium rub calls as advisory-level. True rub can still become
        # primary when it remains high after the gates and suppressors.
        _refresh_result_confidence(rub)
        if rub.score < 65.0:
            rub.confidence = _cap_confidence(rub.confidence, "low")


def _postprocess_results(asset: AssetDefinition, results: List[FaultResult]) -> None:
    _ORIGINAL_POSTPROCESS_RESULTS_BEFORE_CONSERVATIVE_PATCH(asset, results)
    _conservative_rotor_rub_postprocess(asset, results)


def _fault_recommendations(result: FaultResult) -> List[str]:
    if result.fault_key == "rotor_rub":
        severity_action = {
            "urgent": "Inspect at the earliest safe opportunity and be ready to correct during the next available stop.",
            "plan": "Plan confirmatory checks and corrective work in the next maintenance window.",
            "monitor": "Trend the condition and confirm with a complementary test before major intervention.",
        }[_fault_urgency(result.score, result.confidence)]
        return [
            severity_action,
            "Treat this as a possible intermittent contact / rub-like pattern only after ruling out belt/pulley faults, rotating-fit looseness, fluid-film instability and structural resonance.",
            "Inspect seals, guards, fans, wear rings, internal clearances, thermal growth margins and contact marks only if the fractional/contact-like pattern repeats or increases.",
        ]
    return _ORIGINAL_FAULT_RECOMMENDATIONS_BEFORE_CONSERVATIVE_PATCH(result)


# Make the severity model slightly less aggressive for advisory-level rub calls.
# High-confidence / high-score rub can still be urgent through diagnostic score
# and condition severity; this only reduces the generic prior risk bonus.
try:
    FAULT_RISK_BONUS["rotor_rub"] = min(float(FAULT_RISK_BONUS.get("rotor_rub", 0.0)), 0.03)
except Exception:
    pass



# ---------------------------------------------------------------------------
# Pattern-first diagnostic reasoning layer
# ---------------------------------------------------------------------------
# This layer implements a hybrid diagnostic-agent workflow:
#   1) deterministic signal processing and fault scoring remain in diagnose_asset
#   2) a pattern-first reasoning layer compares competing hypotheses
#   3) public output shows one primary interpretation, alternatives, evidence,
#      missing metadata, and recommended next checks
#
# The functions below do not replace the physics/rule engine. They wrap it with
# a safer interpretation layer so generic patterns such as fractional vibration
# are not over-presented as overly specific faults such as rotor rub.

FAULT_PUBLIC_LABELS: Dict[str, str] = {
    "unbalance": "Unbalance / eccentricity-like 1X response",
    "misalignment": "Possible coupling / shaft misalignment",
    "looseness_type_a_base_structure": "Possible structural looseness at base/foundation",
    "looseness_type_b_pedestal_support": "Possible pedestal / support looseness",
    "looseness_type_c_rotating_fit": "Possible rotating-fit / internal clearance looseness",
    "soft_foot_or_frame_distortion": "Possible soft foot or frame distortion",
    "bent_shaft_or_bow": "Possible bent shaft / rotor bow",
    "resonance_or_structural_amplification": "Possible resonance / structural amplification",
    "rotor_rub": "Possible intermittent contact / rub-like fractional vibration",
    "motor_electrical_forcing": "Possible motor electrical forcing",
    "lubrication_distress": "Possible bearing lubrication distress",
    "bearing_bpfo": "Possible bearing outer-race defect",
    "bearing_bpfi": "Possible bearing inner-race defect",
    "bearing_bsf": "Possible rolling-element defect",
    "bearing_ftf": "Possible cage / train defect",
    "bearing_wear_progression": "Possible bearing wear progression",
    "fluid_film_instability": "Possible fluid-film instability",
    "thrust_bearing_or_axial_overload": "Possible thrust bearing / axial overload",
    "gear_mesh_fault": "Possible gear mesh fault",
    "gear_misalignment": "Possible gear misalignment",
    "gear_eccentricity_or_runout": "Possible gear eccentricity / runout",
    "gear_backlash_or_looseness": "Possible gear backlash / looseness",
    "gear_tooth_wear": "Possible gear tooth wear",
    "gear_localized_tooth_damage": "Possible localized gear tooth damage",
    "belt_sheave_misalignment": "Possible belt/sheave misalignment",
    "belt_sheave_eccentricity": "Possible sheave eccentricity / runout",
    "belt_slip_or_tension_fault": "Possible belt slip / tension issue",
    "belt_wear_or_damage": "Possible belt wear / damage",
    "belt_span_resonance": "Possible belt span resonance",
    "hydraulic_vane_or_blade_pass": "Possible vane/blade-pass forcing",
    "cavitation_or_aeration": "Possible cavitation / aeration",
}

PATTERN_PUBLIC_LABELS: Dict[str, str] = {
    "synchronous": "1X synchronous vibration pattern",
    "harmonic": "harmonic vibration pattern",
    "subsynchronous": "sub-synchronous / fractional vibration pattern",
    "modulation": "modulation / sideband vibration pattern",
    "broadband": "broadband / impact-like vibration pattern",
    "unknown": "uncertain vibration pattern",
}


def _fault_label(fault_key: str) -> str:
    return FAULT_PUBLIC_LABELS.get(fault_key, fault_key.replace("_", " "))


def _pattern_label(pattern_family: str) -> str:
    return PATTERN_PUBLIC_LABELS.get(pattern_family, pattern_family.replace("_", " "))


def _result_sort_key(result: FaultResult) -> Tuple[float, float, str]:
    severity = float(result.fault_severity_score) if result.fault_severity_score is not None else float(result.score)
    return (-severity, -float(result.score), str(result.fault_key))


def _confidence_float(confidence: str) -> float:
    return {"high": 0.90, "medium": 0.65, "low": 0.38, "none": 0.10}.get(str(confidence).lower(), 0.25)


def _severity_rank(label: Optional[str]) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(str(label or "").lower(), 0)


def _serialize_reasoning_fault(result: FaultResult, include_debug: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "fault_key": result.fault_key,
        "label": _fault_label(result.fault_key),
        "score": float(round(result.score, 2)),
        "confidence": result.confidence,
        "severity_label": result.fault_severity_label,
        "severity_score": None if result.fault_severity_score is None else float(round(result.fault_severity_score, 1)),
        "urgency": result.urgency,
        "segment": result.diagnostic_segment,
        "scope": result.scope,
        "target": result.target,
    }
    if include_debug:
        out.update({
            "evidence": list(result.evidence[:8]),
            "limitations": list(result.limitations[:8]),
            "recommendations": list(result.recommendations[:5]),
            "supporting_metrics": {
                str(k): float(round(v, 4))
                for k, v in (result.supporting_metrics or {}).items()
                if isinstance(v, (int, float))
            },
            "fault_explanation": dict(result.fault_explanation or {}),
        })
    return out


def _axis_feature_snapshot(asset: AssetDefinition, max_axes: int = 12) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sensor in asset.sensors:
        feats_by_axis = _axis_features_for_sensor_cached(asset, sensor)
        for axis_name, feat in feats_by_axis.items():
            rows.append({
                "sensor_id": sensor.sensor_id,
                "component_id": sensor.component_id,
                "component_type": sensor.component_type,
                "location_tag": sensor.location_tag,
                "installed_on": sensor.installed_on,
                "axis": axis_name,
                "shaft_hz": float(round(feat.shaft_hz, 4)),
                "dominant_freq_hz": float(round(feat.dominant_freq_hz, 4)),
                "dominant_order": float(round(feat.dominant_order, 4)),
                "rms_spectrum": float(round(feat.rms_spectrum, 6)),
                "one_x_ratio": float(round(feat.amp_ratio(feat.amp_1x), 4)),
                "two_x_ratio": float(round(feat.amp_ratio(feat.amp_2x), 4)),
                "three_x_ratio": float(round(feat.amp_ratio(feat.amp_3x), 4)),
                "half_x_ratio": float(round(feat.amp_ratio(feat.amp_05x), 4)),
                "fractional_ratio": float(round(feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x + feat.amp_35x), 4)),
                "hf_rms_ratio": float(round(feat.hf_rms_ratio, 4)),
                "crest_factor": float(round(feat.crest_factor, 4)),
                "kurtosis": float(round(feat.kurtosis, 4)),
                "impact_periodicity": float(round(feat.wf_impact_periodicity, 4)),
            })
    rows.sort(key=lambda r: (-abs(float(r.get("rms_spectrum", 0.0))), str(r.get("sensor_id", "")), str(r.get("axis", ""))))
    return rows[:max_axes]


def _axis_aggregate_metrics(axis_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    keys = ["one_x_ratio", "two_x_ratio", "three_x_ratio", "half_x_ratio", "fractional_ratio", "hf_rms_ratio", "crest_factor", "kurtosis", "impact_periodicity"]
    out: Dict[str, float] = {}
    for key in keys:
        vals = [float(r.get(key, 0.0) or 0.0) for r in axis_rows]
        if vals:
            out[f"mean_{key}"] = float(round(mean(vals), 4))
            out[f"max_{key}"] = float(round(max(vals), 4))
    radial = [r for r in axis_rows if str(r.get("axis", "")).lower() in {"horizontal", "vertical", "radial"}]
    axial = [r for r in axis_rows if str(r.get("axis", "")).lower() == "axial"]
    if radial:
        out["mean_radial_one_x_ratio"] = float(round(mean(float(r.get("one_x_ratio", 0.0) or 0.0) for r in radial), 4))
        out["mean_radial_fractional_ratio"] = float(round(mean(float(r.get("fractional_ratio", 0.0) or 0.0) for r in radial), 4))
    if axial:
        out["mean_axial_one_x_ratio"] = float(round(mean(float(r.get("one_x_ratio", 0.0) or 0.0) for r in axial), 4))
        out["mean_axial_two_x_ratio"] = float(round(mean(float(r.get("two_x_ratio", 0.0) or 0.0) for r in axial), 4))
    return out


def _asset_context_summary(asset: AssetDefinition) -> Dict[str, Any]:
    drive_type = _asset_drive_type(asset) or ("belt" if _asset_has_belt_drive(asset) else "direct_coupled" if _asset_is_direct_coupled(asset) else "unknown")
    return {
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type,
        "running_rpm": float(asset.running_rpm),
        "shaft_hz": float(round(shaft_hz_from_rpm(asset.running_rpm), 4)),
        "drive_type": drive_type,
        "sensor_count": len(asset.sensors),
        "bearing_count": len(asset.bearings),
        "gear_stage_count": len(asset.gear_stages),
        "belt_drive_count": len(getattr(asset, "belt_drives", []) or []),
        "hydraulic_element_count": len(asset.hydraulic_elements),
        "motor_count": len(asset.motors),
    }


def _missing_diagnostic_metadata(asset: AssetDefinition, results: Optional[List[FaultResult]] = None) -> List[str]:
    missing: List[str] = []
    component_types = {str(s.component_type).lower() for s in asset.sensors}
    drive_type = _asset_drive_type(asset)
    if not drive_type and not _asset_has_belt_drive(asset) and not _asset_is_direct_coupled(asset):
        missing.append("drive_type/direct_coupled/belt_drive_present")
    if not asset.metadata.get("trend_history_available") and not asset.metadata.get("trend_features"):
        missing.append("trend_history_or_persistence_features")
    if not asset.metadata.get("load_condition") and not asset.metadata.get("operating_state"):
        missing.append("load_condition_or_operating_state")
    if "gearbox" in component_types and not asset.gear_stages:
        missing.append("gear_stage_teeth_and_stage_speed")
    if any(ct in component_types for ct in {"motor", "pump", "fan", "blower", "compressor", "gearbox"}) and not asset.bearings:
        missing.append("bearing_id_or_bearing_fault_frequencies")
    if _asset_has_belt_drive(asset) and not getattr(asset, "belt_drives", None):
        missing.append("belt_geometry_or_belt_pass_frequency")
    if any(ct == "motor" for ct in component_types) and not asset.motors:
        missing.append("motor_line_frequency_and_pole_metadata")
    if results and any(r.fault_key == "rotor_rub" for r in results):
        if not asset.metadata.get("rub_confirmation_available"):
            missing.append("rub_confirmation_inspection_phase_or_speed_sweep")
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _rpm_quality_assessment(asset: AssetDefinition, axis_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if asset.running_rpm <= 0.0:
        return {"confidence": "none", "notes": ["Running RPM is missing or non-positive; order-based diagnosis is unreliable."]}
    if not axis_rows:
        return {"confidence": "low", "notes": ["No valid spectral axes were available for RPM/order validation."]}
    order_hits = 0
    strong_axes = 0
    notes: List[str] = []
    for row in axis_rows:
        order = float(row.get("dominant_order", 0.0) or 0.0)
        one_x = float(row.get("one_x_ratio", 0.0) or 0.0)
        two_x = float(row.get("two_x_ratio", 0.0) or 0.0)
        three_x = float(row.get("three_x_ratio", 0.0) or 0.0)
        frac = float(row.get("fractional_ratio", 0.0) or 0.0)
        if max(one_x, two_x, three_x, frac) >= 1.0:
            strong_axes += 1
        if min(abs(order - c) for c in [0.5, 1.0, 1.5, 2.0, 3.0]) <= 0.12 or max(one_x, two_x, three_x) >= 1.25:
            order_hits += 1
    if order_hits >= max(1, int(0.50 * max(strong_axes, 1))):
        confidence = "high"
    elif order_hits > 0:
        confidence = "medium"
    else:
        confidence = "low"
        notes.append("Dominant spectral peaks do not align well with expected order targets; verify RPM and sampling rate.")
    if strong_axes == 0:
        confidence = "low"
        notes.append("Order energy is weak across axes; RPM confidence is limited.")
    return {"confidence": confidence, "order_aligned_axes": order_hits, "strong_axes_checked": strong_axes, "notes": notes}


def _pattern_evidence(profile: PatternFamilyProfile, axis_metrics: Mapping[str, float]) -> List[str]:
    evidence: List[str] = []
    family = profile.dominant_family
    direction = profile.dominant_direction
    evidence.append(f"Pattern classifier: {_pattern_label(family)} with {direction} directional bias.")
    mean_1x = float(axis_metrics.get("mean_one_x_ratio", profile.metrics.get("mean_1x_ratio", 0.0)))
    mean_harm = float(profile.metrics.get("mean_harmonic_ratio", axis_metrics.get("mean_two_x_ratio", 0.0) + axis_metrics.get("mean_three_x_ratio", 0.0)))
    mean_frac = float(profile.metrics.get("mean_fractional_ratio", axis_metrics.get("mean_fractional_ratio", 0.0)))
    mean_hf = float(profile.metrics.get("mean_hf_rms_ratio", axis_metrics.get("mean_hf_rms_ratio", 0.0)))
    if mean_1x >= 1.5:
        evidence.append(f"1X/synchronous content is elevated (mean 1X ratio {mean_1x:.2f}x RMS).")
    if mean_harm >= 1.5:
        evidence.append(f"Harmonic content is elevated (mean harmonic ratio {mean_harm:.2f}x RMS).")
    if mean_frac >= 1.0:
        evidence.append(f"Fractional/sub-synchronous content is present (mean fractional ratio {mean_frac:.2f}x RMS).")
    if mean_hf >= 0.35:
        evidence.append(f"Broadband/high-frequency contribution is meaningful (mean HF RMS ratio {mean_hf:.2f}).")
    return evidence[:6]


def _fault_evidence_for(result: FaultResult) -> List[str]:
    evidence: List[str] = []
    if result.evidence:
        evidence.extend(str(x) for x in result.evidence[:3])
    metrics = result.supporting_metrics or {}
    metric_phrases = []
    for key in ["mean_1x_ratio", "mean_2x_ratio", "mean_3x_ratio", "mean_fractional_ratio", "mean_harmonic_string_ratio", "mean_hf_rms_ratio", "num_supporting_axes"]:
        if key in metrics:
            try:
                metric_phrases.append(f"{key}={float(metrics[key]):.2f}")
            except (TypeError, ValueError):
                pass
    if metric_phrases:
        evidence.append("Supporting metrics: " + ", ".join(metric_phrases[:5]) + ".")
    return evidence[:5]


def _fault_evidence_against(result: FaultResult, asset: AssetDefinition, pattern_profile: PatternFamilyProfile, all_results: List[FaultResult]) -> List[str]:
    against: List[str] = []
    fault_key = result.fault_key
    competitors = [r for r in all_results if r is not result and r.score >= result.score - 10.0]
    if result.limitations:
        against.extend(str(x) for x in result.limitations[:3])
    if fault_key == "rotor_rub":
        against.append("Fractional/sub-synchronous vibration is not unique to rub; belt/pulley, looseness, fluid-film instability and resonance can produce similar evidence.")
        if _asset_has_belt_drive(asset):
            against.append("Belt-drive metadata is present, so belt/pulley causes should be tested before naming rub.")
        elif _asset_drive_type_unknown(asset):
            against.append("Drive type is unknown, so belt/pulley causes have not been ruled out.")
        if pattern_profile.dominant_family not in {"subsynchronous", "broadband", "harmonic"}:
            against.append("The overall pattern is not dominantly rub-like.")
    if fault_key == "unbalance":
        mean_frac = float(result.supporting_metrics.get("mean_fractional_ratio", 0.0)) if result.supporting_metrics else 0.0
        mean_harm = float(result.supporting_metrics.get("mean_harmonic_string_ratio", 0.0)) if result.supporting_metrics else 0.0
        if mean_frac >= 1.0 or mean_harm >= 3.0:
            against.append("Substantial fractional/harmonic content makes pure unbalance less likely.")
    if fault_key == "misalignment":
        if pattern_profile.axial_bias < 0.40:
            against.append("Axial directional bias is not strong, limiting misalignment confidence.")
    if fault_key.startswith("bearing") or fault_key == "lubrication_distress":
        if not asset.bearings:
            against.append("Bearing geometry/fault-frequency metadata is missing, limiting bearing-specific confidence.")
    if fault_key.startswith("gear"):
        if not asset.gear_stages:
            against.append("Gear tooth/stage metadata is missing, limiting gear-specific confidence.")
    if competitors:
        best_comp = max(competitors, key=lambda r: r.score)
        against.append(f"Competing hypothesis {best_comp.fault_key} has a nearby score ({best_comp.score:.1f}) and may explain overlapping evidence.")
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for item in against:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:6]


def _choose_primary_hypothesis(results: List[FaultResult], pattern_profile: PatternFamilyProfile, asset: AssetDefinition) -> Optional[FaultResult]:
    if not results:
        return None
    ranked = sorted(results, key=lambda r: (r.diagnostic_segment != "primary", -r.score, _result_sort_key(r)))
    primary_candidates = [r for r in ranked if r.diagnostic_segment == "primary"] or ranked
    chosen = primary_candidates[0]
    # Do not let advisory-level rotor rub dominate over a nearby broader fault.
    if chosen.fault_key == "rotor_rub" and chosen.score < 70.0:
        broader = [
            r for r in results
            if r.fault_key in {
                "looseness_type_c_rotating_fit",
                "looseness_type_b_pedestal_support",
                "resonance_or_structural_amplification",
                "unbalance",
                "belt_sheave_eccentricity",
                "belt_slip_or_tension_fault",
                "fluid_film_instability",
            }
            and r.score >= chosen.score - 12.0
        ]
        if broader:
            return max(broader, key=lambda r: r.score)
    return chosen


def _root_cause_certainty(primary: Optional[FaultResult], missing_metadata: List[str], rpm_quality: Mapping[str, Any]) -> str:
    if primary is None:
        return "no_fault_candidate"
    conf = _confidence_float(primary.confidence)
    severity = _severity_rank(primary.fault_severity_label)
    missing_penalty = 0.10 * min(len(missing_metadata), 4)
    rpm_penalty = {"high": 0.0, "medium": 0.08, "low": 0.20, "none": 0.35}.get(str(rpm_quality.get("confidence", "low")), 0.15)
    certainty = _clamp(0.55 * conf + 0.35 * _score_linear(primary.score, 35.0, 80.0) + 0.10 * _score_linear(severity, 1.0, 4.0) - missing_penalty - rpm_penalty, 0.0, 1.0)
    if certainty >= 0.70:
        return "likely"
    if certainty >= 0.45:
        return "candidate"
    return "uncertain"


def _operator_headline(primary: Optional[FaultResult], pattern_profile: PatternFamilyProfile, certainty: str) -> str:
    pattern = _pattern_label(pattern_profile.dominant_family)
    if primary is None:
        return f"{pattern.capitalize()} detected, but no fault hypothesis crossed reporting threshold."
    if certainty == "likely":
        return f"Likely {_fault_label(primary.fault_key).lower()} with {pattern}."
    if certainty == "candidate":
        return f"Possible {_fault_label(primary.fault_key).lower()} with {pattern}."
    return f"{pattern.capitalize()} detected; root cause remains uncertain."


def _status_from_results(results: List[FaultResult]) -> str:
    if not results:
        return "normal_or_insufficient_evidence"
    max_sev = max((_severity_rank(r.fault_severity_label) for r in results), default=0)
    max_score = max((float(r.score) for r in results), default=0.0)
    if max_sev >= 4 or max_score >= 90.0:
        return "immediate_review"
    if max_sev >= 3 or max_score >= 75.0:
        return "urgent"
    if max_sev >= 2 or max_score >= 60.0:
        return "plan"
    return "monitor"


def _recommended_next_checks(primary: Optional[FaultResult], alternatives: List[FaultResult], missing_metadata: List[str], asset: AssetDefinition) -> List[str]:
    checks: List[str] = []
    if primary is not None:
        checks.extend(primary.recommendations[:3])
    # Add generic checks by pattern / missing metadata.
    if "drive_type/direct_coupled/belt_drive_present" in missing_metadata:
        checks.append("Confirm drive type: direct-coupled, belt-driven, gearbox-driven, or other.")
    if "trend_history_or_persistence_features" in missing_metadata:
        checks.append("Trend the same features under comparable speed/load before escalating a low-severity diagnosis.")
    if "bearing_id_or_bearing_fault_frequencies" in missing_metadata:
        checks.append("Add bearing number or BPFO/BPFI/BSF/FTF frequencies to enable bearing-specific confirmation.")
    if "gear_stage_teeth_and_stage_speed" in missing_metadata:
        checks.append("Add gear tooth counts and stage speed to evaluate gear mesh and sidebands reliably.")
    if any(r.fault_key == "rotor_rub" for r in ([primary] if primary else []) + alternatives):
        checks.append("Treat rub/contact as an inspection hypothesis only after ruling out looseness, belt/pulley effects, resonance and fluid-film instability.")
    # Deduplicate.
    seen = set()
    out = []
    for item in checks:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out[:6]


def build_diagnostic_reasoning_report(
    asset: AssetDefinition,
    results: List[FaultResult],
    include_debug: bool = False,
) -> Dict[str, Any]:
    """
    Convert raw rule-engine fault scores into a pattern-first diagnostic report.

    This is the recommended default output for product/API use. It preserves the
    deterministic script scores, but presents them as a structured investigation:
    pattern -> primary hypothesis -> alternatives -> evidence for/against ->
    missing data -> next checks.
    """
    # Ensure feature cache and pattern profile exist after diagnose_asset.
    pattern_profile = classify_asset_pattern(asset)
    axis_rows = _axis_feature_snapshot(asset)
    axis_metrics = _axis_aggregate_metrics(axis_rows)
    rpm_quality = _rpm_quality_assessment(asset, axis_rows)
    sorted_results = sorted(results, key=_result_sort_key)
    primary = _choose_primary_hypothesis(sorted_results, pattern_profile, asset)
    alternatives = [r for r in sorted_results if primary is None or r is not primary]
    missing_metadata = _missing_diagnostic_metadata(asset, sorted_results)
    certainty = _root_cause_certainty(primary, missing_metadata, rpm_quality)
    status = _status_from_results(sorted_results)

    primary_payload = None
    if primary is not None:
        primary_payload = _serialize_reasoning_fault(primary, include_debug=include_debug)
        primary_payload["evidence_for"] = _fault_evidence_for(primary)
        primary_payload["evidence_against"] = _fault_evidence_against(primary, asset, pattern_profile, sorted_results)
        primary_payload["root_cause_certainty"] = certainty

    alternative_payloads = []
    for alt in alternatives[:4]:
        payload = _serialize_reasoning_fault(alt, include_debug=False)
        payload["why_not_primary"] = _fault_evidence_against(alt, asset, pattern_profile, sorted_results)[:3]
        alternative_payloads.append(payload)

    pattern_payload = {
        "family": pattern_profile.dominant_family,
        "label": _pattern_label(pattern_profile.dominant_family),
        "direction": pattern_profile.dominant_direction,
        "scores": {
            "synchronous": float(round(pattern_profile.synchronous_score, 1)),
            "harmonic": float(round(pattern_profile.harmonic_score, 1)),
            "subsynchronous": float(round(pattern_profile.subsynchronous_score, 1)),
            "modulation": float(round(pattern_profile.modulation_score, 1)),
            "broadband": float(round(pattern_profile.broadband_score, 1)),
        },
        "directional_bias": {
            "radial": float(round(pattern_profile.radial_bias, 3)),
            "axial": float(round(pattern_profile.axial_bias, 3)),
            "mixed": float(round(pattern_profile.mixed_bias, 3)),
        },
        "evidence": _pattern_evidence(pattern_profile, axis_metrics),
        "metrics": {k: float(round(v, 4)) for k, v in pattern_profile.metrics.items()},
    }

    operator_summary = {
        "status": status,
        "headline": _operator_headline(primary, pattern_profile, certainty),
        "primary_hypothesis": None if primary is None else _fault_label(primary.fault_key),
        "root_cause_certainty": certainty,
        "confidence_note": (
            "Pattern confidence and fault/root-cause confidence are separated; root cause is limited when metadata, trend history, or confirmation tests are missing."
        ),
        "recommended_next_checks": _recommended_next_checks(primary, alternatives[:4], missing_metadata, asset),
    }

    llm_ready_payload = {
        "asset_context": _asset_context_summary(asset),
        "pattern_summary": pattern_payload,
        "axis_feature_summary": axis_rows[:8],
        "script_fault_scores": [_serialize_reasoning_fault(r, include_debug=False) for r in sorted_results[:8]],
        "missing_inputs": list(missing_metadata),
        "rpm_quality": rpm_quality,
        "instruction": (
            "Use only this structured evidence. Do not invent faults. Compare hypotheses, list evidence for/against, "
            "and keep rotor rub as a secondary hypothesis unless rub-specific evidence is strong and belt/pulley/looseness/resonance are ruled out."
        ),
    }

    report: Dict[str, Any] = {
        "asset_id": asset.asset_id,
        "status": status,
        "operator_summary": operator_summary,
        "pattern": pattern_payload,
        "primary_hypothesis": primary_payload,
        "alternative_hypotheses": alternative_payloads,
        "missing_metadata": list(missing_metadata),
        "data_quality": {
            "rpm_quality": rpm_quality,
            "axis_count_used": len(axis_rows),
        },
        "llm_ready_payload": llm_ready_payload,
    }
    if include_debug:
        report["debug"] = {
            "raw_fault_scores": [_serialize_reasoning_fault(r, include_debug=True) for r in sorted_results],
            "axis_metrics": axis_metrics,
            "pattern_profile_raw": pattern_profile.as_dict(),
        }
    return report


def diagnose_asset_with_reasoning(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
    include_debug: bool = False,
) -> Dict[str, Any]:
    """
    Recommended high-level API.

    Returns a pattern-first diagnostic report instead of a long raw list of
    faults. Raw script scores remain available in report["debug"] when
    include_debug=True.
    """
    results = diagnose_asset(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
    )
    return build_diagnostic_reasoning_report(asset, results, include_debug=include_debug)


def build_maintenance_feedback_record(
    report: Mapping[str, Any],
    confirmed_fault: Optional[str] = None,
    technician_notes: str = "",
    action_taken: str = "",
    post_repair_result: str = "",
    false_positive_faults: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Store this record after maintenance to support future threshold tuning or
    supervised/reward-model training. This function is intentionally simple and
    JSON-serializable.
    """
    primary = report.get("primary_hypothesis") or {}
    return {
        "asset_id": report.get("asset_id"),
        "predicted_primary_fault": primary.get("fault_key"),
        "predicted_primary_label": primary.get("label"),
        "predicted_status": report.get("status"),
        "predicted_pattern": (report.get("pattern") or {}).get("family"),
        "alternative_faults": [x.get("fault_key") for x in report.get("alternative_hypotheses", []) if isinstance(x, Mapping)],
        "confirmed_fault": confirmed_fault,
        "false_positive_faults": false_positive_faults or [],
        "technician_notes": technician_notes,
        "action_taken": action_taken,
        "post_repair_result": post_repair_result,
        "missing_metadata_at_prediction": list(report.get("missing_metadata", [])),
    }


# ---------------------------------------------------------------------------
# Pattern-first / metadata-aware output layer v2
# ---------------------------------------------------------------------------
# This block intentionally overrides build_diagnostic_reasoning_report() while
# keeping the existing signal-processing and rule-scoring engine unchanged.
# Implemented improvements:
#   1) pattern-first diagnosis
#   3) stronger metadata-aware confidence and suppression
#   4) separate pattern confidence from fault/root-cause confidence
#  11) simplified operator / engineer / debug output views

DIAGNOSTIC_REASONING_LAYER_VERSION = "pattern_first_metadata_views_v2"

PATTERN_FAULT_AFFINITY: Dict[str, Dict[str, float]] = {
    "synchronous": {
        "unbalance": 1.00,
        "belt_sheave_eccentricity": 0.85,
        "resonance_or_structural_amplification": 0.75,
        "bent_shaft_or_bow": 0.65,
        "motor_electrical_forcing": 0.60,
        "misalignment": 0.55,
    },
    "harmonic": {
        "looseness_type_c_rotating_fit": 1.00,
        "looseness_type_b_pedestal_support": 0.90,
        "gear_backlash_or_looseness": 0.85,
        "misalignment": 0.70,
        "rotor_rub": 0.55,
        "soft_foot_or_frame_distortion": 0.55,
    },
    "subsynchronous": {
        "fluid_film_instability": 1.00,
        "belt_slip_or_tension_fault": 0.90,
        "belt_span_resonance": 0.85,
        "looseness_type_c_rotating_fit": 0.82,
        "rotor_rub": 0.62,
        "resonance_or_structural_amplification": 0.60,
        "unbalance": 0.35,
    },
    "modulation": {
        "gear_mesh_fault": 1.00,
        "gear_eccentricity_or_runout": 0.95,
        "gear_tooth_wear": 0.88,
        "belt_wear_or_damage": 0.82,
        "belt_slip_or_tension_fault": 0.80,
        "bearing_wear_progression": 0.72,
        "motor_electrical_forcing": 0.65,
        "looseness_type_c_rotating_fit": 0.62,
        "rotor_rub": 0.40,
    },
    "broadband": {
        "lubrication_distress": 1.00,
        "bearing_wear_progression": 0.90,
        "bearing_bpfo": 0.85,
        "bearing_bpfi": 0.85,
        "bearing_bsf": 0.80,
        "cavitation_or_aeration": 0.80,
        "looseness_type_c_rotating_fit": 0.65,
        "rotor_rub": 0.55,
    },
}


def _reasoning_label_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    if score >= 0.25:
        return "low"
    return "very_low"


def _pattern_confidence_assessment(
    profile: PatternFamilyProfile,
    axis_metrics: Mapping[str, float],
    rpm_quality: Mapping[str, Any],
    axis_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    scores = {
        "synchronous": float(profile.synchronous_score),
        "harmonic": float(profile.harmonic_score),
        "subsynchronous": float(profile.subsynchronous_score),
        "modulation": float(profile.modulation_score),
        "broadband": float(profile.broadband_score),
    }
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    strength = _score_linear(top_score, 25.0, 75.0)
    separation = _score_linear(top_score - second_score, 5.0, 30.0)
    rpm_factor = {"high": 1.0, "medium": 0.75, "low": 0.45, "none": 0.15}.get(str(rpm_quality.get("confidence", "low")), 0.45)
    axis_support = _score_linear(len(axis_rows), 1.0, 3.0)
    direction_support = max(float(profile.radial_bias), float(profile.axial_bias), 0.0)
    value = _clamp(
        0.45 * strength +
        0.20 * separation +
        0.15 * rpm_factor +
        0.10 * axis_support +
        0.10 * _score_linear(direction_support, 0.50, 0.85),
        0.0,
        1.0,
    )
    basis = [
        f"dominant pattern score={top_score:.1f}",
        f"second pattern score={second_score:.1f}",
        f"RPM/order confidence={rpm_quality.get('confidence', 'unknown')}",
        f"axes used={len(axis_rows)}",
    ]
    if abs(top_score - second_score) < 8.0:
        basis.append("pattern families are close; pattern confidence is limited")
    return {
        "family": top_name,
        "label": _pattern_label(top_name),
        "score": float(round(value, 3)),
        "level": _reasoning_label_from_score(value),
        "basis": basis,
    }


def _fault_pattern_fit_score(fault_key: str, pattern_family: str) -> float:
    affinity = PATTERN_FAULT_AFFINITY.get(pattern_family, {})
    if fault_key in affinity:
        return float(affinity[fault_key])
    if fault_key.startswith("bearing"):
        return 0.75 if pattern_family == "broadband" else 0.45
    if fault_key.startswith("gear"):
        return 0.85 if pattern_family == "modulation" else 0.45
    if fault_key.startswith("belt"):
        return 0.85 if pattern_family in {"subsynchronous", "modulation"} else 0.45
    if fault_key in {"hydraulic_vane_or_blade_pass", "cavitation_or_aeration"}:
        return 0.80 if pattern_family in {"modulation", "broadband"} else 0.45
    return 0.50


def _has_fluid_film_bearing_metadata(asset: AssetDefinition) -> bool:
    if any(getattr(b, "bearing_type", "").lower() == "fluid_film" for b in asset.bearings):
        return True
    return bool(asset.metadata.get("fluid_film_bearing") or asset.metadata.get("sleeve_bearing"))


def _metadata_support_for_fault(asset: AssetDefinition, fault_key: str, missing: List[str]) -> Tuple[float, List[str]]:
    drive_type = _asset_drive_type(asset)
    drive_unknown = _asset_drive_type_unknown(asset)
    has_belt = _asset_has_belt_drive(asset)
    direct_coupled = _asset_is_direct_coupled(asset)
    notes: List[str] = []
    support = 0.82

    # Fault-family specific metadata requirements.
    if fault_key.startswith("bearing") or fault_key in {"lubrication_distress", "bearing_wear_progression", "thrust_bearing_or_axial_overload"}:
        if not asset.bearings:
            support = min(support, 0.50)
            notes.append("bearing metadata/fault frequencies are missing")
    if fault_key == "fluid_film_instability":
        if not _has_fluid_film_bearing_metadata(asset):
            support = min(support, 0.42)
            notes.append("fluid-film/sleeve bearing metadata is missing")
    if fault_key.startswith("gear"):
        if not asset.gear_stages:
            support = min(support, 0.45)
            notes.append("gear tooth/stage-speed metadata is missing")
    if fault_key.startswith("belt"):
        if not has_belt and str(drive_type).lower() != "belt":
            support = min(support, 0.48 if drive_unknown else 0.35)
            notes.append("belt drive has not been confirmed")
        elif has_belt and not getattr(asset, "belt_drives", None):
            support = min(support, 0.60)
            notes.append("belt geometry/pass-frequency metadata is incomplete")
    if fault_key == "motor_electrical_forcing":
        if not asset.motors:
            support = min(support, 0.55)
            notes.append("motor line-frequency/pole metadata is missing")
    if fault_key in {"hydraulic_vane_or_blade_pass", "cavitation_or_aeration"}:
        if not asset.hydraulic_elements:
            support = min(support, 0.52)
            notes.append("hydraulic vane/blade metadata is missing")

    # Rotor rub is intentionally conservative.
    if fault_key == "rotor_rub":
        if has_belt or str(drive_type).lower() == "belt":
            support = min(support, 0.38)
            notes.append("belt/pulley sources can create similar fractional vibration")
        elif drive_unknown:
            support = min(support, 0.50)
            notes.append("drive type is unknown; belt/pulley sources are not ruled out")
        elif direct_coupled:
            support = max(support, 0.72)
        if not asset.metadata.get("rub_confirmation_available"):
            support = min(support, 0.62)
            notes.append("rub-specific confirmation data is missing")

    # Global diagnostic context limits root-cause confidence.
    if "trend_history_or_persistence_features" in missing:
        support = min(support, 0.78)
        notes.append("trend/persistence evidence is missing")
    if "load_condition_or_operating_state" in missing:
        support = min(support, 0.82)
        notes.append("load/operating-state context is missing")
    if "drive_type/direct_coupled/belt_drive_present" in missing and fault_key in {"rotor_rub", "unbalance", "resonance_or_structural_amplification"}:
        support = min(support, 0.68)
        if "drive type is unknown; belt/pulley sources are not ruled out" not in notes:
            notes.append("drive type is missing")

    # Deduplicate notes.
    seen = set()
    out_notes = []
    for item in notes:
        if item not in seen:
            seen.add(item)
            out_notes.append(item)
    return float(_clamp(support, 0.0, 1.0)), out_notes


def _fault_confidence_assessment(
    result: FaultResult,
    asset: AssetDefinition,
    pattern_profile: PatternFamilyProfile,
    pattern_confidence: Mapping[str, Any],
    missing_metadata: List[str],
    rpm_quality: Mapping[str, Any],
) -> Dict[str, Any]:
    base = _confidence_float(result.confidence)
    score_factor = _score_linear(float(result.score), 25.0, 80.0)
    pattern_fit = _fault_pattern_fit_score(result.fault_key, pattern_profile.dominant_family)
    metadata_support, metadata_notes = _metadata_support_for_fault(asset, result.fault_key, missing_metadata)
    rpm_factor = {"high": 1.0, "medium": 0.78, "low": 0.45, "none": 0.15}.get(str(rpm_quality.get("confidence", "low")), 0.45)
    severity_factor = _score_linear(_severity_rank(result.fault_severity_label), 1.0, 4.0)
    value = _clamp(
        0.30 * base +
        0.25 * score_factor +
        0.20 * pattern_fit +
        0.15 * metadata_support +
        0.05 * rpm_factor +
        0.05 * severity_factor,
        0.0,
        1.0,
    )

    # Conservative cap for low-severity rotor rub without confirmation.
    if result.fault_key == "rotor_rub" and result.fault_severity_label in {None, "low"} and not asset.metadata.get("rub_confirmation_available"):
        value = min(value, 0.54)
        metadata_notes.append("rotor rub is capped because severity is low and no rub confirmation is available")

    return {
        "score": float(round(value, 3)),
        "level": _reasoning_label_from_score(value),
        "base_script_confidence": result.confidence,
        "pattern_fit_score": float(round(pattern_fit, 3)),
        "metadata_support_score": float(round(metadata_support, 3)),
        "rpm_factor": float(round(rpm_factor, 3)),
        "limiters": list(dict.fromkeys(metadata_notes + list(result.limitations[:3]))),
    }


def _hypothesis_record(
    result: FaultResult,
    asset: AssetDefinition,
    pattern_profile: PatternFamilyProfile,
    pattern_confidence: Mapping[str, Any],
    missing_metadata: List[str],
    rpm_quality: Mapping[str, Any],
    include_debug: bool = False,
) -> Dict[str, Any]:
    raw = _serialize_reasoning_fault(result, include_debug=include_debug)
    fault_conf = _fault_confidence_assessment(result, asset, pattern_profile, pattern_confidence, missing_metadata, rpm_quality)
    adjusted = _clamp(float(result.score) * (0.55 + 0.45 * fault_conf["score"]), 0.0, 100.0)
    raw.update({
        "raw_script_score": float(round(result.score, 2)),
        "reasoning_adjusted_score": float(round(adjusted, 2)),
        "fault_confidence": fault_conf,
        "evidence_for": _fault_evidence_for(result),
        "evidence_against": _fault_evidence_against(result, asset, pattern_profile, []),
    })
    return raw


def _rank_hypotheses_pattern_first(
    results: List[FaultResult],
    asset: AssetDefinition,
    pattern_profile: PatternFamilyProfile,
    pattern_confidence: Mapping[str, Any],
    missing_metadata: List[str],
    rpm_quality: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    records = [
        _hypothesis_record(r, asset, pattern_profile, pattern_confidence, missing_metadata, rpm_quality, include_debug=False)
        for r in results
    ]
    # Do not allow metadata-weak specific faults to outrank a broad pattern-level diagnosis.
    for rec in records:
        fk = str(rec.get("fault_key"))
        fc = rec.get("fault_confidence", {}) or {}
        if fc.get("metadata_support_score", 1.0) < 0.50 and fk in {
            "rotor_rub", "fluid_film_instability", "gear_mesh_fault", "gear_misalignment",
            "gear_eccentricity_or_runout", "gear_backlash_or_looseness", "gear_tooth_wear",
            "gear_localized_tooth_damage", "bearing_bpfo", "bearing_bpfi", "bearing_bsf", "bearing_ftf",
            "belt_sheave_misalignment", "belt_sheave_eccentricity", "belt_slip_or_tension_fault",
            "belt_wear_or_damage", "belt_span_resonance",
        }:
            rec["reasoning_adjusted_score"] = float(round(float(rec.get("reasoning_adjusted_score", 0.0)) * 0.75, 2))
            rec.setdefault("reasoning_notes", []).append("demoted because required metadata is incomplete")
    return sorted(records, key=lambda r: (-float(r.get("reasoning_adjusted_score", 0.0)), -float(r.get("raw_script_score", 0.0)), str(r.get("fault_key"))))


def _simple_evidence_summary(pattern_payload: Mapping[str, Any], primary_payload: Optional[Mapping[str, Any]]) -> List[str]:
    out: List[str] = []
    for item in list(pattern_payload.get("evidence", []) or [])[:3]:
        out.append(str(item))
    if primary_payload:
        for item in list(primary_payload.get("evidence_for", []) or [])[:2]:
            if item not in out:
                out.append(str(item))
    return out[:4]


def _simple_missing_info(missing_metadata: List[str]) -> List[str]:
    label_map = {
        "drive_type/direct_coupled/belt_drive_present": "drive type / belt-drive status",
        "trend_history_or_persistence_features": "trend history / persistence",
        "load_condition_or_operating_state": "load or operating state",
        "gear_stage_teeth_and_stage_speed": "gear tooth count and stage speed",
        "bearing_id_or_bearing_fault_frequencies": "bearing ID or bearing fault frequencies",
        "belt_geometry_or_belt_pass_frequency": "belt geometry or belt pass frequency",
        "motor_line_frequency_and_pole_metadata": "motor electrical metadata",
        "rub_confirmation_inspection_phase_or_speed_sweep": "rub confirmation from inspection/phase/speed sweep",
    }
    return [label_map.get(x, x) for x in missing_metadata[:6]]


def _operator_severity(primary: Optional[Mapping[str, Any]], status: str) -> str:
    if primary and primary.get("severity_label"):
        return str(primary.get("severity_label"))
    if status in {"immediate_review", "urgent"}:
        return "high"
    if status == "plan":
        return "medium"
    return "low"


def _build_controlled_reasoning_text(
    pattern_payload: Mapping[str, Any],
    primary_payload: Optional[Mapping[str, Any]],
    alternatives: List[Mapping[str, Any]],
    missing_metadata: List[str],
    asset_context: Mapping[str, Any],
) -> str:
    if primary_payload is None:
        return f"The dominant pattern is {pattern_payload.get('label', 'uncertain')}, but no root-cause hypothesis has enough support to be named as primary. Confidence remains limited by missing metadata."
    fault_key = str(primary_payload.get("fault_key", ""))
    label = str(primary_payload.get("label", fault_key))
    metrics = pattern_payload.get("metrics", {}) or {}
    mean_1x = float(metrics.get("mean_1x_ratio", 0.0) or 0.0)
    mean_harm = float(metrics.get("mean_harmonic_ratio", 0.0) or 0.0)
    mean_frac = float(metrics.get("mean_fractional_ratio", 0.0) or 0.0)
    mean_side = float(metrics.get("mean_sideband_ratio", 0.0) or 0.0)
    sentences: List[str] = []
    if fault_key == "looseness_type_c_rotating_fit":
        sentences.append("The score favors Type C rotating-fit/internal looseness because the pattern is not a clean 1X-only response.")
        details = []
        if mean_harm > 0:
            details.append(f"harmonic content is elevated, mean harmonic ratio {mean_harm:.2f}x RMS")
        if mean_side > 0:
            details.append(f"sideband/modulation content is present, mean sideband ratio {mean_side:.2f}")
        if mean_frac > 0:
            details.append(f"fractional/subsynchronous content is present, mean fractional ratio {mean_frac:.2f}x RMS")
        if mean_1x > 0:
            details.append(f"1X is present but not isolated, mean 1X ratio {mean_1x:.2f}x RMS")
        if details:
            sentences.append("Key evidence: " + "; ".join(details) + ".")
    else:
        sentences.append(f"The primary hypothesis is {label} because it has the strongest pattern-adjusted support after metadata checks.")

    rotor_alt = next((x for x in alternatives if x.get("fault_key") == "rotor_rub"), None)
    if fault_key != "rotor_rub":
        if rotor_alt:
            sentences.append("Rotor rub is kept as a secondary possibility rather than the main diagnosis because fractional/subsynchronous vibration is not specific to rub.")
        else:
            sentences.append("Rotor rub is not shown as a main fault because rub-specific evidence is insufficient.")
        rub_reasons = []
        if fault_key == "looseness_type_c_rotating_fit":
            rub_reasons.append("Type C looseness explains the same fractional and harmonic evidence more broadly")
        drive_type = str(asset_context.get("drive_type", "unknown")).lower()
        if drive_type in {"unknown", "", "none"}:
            rub_reasons.append("drive type is unknown, so belt/pulley influence has not been ruled out")
        elif drive_type == "belt":
            rub_reasons.append("belt/pulley faults can create similar fractional/subsynchronous components")
        if mean_frac > 0:
            rub_reasons.append("fractional content can also come from looseness, belt/pulley effects, resonance, or clearance issues")
        if rub_reasons:
            sentences.append("Rub suppression reason: " + "; ".join(rub_reasons) + ".")

    missing_readable = _simple_missing_info(missing_metadata)
    if missing_readable:
        sentences.append("Confidence remains limited because " + "; ".join(missing_readable[:4]) + " are missing or incomplete.")
    return " ".join(sentences)


def _build_report_views(
    asset: AssetDefinition,
    status: str,
    pattern_payload: Mapping[str, Any],
    primary_payload: Optional[Mapping[str, Any]],
    alternatives: List[Mapping[str, Any]],
    missing_metadata: List[str],
    data_quality: Mapping[str, Any],
    include_debug: bool,
    raw_results: List[FaultResult],
    axis_metrics: Mapping[str, float],
    pattern_profile: PatternFamilyProfile,
) -> Dict[str, Any]:
    asset_context = _asset_context_summary(asset)
    reasoning_text = _build_controlled_reasoning_text(pattern_payload, primary_payload, alternatives, missing_metadata, asset_context)
    primary_name = None if primary_payload is None else str(primary_payload.get("label"))
    operator = {
        "status": status,
        "headline": _operator_headline(None if primary_payload is None else next((r for r in raw_results if r.fault_key == primary_payload.get("fault_key")), None), pattern_profile, "candidate" if primary_payload else "uncertain"),
        "pattern": {
            "label": pattern_payload.get("label"),
            "confidence": pattern_payload.get("pattern_confidence", {}).get("level"),
        },
        "primary_finding": primary_name,
        "fault_confidence": None if primary_payload is None else (primary_payload.get("fault_confidence", {}) or {}).get("level"),
        "severity": _operator_severity(primary_payload, status),
        "evidence_summary": _simple_evidence_summary(pattern_payload, primary_payload),
        "reasoning_text": reasoning_text,
        "recommended_next_checks": _recommended_next_checks(
            None if primary_payload is None else next((r for r in raw_results if r.fault_key == primary_payload.get("fault_key")), None),
            [r for r in raw_results if primary_payload is None or r.fault_key != primary_payload.get("fault_key")][:4],
            missing_metadata,
            asset,
        )[:4],
        "missing_info_limiting_confidence": _simple_missing_info(missing_metadata),
    }
    engineer = {
        "asset_context": asset_context,
        "pattern": pattern_payload,
        "hypotheses": [x for x in ([primary_payload] if primary_payload else []) + alternatives[:6] if x],
        "data_quality": data_quality,
        "missing_metadata": missing_metadata,
        "differential_diagnosis_notes": {
            "pattern_first": "Pattern is interpreted before naming a root cause.",
            "metadata_gate": "Specific faults are demoted when required machine metadata is missing.",
            "confidence_split": "Pattern confidence and root-cause/fault confidence are reported separately.",
        },
    }
    views: Dict[str, Any] = {"operator": operator, "engineer": engineer}
    if include_debug:
        views["debug"] = {
            "raw_fault_scores": [_serialize_reasoning_fault(r, include_debug=True) for r in raw_results],
            "axis_metrics": axis_metrics,
            "pattern_profile_raw": pattern_profile.as_dict(),
        }
    return views


def build_diagnostic_reasoning_report(
    asset: AssetDefinition,
    results: List[FaultResult],
    include_debug: bool = False,
) -> Dict[str, Any]:
    """
    Pattern-first, metadata-aware diagnostic report.

    This v2 output layer implements:
    - pattern-first interpretation
    - metadata-aware confidence/suppression
    - separate pattern confidence and fault/root-cause confidence
    - simple operator view, richer engineer view, optional debug view
    """
    pattern_profile = classify_asset_pattern(asset)
    axis_rows = _axis_feature_snapshot(asset)
    axis_metrics = _axis_aggregate_metrics(axis_rows)
    rpm_quality = _rpm_quality_assessment(asset, axis_rows)
    sorted_raw_results = sorted(results, key=_result_sort_key)
    missing_metadata = _missing_diagnostic_metadata(asset, sorted_raw_results)
    pattern_conf = _pattern_confidence_assessment(pattern_profile, axis_metrics, rpm_quality, axis_rows)

    pattern_payload = {
        "family": pattern_profile.dominant_family,
        "label": _pattern_label(pattern_profile.dominant_family),
        "direction": pattern_profile.dominant_direction,
        "pattern_confidence": pattern_conf,
        "scores": {
            "synchronous": float(round(pattern_profile.synchronous_score, 1)),
            "harmonic": float(round(pattern_profile.harmonic_score, 1)),
            "subsynchronous": float(round(pattern_profile.subsynchronous_score, 1)),
            "modulation": float(round(pattern_profile.modulation_score, 1)),
            "broadband": float(round(pattern_profile.broadband_score, 1)),
        },
        "directional_bias": {
            "radial": float(round(pattern_profile.radial_bias, 3)),
            "axial": float(round(pattern_profile.axial_bias, 3)),
            "mixed": float(round(pattern_profile.mixed_bias, 3)),
        },
        "evidence": _pattern_evidence(pattern_profile, axis_metrics),
        "metrics": {k: float(round(v, 4)) for k, v in pattern_profile.metrics.items()},
    }

    ranked_hypotheses = _rank_hypotheses_pattern_first(
        sorted_raw_results,
        asset,
        pattern_profile,
        pattern_conf,
        missing_metadata,
        rpm_quality,
    )

    # Only show a primary root-cause if adjusted evidence and confidence are sufficient.
    primary_payload: Optional[Dict[str, Any]] = None
    if ranked_hypotheses:
        top = ranked_hypotheses[0]
        top_conf = (top.get("fault_confidence", {}) or {}).get("score", 0.0)
        if float(top.get("reasoning_adjusted_score", 0.0)) >= 18.0 and float(top_conf) >= 0.30:
            primary_payload = top

    alternatives = [h for h in ranked_hypotheses if primary_payload is None or h.get("fault_key") != primary_payload.get("fault_key")]

    # If the only high specific fault is metadata-weak, present as pattern-only.
    if primary_payload is not None:
        fc = primary_payload.get("fault_confidence", {}) or {}
        if fc.get("metadata_support_score", 1.0) < 0.40 and fc.get("score", 0.0) < 0.55:
            alternatives.insert(0, primary_payload)
            primary_payload = None

    status = _status_from_results(sorted_raw_results)
    data_quality = {
        "rpm_quality": rpm_quality,
        "axis_count_used": len(axis_rows),
        "pattern_confidence": pattern_conf,
    }
    views = _build_report_views(
        asset=asset,
        status=status,
        pattern_payload=pattern_payload,
        primary_payload=primary_payload,
        alternatives=alternatives,
        missing_metadata=missing_metadata,
        data_quality=data_quality,
        include_debug=include_debug,
        raw_results=sorted_raw_results,
        axis_metrics=axis_metrics,
        pattern_profile=pattern_profile,
    )

    operator = views["operator"]
    llm_ready_payload = {
        "asset_context": _asset_context_summary(asset),
        "pattern_summary": pattern_payload,
        "axis_feature_summary": axis_rows[:8],
        "ranked_hypotheses": [x for x in ([primary_payload] if primary_payload else []) + alternatives[:6] if x],
        "missing_inputs": list(missing_metadata),
        "data_quality": data_quality,
        "instruction": (
            "Use only this structured evidence. First state the vibration pattern, then compare hypotheses. "
            "Do not invent faults. Do not name rotor rub as primary unless rub-specific evidence is strong and competing belt/looseness/resonance explanations are ruled out."
        ),
    }

    report: Dict[str, Any] = {
        "schema_version": DIAGNOSTIC_REASONING_LAYER_VERSION,
        "asset_id": asset.asset_id,
        "status": status,
        "views": views,
        # Backward-compatible top-level fields:
        "operator_summary": operator,
        "pattern": pattern_payload,
        "primary_hypothesis": primary_payload,
        "alternative_hypotheses": alternatives[:6],
        "missing_metadata": list(missing_metadata),
        "data_quality": data_quality,
        "llm_ready_payload": llm_ready_payload,
    }
    if include_debug:
        report["debug"] = views.get("debug", {})
    return report


# ---------------------------------------------------------------------------
# Domain-separated spectral routing patch
# ---------------------------------------------------------------------------
# Design intent
# -------------
# - Shaft / train / structural faults use VELOCITY spectrum:
#   unbalance, misalignment, looseness, soft foot, bent shaft, resonance,
#   shaft-order pattern classifier, belt/sheave order checks, and motor
#   vibration lines.
# - Bearing, lubrication, gear, hydraulic, and contact/high-frequency evidence
#   use ACCELERATION waveform/spectrum and acceleration envelope spectrum.
# - Backward compatibility: if only acceleration waveform is supplied, velocity
#   waveform/spectrum are derived automatically. The legacy signal.spectrum field
#   is then set to velocity spectrum so existing shaft-order rules behave as
#   intended.

G_TO_MM_PER_S2 = 9806.65

SHAFT_ORDER_FAULT_KEYS = {
    "unbalance", "misalignment", "looseness_type_a_base_structure",
    "looseness_type_b_pedestal_support", "looseness_type_c_rotating_fit",
    "soft_foot_or_frame_distortion", "bent_shaft_or_bow",
    "resonance_or_structural_amplification", "motor_electrical_forcing",
    "belt_sheave_misalignment", "belt_sheave_eccentricity",
    "belt_slip_or_tension_fault", "belt_span_resonance",
}

ACCELERATION_FAULT_KEYS = {
    "lubrication_distress", "bearing_bpfo", "bearing_bpfi", "bearing_bsf",
    "bearing_ftf", "bearing_wear_progression", "gear_mesh_fault",
    "gear_misalignment", "gear_eccentricity_or_runout",
    "gear_backlash_or_looseness", "gear_tooth_wear",
    "gear_localized_tooth_damage", "hydraulic_vane_or_blade_pass",
    "cavitation_or_aeration", "rotor_rub",
}


def _fft_single_sided_amplitude(x: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size < 2 or fs <= 0.0:
        return _EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY
    x = x - float(np.mean(x))
    win = np.hanning(x.size)
    xw = x * win
    freqs = np.fft.rfftfreq(x.size, d=1.0 / fs)
    scale = 2.0 / max(float(np.sum(win)), 1e-12)
    amps = np.abs(np.fft.rfft(xw)) * scale
    if amps.size:
        amps[0] *= 0.5
    return freqs.astype(float), amps.astype(float)


def _velocity_from_acceleration_waveform_mm_s(accel_g: np.ndarray, fs: float) -> np.ndarray:
    """Frequency-domain integration: acceleration(g) -> velocity(mm/s)."""
    x = np.asarray(accel_g, dtype=float).reshape(-1)
    if x.size < 2 or fs <= 0.0:
        return _EMPTY_FLOAT_ARRAY
    a_mm_s2 = (x - float(np.mean(x))) * G_TO_MM_PER_S2
    spec = np.fft.rfft(a_mm_s2)
    freqs = np.fft.rfftfreq(x.size, d=1.0 / fs)
    omega = 2.0 * np.pi * freqs
    vel_spec = np.zeros_like(spec, dtype=complex)
    mask = omega > 1e-12
    vel_spec[mask] = spec[mask] / (1j * omega[mask])
    vel_spec[0] = 0.0
    v = np.fft.irfft(vel_spec, n=x.size)
    try:
        v = detrend(v, type="linear")
    except Exception:
        v = v - float(np.mean(v))
    return np.asarray(v, dtype=float)


def _domain_attr_names(domain: str) -> Tuple[str, str]:
    if domain == "velocity":
        return "velocity_freqs_hz", "velocity_spectrum"
    if domain == "acceleration":
        return "acceleration_freqs_hz", "acceleration_spectrum"
    return "freqs_hz", "spectrum"


def _has_domain_spectrum(signal: AxisSignal, domain: str) -> bool:
    f_attr, a_attr = _domain_attr_names(domain)
    freqs = getattr(signal, f_attr, None)
    amps = getattr(signal, a_attr, None)
    return freqs is not None and amps is not None and len(freqs) > 0 and len(freqs) == len(amps)


def _ensure_signal_domain_spectra(signal: AxisSignal) -> None:
    """Populate explicit acceleration/velocity spectra when possible."""
    if getattr(signal, "_domain_spectra_prepared", False):
        return

    # Preserve a supplied legacy spectrum under the declared kind.
    kind = str(getattr(signal, "spectrum_kind", "auto") or "auto").lower()
    if kind == "velocity" and not _has_domain_spectrum(signal, "velocity"):
        signal.velocity_freqs_hz = list(signal.freqs_hz or [])
        signal.velocity_spectrum = list(signal.spectrum or [])
    elif kind == "acceleration" and not _has_domain_spectrum(signal, "acceleration"):
        signal.acceleration_freqs_hz = list(signal.freqs_hz or [])
        signal.acceleration_spectrum = list(signal.spectrum or [])

    fs = float(getattr(signal, "waveform_sample_rate_hz", None) or 0.0)

    # Derive acceleration spectrum from acceleration waveform if available.
    acc_wave = _waveform_array(signal, "acceleration")
    if acc_wave is not None and fs > 0.0:
        if not _has_domain_spectrum(signal, "acceleration"):
            af, aa = _fft_single_sided_amplitude(acc_wave, fs)
            signal.acceleration_freqs_hz = af.tolist()
            signal.acceleration_spectrum = aa.tolist()
        if signal.overall_acceleration_g is None:
            signal.overall_acceleration_g = _rms(acc_wave - np.mean(acc_wave))

        if signal.velocity_waveform is None:
            v = _velocity_from_acceleration_waveform_mm_s(acc_wave, fs)
            if v.size:
                signal.velocity_waveform = v.tolist()
        vel_wave = _waveform_array(signal, "velocity")
        if vel_wave is not None:
            if not _has_domain_spectrum(signal, "velocity"):
                vf, va = _fft_single_sided_amplitude(vel_wave, fs)
                signal.velocity_freqs_hz = vf.tolist()
                signal.velocity_spectrum = va.tolist()
            if signal.overall_velocity_mm_s is None:
                signal.overall_velocity_mm_s = _rms(vel_wave - np.mean(vel_wave))

    # Derive velocity spectrum from velocity waveform if explicitly available.
    vel_wave = _waveform_array(signal, "velocity")
    if vel_wave is not None and fs > 0.0 and not _has_domain_spectrum(signal, "velocity"):
        vf, va = _fft_single_sided_amplitude(vel_wave, fs)
        signal.velocity_freqs_hz = vf.tolist()
        signal.velocity_spectrum = va.tolist()
        if signal.overall_velocity_mm_s is None:
            signal.overall_velocity_mm_s = _rms(vel_wave - np.mean(vel_wave))

    # If no explicit velocity spectrum exists, keep backward compatibility by
    # treating the legacy spectrum as velocity. This avoids breaking existing
    # callers that already passed velocity spectra in signal.spectrum.
    if not _has_domain_spectrum(signal, "velocity") and signal.freqs_hz and signal.spectrum:
        signal.velocity_freqs_hz = list(signal.freqs_hz)
        signal.velocity_spectrum = list(signal.spectrum)

    # If no explicit acceleration spectrum exists, and a legacy acceleration-like
    # spectrum was not declared, use the legacy spectrum as a final fallback for
    # acceleration-domain modules. This is conservative and preserves old behavior.
    if not _has_domain_spectrum(signal, "acceleration") and signal.freqs_hz and signal.spectrum:
        signal.acceleration_freqs_hz = list(signal.freqs_hz)
        signal.acceleration_spectrum = list(signal.spectrum)

    # Legacy main spectrum is now the velocity spectrum for shaft/order rules.
    if _has_domain_spectrum(signal, "velocity"):
        signal.freqs_hz = list(signal.velocity_freqs_hz or [])
        signal.spectrum = list(signal.velocity_spectrum or [])
        signal.spectrum_kind = "velocity"

    signal._domain_spectra_prepared = True


def prepare_asset_signal_domains(asset: AssetDefinition) -> None:
    for sensor in asset.sensors:
        for signal in sensor.directions.values():
            if hasattr(signal, "_runtime_np_cache"):
                getattr(signal, "_runtime_np_cache").clear()
            signal._domain_spectra_prepared = False
            _ensure_signal_domain_spectra(signal)
            if hasattr(signal, "_runtime_np_cache"):
                getattr(signal, "_runtime_np_cache").clear()
    asset.metadata["spectrum_routing"] = {
        "shaft_faults": "velocity_spectrum",
        "bearing_lubrication_gear_hydraulic_contact_faults": "acceleration_waveform/spectrum/envelope",
        "legacy_signal_spectrum_after_prepare": "velocity_spectrum",
    }


def _cached_domain_spectrum_arrays(signal: AxisSignal, domain: str) -> Tuple[np.ndarray, np.ndarray]:
    _ensure_signal_domain_spectra(signal)
    cache = _runtime_cache_dict(signal, "_runtime_np_cache")
    key = ("__domain_spectrum__", domain)
    if key in cache:
        return cache[key]
    f_attr, a_attr = _domain_attr_names(domain)
    freqs = _cached_signal_array(signal, f_attr)
    amps = _cached_signal_array(signal, a_attr)
    if freqs is None or amps is None or freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        freqs, amps = _cached_signal_array(signal, "freqs_hz"), _cached_signal_array(signal, "spectrum")
    if freqs is None or amps is None or freqs.size == 0 or amps.size == 0 or freqs.size != amps.size:
        out = (_EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY)
    else:
        positive = freqs > 0.0
        f2, a2 = (freqs[positive], amps[positive]) if np.any(positive) else (_EMPTY_FLOAT_ARRAY, _EMPTY_FLOAT_ARRAY)
        if f2.size > 1 and np.any(np.diff(f2) < 0.0):
            order = np.argsort(f2)
            f2, a2 = f2[order], a2[order]
        out = (f2, a2)
    cache[key] = out
    return out


# Override default spectrum cache: legacy extraction now means velocity.
def _cached_signal_spectrum_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    return _cached_domain_spectrum_arrays(signal, "velocity")


def _cached_acceleration_spectrum_arrays(signal: AxisSignal) -> Tuple[np.ndarray, np.ndarray]:
    return _cached_domain_spectrum_arrays(signal, "acceleration")


def _spectrum_pack(freqs: np.ndarray, amps: np.ndarray, shaft_hz: float, tolerance_hz: float) -> Dict[str, float]:
    if freqs.size == 0 or amps.size == 0:
        return {
            "rms": 0.0, "hf_rms_ratio": 0.0, "noise_floor": 0.0, "subsync_freq_hz": 0.0, "subsync_amp": 0.0,
            "amp_05x": 0.0, "amp_1x": 0.0, "amp_15x": 0.0, "amp_2x": 0.0, "amp_25x": 0.0, "amp_3x": 0.0,
        }
    rms = _rms(amps)
    hf_start = max(5.0 * shaft_hz, 50.0 if freqs[-1] >= 100.0 else 3.0 * shaft_hz)
    hf_mask = freqs >= hf_start
    targets = {
        "amp_05x": 0.5 * shaft_hz,
        "amp_1x": 1.0 * shaft_hz,
        "amp_15x": 1.5 * shaft_hz,
        "amp_2x": 2.0 * shaft_hz,
        "amp_25x": 2.5 * shaft_hz,
        "amp_3x": 3.0 * shaft_hz,
        "amp_35x": 3.5 * shaft_hz,
        "amp_4x": 4.0 * shaft_hz,
        "amp_5x": 5.0 * shaft_hz,
        "amp_6x": 6.0 * shaft_hz,
        "amp_7x": 7.0 * shaft_hz,
        "amp_8x": 8.0 * shaft_hz,
        "amp_9x": 9.0 * shaft_hz,
        "amp_10x": 10.0 * shaft_hz,
    }
    peaks = _peak_amplitudes_at_targets(freqs, amps, targets, tolerance_hz)
    subsync_freq, subsync_amp = _peak_in_band(freqs, amps, 0.42 * shaft_hz, 0.48 * shaft_hz)
    out = {
        "rms": rms,
        "hf_rms_ratio": _safe_ratio(_rms(amps[hf_mask]) if np.any(hf_mask) else 0.0, rms),
        "noise_floor": float(np.median(np.abs(amps))) if amps.size else 0.0,
        "subsync_freq_hz": subsync_freq,
        "subsync_amp": subsync_amp,
    }
    out.update(peaks)
    return out


def _acceleration_pack(signal: AxisSignal, feat: AxisFeatures) -> Dict[str, float]:
    freqs, amps = _cached_acceleration_spectrum_arrays(signal)
    pack = _spectrum_pack(freqs, amps, feat.shaft_hz, feat.tolerance_hz)
    pack["crest_factor"] = feat.crest_factor
    pack["kurtosis"] = feat.kurtosis
    pack["wf_impact_periodicity"] = feat.wf_impact_periodicity
    return pack


def _pack_amp_ratio(pack: Mapping[str, float], key_or_sum: Any) -> float:
    rms = max(float(pack.get("rms", 0.0)), 1e-12)
    if isinstance(key_or_sum, str):
        value = float(pack.get(key_or_sum, 0.0))
    else:
        value = float(sum(float(pack.get(k, 0.0)) for k in key_or_sum))
    return _safe_ratio(value, rms)


# Sideband helper now uses velocity by default; gear/hydraulic helpers use their
# own acceleration-domain implementations below.
def _sideband_pair_ratio(signal: AxisSignal, center_hz: float, spacing_hz: float, tolerance_hz: float) -> float:
    if center_hz <= 0.0 or spacing_hz <= 0.0:
        return 0.0
    freqs, amps = _cached_domain_spectrum_arrays(signal, "velocity")
    if freqs.size == 0 or amps.size == 0:
        return 0.0
    _, center_amp = _peak_at(freqs, amps, center_hz, tolerance_hz)
    if center_amp <= 1e-12:
        return 0.0
    _, left_amp = _peak_at(freqs, amps, center_hz - spacing_hz, tolerance_hz)
    _, right_amp = _peak_at(freqs, amps, center_hz + spacing_hz, tolerance_hz)
    # Avoid false high sideband ratios when the carrier/center is extremely weak.
    center_ratio = _safe_ratio(center_amp, max(_rms(amps), 1e-12))
    if center_ratio < 0.35:
        return 0.0
    symmetry = _safe_ratio(min(left_amp, right_amp), max(left_amp, right_amp, 1e-12))
    ratio = _safe_ratio(0.5 * (left_amp + right_amp), center_amp)
    if symmetry < 0.20:
        ratio *= 0.50
    return float(ratio)


# Rotor rub: shaft-order evidence still comes from velocity via feat; contact/
# impulsiveness comes from acceleration waveform and acceleration spectrum.
def _score_rub(sensor: SensorMeasurement, feat: AxisFeatures) -> float:
    signal = sensor.directions.get(feat.axis)
    acc = _acceleration_pack(signal, feat) if signal is not None else {}
    frac_v = feat.amp_ratio(feat.amp_05x + feat.amp_15x + feat.amp_25x)
    frac_a = _pack_amp_ratio(acc, ["amp_05x", "amp_15x", "amp_25x"])
    frac = 0.55 * frac_v + 0.45 * frac_a
    score = (
        18.0 * _score_linear(frac, 0.8, 3.0) +
        14.0 * _score_linear(0.5 * feat.amp_ratio(feat.amp_05x) + 0.5 * _pack_amp_ratio(acc, "amp_05x"), 0.4, 1.8) +
        9.0 * _score_linear(0.5 * feat.amp_ratio(feat.amp_15x) + 0.5 * _pack_amp_ratio(acc, "amp_15x"), 0.3, 1.5) +
        9.0 * _score_linear(0.5 * feat.amp_ratio(feat.amp_25x) + 0.5 * _pack_amp_ratio(acc, "amp_25x"), 0.2, 1.0) +
        18.0 * _score_linear(max(acc.get("kurtosis", feat.kurtosis), 0.0), 0.8, 3.5) +
        16.0 * _score_linear(acc.get("crest_factor", feat.crest_factor), 4.0, 7.0) +
        8.0 * _score_linear(0.5 * feat.amp_ratio(feat.amp_2x + feat.amp_3x) + 0.5 * _pack_amp_ratio(acc, ["amp_2x", "amp_3x"]), 0.6, 2.5) +
        8.0 * _score_linear(acc.get("wf_impact_periodicity", feat.wf_impact_periodicity), 0.35, 0.80)
    )
    return float(score * _axis_weight("rotor_rub", sensor, feat.axis) * _component_weight("rotor_rub", sensor))


# Motor electrical vibration lines are low-frequency shaft/vibration evidence;
# use velocity spectrum.
def _score_motor_electrical(sensor: SensorMeasurement, feat: AxisFeatures, asset: AssetDefinition) -> float:
    motor = next((m for m in asset.motors if m.component_id == sensor.component_id), None)
    if motor is None:
        return 0.0
    signal = sensor.directions[feat.axis]
    freqs, amps = _cached_domain_spectrum_arrays(signal, "velocity")
    if freqs.size == 0 or amps.size == 0:
        return 0.0
    line = float(motor.line_frequency_hz)
    tol = max(feat.tolerance_hz, 1.0)
    _, amp_1lf = _peak_at(freqs, amps, line, tol)
    _, amp_2lf = _peak_at(freqs, amps, 2.0 * line, tol)
    line_ratio = _safe_ratio(amp_1lf, max(feat.rms_spectrum, 1e-12))
    double_line_ratio = _safe_ratio(amp_2lf, max(feat.rms_spectrum, 1e-12))
    score = (
        38.0 * _score_linear(double_line_ratio, 0.5, 3.0) +
        18.0 * _score_linear(line_ratio, 0.4, 2.0) +
        14.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_05x + feat.amp_15x), 0.8, 2.5)) +
        15.0 * (1.0 - _score_linear(feat.amp_ratio(feat.amp_2x + feat.amp_3x + feat.amp_4x + feat.amp_5x), 2.0, 6.0)) +
        15.0 * _score_linear(max(line_ratio, double_line_ratio), 0.7, 3.0)
    )
    return float(score * _axis_weight("motor_electrical_forcing", sensor, feat.axis) * _component_weight("motor_electrical_forcing", sensor))


def _bearing_local_score_from_axis(
    fault_key: str,
    asset: AssetDefinition,
    bearing: BearingDefinition,
    sensor: SensorMeasurement,
    feat: AxisFeatures,
    signal: AxisSignal,
) -> Tuple[float, List[str], Dict[str, float]]:
    temp_delta = _temperature_delta_c(asset, sensor)
    acc = _acceleration_pack(signal, feat)
    evidence_pack = _bearing_characteristic_evidence(asset, bearing, sensor, feat, signal)
    acc_hf = float(acc.get("hf_rms_ratio", 0.0))
    acc_kurt = float(acc.get("kurtosis", feat.kurtosis))
    acc_crest = float(acc.get("crest_factor", feat.crest_factor))
    periodicity = float(acc.get("wf_impact_periodicity", feat.wf_impact_periodicity))
    random_impact = 1.0 - periodicity

    if fault_key == "lubrication_distress":
        best_defect = evidence_pack.get("best_defect_env_score", 0.0)
        raceway_fraction = evidence_pack.get("raceway_fraction", 0.0)
        cage_ball_fraction = evidence_pack.get("cage_ball_fraction", 0.0)
        shaft_order_acc = _pack_amp_ratio(acc, ["amp_1x", "amp_2x", "amp_3x"])
        score = (
            22.0 * _score_linear(acc_hf, 0.55, 2.50) +
            12.0 * _score_linear(max(acc_kurt, 0.0), 0.40, 2.80) +
            10.0 * _score_linear(acc_crest, 3.2, 6.2) +
            14.0 * _score_linear(temp_delta, 4.0, 18.0) +
            18.0 * _score_linear(random_impact, 0.30, 0.85) +
            10.0 * _score_linear(evidence_pack.get("envelope_centroid_ratio", 0.0), 0.18, 0.55) +
            8.0 * _score_linear(cage_ball_fraction, 0.40, 0.80) +
            6.0 * (1.0 - _score_linear(best_defect, 28.0, 70.0))
        )
        if shaft_order_acc > 7.0:
            score *= 0.82
        if best_defect >= 55.0 and periodicity >= 0.35:
            score *= 0.58
        if raceway_fraction >= 0.60 and evidence_pack.get("defect_hit_total", 0.0) >= 3.0:
            score *= 0.72
        metrics = {"temp_delta_c": temp_delta, "waveform_impact_periodicity": periodicity, "random_impact_ratio": random_impact, "acc_hf_rms_ratio": acc_hf, "acc_kurtosis": acc_kurt, "acc_crest_factor": acc_crest, **evidence_pack}
        evidence = [f"{sensor.sensor_id}/{feat.axis}: ACC_HF={acc_hf:.2f}, acc_kurtosis={acc_kurt:.2f}, acc_crest={acc_crest:.2f}, impact_periodicity={periodicity:.2f}, random_impact={random_impact:.2f}, best_defect_env={best_defect:.1f}, env_centroid={evidence_pack.get('envelope_centroid_ratio', 0.0):.2f}, temp_delta={temp_delta:.1f}C"]
        score *= _bearing_like_weight(sensor, feat.axis)
        return float(score), evidence, metrics

    if fault_key == "bearing_wear_progression":
        if bearing.bearing_type != "rolling":
            return 0.0, [], {}
        best_defect = evidence_pack.get("best_defect_env_score", 0.0)
        best_hits = evidence_pack.get("best_defect_hits", 0.0)
        raceway_fraction = evidence_pack.get("raceway_fraction", 0.0)
        score = (
            36.0 * _score_linear(best_defect, 18.0, 78.0) +
            12.0 * _score_linear(best_hits, 1.0, 4.0) +
            12.0 * _score_linear(evidence_pack.get("defect_hit_total", 0.0), 2.0, 8.0) +
            14.0 * _score_linear(periodicity, 0.22, 0.80) +
            10.0 * _score_linear(temp_delta, 4.0, 18.0) +
            8.0 * _score_linear(acc_hf, 0.50, 2.20) +
            8.0 * _score_linear(max(acc_kurt, 0.0), 0.30, 2.80)
        )
        score *= 0.85 + 0.30 * _score_linear(raceway_fraction, 0.35, 0.80)
        if best_defect < 24.0:
            score *= 0.55
        if random_impact >= 0.70 and periodicity < 0.18:
            score *= 0.52
        metrics = {"temp_delta_c": temp_delta, "waveform_impact_periodicity": periodicity, "random_impact_ratio": random_impact, "acc_hf_rms_ratio": acc_hf, "acc_kurtosis": acc_kurt, "acc_crest_factor": acc_crest, **evidence_pack}
        evidence = [f"{sensor.sensor_id}/{feat.axis}: best_defect_env={best_defect:.1f}, defect_hits={best_hits:.0f}, total_hits={evidence_pack.get('defect_hit_total', 0.0):.0f}, periodicity={periodicity:.2f}, raceway_fraction={raceway_fraction:.2f}, ACC_HF={acc_hf:.2f}, temp_delta={temp_delta:.1f}C"]
        score *= _bearing_like_weight(sensor, feat.axis)
        return float(score), evidence, metrics

    if fault_key == "fluid_film_instability":
        if bearing.bearing_type != "fluid_film":
            return 0.0, [], {}
        subsync_ratio = _safe_ratio(acc.get("subsync_freq_hz", 0.0), feat.shaft_hz)
        score = (
            34.0 * (1.0 - min(abs(subsync_ratio - 0.45) / 0.08, 1.0)) if acc.get("subsync_freq_hz", 0.0) > 0 else 0.0 +
            28.0 * _score_linear(_safe_ratio(acc.get("subsync_amp", 0.0), max(acc.get("rms", 0.0), 1e-12)), 0.5, 2.0) +
            14.0 * _score_linear(_safe_ratio(acc.get("subsync_amp", 0.0), max(acc.get("amp_1x", 0.0), 1e-12)), 0.15, 0.8) +
            10.0 * (1.0 - _score_linear(_pack_amp_ratio(acc, ["amp_2x", "amp_3x", "amp_4x"]), 1.2, 4.0)) +
            10.0 * _score_linear(temp_delta, 4.0, 18.0)
        )
        evidence = [f"{sensor.sensor_id}/{feat.axis}: accel_subsync={subsync_ratio:.2f}x, subsync_amp={_safe_ratio(acc.get('subsync_amp', 0.0), max(acc.get('rms', 0.0), 1e-12)):.2f}xRMS"]
        score *= _axis_weight(fault_key, sensor, feat.axis) * _component_weight(fault_key, sensor)
        return float(score), evidence, {"temp_delta_c": temp_delta, "acc_subsync_ratio": subsync_ratio, "acc_hf_rms_ratio": acc_hf}

    if fault_key == "thrust_bearing_or_axial_overload":
        score = (
            30.0 * (1.0 if feat.axis == "axial" else 0.0) +
            20.0 * _score_linear(_pack_amp_ratio(acc, ["amp_1x", "amp_2x"]), 1.5, 5.5) +
            20.0 * _score_linear(temp_delta, 4.0, 18.0) +
            15.0 * _score_linear(max(acc_kurt, 0.0), 0.4, 2.5) +
            15.0 * _score_linear(acc_crest, 3.5, 6.0)
        )
        evidence = [f"{sensor.sensor_id}/{feat.axis}: axial context, acc_1x+2x={_pack_amp_ratio(acc, ['amp_1x', 'amp_2x']):.2f}xRMS, temp_delta={temp_delta:.1f}C"]
        score *= _axis_weight(fault_key, sensor, feat.axis) * _component_weight(fault_key, sensor)
        return float(score), evidence, {"temp_delta_c": temp_delta, "acc_1x_2x_ratio": _pack_amp_ratio(acc, ["amp_1x", "amp_2x"]), "acc_kurtosis": acc_kurt, "acc_crest_factor": acc_crest}

    # Specific rolling-element defect families use acceleration envelope as the
    # primary evidence, with acceleration HF/impact features as support.
    freqs_map = bearing_fault_frequencies_hz(sensor.local_rpm or asset.running_rpm, bearing)
    if not freqs_map:
        return 0.0, [], {}
    family = fault_key.split("_", 1)[1]
    target_hz = freqs_map.get(family, 0.0)
    env_score, hits = envelope_harmonic_hit_score(signal, target_hz, max(feat.tolerance_hz, target_hz * 0.03), harmonics=4)
    score = (
        56.0 * _score_linear(env_score, 18.0, 75.0) +
        16.0 * _score_linear(acc_hf, 0.7, 2.5) +
        10.0 * _score_linear(max(acc_kurt, 0.0), 0.4, 2.8) +
        6.0 * _score_linear(acc_crest, 3.4, 6.5) +
        6.0 * _score_linear(temp_delta, 4.0, 18.0) +
        6.0 * _score_linear(periodicity, 0.25, 0.80)
    )
    score *= _axis_weight(fault_key, sensor, feat.axis) * _component_weight(fault_key, sensor)
    evidence = [f"{sensor.sensor_id}/{feat.axis}: {family.upper()}={target_hz:.1f}Hz, envelope_score={env_score:.1f}, hits={hits}, ACC_HF={acc_hf:.2f}, impact_periodicity={periodicity:.2f}, temp_delta={temp_delta:.1f}C"]
    metrics = {"temp_delta_c": temp_delta, "envelope_hits": float(hits), "acc_hf_rms_ratio": acc_hf, "acc_kurtosis": acc_kurt, "acc_crest_factor": acc_crest, "waveform_impact_periodicity": periodicity}
    return float(score), evidence, metrics


def _gear_axis_score(asset: AssetDefinition, stage: GearStageDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Tuple[float, List[str], Dict[str, float]]:
    input_rpm = stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm
    gmf = gear_mesh_frequency_hz(input_rpm, stage)
    freqs, amps = _cached_acceleration_spectrum_arrays(signal)
    if freqs.size == 0 or amps.size == 0:
        return 0.0, [], {}
    acc = _acceleration_pack(signal, feat)
    acc_rms = max(float(acc.get("rms", 0.0)), 1e-12)
    tol = max(feat.tolerance_hz, gmf * 0.03)
    _, gmf_amp = _peak_at(freqs, amps, gmf, tol)
    _, gmf2_amp = _peak_at(freqs, amps, 2.0 * gmf, tol)
    _, left = _peak_at(freqs, amps, gmf - feat.shaft_hz, tol)
    _, right = _peak_at(freqs, amps, gmf + feat.shaft_hz, tol)
    symmetry = _safe_ratio(min(left, right), max(left, right, 1e-12))
    sideband_ratio = _safe_ratio(left + right, max(gmf_amp, 1e-12))
    env_score, env_hits = envelope_harmonic_hit_score(signal, gmf, tol, harmonics=3)
    score = (
        30.0 * _score_linear(_safe_ratio(gmf_amp, acc_rms), 0.6, 3.5) +
        12.0 * _score_linear(_safe_ratio(gmf2_amp, acc_rms), 0.3, 2.0) +
        22.0 * _score_linear(sideband_ratio, 0.2, 1.0) +
        10.0 * _score_linear(symmetry, 0.2, 0.8) +
        16.0 * _score_linear(env_score, 18.0, 75.0) +
        6.0 * _score_linear(acc.get("hf_rms_ratio", 0.0), 0.7, 2.5) +
        4.0 * _score_linear(max(acc.get("kurtosis", 0.0), 0.0), 0.4, 2.5)
    )
    score *= _axis_weight("gear_mesh_fault", sensor, feat.axis) * _component_weight("gear_mesh_fault", sensor)
    evidence = [f"{sensor.sensor_id}/{feat.axis}: GMF={gmf:.1f}Hz, ACC_GMF={_safe_ratio(gmf_amp, acc_rms):.2f}xRMS, SB={sideband_ratio:.2f}, symmetry={symmetry:.2f}, env={env_score:.1f}, hits={env_hits}"]
    metrics = {"gmf_hz": gmf, "sideband_ratio": sideband_ratio, "symmetry": symmetry, "env_score": env_score, "acc_hf_rms_ratio": acc.get("hf_rms_ratio", 0.0)}
    return float(score), evidence, metrics


def _gear_subfault_features(asset: AssetDefinition, stage: GearStageDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Dict[str, float]:
    cache = asset.metadata.setdefault("_gear_subfault_feature_cache", {})
    key = ("accel_domain", stage.gear_stage_id, sensor.sensor_id, feat.axis.lower())
    if key in cache:
        return cache[key]
    freqs, amps = _cached_acceleration_spectrum_arrays(signal)
    acc = _acceleration_pack(signal, feat)
    acc_rms = max(float(acc.get("rms", 0.0)), 1e-12)
    in_hz, out_hz = _stage_shaft_speeds_hz(asset, stage, sensor)
    gmf = gear_mesh_frequency_hz((stage.stage_input_rpm or sensor.local_rpm or asset.running_rpm), stage)
    tol = max(feat.tolerance_hz, gmf * 0.03)
    harm = _mesh_harmonic_pack(freqs, amps, gmf, tol, harmonics=4)
    sb_in_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, in_hz, tol, sidebands=3)
    sb_in_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, in_hz, tol, sidebands=2)
    sb_out_1 = _mesh_sideband_pack(freqs, amps, 1.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_2 = _mesh_sideband_pack(freqs, amps, 2.0 * gmf, out_hz, tol, sidebands=3)
    sb_out_3 = _mesh_sideband_pack(freqs, amps, 3.0 * gmf, out_hz, tol, sidebands=2)
    wave = _mesh_band_waveform_metrics(signal, gmf)
    spacing_owner = "input"
    if max(sb_out_1["mean_pair_ratio"], sb_out_2["mean_pair_ratio"], sb_out_3["mean_pair_ratio"]) > max(sb_in_1["mean_pair_ratio"], sb_in_2["mean_pair_ratio"], sb_in_3["mean_pair_ratio"]):
        spacing_owner = "output"
    gnf_ratio = _gear_mesh_resonance_band_energy(freqs, amps, gmf)
    _, in1_amp = _peak_at(freqs, amps, in_hz, max(feat.tolerance_hz, 0.03 * max(in_hz, 1.0)))
    _, out1_amp = _peak_at(freqs, amps, out_hz, max(feat.tolerance_hz, 0.03 * max(out_hz, 1.0))) if out_hz > 0 else (0.0, 0.0)
    out = {
        "gmf_hz": gmf,
        "gmf1_ratio": _safe_ratio(harm["gmf1"], acc_rms),
        "gmf2_ratio": _safe_ratio(harm["gmf2"], acc_rms),
        "gmf3_ratio": _safe_ratio(harm["gmf3"], acc_rms),
        "gmf23_over_gmf1": harm["gmf23_over_gmf1"],
        "gmf234_over_rms": _safe_ratio(harm["gmf2"] + harm["gmf3"] + harm.get("gmf4", 0.0), acc_rms),
        "gmf123_over_rms": _safe_ratio(harm["gmf1"] + harm["gmf2"] + harm["gmf3"], acc_rms),
        "sb_in_1": sb_in_1["mean_pair_ratio"], "sb_in_2": sb_in_2["mean_pair_ratio"], "sb_in_3": sb_in_3["mean_pair_ratio"],
        "sb_out_1": sb_out_1["mean_pair_ratio"], "sb_out_2": sb_out_2["mean_pair_ratio"], "sb_out_3": sb_out_3["mean_pair_ratio"],
        "sb_in_count": sb_in_1["count"] + sb_in_2["count"] + sb_in_3["count"],
        "sb_out_count": sb_out_1["count"] + sb_out_2["count"] + sb_out_3["count"],
        "sb_in_sym": float(np.mean([sb_in_1["pair_symmetry"], sb_in_2["pair_symmetry"], sb_in_3["pair_symmetry"]])),
        "sb_out_sym": float(np.mean([sb_out_1["pair_symmetry"], sb_out_2["pair_symmetry"], sb_out_3["pair_symmetry"]])),
        "dominant_spacing_owner_input": 1.0 if spacing_owner == "input" else 0.0,
        "dominant_spacing_owner_output": 1.0 if spacing_owner == "output" else 0.0,
        "mesh_resonance_ratio": gnf_ratio,
        "input_1x_ratio": _safe_ratio(in1_amp, acc_rms),
        "output_1x_ratio": _safe_ratio(out1_amp, acc_rms),
        "mesh_band_crest": wave["mesh_band_crest"],
        "mesh_band_kurtosis": wave["mesh_band_kurtosis"],
        "mesh_env_rms": wave["mesh_env_rms"],
        "mesh_env_impact_periodicity": wave["mesh_env_impact_periodicity"],
        "hf_rms_ratio": acc.get("hf_rms_ratio", 0.0),
        "kurtosis": acc.get("kurtosis", 0.0),
        "crest_factor": acc.get("crest_factor", 0.0),
        "axis_radial": 1.0 if feat.axis in {"horizontal", "vertical", "radial"} else 0.0,
        "axis_axial": 1.0 if feat.axis == "axial" else 0.0,
        "spectrum_domain": 1.0,
    }
    cache[key] = out
    return out


def _hydraulic_axis_scores(asset: AssetDefinition, hydraulic: HydraulicElementDefinition, sensor: SensorMeasurement, feat: AxisFeatures, signal: AxisSignal) -> Dict[str, Tuple[float, List[str], Dict[str, float]]]:
    local_rpm = hydraulic.local_rpm or sensor.local_rpm or asset.running_rpm
    pass_hz = hydraulic_pass_frequency_hz(local_rpm, hydraulic)
    freqs, amps = _cached_acceleration_spectrum_arrays(signal)
    if freqs.size == 0 or amps.size == 0:
        return {"pass": (0.0, [], {}), "cavitation": (0.0, [], {})}
    acc = _acceleration_pack(signal, feat)
    acc_rms = max(float(acc.get("rms", 0.0)), 1e-12)
    tol = max(feat.tolerance_hz, pass_hz * 0.03)
    _, pass_amp = _peak_at(freqs, amps, pass_hz, tol)
    _, left = _peak_at(freqs, amps, max(pass_hz - feat.shaft_hz, 0.0), tol)
    _, right = _peak_at(freqs, amps, pass_hz + feat.shaft_hz, tol)
    pass_ratio = _safe_ratio(pass_amp, acc_rms)
    sideband_ratio = _safe_ratio(left + right, max(pass_amp, 1e-12))
    dominant_order_match = 1.0 - min(abs(feat.dominant_order - float(hydraulic.pass_count)) / max(float(hydraulic.pass_count), 1.0), 1.0)
    score_pass = (
        36.0 * _score_linear(pass_ratio, 0.5, 3.0) +
        18.0 * dominant_order_match +
        18.0 * _score_linear(sideband_ratio, 0.10, 0.80) +
        10.0 * _score_linear(acc.get("hf_rms_ratio", 0.0), 0.6, 2.0) +
        10.0 * _score_linear(_temperature_delta_c(asset, sensor), 4.0, 16.0) +
        8.0 * _score_linear(max(acc.get("kurtosis", 0.0), 0.0), 0.4, 2.5)
    )
    cav_score = (
        34.0 * _score_linear(acc.get("hf_rms_ratio", 0.0), 0.6, 2.4) +
        20.0 * _score_linear(max(acc.get("kurtosis", 0.0), 0.0), 0.5, 3.5) +
        16.0 * _score_linear(acc.get("crest_factor", 0.0), 3.5, 7.5) +
        14.0 * _score_linear(_safe_ratio(left + right, max(acc_rms, 1e-12)), 0.2, 1.5) +
        16.0 * _score_linear(_temperature_delta_c(asset, sensor), 4.0, 16.0)
    )
    score_pass *= _axis_weight("hydraulic_vane_or_blade_pass", sensor, feat.axis) * _component_weight("hydraulic_vane_or_blade_pass", sensor)
    cav_score *= _axis_weight("cavitation_or_aeration", sensor, feat.axis) * _component_weight("cavitation_or_aeration", sensor)
    return {
        "pass": (float(score_pass), [f"{sensor.sensor_id}/{feat.axis}: pass={pass_hz:.1f}Hz, ACC_pass={pass_ratio:.2f}xRMS, SB={sideband_ratio:.2f}"], {"pass_hz": pass_hz, "pass_ratio": pass_ratio, "sideband_ratio": sideband_ratio, "acc_hf_rms_ratio": acc.get("hf_rms_ratio", 0.0)}),
        "cavitation": (float(cav_score), [f"{sensor.sensor_id}/{feat.axis}: ACC_HF={acc.get('hf_rms_ratio', 0.0):.2f}, acc_kurtosis={acc.get('kurtosis', 0.0):.2f}, acc_crest={acc.get('crest_factor', 0.0):.2f}"], {"acc_hf_rms_ratio": acc.get("hf_rms_ratio", 0.0), "acc_kurtosis": acc.get("kurtosis", 0.0), "acc_crest_factor": acc.get("crest_factor", 0.0)}),
    }


# Wrap diagnosis entry points so spectra are prepared automatically.
_domain_previous_diagnose_asset = diagnose_asset


def diagnose_asset(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
) -> List[FaultResult]:
    prepare_asset_signal_domains(asset)
    asset.metadata.pop("_scope_sensor_cache", None)
    asset.metadata.pop("_temperature_delta_cache", None)
    asset.metadata.pop("_bearing_characteristic_cache", None)
    asset.metadata.pop("_gear_subfault_feature_cache", None)
    asset.metadata.pop("_hydraulic_axis_score_cache", None)
    asset.metadata.pop("_belt_axis_metrics_cache", None)
    _clear_signal_runtime_caches(asset)
    return _domain_previous_diagnose_asset(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
    )


_domain_previous_diagnose_asset_with_reasoning = diagnose_asset_with_reasoning


def diagnose_asset_with_reasoning(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
    include_debug: bool = False,
) -> Dict[str, Any]:
    report = _domain_previous_diagnose_asset_with_reasoning(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
        include_debug=include_debug,
    )
    report.setdefault("data_quality", {})["spectrum_routing"] = dict(asset.metadata.get("spectrum_routing", {}))
    report.setdefault("llm_ready_payload", {})["spectrum_routing"] = dict(asset.metadata.get("spectrum_routing", {}))
    return report


# ---------------------------------------------------------------------------
# Compact final-output layer
# ---------------------------------------------------------------------------
# Default public output is now a plain text block with:
# - Primary finding
# - Raw score
# - Reasoning-adjusted score
# - Fault confidence
# - Severity
# - Urgency
# - Pattern
# - Pattern confidence
# - One alternative fault: highest reasoning-adjusted alternative
#
# Use output_format="full" only for internal debugging/engineering review.

_compact_previous_diagnose_asset_with_reasoning = diagnose_asset_with_reasoning


def _compact_fault_block(prefix: str, payload: Optional[Mapping[str, Any]]) -> List[str]:
    """Return fixed-format output lines for primary or alternative fault."""
    if not payload:
        return [f"{prefix}: none"]

    fault_key = str(payload.get("fault_key") or payload.get("label") or "unknown")
    raw_score = payload.get("raw_script_score", payload.get("score"))
    adjusted_score = payload.get("reasoning_adjusted_score", raw_score)
    fault_confidence = (payload.get("fault_confidence", {}) or {}).get("level") or payload.get("confidence") or "unknown"
    severity = payload.get("severity_label") or payload.get("fault_severity_label") or "unknown"
    urgency = payload.get("urgency") or "unknown"

    def _fmt_score(value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "unknown"

    return [
        f"{prefix}: {fault_key}",
        f"Raw score: {_fmt_score(raw_score)}",
        f"Reasoning-adjusted score: {_fmt_score(adjusted_score)}",
        f"Fault confidence: {str(fault_confidence).lower()}",
        f"Severity: {str(severity).lower()}",
        f"Urgency: {str(urgency).lower()}",
    ]


def build_compact_diagnostic_output(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a compact dictionary from the full reasoning report."""
    primary = report.get("primary_hypothesis") or None
    alternatives = report.get("alternative_hypotheses") or []
    alternative = alternatives[0] if alternatives else None
    pattern = report.get("pattern") or {}
    pattern_label = pattern.get("label") or pattern.get("family") or "unknown"
    pattern_confidence = ((pattern.get("pattern_confidence", {}) or {}).get("level") or "unknown")

    def _score(payload: Optional[Mapping[str, Any]], key: str) -> Optional[float]:
        if not payload:
            return None
        value = payload.get(key)
        if value is None and key == "raw_script_score":
            value = payload.get("score")
        if value is None and key == "reasoning_adjusted_score":
            value = payload.get("raw_script_score", payload.get("score"))
        try:
            return round(float(value), 2)
        except Exception:
            return None

    def _confidence(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        return str(((payload.get("fault_confidence", {}) or {}).get("level") or payload.get("confidence") or "unknown")).lower()

    def _severity(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        return str(payload.get("severity_label") or payload.get("fault_severity_label") or "unknown").lower()

    def _urgency(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        return str(payload.get("urgency") or "unknown").lower()

    return {
        "primary": None if not primary else str(primary.get("fault_key") or primary.get("label") or "unknown"),
        "primary_raw_score": _score(primary, "raw_script_score"),
        "primary_reasoning_adjusted_score": _score(primary, "reasoning_adjusted_score"),
        "primary_fault_confidence": _confidence(primary),
        "primary_severity": _severity(primary),
        "primary_urgency": _urgency(primary),
        "pattern": str(pattern_label),
        "pattern_confidence": str(pattern_confidence).lower(),
        "alternative": None if not alternative else str(alternative.get("fault_key") or alternative.get("label") or "unknown"),
        "alternative_raw_score": _score(alternative, "raw_script_score"),
        "alternative_reasoning_adjusted_score": _score(alternative, "reasoning_adjusted_score"),
        "alternative_fault_confidence": _confidence(alternative),
        "alternative_severity": _severity(alternative),
        "alternative_urgency": _urgency(alternative),
    }


def format_compact_diagnostic_output(report: Mapping[str, Any]) -> str:
    """Format the final public result exactly as the requested plain-text block."""
    primary = report.get("primary_hypothesis") or None
    alternatives = report.get("alternative_hypotheses") or []
    alternative = alternatives[0] if alternatives else None
    pattern = report.get("pattern") or {}
    pattern_label = pattern.get("label") or pattern.get("family") or "unknown"
    pattern_confidence = ((pattern.get("pattern_confidence", {}) or {}).get("level") or "unknown")

    lines: List[str] = []
    lines.extend(_compact_fault_block("Primary", primary))
    lines.append(f"Pattern: {pattern_label}")
    lines.append(f"Pattern confidence: {str(pattern_confidence).lower()}")
    lines.append("")
    lines.extend(_compact_fault_block("Alternative", alternative))
    return "\n".join(lines)


def diagnose_asset_with_reasoning(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
    include_debug: bool = False,
    output_format: str = "compact_text",
) -> Any:
    """
    Public diagnosis entry point.

    Default output_format="compact_text" returns exactly:
        Primary: <fault>
        Raw score: <score>
        Reasoning-adjusted score: <score>
        Fault confidence: <level>
        Severity: <level>
        Urgency: <level>
        Pattern: <pattern>
        Pattern confidence: <level>

        Alternative: <fault>
        Raw score: <score>
        Reasoning-adjusted score: <score>
        Fault confidence: <level>
        Severity: <level>
        Urgency: <level>

    Set output_format="compact_dict" for a small JSON-friendly dict.
    Set output_format="full" for the previous full engineering/debug report.
    """
    full_report = _compact_previous_diagnose_asset_with_reasoning(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
        include_debug=include_debug,
    )

    normalized_format = str(output_format or "compact_text").lower()
    if normalized_format == "full":
        return full_report
    if normalized_format in {"compact_dict", "dict", "json"}:
        return build_compact_diagnostic_output(full_report)
    return format_compact_diagnostic_output(full_report)


# Convenience alias for callers that still need the complete report explicitly.
diagnose_asset_with_reasoning_full = _compact_previous_diagnose_asset_with_reasoning


# ---------------------------------------------------------------------------
# Dual-domain compact output layer
# ---------------------------------------------------------------------------
# Public output now separates:
#   1) Shaft / Drive-train faults: velocity-spectrum/order based
#   2) Impact / Bearing / Lubrication / Gear faults: acceleration/envelope/HF based
# Each section returns one primary and one alternative in the fixed compact format.

_dual_domain_previous_diagnose_asset_with_reasoning = diagnose_asset_with_reasoning_full

_SHAFT_DRIVETRAIN_FAULT_KEYS = {
    "unbalance",
    "misalignment",
    "looseness_type_a_structural",
    "looseness_type_b_pedestal_support",
    "looseness_type_c_rotating_fit",
    "soft_foot_or_frame_distortion",
    "bent_shaft_or_bow",
    "resonance_or_structural_amplification",
    "motor_electrical_forcing",
    "belt_sheave_eccentricity",
    "belt_sheave_misalignment",
    "belt_slip_or_tension_fault",
    "belt_wear_or_damage",
    "belt_span_resonance",
}

_IMPACT_BEARING_LUBE_GEAR_FAULT_KEYS = {
    "lubrication_distress",
    "bearing_bpfo",
    "bearing_bpfi",
    "bearing_bsf",
    "bearing_ftf",
    "bearing_wear_progression",
    "fluid_film_instability",
    "thrust_bearing_or_axial_overload",
    "gear_mesh_fault",
    "gear_tooth_wear",
    "gear_tooth_damage",
    "gear_eccentricity",
    "gear_backlash",
    "gear_misalignment",
    "hydraulic_vane_or_blade_pass",
    "cavitation_or_aeration",
    "rotor_rub",  # kept here as contact-like only when it survives suppression
}


def _dual_safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _dual_signal_array(values: Optional[List[float]]) -> np.ndarray:
    if values is None:
        return np.asarray([], dtype=float)
    try:
        arr = np.asarray(values, dtype=float)
        return arr[np.isfinite(arr)] if arr.ndim == 1 else np.asarray([], dtype=float)
    except Exception:
        return np.asarray([], dtype=float)


def _dual_band_rms(freqs: np.ndarray, amps: np.ndarray, lo_hz: float, hi_hz: float) -> float:
    if freqs.size == 0 or amps.size == 0 or lo_hz >= hi_hz:
        return 0.0
    n = min(freqs.size, amps.size)
    f = freqs[:n]
    a = amps[:n]
    mask = (f >= lo_hz) & (f <= hi_hz) & np.isfinite(a)
    if not np.any(mask):
        return 0.0
    return float(np.sqrt(np.mean(np.square(np.abs(a[mask])))))


def _dual_peak_freq_in_band(freqs: np.ndarray, amps: np.ndarray, lo_hz: float, hi_hz: float) -> float:
    if freqs.size == 0 or amps.size == 0:
        return 0.0
    n = min(freqs.size, amps.size)
    f = freqs[:n]
    a = np.abs(amps[:n])
    mask = (f >= lo_hz) & (f <= hi_hz) & np.isfinite(a)
    if not np.any(mask):
        return 0.0
    idx_local = int(np.argmax(a[mask]))
    return float(f[mask][idx_local])


def _dual_waveform_metrics(signal: AxisSignal) -> Tuple[float, float]:
    wf = _dual_signal_array(signal.acceleration_waveform or signal.waveform)
    if wf.size < 8:
        return 0.0, 0.0
    wf = wf - np.mean(wf)
    rms = float(np.sqrt(np.mean(wf * wf)))
    if rms <= 1e-12:
        return 0.0, 0.0
    crest = float(np.max(np.abs(wf)) / rms)
    kurt = float(np.mean((wf / rms) ** 4) - 3.0)
    return crest, kurt


def _score_hf_haystack_axis(sensor: SensorMeasurement, signal: AxisSignal) -> Optional[Dict[str, Any]]:
    """Score high-frequency acceleration haystack without needing bearing geometry."""
    freqs = _dual_signal_array(signal.acceleration_freqs_hz or signal.freqs_hz)
    amps = _dual_signal_array(signal.acceleration_spectrum)
    if amps.size == 0:
        # If explicit acceleration spectrum is absent and the legacy spectrum is marked as acceleration, use it.
        if str(getattr(signal, "spectrum_kind", "")).lower() == "acceleration":
            amps = _dual_signal_array(signal.spectrum)
    if freqs.size == 0 or amps.size == 0:
        return None

    n = min(freqs.size, amps.size)
    freqs = freqs[:n]
    amps = np.abs(amps[:n])
    nyquist = float(np.nanmax(freqs)) if freqs.size else 0.0
    if nyquist < 2500.0:
        return None

    # Preferred fixed haystack window for common 12.8 kHz vibration sensors.
    # Fall back to a relative HF window if the Nyquist frequency is lower.
    if nyquist >= 4500.0:
        hf_lo, hf_hi = 3500.0, 4500.0
        ref_lo, ref_hi = 2000.0, 3000.0
    else:
        hf_lo, hf_hi = 0.62 * nyquist, 0.82 * nyquist
        ref_lo, ref_hi = 0.35 * nyquist, 0.52 * nyquist

    hf_rms = _dual_band_rms(freqs, amps, hf_lo, hf_hi)
    ref_rms = _dual_band_rms(freqs, amps, ref_lo, ref_hi)
    total_rms = float(np.sqrt(np.mean(np.square(amps)))) if amps.size else 0.0
    ratio_ref = _safe_ratio(hf_rms, max(ref_rms, 1e-12))
    ratio_total = _safe_ratio(hf_rms, max(total_rms, 1e-12))
    crest, kurt = _dual_waveform_metrics(signal)
    env_rms = float(np.sqrt(np.mean(np.square(_dual_signal_array(signal.envelope_spectrum))))) if signal.envelope_spectrum else 0.0
    peak_hz = _dual_peak_freq_in_band(freqs, amps, hf_lo, hf_hi)

    score = (
        35.0 * _score_linear(ratio_ref, 2.0, 8.0) +
        25.0 * _score_linear(hf_rms, 0.05, 0.40) +
        12.0 * _score_linear(ratio_total, 0.8, 3.0) +
        12.0 * _score_linear(crest, 3.5, 8.0) +
        10.0 * _score_linear(max(kurt, 0.0), 1.0, 7.0) +
        6.0 * _score_linear(env_rms, 0.01, 0.20)
    )

    if score < 18.0:
        return None

    return {
        "axis": signal.axis,
        "score": float(min(score, 100.0)),
        "hf_band_rms": hf_rms,
        "reference_band_rms": ref_rms,
        "hf_to_reference_ratio": ratio_ref,
        "hf_to_total_ratio": ratio_total,
        "crest_factor": crest,
        "kurtosis": kurt,
        "envelope_rms": env_rms,
        "peak_hz": peak_hz,
        "band_lo_hz": hf_lo,
        "band_hi_hz": hf_hi,
    }


def _build_hf_haystack_candidates(asset: AssetDefinition) -> List[Dict[str, Any]]:
    """Build local impact/lubrication candidates from acceleration HF haystack evidence."""
    candidates: List[Dict[str, Any]] = []
    for sensor in asset.sensors:
        axis_scores: List[Dict[str, Any]] = []
        for signal in sensor.directions.values():
            scored = _score_hf_haystack_axis(sensor, signal)
            if scored:
                axis_scores.append(scored)
        if not axis_scores:
            continue
        axis_scores = sorted(axis_scores, key=lambda x: x.get("score", 0.0), reverse=True)
        top_scores = [float(x["score"]) for x in axis_scores[:3]]
        score = float(max(top_scores) * 0.60 + (sum(top_scores) / len(top_scores)) * 0.40)
        if len(axis_scores) >= 2:
            score = min(100.0, score * 1.08)
        confidence_level = "high" if score >= 75.0 else "medium" if score >= 45.0 else "low"
        severity_label = "medium" if score >= 75.0 else "low"
        location = sensor.location_tag or sensor.sensor_id
        best = axis_scores[0]
        evidence = [
            f"{sensor.sensor_id}/{x['axis']}: HF haystack {x['band_lo_hz']:.0f}-{x['band_hi_hz']:.0f} Hz, "
            f"HF_RMS={x['hf_band_rms']:.4g}, HF/ref={x['hf_to_reference_ratio']:.2f}, peak={x['peak_hz']:.1f} Hz"
            for x in axis_scores[:3]
        ]
        candidates.append({
            "fault_key": "lubrication_hf_haystack",
            "label": f"{location} high-frequency haystack / possible lubrication distress",
            "score": round(score, 2),
            "raw_script_score": round(score, 2),
            "reasoning_adjusted_score": round(score * 0.86, 2),
            "confidence": confidence_level,
            "fault_confidence": {
                "score": round(0.78 if confidence_level == "high" else 0.58 if confidence_level == "medium" else 0.36, 3),
                "level": confidence_level,
                "base_script_confidence": confidence_level,
                "limiters": [
                    "bearing fault frequencies were not provided, so this is a lubrication/roughness advisory rather than a specific BPFO/BPFI/BSF/FTF diagnosis",
                    "trend/persistence evidence is required to confirm progression",
                ],
            },
            "severity_label": severity_label,
            "severity_score": round(min(65.0, score * 0.55), 1),
            "urgency": "monitor",
            "segment": "primary" if score >= 45.0 else "low_confidence",
            "scope": "impact_local",
            "target": sensor.sensor_id,
            "pattern_label": f"high-frequency acceleration haystack around {best['peak_hz']:.0f} Hz",
            "pattern_confidence": "high" if score >= 55.0 else "medium",
            "evidence_for": evidence,
            "evidence_against": [
                "Specific bearing defect family cannot be confirmed without bearing geometry or direct bearing fault frequencies."
            ],
            "supporting_metrics": {
                "num_supporting_axes": float(len(axis_scores)),
                "max_hf_band_rms": round(float(best["hf_band_rms"]), 6),
                "max_hf_to_reference_ratio": round(float(best["hf_to_reference_ratio"]), 3),
                "dominant_hf_peak_hz": round(float(best["peak_hz"]), 2),
            },
        })
    return sorted(candidates, key=lambda x: x.get("reasoning_adjusted_score", x.get("score", 0.0)), reverse=True)


def _normalize_fault_payload_from_raw(raw: Mapping[str, Any], report: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a raw FaultResult dict from debug.raw_fault_scores to compact payload format."""
    score = _dual_safe_float(raw.get("score"), 0.0)
    adjusted = _dual_safe_float(raw.get("reasoning_adjusted_score"), score)
    if adjusted == score:
        # Reuse adjustment from the ranked hypotheses if available.
        for hyp in [report.get("primary_hypothesis") or {}, *(report.get("alternative_hypotheses") or [])]:
            if hyp.get("fault_key") == raw.get("fault_key"):
                adjusted = _dual_safe_float(hyp.get("reasoning_adjusted_score"), score)
                break
    conf = str(raw.get("confidence") or "unknown").lower()
    level = "high" if score >= 75.0 else "medium" if score >= 45.0 else conf if conf != "unknown" else "low"
    return {
        "fault_key": raw.get("fault_key") or "unknown",
        "label": raw.get("label") or raw.get("fault_key") or "unknown",
        "score": round(score, 2),
        "raw_script_score": round(score, 2),
        "reasoning_adjusted_score": round(adjusted, 2),
        "confidence": conf,
        "fault_confidence": {"level": level},
        "severity_label": raw.get("severity_label") or raw.get("fault_severity_label") or "unknown",
        "severity_score": raw.get("severity_score") or raw.get("fault_severity_score"),
        "urgency": raw.get("urgency") or "unknown",
        "segment": raw.get("segment") or raw.get("diagnostic_segment") or "unknown",
        "scope": raw.get("scope") or "unknown",
        "target": raw.get("target"),
        "evidence_for": raw.get("evidence") or [],
        "evidence_against": raw.get("limitations") or [],
        "supporting_metrics": raw.get("supporting_metrics") or {},
    }


def _domain_candidates(report: Mapping[str, Any], asset: AssetDefinition, domain: str) -> List[Dict[str, Any]]:
    raw_scores = (((report.get("debug") or {}).get("raw_fault_scores")) or [])
    keys = _SHAFT_DRIVETRAIN_FAULT_KEYS if domain == "shaft" else _IMPACT_BEARING_LUBE_GEAR_FAULT_KEYS
    candidates: List[Dict[str, Any]] = []
    for raw in raw_scores:
        if str(raw.get("fault_key")) in keys:
            candidates.append(_normalize_fault_payload_from_raw(raw, report))
    if domain == "impact":
        # Add high-frequency haystack / lubrication roughness advisory independent of bearing geometry.
        candidates.extend(_build_hf_haystack_candidates(asset))
    # Deduplicate by (fault_key, target), keeping the highest adjusted score.
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for cand in candidates:
        key = (str(cand.get("fault_key")), str(cand.get("target") or cand.get("label") or ""))
        score = _dual_safe_float(cand.get("reasoning_adjusted_score", cand.get("score")), 0.0)
        if key not in best or score > _dual_safe_float(best[key].get("reasoning_adjusted_score", best[key].get("score")), 0.0):
            best[key] = cand
    return sorted(best.values(), key=lambda x: _dual_safe_float(x.get("reasoning_adjusted_score", x.get("score")), 0.0), reverse=True)


def _select_primary_and_alternative(candidates: List[Dict[str, Any]], min_primary: float = 15.0) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    viable = [c for c in candidates if _dual_safe_float(c.get("raw_script_score", c.get("score")), 0.0) >= min_primary]
    if not viable:
        return None, None
    primary = viable[0]
    alternative = viable[1] if len(viable) > 1 else None
    return primary, alternative


def _pattern_for_domain(report: Mapping[str, Any], domain: str, primary: Optional[Mapping[str, Any]]) -> Tuple[str, str]:
    if domain == "impact" and primary and str(primary.get("fault_key")) == "lubrication_hf_haystack":
        return str(primary.get("pattern_label") or "high-frequency acceleration haystack"), str(primary.get("pattern_confidence") or "medium").lower()
    pattern = report.get("pattern") or {}
    label = str(pattern.get("label") or pattern.get("family") or "unknown")
    conf = str(((pattern.get("pattern_confidence", {}) or {}).get("level") or "unknown")).lower()
    return label, conf


def _format_domain_section(title: str, primary: Optional[Mapping[str, Any]], alternative: Optional[Mapping[str, Any]], pattern_label: str, pattern_confidence: str) -> List[str]:
    lines = [f"{title}:"]
    lines.extend(_compact_fault_block("Primary", primary))
    lines.append(f"Pattern: {pattern_label}")
    lines.append(f"Pattern confidence: {str(pattern_confidence).lower()}")
    lines.append("")
    lines.extend(_compact_fault_block("Alternative", alternative))
    return lines


def build_dual_domain_compact_output(report: Mapping[str, Any], asset: AssetDefinition) -> Dict[str, Any]:
    shaft_candidates = _domain_candidates(report, asset, "shaft")
    impact_candidates = _domain_candidates(report, asset, "impact")
    shaft_primary, shaft_alt = _select_primary_and_alternative(shaft_candidates)
    impact_primary, impact_alt = _select_primary_and_alternative(impact_candidates)
    shaft_pattern, shaft_pattern_conf = _pattern_for_domain(report, "shaft", shaft_primary)
    impact_pattern, impact_pattern_conf = _pattern_for_domain(report, "impact", impact_primary)
    return {
        "shaft_drive_train": build_compact_diagnostic_output({
            "primary_hypothesis": shaft_primary,
            "alternative_hypotheses": [shaft_alt] if shaft_alt else [],
            "pattern": {"label": shaft_pattern, "pattern_confidence": {"level": shaft_pattern_conf}},
        }),
        "impact_bearing_lubrication_gear": build_compact_diagnostic_output({
            "primary_hypothesis": impact_primary,
            "alternative_hypotheses": [impact_alt] if impact_alt else [],
            "pattern": {"label": impact_pattern, "pattern_confidence": {"level": impact_pattern_conf}},
        }),
    }


def format_dual_domain_compact_output(report: Mapping[str, Any], asset: AssetDefinition) -> str:
    shaft_candidates = _domain_candidates(report, asset, "shaft")
    impact_candidates = _domain_candidates(report, asset, "impact")
    shaft_primary, shaft_alt = _select_primary_and_alternative(shaft_candidates)
    impact_primary, impact_alt = _select_primary_and_alternative(impact_candidates)
    shaft_pattern, shaft_pattern_conf = _pattern_for_domain(report, "shaft", shaft_primary)
    impact_pattern, impact_pattern_conf = _pattern_for_domain(report, "impact", impact_primary)

    lines: List[str] = []
    lines.extend(_format_domain_section("Shaft / Drive-train", shaft_primary, shaft_alt, shaft_pattern, shaft_pattern_conf))
    lines.append("")
    lines.extend(_format_domain_section("Impact / Bearing / Lubrication / Gear", impact_primary, impact_alt, impact_pattern, impact_pattern_conf))
    return "\n".join(lines)


def diagnose_asset_with_reasoning(
    asset: AssetDefinition,
    minimum_score: float = 15.0,
    condition_scorer: Optional[ConditionHealthScorer] = None,
    compute_condition_summary: bool = False,
    include_debug: bool = False,
    output_format: str = "dual_compact_text",
) -> Any:
    """
    Public diagnosis entry point with separated diagnostic heads.

    Default output_format="dual_compact_text" returns only:
      Shaft / Drive-train: primary + one alternative
      Impact / Bearing / Lubrication / Gear: primary + one alternative

    Use output_format="dual_compact_dict" for a small JSON-friendly object.
    Use output_format="full" for the complete engineering report.
    """
    # Force debug internally so each domain can be ranked from all raw fault scores.
    full_report = _dual_domain_previous_diagnose_asset_with_reasoning(
        asset,
        minimum_score=minimum_score,
        condition_scorer=condition_scorer,
        compute_condition_summary=compute_condition_summary,
        include_debug=True,
    )
    normalized_format = str(output_format or "dual_compact_text").lower()
    if normalized_format == "full":
        if not include_debug:
            full_report = dict(full_report)
            full_report.pop("debug", None)
        return full_report
    if normalized_format in {"dual_compact_dict", "compact_dict", "dict", "json"}:
        return build_dual_domain_compact_output(full_report, asset)
    return format_dual_domain_compact_output(full_report, asset)


# Convenience alias for callers that still need the complete report explicitly.
diagnose_asset_with_reasoning_full = _dual_domain_previous_diagnose_asset_with_reasoning
