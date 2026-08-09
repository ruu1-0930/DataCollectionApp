"""Pure full-session plantar-pressure aggregation."""

import math


SENSOR_KEYS = tuple(f"p{index}" for index in range(1, 10))
MIN_VALID_SAMPLES = 3
MIN_MATCHED_SENSORS = 6
THRESHOLD_PROFILE = "pressure_asymmetry_research_v1"


def _eligible(value):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
    ):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _positive_mean(values):
    try:
        direct_mean = math.fsum(values) / len(values)
    except OverflowError:
        direct_mean = None
    if direct_mean is not None and math.isfinite(direct_mean):
        return direct_mean

    scale = max(values)
    normalized_mean = math.fsum(value / scale for value in values) / len(values)
    return scale * normalized_mean


def _positive_pair_metrics(left, right):
    direct_total = left + right
    if math.isfinite(direct_total):
        left_share = left / direct_total * 100
        return {
            "left_share_pct": left_share,
            "right_share_pct": 100 - left_share,
            "asymmetry_pct": abs(left - right) / (direct_total / 2) * 100,
        }

    scale = max(left, right)
    left_scaled = left / scale
    right_scaled = right / scale
    scaled_total = left_scaled + right_scaled
    left_share = left_scaled / scaled_total * 100
    return {
        "left_share_pct": left_share,
        "right_share_pct": 100 - left_share,
        "asymmetry_pct": abs(left_scaled - right_scaled)
        / (scaled_total / 2)
        * 100,
    }


def _representable_positive_sum(values):
    try:
        total = math.fsum(values)
    except OverflowError:
        return None
    return total if math.isfinite(total) else None


def pressure_attention_level(asymmetry_pct):
    if asymmetry_pct >= 30:
        return "high"
    if asymmetry_pct >= 20:
        return "moderate"
    if asymmetry_pct >= 10:
        return "mild"
    return "normal"


def _side_summary(frames, foot):
    rows = [frame[foot] for frame in frames if frame.get(foot) is not None]
    sensors = {}
    for sensor in SENSOR_KEYS:
        values = [row.get(sensor) for row in rows if _eligible(row.get(sensor))]
        sensors[sensor] = {
            "mean_adc": _positive_mean(values) if values else None,
            "valid_samples": len(values),
            "total_samples": len(rows),
        }
    return {"sensors": sensors}


def _matched_sensor_summary(left, right):
    sensors = {}
    for sensor in SENSOR_KEYS:
        left_stats = left["sensors"][sensor]
        right_stats = right["sensors"][sensor]
        if (
            left_stats["mean_adc"] is None
            or right_stats["mean_adc"] is None
            or left_stats["valid_samples"] < MIN_VALID_SAMPLES
            or right_stats["valid_samples"] < MIN_VALID_SAMPLES
        ):
            continue

        left_mean = left_stats["mean_adc"]
        right_mean = right_stats["mean_adc"]
        difference = left_mean - right_mean
        asymmetry = _positive_pair_metrics(left_mean, right_mean)["asymmetry_pct"]
        sensors[sensor] = {
            "difference_adc": difference,
            "asymmetry_pct": asymmetry,
            "higher_side": "left" if difference > 0 else "right" if difference < 0 else None,
        }
    return sensors


def _bilateral_summary(left, right):
    sensors = _matched_sensor_summary(left, right)
    if not sensors:
        return {
            "matched_sensor_count": 0,
            "left_load_proxy_adc": None,
            "right_load_proxy_adc": None,
            "left_load_share_pct": None,
            "right_load_share_pct": None,
            "load_asymmetry_pct": None,
            "sensors": {},
        }

    matched = tuple(sensors)
    left_proxy = _representable_positive_sum(
        left["sensors"][sensor]["mean_adc"] for sensor in matched
    )
    right_proxy = _representable_positive_sum(
        right["sensors"][sensor]["mean_adc"] for sensor in matched
    )
    if left_proxy is None or right_proxy is None:
        return {
            "matched_sensor_count": len(matched),
            "left_load_proxy_adc": None,
            "right_load_proxy_adc": None,
            "left_load_share_pct": None,
            "right_load_share_pct": None,
            "load_asymmetry_pct": None,
            "sensors": sensors,
        }

    load_metrics = _positive_pair_metrics(left_proxy, right_proxy)
    return {
        "matched_sensor_count": len(matched),
        "left_load_proxy_adc": left_proxy,
        "right_load_proxy_adc": right_proxy,
        "left_load_share_pct": load_metrics["left_share_pct"],
        "right_load_share_pct": load_metrics["right_share_pct"],
        "load_asymmetry_pct": load_metrics["asymmetry_pct"],
        "sensors": sensors,
    }


def _attention_summary(bilateral, both_feet_present):
    matched_count = bilateral["matched_sensor_count"]
    load_aggregates_available = bilateral["left_load_proxy_adc"] is not None
    if not both_feet_present or matched_count == 0 or not load_aggregates_available:
        quality = "insufficient"
    elif matched_count < MIN_MATCHED_SENSORS:
        quality = "partial"
    else:
        quality = "usable"

    if quality == "insufficient":
        return {
            "level": None,
            "quality": "insufficient",
            "reason_codes": ["insufficient_pressure_data"],
        }

    reasons = []
    left_proxy = bilateral["left_load_proxy_adc"]
    right_proxy = bilateral["right_load_proxy_adc"]
    if left_proxy is not None and left_proxy > right_proxy:
        reasons.append("left_load_higher")
    elif right_proxy is not None and right_proxy > left_proxy:
        reasons.append("right_load_higher")

    sensor_asymmetries = [
        sensor["asymmetry_pct"] for sensor in bilateral["sensors"].values()
    ]
    if any(asymmetry >= 10 for asymmetry in sensor_asymmetries):
        reasons.append("sensor_asymmetry")

    if quality == "partial":
        reasons.append("partial_sensor_coverage")

    level = None
    if quality == "usable":
        maximum_asymmetry = max(
            [bilateral["load_asymmetry_pct"], *sensor_asymmetries]
        )
        level = pressure_attention_level(maximum_asymmetry)

    return {"level": level, "quality": quality, "reason_codes": reasons}


def summarize_pressure(frames):
    """Summarize nonzero pressure means and matched bilateral asymmetry."""
    frames = list(frames)
    left = _side_summary(frames, "L")
    right = _side_summary(frames, "R")
    bilateral = _bilateral_summary(left, right)
    both_feet_present = any(frame.get("L") is not None for frame in frames) and any(
        frame.get("R") is not None for frame in frames
    )
    return {
        "method": "nonzero_mean_v1",
        "unit": "ADC",
        "threshold_profile": THRESHOLD_PROFILE,
        "left": left,
        "right": right,
        "bilateral": bilateral,
        "attention": _attention_summary(bilateral, both_feet_present),
    }
