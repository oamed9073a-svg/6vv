"""VK-бот для администратора маникюрного салона: запись клиентов и
управление записями. Использует Bots Long Poll API сообщества."""
import json
import logging
import random
import re
from datetime import datetime

import vk_api
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll

import config
import database as db
import keyboards as kb
import states as st
from salon import (
    BOOKING_DAYS_AHEAD,
    MASTERS,
    SERVICES,
    master_by_key,
    service_by_key,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("salon-bot")

PHONE_RE = re.compile(r"[\d\-\+\(\)\s]{6,}")


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class SalonBot:
    def __init__(self) -> None:
        self.session = vk_api.VkApi(token=config.VK_TOKEN)
        self.vk = self.session.get_api()
        self.longpoll = VkBotLongPoll(self.session, config.GROUP_ID)

    # --- отправка сообщений -------------------------------------------------
    def send(self, user_id: int, message: str, keyboard: str | None = None) -> None:
        params = {
            "user_id": user_id,
            "message": message,
            "random_id": random.randint(1, 2**31),
        }
        if keyboard is not None:
            params["keyboard"] = keyboard
        try:
            self.vk.messages.send(**params)
        except vk_api.exceptions.ApiError as e:
            log.warning("Не удалось отправить сообщение %s: %s", user_id, e)

    def notify_admins(self, text: str) -> None:
        for admin_id in config.ADMIN_IDS:
            self.send(admin_id, text)

    # --- основной цикл ------------------------------------------------------
    def run(self) -> None:
        db.init_db()
        log.info("Бот запущен. Сообщество %s. Админы: %s", config.GROUP_ID, config.ADMIN_IDS)
        for event in self.longpoll.listen():
            if event.type != VkBotEventType.MESSAGE_NEW:
                continue
            try:
                self._on_message(event)
            except Exception:  # noqa: BLE001 — бот не должен падать из-за одного сообщения
                log.exception("Ошибка при обработке сообщения")

    def _on_message(self, event) -> None:
        msg = event.obj.message
        user_id = msg["from_id"]
        if user_id < 0:  # сообщения от сообществ игнорируем
            return
        text = (msg.get("text") or "").strip()
        payload = self._parse_payload(msg.get("payload"))
        cmd = payload.get("cmd")
        value = payload.get("value")

        # Глобальные команды доступны из любого состояния.
        if cmd == "cancel" or text.lower() in {"отмена", "/start", "начать", "меню", "start"}:
            self._show_main_menu(user_id)
            return
        if cmd in {"admin_exit"}:
            self._show_main_menu(user_id)
            return

        if cmd:
            self._dispatch_command(user_id, cmd, value)
        else:
            self._dispatch_text(user_id, text)

    @staticmethod
    def _parse_payload(raw) -> dict:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    # --- роутинг по командам кнопок ----------------------------------------
    def _dispatch_command(self, user_id: int, cmd: str, value) -> None:
        handlers = {
            "menu": lambda: self._show_main_menu(user_id),
            "book": lambda: self._start_booking(user_id),
            "service": lambda: self._on_service(user_id, value),
            "master": lambda: self._on_master(user_id, value),
            "date": lambda: self._on_date(user_id, value),
            "time": lambda: self._on_time(user_id, value),
            "confirm": lambda: self._on_confirm(user_id),
            "my": lambda: self._show_my_bookings(user_id),
            "client_cancel": lambda: self._client_cancel(user_id, value),
            "info": lambda: self._show_info(user_id),
            "admin": lambda: self._enter_admin(user_id),
            "admin_today": lambda: self._admin_today(user_id),
            "admin_date": lambda: self._admin_ask_date(user_id),
            "admin_pick_date": lambda: self._admin_show_date(user_id, value),
            "admin_cancel": lambda: self._admin_ask_cancel(user_id),
        }
        handler = handlers.get(cmd)
        if handler:
            handler()
        else:
            self._show_main_menu(user_id)

    # --- роутинг по тексту (ввод данных) -----------------------------------
    def _dispatch_text(self, user_id: int, text: str) -> None:
        session = st.get(user_id)
        state = session.state
        if state == st.ENTERING_NAME:
            self._on_name(user_id, text)
        elif state == st.ENTERING_PHONE:
            self._on_phone(user_id, text)
        elif state == st.ADMIN_WAIT_DATE:
            self._admin_show_date(user_id, text)
        elif state == st.ADMIN_WAIT_CANCEL_ID:
            self._admin_do_cancel(user_id, text)
        else:
            self._show_main_menu(user_id, greet=True)

    # --- клиентский сценарий ------------------------------------------------
    def _show_main_menu(self, user_id: int, greet: bool = False) -> None:
        st.reset(user_id)
        if greet:
            text = (
                f"Здравствуйте! Это бот записи «{config.SALON_NAME}». "
                f"Выберите действие 👇"
            )
        else:
            text = "Главное меню. Чем могу помочь?"
        self.send(user_id, text, kb.main_menu(is_admin(user_id)))

    def _start_booking(self, user_id: int) -> None:
        session = st.get(user_id)
        session.state = st.CHOOSING_SERVICE
        session.data = {}
        self.send(user_id, "Выберите услугу:", kb.services_menu())

    def _on_service(self, user_id: int, value) -> None:
        service = service_by_key(value or "")
        if not service:
            self.send(user_id, "Пожалуйста, выберите услугу из списка.", kb.services_menu())
            return
        session = st.get(user_id)
        session.data["service_key"] = service.key
        session.state = st.CHOOSING_MASTER
        self.send(
            user_id,
            f"Услуга: {service.title} ({service.price}₽, {service.duration_min} мин).\n"
            f"Выберите мастера:",
            kb.masters_menu(),
        )

    def _on_master(self, user_id: int, value) -> None:
        master = master_by_key(value or "")
        if not master:
            self.send(user_id, "Пожалуйста, выберите мастера из списка.", kb.masters_menu())
            return
        session = st.get(user_id)
        session.data["master_key"] = master.key
        session.state = st.CHOOSING_DATE
        dates = db.upcoming_dates(BOOKING_DAYS_AHEAD)
        self.send(user_id, f"Мастер: {master.name}.\nВыберите дату:", kb.dates_menu(dates))

    def _on_date(self, user_id: int, value) -> None:
        session = st.get(user_id)
        if not self._valid_date(value):
            self.send(user_id, "Пожалуйста, выберите дату из списка.",
                      kb.dates_menu(db.upcoming_dates(BOOKING_DAYS_AHEAD)))
            return
        service = service_by_key(session.data.get("service_key", ""))
        master_key = session.data.get("master_key", "")
        if not service or not master_key:
            self._start_booking(user_id)
            return
        slots = db.available_slots(master_key, value, service.duration_min)
        if not slots:
            self.send(
                user_id,
                "На эту дату свободного времени нет 😔 Выберите другую дату:",
                kb.dates_menu(db.upcoming_dates(BOOKING_DAYS_AHEAD)),
            )
            return
        session.data["date"] = value
        session.state = st.CHOOSING_TIME
        self.send(user_id, "Выберите время:", kb.times_menu(slots))

    def _on_time(self, user_id: int, value) -> None:
        session = st.get(user_id)
        service = service_by_key(session.data.get("service_key", ""))
        master_key = session.data.get("master_key", "")
        date = session.data.get("date", "")
        if not (service and master_key and date):
            self._start_booking(user_id)
            return
        # Повторно проверяем, что слот всё ещё свободен.
        if value not in db.available_slots(master_key, date, service.duration_min):
            slots = db.available_slots(master_key, date, service.duration_min)
            self.send(user_id, "Это время уже заняли. Выберите другое:", kb.times_menu(slots))
            return
        session.data["time"] = value
        session.state = st.ENTERING_NAME
        self.send(user_id, "Как вас зовут? Напишите имя одним сообщением.", kb.cancel_only())

    def _on_name(self, user_id: int, text: str) -> None:
        name = text.strip()
        if not (2 <= len(name) <= 60):
            self.send(user_id, "Введите корректное имя (от 2 до 60 символов).", kb.cancel_only())
            return
        session = st.get(user_id)
        session.data["client_name"] = name
        session.state = st.ENTERING_PHONE
        self.send(user_id, "Укажите номер телефона для связи:", kb.cancel_only())

    def _on_phone(self, user_id: int, text: str) -> None:
        phone = text.strip()
        digits = re.sub(r"\D", "", phone)
        if not (PHONE_RE.fullmatch(phone) and 10 <= len(digits) <= 15):
            self.send(user_id, "Введите корректный номер телефона, например +7 900 123-45-67.",
                      kb.cancel_only())
            return
        session = st.get(user_id)
        session.data["phone"] = phone
        session.state = st.CONFIRMING
        self.send(user_id, self._summary(session.data), kb.confirm_menu())

    def _on_confirm(self, user_id: int) -> None:
        session = st.get(user_id)
        d = session.data
        service = service_by_key(d.get("service_key", ""))
        master = master_by_key(d.get("master_key", ""))
        required = ("service_key", "master_key", "date", "time", "client_name", "phone")
        if not service or not master or not all(d.get(k) for k in required):
            self._show_main_menu(user_id)
            return
        # Финальная проверка занятости слота.
        if d["time"] not in db.available_slots(master.key, d["date"], service.duration_min):
            self.send(user_id, "К сожалению, это время только что заняли. Начнём заново.")
            self._start_booking(user_id)
            return
        booking_id = db.create_booking(
            user_id=user_id,
            client_name=d["client_name"],
            phone=d["phone"],
            service_key=service.key,
            master_key=master.key,
            date=d["date"],
            time=d["time"],
            duration_min=service.duration_min,
        )
        st.reset(user_id)
        self.send(
            user_id,
            f"✅ Запись №{booking_id} подтверждена!\n\n{self._summary(d)}\n\n"
            f"Ждём вас 💅",
            kb.main_menu(is_admin(user_id)),
        )
        self.notify_admins(
            f"🔔 Новая запись №{booking_id}\n"
            f"{d['date']} в {d['time']}\n"
            f"Услуга: {service.title} ({service.price}₽)\n"
            f"Мастер: {master.name}\n"
            f"Клиент: {d['client_name']}, {d['phone']}"
        )

    def _show_my_bookings(self, user_id: int) -> None:
        rows = db.active_bookings_by_user(user_id)
        if not rows:
            self.send(user_id, "У вас пока нет активных записей.", kb.main_menu(is_admin(user_id)))
            return
        lines = ["Ваши записи:\n"]
        buttons = []
        for row in rows:
            lines.append(db.describe_booking(row) + "\n")
            buttons.append([
                {"action": {"type": "text",
                            "label": f"❌ Отменить №{row['id']}",
                            "payload": json.dumps({"cmd": "client_cancel", "value": row["id"]})},
                 "color": "negative"}
            ])
        keyboard = json.dumps({"one_time": False, "inline": True, "buttons": buttons},
                              ensure_ascii=False)
        self.send(user_id, "\n".join(lines), keyboard)

    def _client_cancel(self, user_id: int, value) -> None:
        try:
            booking_id = int(value)
        except (TypeError, ValueError):
            self._show_main_menu(user_id)
            return
        row = db.get_booking(booking_id)
        if not row or row["user_id"] != user_id:
            self.send(user_id, "Запись не найдена.", kb.main_menu(is_admin(user_id)))
            return
        if db.cancel_booking(booking_id):
            self.send(user_id, f"Запись №{booking_id} отменена.", kb.main_menu(is_admin(user_id)))
            self.notify_admins(
                f"⚠️ Клиент отменил запись №{booking_id} "
                f"({row['date']} в {row['time']}, {row['client_name']})."
            )
        else:
            self.send(user_id, "Эту запись уже нельзя отменить.", kb.main_menu(is_admin(user_id)))

    def _show_info(self, user_id: int) -> None:
        lines = [f"💅 {config.SALON_NAME} — услуги и цены:\n"]
        for s in SERVICES:
            lines.append(f"• {s.title} — {s.price}₽ ({s.duration_min} мин)")
        lines.append("\nНаши мастера: " + ", ".join(m.name for m in MASTERS))
        self.send(user_id, "\n".join(lines), kb.main_menu(is_admin(user_id)))

    # --- админ-сценарий -----------------------------------------------------
    def _enter_admin(self, user_id: int) -> None:
        if not is_admin(user_id):
            self._show_main_menu(user_id)
            return
        session = st.get(user_id)
        session.state = st.ADMIN_MENU
        self.send(user_id, "Меню администратора:", kb.admin_menu())

    def _admin_today(self, user_id: int) -> None:
        if not is_admin(user_id):
            return
        today = datetime.now().strftime("%Y-%m-%d")
        self._admin_show_date(user_id, today)

    def _admin_ask_date(self, user_id: int) -> None:
        if not is_admin(user_id):
            return
        session = st.get(user_id)
        session.state = st.ADMIN_WAIT_DATE
        self.send(
            user_id,
            "Выберите дату или пришлите её в формате ГГГГ-ММ-ДД:",
            kb.admin_dates_menu(db.upcoming_dates(BOOKING_DAYS_AHEAD)),
        )

    def _admin_show_date(self, user_id: int, value) -> None:
        if not is_admin(user_id):
            return
        date = (value or "").strip()
        if not self._valid_date(date):
            self.send(user_id, "Некорректная дата. Формат: ГГГГ-ММ-ДД.", kb.admin_menu())
            return
        rows = db.bookings_by_date(date)
        session = st.get(user_id)
        session.state = st.ADMIN_MENU
        if not rows:
            self.send(user_id, f"На {date} записей нет.", kb.admin_menu())
            return
        lines = [f"Записи на {date} ({len(rows)}):\n"]
        for row in rows:
            lines.append(db.describe_booking(row, with_client=True) + "\n")
        self.send(user_id, "\n".join(lines), kb.admin_menu())

    def _admin_ask_cancel(self, user_id: int) -> None:
        if not is_admin(user_id):
            return
        session = st.get(user_id)
        session.state = st.ADMIN_WAIT_CANCEL_ID
        self.send(user_id, "Пришлите номер записи, которую нужно отменить (например, 12):",
                  kb.admin_menu())

    def _admin_do_cancel(self, user_id: int, text: str) -> None:
        if not is_admin(user_id):
            return
        session = st.get(user_id)
        session.state = st.ADMIN_MENU
        digits = re.sub(r"\D", "", text)
        if not digits:
            self.send(user_id, "Нужен числовой номер записи.", kb.admin_menu())
            return
        booking_id = int(digits)
        row = db.get_booking(booking_id)
        if not row:
            self.send(user_id, f"Запись №{booking_id} не найдена.", kb.admin_menu())
            return
        if db.cancel_booking(booking_id):
            self.send(user_id, f"Запись №{booking_id} отменена.", kb.admin_menu())
            self.send(
                row["user_id"],
                f"Здравствуйте! Ваша запись №{booking_id} "
                f"({row['date']} в {row['time']}) отменена администратором. "
                f"Свяжитесь с нами для уточнения деталей.",
            )
        else:
            self.send(user_id, f"Запись №{booking_id} уже была отменена.", kb.admin_menu())

    # --- утилиты ------------------------------------------------------------
    @staticmethod
    def _valid_date(value) -> bool:
        if not value:
            return False
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _summary(data: dict) -> str:
        service = service_by_key(data.get("service_key", ""))
        master = master_by_key(data.get("master_key", ""))
        service_line = (
            f"Услуга: {service.title} ({service.price}₽)" if service else "Услуга: -"
        )
        master_line = f"Мастер: {master.name}" if master else "Мастер: -"
        return "\n".join([
            "Проверьте запись:",
            service_line,
            master_line,
            f"Дата: {data.get('date', '-')}",
            f"Время: {data.get('time', '-')}",
            f"Имя: {data.get('client_name', '-')}",
            f"Телефон: {data.get('phone', '-')}",
        ])


def main() -> None:
    SalonBot().run()


if __name__ == "__main__":
    main()
