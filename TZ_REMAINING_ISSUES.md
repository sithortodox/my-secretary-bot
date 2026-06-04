# 🔧 Техническое задание: Исправление оставшихся проблем безопасности

**Дата создания:** 2026-06-04  
**Статус:** 🔴 **В ОЧЕРЕДИ**  
**Приоритет:** КРИТИЧЕСКИЙ + ВЫСОКИЙ  

---

## 📋 Обзор

На основе анализа обновлённого кода выявлены **5 оставшихся проблем**, которые препятствуют полноценной безопасности и надежности системы. Большинство критических ошибок (валидация env, .gitignore, таймауты) уже исправлены. Остаются **2 критические** и **3 высокие** проблемы.

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (Исправить СРОЧНО)

### ✅ Issue #1: BOT_TOKEN раскрывается в коде (`handlers/business.py:541-542`)

**Описание:**
Токен Telegram-бота вставляется в строку для формирования URL. При ошибке или исключении токен может попасть в логи или stack trace.

**Текущий код:**
```python
# handlers/business.py:541-542
from config import BOT_TOKEN
image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
```

**Проблемы:**
- ❌ Токен вставляется в строку явно
- ❌ При исключении в stack trace может быть виден полный URL с токеном
- ❌ `image_url` передаётся в `ask_llm_vision()` - может быть залогирована

**Решение:**
Использовать встроенный метод aiogram для безопасной загрузки файлов вместо ручного конструирования URL.

**Код исправления:**
```python
# ✅ ВАРИАНТ 1: Использовать bot.download_file()
if media_type == "photo" and message.photo:
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        
        # Скачиваем файл в память вместо использования URL с токеном
        file_bytes = await bot.download(file)
        
        # Конвертируем в base64 для vision API
        import base64
        image_base64 = base64.b64encode(file_bytes).decode('utf-8')
        image_url = f"data:image/jpeg;base64,{image_base64}"
        
        # Используем base64 URL вместо прямого токена
        image_description = await ask_llm_vision(
            vision_prompt, image_url, ..., active_model=active_model
        )
```

или

```python
# ✅ ВАРИАНТ 2: Использовать file_path напрямую без URL конструирования
if media_type == "photo" and message.photo:
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        
        # Пусть vision API работает с file_path через Telegram API
        # Но НЕ встраиваем токен в строку
        image_url = f"https://api.telegram.org/file/bot{await _get_bot_token_safely()}/{file.file_path}"
        
        # ИЛИ используем прокси для скрытия токена
```

**Рекомендуемый подход:** **ВАРИАНТ 1** (base64 encoding) — безопаснее, токен никогда не видна в строках.

**Файлы для изменения:**
- `handlers/business.py` (строки 537-566)
- Возможно, `services/llm.py` (функция `ask_llm_vision()`)

**Критерии приёмки:**
- [ ] Токен BOT_TOKEN не появляется в строках URL
- [ ] Файлы загружаются и обрабатываются корректно
- [ ] Нет утечек токена в логах при ошибках
- [ ] Vision API продолжает работать как раньше

**Тестирование:**
```bash
# Отправить фото в бот и проверить:
1. Фото обрабатывается корректно
2. В логах (bot.log) нет URL с токеном
3. Stack trace при ошибке не содержит токен
```

---

### ✅ Issue #2: Rate limiting НЕ реализован

**Описание:**
Переменная `RATE_LIMIT_MESSAGES_PER_MINUTE` добавлена в `config.py`, но не используется нигде в коде. Нет механизма ограничения количества сообщений на пользователя.

**Текущий статус:**
```python
# config.py:41
RATE_LIMIT_MESSAGES_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_MESSAGES_PER_MINUTE", "20"))

# handlers/business.py — переменная НЕ используется ❌
```

**Проблемы:**
- ❌ Нет проверки количества сообщений от одного пользователя
- ❌ Каждое сообщение безусловно вызывает LLM API
- ❌ Риск неограниченных расходов при DDoS/spam
- ❌ Нет защиты от боевых атак

