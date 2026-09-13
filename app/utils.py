from datetime import date

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

SHORT_MONTHS = [
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_seconds(total: float) -> str:
    seconds = int(max(0, total))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин {secs:02d} с"
    return f"{secs} с"


def format_compact(total: float) -> str:
    seconds = int(max(0, total))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}ч {minutes:02d}м"
    if minutes:
        return f"{minutes}м"
    return f"{seconds}с"


def ru_date(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1].capitalize()}"


def ru_date_short(d: date) -> str:
    return f"{d.day} {SHORT_MONTHS[d.month - 1]}"
