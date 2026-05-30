"""Данные салона: услуги, мастера и часы работы.

Отредактируйте этот файл под свой салон. Длительность услуги (duration_min)
используется для расчёта свободных слотов времени.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    key: str
    title: str
    price: int          # рублей
    duration_min: int   # длительность в минутах


@dataclass(frozen=True)
class Master:
    key: str
    name: str


SERVICES = [
    Service("manicure", "Маникюр классический", 1200, 60),
    Service("gel", "Маникюр + гель-лак", 2000, 90),
    Service("pedicure", "Педикюр", 2200, 90),
    Service("design", "Дизайн ногтей", 800, 30),
    Service("removal", "Снятие покрытия", 500, 30),
]

MASTERS = [
    Master("anna", "Анна"),
    Master("maria", "Мария"),
    Master("olga", "Ольга"),
]

# Часы работы салона.
WORK_START_HOUR = 10   # открытие, 10:00
WORK_END_HOUR = 20     # закрытие, 20:00 (последний приём должен завершиться до этого времени)

# Шаг сетки записи в минутах.
SLOT_STEP_MIN = 30

# На сколько дней вперёд можно записаться.
BOOKING_DAYS_AHEAD = 7


def service_by_key(key: str) -> Service | None:
    return next((s for s in SERVICES if s.key == key), None)


def master_by_key(key: str) -> Master | None:
    return next((m for m in MASTERS if m.key == key), None)