**Решение:**
Реализовать per-user rate limiting с кольцевым буфером временных меток.

**Файл для создания:** `services/rate_limiter.py`

**Код:**
```python
# services/rate_limiter.py

import time
from collections import defaultdict
from logger import logger
from config import RATE_LIMIT_MESSAGES_PER_MINUTE

# Хранилище временных меток сообщений на пользователя
_message_timestamps: dict[int, list[float]] = defaultdict(list)


def is_rate_limited(user_id: int, owner_id: int) -> bool:
    """
    Проверяет, превышен ли лимит сообщений для пользователя.
    
    Args:
        user_id: ID тучателя сообщения (собеседник)
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
```

**Интеграция в `handlers/business.py`:**

```python
# handlers/business.py (в функции handle_business_message)

from services.rate_limiter import is_rate_limited
from config import RATE_LIMIT_MESSAGES_PER_MINUTE

# ... существующий код ...

@router.business_message()
async def handle_business_message(message: Message, bot: Bot):
    owner_id = await _get_owner_id(message, bot)
    if not owner_id:
        logger.warning(f"[MSG] Could not get owner_id...")
        return
    
    # Проверка rate limit (ПОСЛЕ получения owner_id)
    if is_rate_limited(message.from_user.id, owner_id):
        logger.info(f"[RATE_LIMIT] Message from {message.from_user.id} blocked (limit exceeded)")
        # Опционально: отправить уведомление владельцу об одноразовой блокировке
        try:
            remaining = get_rate_limit_remaining(message.from_user.id, owner_id)
            await bot.send_message(
                chat_id=owner_id,
                text=f"⚠️ Получено слишком много сообщений от одного контакта. "
                     f"Бот пропустит это сообщение. Осталось: {remaining} в минуту."
            )
        except:
            pass
        return  # Пропускаем обработку
    
    # Дальше существующий код...
```

**Переменные окружения (`.env.example`):**
```env
# Rate limiting
RATE_LIMIT_MESSAGES_PER_MINUTE=20  # Максимум 20 сообщений в минуту на контакт
```

**Файлы для изменения:**
- `services/rate_limiter.py` (создать новый)
- `handlers/business.py` (добавить проверку)
- `.env.example` (добавить переменную)
- `requirements.txt` (нет новых зависимостей)

**Критерии приёмки:**
- [ ] Функция `is_rate_limited()` работает корректно
- [ ] После 20 сообщений в минуту дальнейшие пропускаются
- [ ] Лимит сбрасывается каждую минуту
- [ ] Логируется факт превышения лимита
- [ ] Тесты показывают корректное поведение

**Тестирование:**
```bash
# В .env установить RATE_LIMIT_MESSAGES_PER_MINUTE=3 для тестирования
# Отправить 4 сообщения подряд
# Проверить что 4-е сообщение не обработано
# Проверить логи
```

---

## 🟠 ВЫСОКИЕ ПРОБЛЕМЫ (Важно исправить)

### ✅ Issue #3: Async задачи паузы НЕ отслеживаются

**Описание:**
В функции `on_escalation_pause()` создаётся фоновая задача `_unpause()` без отслеживания. Если функция вызывается много раз, может накопиться много задач в памяти.

**Текущий код:**
```python
# handlers/business.py:750-776
async def on_escalation_pause(callback, bot: Bot) -> None:
    """Обработчик кнопки 'Пауза' — ставит чат на паузу."""
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    owner_id = callback.from_user.id

    await set_escalated(owner_id, chat_id, True)
    
    # ... сообщение ...
    
    async def _unpause():
        await asyncio.sleep(1800)  # 30 минут
        await set_escalated(owner_id, chat_id, False)
        # ...

    asyncio.create_task(_unpause())  # ❌ Задача создаётся без отслеживания
```

