import calendar
from datetime import date, timedelta

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

MONTHS_NOM = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

SHORT_MONTHS = [
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Единые периоды для главного окна и панели статистики (индексы совпадают).
PERIOD_KEYS = ["day", "week", "month", "year", "all"]
PERIOD_TITLES = ["Сегодня", "Неделя", "Месяц", "Год", "Всё время"]


def week_start(d: date) -> date:
    """Понедельник календарной недели, в которую входит d."""
    return d - timedelta(days=d.weekday())


def month_days(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def label_day(d: date, today: date | None = None) -> str:
    today = today or date.today()
    base = f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]} {d.year}"
    if d == today:
        return f"Сегодня · {base}"
    if d == today - timedelta(days=1):
        return f"Вчера · {base}"
    return base


def label_week(start: date) -> str:
    end = start + timedelta(days=6)
    if start.year != end.year:
        return (
            f"{start.day} {MONTHS_GEN[start.month - 1]} {start.year} — "
            f"{end.day} {MONTHS_GEN[end.month - 1]} {end.year}"
        )
    if start.month != end.month:
        return f"{start.day} {MONTHS_GEN[start.month - 1]} — {end.day} {MONTHS_GEN[end.month - 1]} {end.year}"
    return f"{start.day} — {end.day} {MONTHS_GEN[start.month - 1]} {start.year}"


def label_month(year: int, month: int) -> str:
    return f"{MONTHS_NOM[month - 1]} {year}"


def label_year(year: int) -> str:
    return f"{year} год"


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
