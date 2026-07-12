"""Evidence metadata for pure gait-session flags."""


CLINICAL_REFERENCE_RULE = {
    "metric_key": "walking_speed_mps",
    "normal_min": 1.0,
    "severe_max": 0.8,
}

EXPLORATORY_FLAG_RULES = {
    "step_length_asymmetry_pct": {
        "direction": "higher_worse",
        "attention_above": 10.0,
        "message": "步长不对称需关注",
    },
    "stride_time_cv_pct": {
        "direction": "higher_worse",
        "attention_above": 3.0,
        "message": "步态时间变异需关注",
    },
    "double_support_ratio_pct": {
        "direction": "higher_worse",
        "attention_above": 28.0,
        "message": "双支撑比例需关注",
    },
    "cadence_spm": {
        "direction": "outside_band",
        "low": 90.0,
        "high": 130.0,
        "message": "步频需关注",
    },
}
