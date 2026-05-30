"""Простая машина состояний в памяти (по user_id).

Состояние теряется при перезапуске бота — это приемлемо: пользователь
просто начнёт запись заново. Подтверждённые записи хранятся в БД.
"""
from dataclasses import dataclass, field

# Состояния диалога записи.
MAIN = "main"
CHOOSING_SERVICE = "choosing_service"
CHOOSING_MASTER = "choosing_master"
CHOOSING_DATE = "choosing_date"
CHOOSING_TIME = "choosing_time"
ENTERING_NAME = "entering_name"
ENTERING_PHONE = "entering_phone"
CONFIRMING = "confirming"

# Состояния админ-режима.
ADMIN_MENU = "admin_menu"
ADMIN_WAIT_DATE = "admin_wait_date"
ADMIN_WAIT_CANCEL_ID = "admin_wait_cancel_id"


@dataclass
class Session:
    state: str = MAIN
    data: dict = field(default_factory=dict)


_sessions: dict[int, Session] = {}


def get(user_id: int) -> Session:
    if user_id not in _sessions:
        _sessions[user_id] = Session()
    return _sessions[user_id]


def reset(user_id: int) -> None:
    _sessions[user_id] = Session()