**Проблемы:**
- ❌ Если нажать паузу несколько раз для одного чата, накопятся задачи
- ❌ Нет механизма отмены старой паузы
- ❌ Утечка памяти при частых нажатиях паузы
- ❌ Возможны race conditions

**Решение:**
Использовать словарь для отслеживания активных паузы и отменять старые перед созданием новых.

**Код исправления:**

```python
# В начале handlers/business.py добавить:
_pause_tasks: dict[tuple[int, int], asyncio.Task] = {}  # (owner_id, chat_id) -> Task


async def on_escalation_pause(callback, bot: Bot) -> None:
    """Обработчик кнопки 'Пауза' — ставит чат на паузу."""
    from services.utils import safe_split_callback, safe_int
    
    parts = safe_split_callback(callback.data, min_parts=3)
    if not parts:
        await callback.answer("❌ Invalid callback data", show_alert=True)
        return
    
    chat_id = safe_int(parts[2], "chat_id")
    if chat_id is None:
        await callback.answer("❌ Invalid chat ID", show_alert=True)
        return
    
    owner_id = callback.from_user.id
    pause_key = (owner_id, chat_id)

    # Отменяем старую задачу паузы если существует
    if pause_key in _pause_tasks:
        old_task = _pause_tasks[pause_key]
        if not old_task.done():
            old_task.cancel()
            logger.info(f"[ESCALATION] Cancelled old pause task for {pause_key}")

    await set_escalated(owner_id, chat_id, True)
    await callback.answer(
        "⏸ Чат на паузе 30 минут. Бот не отвечает.",
        show_alert=True,
    )
    logger.info(f"[ESCALATION] owner_id={owner_id} chat_id={chat_id} paused 30min")

    # Автоматическое снятие паузы через 30 минут
    async def _unpause():
        try:
            await asyncio.sleep(1800)  # 30 минут
            await set_escalated(owner_id, chat_id, False)
            logger.info(f"[ESCALATION] owner_id={owner_id} chat_id={chat_id} auto-unpaused")
            try:
                await bot.send_message(
                    owner_id,
                    f"✅ Пауза для чата {chat_id} окончена. Бот снова отвечает."
                )
            except Exception:
                pass
        except asyncio.CancelledError:
            logger.debug(f"[ESCALATION] Pause task cancelled for {pause_key}")
        finally:
            # Удаляем задачу из словаря
            _pause_tasks.pop(pause_key, None)

    # Создаём и отслеживаем задачу
    task = asyncio.create_task(_unpause())
    _pause_tasks[pause_key] = task
```

**Файлы для изменения:**
- `handlers/business.py` (функция `on_escalation_pause()`, добавить глобальный словарь)

**Критерии приёмки:**
- [ ] Словарь `_pause_tasks` инициализирован
- [ ] При каждой новой паузе старая отменяется
- [ ] Задачи удаляются из словаря при завершении
- [ ] Нет утечек памяти
- [ ] При отмене нет ошибок

**Тестирование:**
```bash
# 1. Нажать "Пауза" для одного чата
# 2. Нажать "Пауза" ещё раз до истечения 30 минут
# 3. Проверить логи - должна быть запись об отмене старой задачи
# 4. Убедиться что проверка памяти показывает нормальное использование
```

---

### ✅ Issue #4: Обработка ошибок DB операций - НЕПОЛНАЯ

**Описание:**
Множество DB операций в `handlers/business.py` не обёрнуты в try/except. При ошибке БД бот может упасть.

**Примеры проблемных мест:**
```python
# handlers/business.py:149
user = await get_user(owner_id)  # ❌ Нет try/except
if not user:
    logger.warning(...)
    return

# handlers/business.py:229
prev_messages = await get_chat_messages(...)  # ❌ Нет try/except
msg_count = len(prev_messages)  # Может быть ошибка если None

# handlers/business.py:237-238
history_30_days = await get_history_30_days(...)  # ❌ Нет try/except
chat_stats = await get_chat_stats_30_days(...)  # ❌ Нет try/except
```

