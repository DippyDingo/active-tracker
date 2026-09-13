def format_seconds(total: float) -> str:
    seconds = int(max(0, total))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин {secs:02d} с"
    return f"{secs} с"
