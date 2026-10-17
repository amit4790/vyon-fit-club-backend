"""Canonical body assessment metric keys and units."""

from __future__ import annotations

METRIC_WEIGHT_KG = "weight_kg"
METRIC_HEIGHT_CM = "height_cm"
METRIC_BMI = "bmi"
METRIC_BODY_FAT_PCT = "body_fat_pct"
METRIC_MUSCLE_MASS_KG = "muscle_mass_kg"
METRIC_BMR_KCAL = "bmr_kcal"
METRIC_WAIST_CM = "waist_cm"
METRIC_CHEST_CM = "chest_cm"
METRIC_UPPER_CHEST_CM = "upper_chest_cm"
METRIC_SHOULDERS_CM = "shoulders_cm"
METRIC_NECK_CM = "neck_cm"
METRIC_ABDOMEN_CM = "abdomen_cm"
METRIC_HIPS_CM = "hips_cm"
METRIC_UPPER_ARM_LEFT_CM = "upper_arm_left_cm"
METRIC_UPPER_ARM_RIGHT_CM = "upper_arm_right_cm"
METRIC_FOREARM_LEFT_CM = "forearm_left_cm"
METRIC_FOREARM_RIGHT_CM = "forearm_right_cm"
METRIC_THIGH_LEFT_CM = "thigh_left_cm"
METRIC_THIGH_RIGHT_CM = "thigh_right_cm"
METRIC_CALF_LEFT_CM = "calf_left_cm"
METRIC_CALF_RIGHT_CM = "calf_right_cm"

METRIC_UNITS: dict[str, str] = {
    METRIC_WEIGHT_KG: "kg",
    METRIC_HEIGHT_CM: "cm",
    METRIC_BMI: "kg/m2",
    METRIC_BODY_FAT_PCT: "%",
    METRIC_MUSCLE_MASS_KG: "kg",
    METRIC_BMR_KCAL: "kcal",
    METRIC_WAIST_CM: "cm",
    METRIC_CHEST_CM: "cm",
    METRIC_UPPER_CHEST_CM: "cm",
    METRIC_SHOULDERS_CM: "cm",
    METRIC_NECK_CM: "cm",
    METRIC_ABDOMEN_CM: "cm",
    METRIC_HIPS_CM: "cm",
    METRIC_UPPER_ARM_LEFT_CM: "cm",
    METRIC_UPPER_ARM_RIGHT_CM: "cm",
    METRIC_FOREARM_LEFT_CM: "cm",
    METRIC_FOREARM_RIGHT_CM: "cm",
    METRIC_THIGH_LEFT_CM: "cm",
    METRIC_THIGH_RIGHT_CM: "cm",
    METRIC_CALF_LEFT_CM: "cm",
    METRIC_CALF_RIGHT_CM: "cm",
}

PROGRESS_SUMMARY_METRICS = (
    METRIC_WEIGHT_KG,
    METRIC_BODY_FAT_PCT,
    METRIC_MUSCLE_MASS_KG,
    METRIC_WAIST_CM,
)

METRIC_SOURCE_MACHINE = "machine"
METRIC_SOURCE_MANUAL = "manual"
METRIC_SOURCE_CALCULATED = "calculated"


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if weight_kg is None or height_cm is None or height_cm <= 0:
        return None
    height_m = height_cm / 100.0
    return round(weight_kg / (height_m * height_m), 1)
