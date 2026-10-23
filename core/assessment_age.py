"""Age helpers for body assessments."""

from datetime import date


def age_years_at(dob: date, on: date) -> int:
    years = on.year - dob.year
    if (on.month, on.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def approximate_dob_from_age(age_years: int, on: date) -> date:
    """Best-effort DOB when only age is known (preserves month/day of assessment)."""
    target_year = on.year - age_years
    if target_year < 1900:
        target_year = 1900
    try:
        return on.replace(year=target_year)
    except ValueError:
        # Feb 29 → Feb 28 on non-leap birth year
        return date(target_year, on.month, min(on.day, 28))
