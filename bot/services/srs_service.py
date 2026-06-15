def sm2_update(
    ease_factor: float,
    interval_days: int,
    repetitions: int,
    quality: int,
) -> tuple[float, int, int]:
    """SM-2 spaced repetition algorithm.

    Returns (new_ease_factor, new_interval_days, new_repetitions).
    """
    if quality >= 3:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval_days * ease_factor)
        repetitions += 1
    else:
        repetitions = 0
        interval = 1

    ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return max(ef, 1.3), interval, repetitions
