import time
from collections import defaultdict
from logger import logger
from config import RATE_LIMIT_MESSAGES_PER_MINUTE

# Хранилище временных меток сообщений на пользователя
_message_timestamps: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(user_id: int, owner_id: int) -> bool:
    """
    Проверяет, превышен ли лимит сообщений для пользователя.
    
    Args:
        user_id: ID отправителя сообщения (собеседник)
        owner_id: ID владельца профиля (тот кто получает сообщение)
    
    Returns:
        True если лимит превышен, False если можно отвечать
    """
    key = f"{owner_id}:{user_id}"  # Уникальный ключ для пары owner-user
    now = time.time()
    cutoff = now - 60  # 60 секунд назад
    
    # Удаляем старые временные метки (старше 1 минуты)
    _message_timestamps[key] = [
        ts for ts in _message_timestamps[key] if ts > cutoff
    ]
    
    # Проверяем лимит
    message_count = len(_message_timestamps[key])
    
    if message_count >= RATE_LIMIT_MESSAGES_PER_MINUTE:
        logger.warning(
            f"[RATE_LIMIT] owner_id={owner_id} chat_id={user_id} "
            f"exceeded limit ({message_count}/{RATE_LIMIT_MESSAGES_PER_MINUTE})"
        )
        return True
    
    # Добавляем текущую временную метку
    _message_timestamps[key].append(now)
    return False


def reset_rate_limit(user_id: int, owner_id: int) -> None:
    """Сбросить лимит для конкретной пары (опционально)."""
    key = f"{owner_id}:{user_id}"
    _message_timestamps[key] = []


def get_rate_limit_remaining(user_id: int, owner_id: int) -> int:
    """Вернуть количество оставшихся сообщений в рамках лимита."""
    key = f"{owner_id}:{user_id}"
    now = time.time()
    cutoff = now - 60
    
    valid_timestamps = [ts for ts in _message_timestamps[key] if ts > cutoff]
    remaining = max(0, RATE_LIMIT_MESSAGES_PER_MINUTE - len(valid_timestamps))
    return remaining
