from datetime import date

import pytest
from pydantic import ValidationError

from core.assessment_age import age_years_at, approximate_dob_from_age
from schemas.medical_questionnaire import MedicalQuestionnaire


def test_age_years_at_birthday_not_yet():
    assert age_years_at(date(2000, 12, 31), date(2026, 1, 1)) == 25


def test_approximate_dob_from_age():
    assert approximate_dob_from_age(30, date(2026, 3, 15)) == date(1996, 3, 15)


def test_questionnaire_requires_declaration():
    with pytest.raises(ValidationError):
        MedicalQuestionnaire(
            medical_conditions=["none"],
            injury_pain=["no"],
            medication_surgery="no",
            exercise_chest_pain="no",
            exercise_doctor_restrict="no",
            fitness_goals=["general_fitness"],
            declaration_accepted=False,
        )


def test_questionnaire_none_exclusive():
    with pytest.raises(ValidationError):
        MedicalQuestionnaire(
            medical_conditions=["none", "diabetes"],
            injury_pain=["no"],
            medication_surgery="no",
            exercise_chest_pain="no",
            exercise_doctor_restrict="no",
            fitness_goals=["general_fitness"],
            declaration_accepted=True,
        )