**Проблемы:**
- ❌ Если БД недоступна - бот упадёт
- ❌ Нет graceful degradation
- ❌ Нет возможности продолжить работу
- ❌ Непредсказуемое поведение при сбоях

**Решение:**
Обернуть все DB операции в try/except с fallback значениями.

**Код исправления:**

```python
# handlers/business.py - в функции handle_business_message

@router.business_message()
async def handle_business_message(message: Message, bot: Bot):
    owner_id = await _get_owner_id(message, bot)
    if not owner_id:
        logger.warning(f"[MSG] Could not get owner_id...")
        return

    # ... существующий код ...
    
    # ✅ УЛУЧШЕНО: Обработка ошибок для get_user
    try:
        user = await get_user(owner_id)
    except Exception as e:
        logger.error(f"[DB_ERROR] Failed to get user {owner_id}: {e}")
        # Graceful degradation - используем дефолтные значения
        user = {
            "is_enabled": True,  # Предполагаем что бот включён
            "active_model": LLM_MODEL,
            "system_prompt": None,
            "escalation_enabled": True,
            "offline_mode": False,
        }
    
    if not user or not user.get("is_enabled"):
        logger.debug(f"[MSG] owner_id={owner_id} auto-reply is OFF, skipping")
        return

    # ... существующий код ...
    
    # ✅ УЛУЧШЕНО: Обработка ошибок для get_chat_messages
    try:
        prev_messages = await get_chat_messages(owner_id, chat_id, limit=100)
    except Exception as e:
        logger.error(f"[DB_ERROR] Failed to get chat messages: {e}")
        prev_messages = []
    
    msg_count = len(prev_messages or [])
    
    # ✅ УЛУЧШЕНО: Обработка ошибок для история и статистика
    history_30_days = []
    chat_stats = None
    try:
        history_30_days = await get_history_30_days(owner_id, chat_id)
        chat_stats = await get_chat_stats_30_days(owner_id, chat_id)
    except Exception as e:
        logger.error(f"[DB_ERROR] Failed to get 30-day history/stats: {e}")
        history_30_days = []
        chat_stats = {
            "user_messages": 0,
            "bot_messages": 0,
            "total_messages": 0,
            "first_message": None,
            "last_message": None,
        }
    
    # ... остальной код ...
```

**Для `_generate_and_send_reply()`:**
```python
async def _generate_and_send_reply(...) -> None:
    """Генерирует и отправляет ответ (вызывается после 15 минут ожидания)."""
    try:
        active_model = user["active_model"] or LLM_MODEL

        # ✅ Все DB операции с обработкой ошибок
        try:
            prev_messages = await get_chat_messages(owner_id, chat_id, limit=100)
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to get messages: {e}")
            prev_messages = []
        
        msg_count = len(prev_messages or [])
        
        try:
            note = await get_note(owner_id, chat_id)
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to get note: {e}")
            note = ""
        
        try:
            history_30_days = await get_history_30_days(owner_id, chat_id)
            chat_stats = await get_chat_stats_30_days(owner_id, chat_id)
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to get history: {e}")
            history_30_days = []
            chat_stats = {...}
        
        # ... генерация ответа ...
        
        # ✅ Обработка ошибок при сохранении
        try:
            await save_message(owner_id, chat_id, "assistant", reply)
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to save message: {e}")
            # Продолжаем отправку несмотря на ошибку сохранения
        
        # ✅ Обработка ошибок при отправке
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=clean_reply,
                business_connection_id=business_connection_id,
            )
        except Exception as e:
            logger.error(f"[SEND_ERROR] Failed to send message: {e}")
    
    except Exception as e:
        logger.critical(f"[CRITICAL] Error in _generate_and_send_reply: {e}", exc_info=True)
```

