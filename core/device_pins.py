"""Device PIN helpers for members and trainers."""

TRAINER_PIN_OFFSET = 50_000


def member_pin(member_id: int) -> int:
    return int(member_id)


def trainer_pin(trainer_id: int) -> int:
    return TRAINER_PIN_OFFSET + int(trainer_id)


def resolve_device_pin(pin: int) -> tuple[str, int] | None:
    """
    Map a device PIN to (person_type, person_id).

    Convention (unchanged): trainer PIN = TRAINER_PIN_OFFSET + trainer_id
    (i.e. PIN > 50000 for valid trainers; PIN 50000 is not a valid trainer).

    Returns:
        ("trainer", trainer_id) when pin > TRAINER_PIN_OFFSET (pin >= 50001)
        ("member", member_id) when 0 < pin <= TRAINER_PIN_OFFSET
        None for invalid pins

    Attendance ingest ignores member mappings; only trainers are punched.
    """
    try:
        value = int(pin)
    except (TypeError, ValueError):
        return None

    if value >= TRAINER_PIN_OFFSET:
        trainer_id = value - TRAINER_PIN_OFFSET
        if trainer_id <= 0:
            return None
        return ("trainer", trainer_id)

    if value <= 0:
        return None
    return ("member", value)
