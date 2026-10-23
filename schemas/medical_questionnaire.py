"""Structured medical & fitness questionnaire on body assessments."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MedicalConditionKey = Literal[
    "none",
    "high_bp",
    "diabetes",
    "heart",
    "asthma",
    "thyroid",
    "other",
]

InjuryPainKey = Literal["no", "back_neck", "knee", "shoulder", "other"]

FitnessGoalKey = Literal[
    "weight_loss",
    "fat_loss",
    "muscle_gain",
    "strength",
    "general_fitness",
    "sports_performance",
]

WorkoutFrequencyKey = Literal["2_3", "4_5", "6"]
YesNoKey = Literal["no", "yes"]
PriorGymKey = Literal["no", "yes"]

FITNESS_GOAL_DISPLAY: dict[str, str] = {
    "weight_loss": "Weight loss",
    "fat_loss": "Fat loss",
    "muscle_gain": "Muscle gain",
    "strength": "Strength",
    "general_fitness": "General fitness",
    "sports_performance": "Sports performance",
}


class MedicalQuestionnaire(BaseModel):
    """Snapshot of client medical & fitness intake at time of assessment."""

    age_years: int | None = Field(None, ge=1, le=120)
    medical_conditions: list[MedicalConditionKey] = Field(default_factory=list)
    medical_conditions_other: str | None = Field(None, max_length=500)
    injury_pain: list[InjuryPainKey] = Field(default_factory=list)
    injury_pain_other: str | None = Field(None, max_length=500)
    medication_surgery: YesNoKey | None = None
    medication_surgery_details: str | None = Field(None, max_length=2000)
    exercise_chest_pain: YesNoKey | None = None
    exercise_doctor_restrict: YesNoKey | None = None
    fitness_goals: list[FitnessGoalKey] = Field(default_factory=list)
    prior_gym: PriorGymKey | None = None
    workout_frequency: WorkoutFrequencyKey | None = None
    other_important_info: str | None = Field(None, max_length=4000)
    declaration_accepted: bool = False
    client_signature: str | None = Field(None, max_length=200)

    @field_validator("medical_conditions")
    @classmethod
    def unique_conditions(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for v in values:
            if v not in seen:
                seen.append(v)
        return seen

    @field_validator("injury_pain")
    @classmethod
    def unique_injury(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for v in values:
            if v not in seen:
                seen.append(v)
        return seen

    @field_validator("fitness_goals")
    @classmethod
    def unique_goals(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for v in values:
            if v not in seen:
                seen.append(v)
        return seen

    @model_validator(mode="after")
    def validate_groups(self) -> "MedicalQuestionnaire":
        if "none" in self.medical_conditions and len(self.medical_conditions) > 1:
            raise ValueError("medical_conditions cannot include 'none' with other options")
        if "no" in self.injury_pain and len(self.injury_pain) > 1:
            raise ValueError("injury_pain cannot include 'no' with other options")
        if "other" in self.medical_conditions and not (self.medical_conditions_other or "").strip():
            raise ValueError("medical_conditions_other is required when 'other' is selected")
        if "other" in self.injury_pain and not (self.injury_pain_other or "").strip():
            raise ValueError("injury_pain_other is required when 'other' is selected")
        if self.medication_surgery == "yes" and not (self.medication_surgery_details or "").strip():
            raise ValueError("medication_surgery_details is required when medication/surgery is yes")
        if not self.declaration_accepted:
            raise ValueError("declaration_accepted must be true")
        return self