**Файлы для изменения:**
- `handlers/business.py` (обернуть все DB операции)

**Критерии приёмки:**
- [ ] Все `await db.*()` вызовы обёрнуты в try/except
- [ ] При ошибке БД бот не падает
- [ ] Используются fallback значения
- [ ] Ошибки логируются с информацией
- [ ] Тесты показывают graceful degradation

**Тестирование:**
```bash
# Симуляция ошибки БД:
# 1. Закрыть БД соединение во время работы
# 2. Отправить сообщение
# 3. Проверить что бот не упал
# 4. Проверить логи с ошибкой
# 5. Проверить что используются fallback значения
```

---

### ✅ Issue #5: Версионирование зависимостей - ТОЧНЫЕ ВЕРСИИ БЕЗ ДИАПАЗОНОВ

**Описание:**
В `requirements.txt` установлены точные версии без верхних границ. Это может привести к неожиданным breaking changes при обновлении.

**Текущий код:**
```
aiogram==3.7.0          # ❌ Точная версия
aiosqlite==0.19.0       # ❌ Точная версия
aiohttp==3.9.5          # ❌ Точная версия
python-dotenv==1.0.1    # ❌ Точная версия
```

**Проблемы:**
- ❌ Нет гибкости при обновлениях
- ❌ При `pip install -r requirements.txt --upgrade` может установиться 4.0.0 с breaking changes
- ❌ Сложно работать в team с разными версиями

**Решение:**
Задать диапазоны версий с нижней (текущей) и верхней (мажор+1) границей.

**Исправленный `requirements.txt`:**

```
# Telegram Bot Framework
aiogram>=3.7.0,<4.0.0

# Database
aiosqlite>=0.19.0,<1.0.0

# HTTP Client
aiohttp>=3.9.0,<4.0.0

# Environment Variables
python-dotenv>=1.0.0,<2.0.0

# Geolocation
geopy>=2.4.0,<3.0.0

# Timezone
timezonefinder>=8.0.0,<9.0.0

# Scheduling
apscheduler>=3.11.0,<4.0.0

# Timezone Support
pytz>=2024.1
```

**Пояснения:**
- `>=X.Y.Z,<X+1.0.0` — позволяет patch и minor обновления (3.7.1, 3.8.0), но блокирует major (4.0.0)
- Для стабильных libs без мажор обновлений используем `>=X.Y.Z` без верхней границы
- `pytz` нет верхней границы т.к. обновляется редко

**Файлы для изменения:**
- `requirements.txt`
- `.env.example` (опционально - добавить комментарий о версионировании)

**Критерии приёмки:**
- [ ] Все основные зависимости имеют диапазоны
- [ ] Нижняя граница = текущая рабочая версия
- [ ] Верхняя граница = следующая major версия
- [ ] `pip install -r requirements.txt` работает
- [ ] `pip install -r requirements.txt --upgrade` не ломает функциональность

**Тестирование:**
```bash
# Обновить зависимости
pip install -r requirements.txt --upgrade

# Запустить бота
python bot.py

# Проверить что всё работает
```

---

## 📋 Чек-лист для разработчика

### Блок 1: BOT_TOKEN безопасность

- [ ] Выбрать подход (base64 или другой)
- [ ] Реализовать безопасную загрузку фото
- [ ] Обновить `ask_llm_vision()` для работы с base64
- [ ] Удалить прямое использование BOT_TOKEN из строк
- [ ] Тестировать загрузку фото
- [ ] Проверить логи на отсутствие токена
- [ ] Обновить документацию

### Блок 2: Rate limiting

- [ ] Создать `services/rate_limiter.py`
- [ ] Реализовать функции `is_rate_limited()`, `get_rate_limit_remaining()`
- [ ] Интегрировать в `handlers/business.py`
- [ ] Добавить переменную в `config.py`
- [ ] Обновить `.env.example`
- [ ] Написать тесты для rate limiting
- [ ] Документировать переменные окружения

