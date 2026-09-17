"""
SKYGUARD Deterministic Data Quality & Physical Validation Module

Applies physical limit checks and rate-of-change thresholding on station observations.
Rule: Missing values MUST remain None / null and NEVER be converted to zero.
"""

from typing import Dict, Any, List, Optional
from backend.models import RawObservation


# Physical climatological limits
TEMP_MIN, TEMP_MAX = -50.0, 60.0  # °C
HUMID_MIN, HUMID_MAX = 0.0, 100.0  # %
PRESS_MIN, PRESS_MAX = 800.0, 1100.0  # hPa

# Maximum allowable rate-of-change between consecutive observations
TEMP_STEP_MAX = 10.0  # °C jump
HUMID_STEP_MAX = 35.0  # % jump
PRESS_STEP_MAX = 15.0  # hPa jump


def validate_physical_limits(observation: RawObservation) -> Dict[str, Any]:
    """
    Checks if measurements are within physically plausible climatological bounds.
    Missing values (None) are treated as missing data, not violations.
    """
    flags = {
        "temp_out_of_bounds": False,
        "humid_out_of_bounds": False,
        "press_out_of_bounds": False,
        "is_valid": True,
        "violations": []
    }

    if observation.temperature is not None:
        if not (TEMP_MIN <= observation.temperature <= TEMP_MAX):
            flags["temp_out_of_bounds"] = True
            flags["is_valid"] = False
            flags["violations"].append(f"Temperature {observation.temperature}°C outside bounds [{TEMP_MIN}, {TEMP_MAX}]")

    if observation.humidity is not None:
        if not (HUMID_MIN <= observation.humidity <= HUMID_MAX):
            flags["humid_out_of_bounds"] = True
            flags["is_valid"] = False
            flags["violations"].append(f"Humidity {observation.humidity}% outside bounds [{HUMID_MIN}, {HUMID_MAX}]")

    if observation.pressure is not None:
        if not (PRESS_MIN <= observation.pressure <= PRESS_MAX):
            flags["press_out_of_bounds"] = True
            flags["is_valid"] = False
            flags["violations"].append(f"Pressure {observation.pressure} hPa outside bounds [{PRESS_MIN}, {PRESS_MAX}]")

    return flags


def check_step_change(current: RawObservation, previous: Optional[RawObservation]) -> Dict[str, Any]:
    """
    Checks for impossible instantaneous step jumps compared to the preceding observation.
    """
    flags = {
        "temp_spike": False,
        "humid_spike": False,
        "press_spike": False,
        "violations": []
    }

    if previous is None:
        return flags

    if current.temperature is not None and previous.temperature is not None:
        if abs(current.temperature - previous.temperature) > TEMP_STEP_MAX:
            flags["temp_spike"] = True
            flags["violations"].append(
                f"Temperature step change {abs(current.temperature - previous.temperature):.1f}°C exceeds threshold {TEMP_STEP_MAX}°C"
            )

    if current.humidity is not None and previous.humidity is not None:
        if abs(current.humidity - previous.humidity) > HUMID_STEP_MAX:
            flags["humid_spike"] = True
            flags["violations"].append(
                f"Humidity step change {abs(current.humidity - previous.humidity):.1f}% exceeds threshold {HUMID_STEP_MAX}%"
            )

    if current.pressure is not None and previous.pressure is not None:
        if abs(current.pressure - previous.pressure) > PRESS_STEP_MAX:
            flags["press_spike"] = True
            flags["violations"].append(
                f"Pressure step change {abs(current.pressure - previous.pressure):.1f} hPa exceeds threshold {PRESS_STEP_MAX} hPa"
            )

    return flags
