"""Конфигурация бота: читается из переменных окружения (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. "
            f"Скопируйте .env.example в .env и заполните значения."
        )
    return value


# Токен сообщества ВК (Управление → Работа с API → Ключи доступа).
VK_TOKEN = _require("VK_TOKEN")

# ID сообщества (без минуса), например 123456789.
GROUP_ID = int(_require("VK_GROUP_ID"))

# ID администраторов салона через запятую: им приходят уведомления о записях
# и для них доступно меню управления. Пример: VK_ADMIN_IDS=12345,67890
ADMIN_IDS = {
    int(x) for x in os.getenv("VK_ADMIN_IDS", "").replace(" ", "").split(",") if x
}

# Путь к файлу базы данных SQLite.
DB_PATH = os.getenv("DB_PATH", "salon.db")

# Название салона (для приветствий и уведомлений).
SALON_NAME = os.getenv("SALON_NAME", "Маникюрный салон")