### Блок 3: Async задачи паузы

- [ ] Добавить глобальный словарь `_pause_tasks`
- [ ] Обновить `on_escalation_pause()` для отслеживания
- [ ] Добавить отмену старых задач
- [ ] Обновить `safe_split_callback` для паузы (если нужно)
- [ ] Тестировать нажатие паузы несколько раз
- [ ] Проверить использование памяти

### Блок 4: Обработка ошибок DB

- [ ] Обернуть `get_user()` в try/except
- [ ] Обернуть `get_chat_messages()` в try/except
- [ ] Обернуть `get_history_30_days()` в try/except
- [ ] Обернуть `get_chat_stats_30_days()` в try/except
- [ ] Обернуть `get_note()` в try/except
- [ ] Обернуть `save_message()` в try/except
- [ ] Добавить fallback значения
- [ ] Тестировать с отключённой БД

### Блок 5: Версионирование

- [ ] Обновить `requirements.txt`
- [ ] Проверить совместимость версий
- [ ] Запустить `pip install -r requirements.txt`
- [ ] Запустить `pip install -r requirements.txt --upgrade`
- [ ] Протестировать работу бота
- [ ] Обновить `.env.example` если нужно

---

## 🎯 Порядок выполнения

### Неделя 1: Критические

1. **BOT_TOKEN безопасность** (1-2 дня)
   - Выбрать подход
   - Реализовать
   - Тестировать

2. **Rate limiting** (1-2 дня)
   - Создать модуль
   - Интегрировать
   - Тестировать

### Неделя 2: Высокие

3. **Async задачи паузы** (1 день)
   - Обновить код
   - Тестировать

4. **Обработка ошибок DB** (2-3 дня)
   - Обернуть операции
   - Добавить fallback
   - Тестировать

### Неделя 3: Средние

5. **Версионирование** (0.5 дня)
   - Обновить requirements.txt
   - Тестировать

---

## 📊 Таблица статуса

| # | Issue | Статус | Риск | Сложность |
|---|-------|--------|------|-----------|
| 1 | BOT_TOKEN в коде | ⏳ TODO | 🔴 ВЫСОКИЙ | ⭐⭐ |
| 2 | Rate limiting | ⏳ TODO | 🔴 ВЫСОКИЙ | ⭐⭐⭐ |
| 3 | Async задачи | ⏳ TODO | 🟠 СРЕДНИЙ | ⭐⭐ |
| 4 | DB обработка ошибок | ⏳ TODO | 🟠 СРЕДНИЙ | ⭐⭐⭐ |
| 5 | Версионирование | ⏳ TODO | 🟡 НИЗКИЙ | ⭐ |

---

## 📝 Примечания для разработчика

### Тестирование Rate limiting:

```python
# Временно установить в .env
RATE_LIMIT_MESSAGES_PER_MINUTE=3

# Отправить 4 сообщения подряд в течение секунды
# Проверить что 4-е пропущено

# Установить обратно нормальное значение
RATE_LIMIT_MESSAGES_PER_MINUTE=20
```

### Тестирование DB ошибок:

```python
# Отключить БД соединение
# Отправить сообщение в бот
# Проверить логи: [DB_ERROR] Failed to get...
# Проверить что бот продолжает работу
# Восстановить БД соединение
```

### Проверка памяти:

```bash
# Во время работы бота (особенно при частых паузах)
# Запустить в другом терминале:
ps aux | grep python  # Смотреть RES (resident memory)
# Должна быть стабильной, а не расти
```

---

## 🔗 Ссылки

- [Aiogram Documentation](https://docs.aiogram.dev/)
- [Python async/await best practices](https://docs.python.org/3/library/asyncio.html)
- [Rate limiting strategies](https://en.wikipedia.org/wiki/Rate_limiting)
- [Security best practices](https://owasp.org/Top10/)

---

**Готово к началу работы!** 🚀
