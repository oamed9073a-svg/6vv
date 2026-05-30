"""Построение клавиатур ВК (JSON)."""
import json
from datetime import datetime

from salon import MASTERS, SERVICES

WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Текстовые подписи кнопок главного меню (используются и хендлерами).
BTN_BOOK = "📅 Записаться"
BTN_MY = "📋 Мои записи"
BTN_INFO = "ℹ️ Услуги и цены"
BTN_CANCEL = "❌ Отмена"
BTN_BACK = "⬅️ Назад"
BTN_ADMIN = "🔧 Администрирование"

# Админ-меню.
BTN_ADMIN_TODAY = "📆 Записи на сегодня"
BTN_ADMIN_DATE = "🗓 Записи по дате"
BTN_ADMIN_CANCEL = "🗑 Отменить запись"
BTN_ADMIN_EXIT = "⬅️ Выйти из админки"


def _button(label: str, color: str = "secondary", payload: dict | None = None) -> dict:
    action = {"type": "text", "label": label}
    if payload is not None:
        action["payload"] = json.dumps(payload, ensure_ascii=False)
    return {"action": action, "color": color}


def _keyboard(rows: list[list[dict]], one_time: bool = False, inline: bool = False) -> str:
    return json.dumps(
        {"one_time": one_time, "inline": inline, "buttons": rows},
        ensure_ascii=False,
    )


def main_menu(is_admin: bool = False) -> str:
    rows = [
        [_button(BTN_BOOK, "primary", {"cmd": "book"})],
        [
            _button(BTN_MY, "secondary", {"cmd": "my"}),
            _button(BTN_INFO, "secondary", {"cmd": "info"}),
        ],
    ]
    if is_admin:
        rows.append([_button(BTN_ADMIN, "positive", {"cmd": "admin"})])
    return _keyboard(rows)


def services_menu() -> str:
    rows = [
        [_button(f"{s.title} — {s.price}₽", "secondary", {"cmd": "service", "value": s.key})]
        for s in SERVICES
    ]
    rows.append([_button(BTN_CANCEL, "negative", {"cmd": "cancel"})])
    return _keyboard(rows, one_time=True)


def masters_menu() -> str:
    rows = [
        [_button(m.name, "secondary", {"cmd": "master", "value": m.key})]
        for m in MASTERS
    ]
    rows.append([_button(BTN_BACK, "secondary", {"cmd": "book"})])
    rows.append([_button(BTN_CANCEL, "negative", {"cmd": "cancel"})])
    return _keyboard(rows, one_time=True)


def _date_label(date: str) -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    return f"{WEEKDAYS_RU[d.weekday()]} {d.strftime('%d.%m')}"


def dates_menu(dates: list[str]) -> str:
    rows = []
    row: list[dict] = []
    for date in dates:
        row.append(_button(_date_label(date), "secondary", {"cmd": "date", "value": date}))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_button(BTN_CANCEL, "negative", {"cmd": "cancel"})])
    return _keyboard(rows, one_time=True)


def times_menu(slots: list[str]) -> str:
    rows = []
    row: list[dict] = []
    for slot in slots:
        row.append(_button(slot, "secondary", {"cmd": "time", "value": slot}))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_button(BTN_CANCEL, "negative", {"cmd": "cancel"})])
    return _keyboard(rows, one_time=True)


def confirm_menu() -> str:
    rows = [
        [_button("✅ Подтвердить", "positive", {"cmd": "confirm"})],
        [_button(BTN_CANCEL, "negative", {"cmd": "cancel"})],
    ]
    return _keyboard(rows, one_time=True)


def cancel_only() -> str:
    return _keyboard([[_button(BTN_CANCEL, "negative", {"cmd": "cancel"})]], one_time=True)


def admin_menu() -> str:
    rows = [
        [_button(BTN_ADMIN_TODAY, "primary", {"cmd": "admin_today"})],
        [_button(BTN_ADMIN_DATE, "secondary", {"cmd": "admin_date"})],
        [_button(BTN_ADMIN_CANCEL, "negative", {"cmd": "admin_cancel"})],
        [_button(BTN_ADMIN_EXIT, "secondary", {"cmd": "admin_exit"})],
    ]
    return _keyboard(rows)


def admin_dates_menu(dates: list[str]) -> str:
    rows = []
    row: list[dict] = []
    for date in dates:
        row.append(_button(_date_label(date), "secondary", {"cmd": "admin_pick_date", "value": date}))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_button(BTN_ADMIN_EXIT, "secondary", {"cmd": "admin_exit"})])
    return _keyboard(rows, one_time=True)
