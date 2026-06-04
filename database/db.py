import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH, SYSTEM_PROMPT_DEFAULT


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id            INTEGER PRIMARY KEY,
                username           TEXT,
                first_name         TEXT,
                plan               TEXT DEFAULT 'personal',
                is_enabled         INTEGER DEFAULT 0,
                is_connected       INTEGER DEFAULT 0,
                is_banned          INTEGER DEFAULT 0,
                timezone           TEXT DEFAULT 'UTC',
                active_model       TEXT DEFAULT 'mimo-v2.5',
                system_prompt      TEXT,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                name        TEXT,
                msg_count   INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contact_notes (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                user_note  TEXT DEFAULT '',
                ai_note    TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id  INTEGER NOT NULL,
                date     TEXT    NOT NULL,
                count    INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id    INTEGER,
                meta       TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id              INTEGER NOT NULL,
                chat_id               INTEGER NOT NULL,
                text                  TEXT NOT NULL,
                send_at               TIMESTAMP NOT NULL,
                business_connection_id TEXT,
                status                TEXT DEFAULT 'pending',
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduled_send_at ON scheduled_messages(send_at, status)"
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS offline_notified (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS escalated_chats (
                user_id      INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                escalated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_messages (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id              INTEGER NOT NULL,
                chat_id               INTEGER NOT NULL,
                sender_name           TEXT,
                sender_username       TEXT,
                message_text          TEXT NOT NULL,
                media_type            TEXT,
                business_connection_id TEXT,
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at            TIMESTAMP NOT NULL,
                status                TEXT DEFAULT 'pending'
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_expires ON pending_messages(expires_at, status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_owner_chat ON pending_messages(owner_id, chat_id, status)"
        )

        # Миграции — добавляем колонки если не существуют
        for migration in [
            "ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'UTC'",
            "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN is_connected INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN business_connection_id TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN offline_mode INTEGER DEFAULT 0",
            "ALTER TABLE contact_notes ADD COLUMN user_note TEXT DEFAULT ''",
            "ALTER TABLE contact_notes ADD COLUMN ai_note TEXT DEFAULT ''",
            "ALTER TABLE contact_notes ADD COLUMN note TEXT DEFAULT ''",
        ]:
            try:
                await db.execute(migration)
            except Exception:
                pass

        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None


async def register_user(user_id: int, username: str, first_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, system_prompt)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, SYSTEM_PROMPT_DEFAULT))
        await db.commit()


async def update_user_setting(user_id: int, key: str, value) -> None:
    allowed = {"is_enabled", "active_model", "system_prompt", "plan", "offline_mode", "offline_reply", "escalation_enabled"}
    if key not in allowed:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id)
        )
        await db.commit()


async def get_history(user_id: int, chat_id: int, limit: int = 12) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND content IS NOT NULL
            AND content != ''
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, chat_id, limit)) as c:
            rows = await c.fetchall()
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def get_history_30_days(user_id: int, chat_id: int) -> list[dict]:
    """Получает всю переписку за последние 30 дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content, created_at FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND created_at >= datetime('now', '-30 days')
            ORDER BY created_at ASC
        """, (user_id, chat_id)) as c:
            rows = await c.fetchall()
            return [{"role": r[0], "content": r[1], "time": r[2]} for r in rows]


async def get_chat_stats_30_days(user_id: int, chat_id: int) -> dict:
    """Статистика чата за 30 дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND role = 'user'
            AND created_at >= datetime('now', '-30 days')
        """, (user_id, chat_id)) as c:
            user_msgs = (await c.fetchone())[0]

        async with db.execute("""
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND role = 'assistant'
            AND created_at >= datetime('now', '-30 days')
        """, (user_id, chat_id)) as c:
            bot_msgs = (await c.fetchone())[0]

        async with db.execute("""
            SELECT MIN(created_at), MAX(created_at) FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND created_at >= datetime('now', '-30 days')
        """, (user_id, chat_id)) as c:
            row = await c.fetchone()
            first_msg = row[0]
            last_msg = row[1]

    return {
        "user_messages": user_msgs,
        "bot_messages": bot_msgs,
        "total_messages": user_msgs + bot_msgs,
        "first_message": first_msg,
        "last_message": last_msg,
    }


async def save_message(user_id: int, chat_id: int, role: str, content: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (user_id, chat_id, role, content)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, role, content))
        await db.commit()


async def save_pending_message(
    owner_id: int,
    chat_id: int,
    sender_name: str,
    sender_username: str,
    message_text: str,
    media_type: str,
    business_connection_id: str,
    delay_minutes: int = 15,
) -> int:
    """Сохраняет входящее сообщение как ожидающее ответа."""
    from datetime import datetime, timedelta
    async with aiosqlite.connect(DB_PATH) as db:
        expires_at = datetime.now() + timedelta(minutes=delay_minutes)
        cursor = await db.execute("""
            INSERT INTO pending_messages (
                owner_id, chat_id, sender_name, sender_username,
                message_text, media_type, business_connection_id, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (owner_id, chat_id, sender_name, sender_username,
              message_text, media_type, business_connection_id, expires_at.isoformat()))
        await db.commit()
        return cursor.lastrowid


async def get_pending_messages(owner_id: int, chat_id: int) -> list[dict]:
    """Получает ожидающие сообщения для чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, message_text, sender_name, expires_at
            FROM pending_messages
            WHERE owner_id = ? AND chat_id = ? AND status = 'pending'
            ORDER BY created_at ASC
        """, (owner_id, chat_id)) as c:
            rows = await c.fetchall()
            return [{"id": r[0], "text": r[1], "sender": r[2], "expires": r[3]} for r in rows]


async def get_expired_pending_messages() -> list[dict]:
    """Получает сообщения, время которых истекло."""
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, owner_id, chat_id, sender_name, sender_username,
                   message_text, media_type, business_connection_id
            FROM pending_messages
            WHERE status = 'pending' AND expires_at <= ?
            ORDER BY created_at ASC
        """, (datetime.now().isoformat(),)) as c:
            rows = await c.fetchall()
            return [{
                "id": r[0], "owner_id": r[1], "chat_id": r[2],
                "sender_name": r[3], "sender_username": r[4],
                "message_text": r[5], "media_type": r[6],
                "business_connection_id": r[7],
            } for r in rows]


async def mark_pending_resolved(pending_id: int, status: str = "replied") -> None:
    """Помечает сообщение как обработанное."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_messages SET status = ? WHERE id = ?",
            (status, pending_id)
        )
        await db.commit()


async def cancel_pending_for_chat(owner_id: int, chat_id: int) -> int:
    """Отменяет все ожидающие сообщения для чата (если владелец ответил). Возвращает количество."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE pending_messages SET status = 'cancelled' WHERE owner_id = ? AND chat_id = ? AND status = 'pending'",
            (owner_id, chat_id)
        )
        await db.commit()
        return cursor.rowcount


async def clear_old_pending() -> None:
    """Очищает старые обработанные сообщения (старше 7 дней)."""
    from datetime import datetime, timedelta
    async with aiosqlite.connect(DB_PATH) as db:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        await db.execute(
            "DELETE FROM pending_messages WHERE status != 'pending' AND created_at < ?",
            (cutoff,)
        )
        await db.commit()


async def upsert_chat(user_id: int, chat_id: int, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chats (user_id, chat_id, name, msg_count, last_active)
            VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                name = excluded.name,
                msg_count = msg_count + 1,
                last_active = CURRENT_TIMESTAMP
        """, (user_id, chat_id, name))
        await db.commit()


async def clear_history(user_id: int, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        await db.commit()


async def clear_all_history(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def get_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT chat_id) FROM messages WHERE user_id = ?", (user_id,)
        ) as c:
            total_chats = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role='user'", (user_id,)
        ) as c:
            total_incoming = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role='assistant'", (user_id,)
        ) as c:
            total_replies = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND role='user' AND DATE(created_at) = DATE('now')
        """, (user_id,)) as c:
            today_msgs = (await c.fetchone())[0]
    return {
        "total_chats": total_chats,
        "total_incoming": total_incoming,
        "total_replies": total_replies,
        "today_msgs": today_msgs,
    }


async def get_chat_list(user_id: int, limit: int = 100) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT c.chat_id, c.name, c.msg_count, c.last_active,
                   (SELECT content FROM messages
                    WHERE user_id = c.user_id AND chat_id = c.chat_id
                    AND role = 'user' ORDER BY created_at DESC LIMIT 1) as last_msg,
                   (SELECT user_note FROM contact_notes
                    WHERE user_id = c.user_id AND chat_id = c.chat_id) as note
            FROM chats c WHERE c.user_id = ?
            ORDER BY c.last_active DESC LIMIT ?
        """, (user_id, limit)) as c:
            return await c.fetchall()


async def get_chat_messages(user_id: int, chat_id: int, limit: int = 8) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content, created_at FROM messages
            WHERE user_id = ? AND chat_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, chat_id, limit)) as c:
            rows = await c.fetchall()
            return list(reversed(rows))


async def get_notes(user_id: int, chat_id: int) -> dict:
    """Возвращает обе заметки: пользовательскую и от ИИ."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_note, ai_note FROM contact_notes WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ) as c:
            row = await c.fetchone()
            if row:
                return {"user_note": row[0] or "", "ai_note": row[1] or ""}
            return {"user_note": "", "ai_note": ""}


async def get_note(user_id: int, chat_id: int) -> str:
    """Возвращает объединённую заметку для LLM."""
    notes = await get_notes(user_id, chat_id)
    parts = []
    if notes["user_note"]:
        parts.append(notes["user_note"])
    if notes["ai_note"]:
        parts.append(notes["ai_note"])
    return " | ".join(parts) if parts else ""


async def set_user_note(user_id: int, chat_id: int, note: str) -> None:
    """Пользователь редактирует свою заметку."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO contact_notes (user_id, chat_id, user_note, ai_note, updated_at)
            VALUES (?, ?, ?, '', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                user_note  = excluded.user_note,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, chat_id, note))
        await db.commit()


async def set_note(user_id: int, chat_id: int, note: str) -> None:
    """ИИ обновляет свою заметку автоматически."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO contact_notes (user_id, chat_id, user_note, ai_note, updated_at)
            VALUES (?, ?, '', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                ai_note    = excluded.ai_note,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, chat_id, note))
        await db.commit()


async def delete_user_note(user_id: int, chat_id: int) -> None:
    """Очищает только пользовательскую заметку."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE contact_notes SET user_note = '' WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        await db.commit()


async def delete_note(user_id: int, chat_id: int) -> None:
    """Очищает обе заметки."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM contact_notes WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        await db.commit()


async def get_global_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')
        """) as c:
            new_today = (await c.fetchone())[0]
    return {
        "total_users": total_users,
        "new_today": new_today,
    }


async def set_connected(user_id: int, connected: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_connected = ? WHERE user_id = ?",
            (1 if connected else 0, user_id)
        )
        await db.commit()


async def is_connected(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user and user.get("is_connected"))


# ── Events / Аналитика ────────────────────────────────────────────────────────

async def log_event(event_type: str, user_id: int | None = None, meta: str = "") -> None:
    """Логируем действие без контента сообщений."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO events (event_type, user_id, meta) VALUES (?, ?, ?)",
                (event_type, user_id, meta)
            )
            await db.commit()
    except Exception:
        pass


async def get_owner_stats() -> dict:
    """Полная статистика для владельца."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Пользователи
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_connected=1") as c:
            connected_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_enabled=1") as c:
            active_users = (await c.fetchone())[0]

        # Онбординг воронка
        async with db.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='onboard_start'"
        ) as c:
            onboard_started = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='onboard_complete'"
        ) as c:
            onboard_done = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='connect_profile'"
        ) as c:
            connected_ever = (await c.fetchone())[0]

        # DAU/WAU/MAU — по событиям
        async with db.execute("""
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE DATE(created_at) = DATE('now') AND user_id IS NOT NULL
        """) as c:
            dau = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE created_at >= datetime('now', '-7 days') AND user_id IS NOT NULL
        """) as c:
            wau = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(DISTINCT user_id) FROM events
            WHERE created_at >= datetime('now', '-30 days') AND user_id IS NOT NULL
        """) as c:
            mau = (await c.fetchone())[0]

        # Прирост
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')"
        ) as c:
            new_today = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"
        ) as c:
            new_week = (await c.fetchone())[0]

        # Сообщения
        async with db.execute("SELECT COUNT(*) FROM events WHERE event_type='message_handled'") as c:
            total_messages = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(*) FROM events
            WHERE event_type='message_handled' AND DATE(created_at) = DATE('now')
        """) as c:
            messages_today = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='llm_error'"
        ) as c:
            llm_errors = (await c.fetchone())[0]

        # Активность по моделям
        async with db.execute("""
            SELECT meta, COUNT(*) as cnt FROM events
            WHERE event_type='message_handled' AND meta != ''
            GROUP BY meta ORDER BY cnt DESC LIMIT 5
        """) as c:
            model_stats = await c.fetchall()

        # Динамика за 7 дней
        async with db.execute("""
            SELECT DATE(created_at) as d, COUNT(*) as cnt
            FROM events WHERE event_type='message_handled'
            AND created_at >= datetime('now', '-7 days')
            GROUP BY d ORDER BY d
        """) as c:
            daily_msgs = await c.fetchall()

    def pct(n, total):
        if not total:
            return "—"
        return f"{round(n / total * 100)}%"

    return {
        "total_users": total_users,
        "connected_users": connected_users,
        "active_users": active_users,
        "onboard_started": onboard_started,
        "onboard_done": onboard_done,
        "connected_ever": connected_ever,
        "onboard_conv": pct(onboard_done, onboard_started),
        "connect_conv": pct(connected_ever, onboard_started),
        "dau": dau, "wau": wau, "mau": mau,
        "new_today": new_today, "new_week": new_week,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "llm_errors": llm_errors,
        "model_stats": model_stats,
        "daily_msgs": daily_msgs,
        "pct_fn": pct,
    }


async def get_users_list(limit: int = 20, offset: int = 0) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, username, first_name, plan, is_enabled, is_connected,
                   created_at
            FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (limit, offset)) as c:
            return await c.fetchall()


async def ban_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def unban_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def delete_user_data(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM contact_notes WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM daily_usage WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
        await db.commit()


async def clean_old_events(days: int = 90) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM events WHERE created_at < datetime('now', '-{days} days')"
        ) as c:
            count = (await c.fetchone())[0]
        await db.execute(
            f"DELETE FROM events WHERE created_at < datetime('now', '-{days} days')"
        )
        await db.commit()
    return count


async def set_user_timezone(user_id: int, timezone: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET timezone = ? WHERE user_id = ?",
            (timezone, user_id)
        )
        await db.commit()


# ── Планировщик сообщений ─────────────────────────────────────────────────────

async def add_scheduled_message(
    owner_id: int,
    chat_id: int,
    text: str,
    send_at_utc: str,
    business_connection_id: str = "",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO scheduled_messages
            (owner_id, chat_id, text, send_at, business_connection_id)
            VALUES (?, ?, ?, ?, ?)
        """, (owner_id, chat_id, text, send_at_utc, business_connection_id))
        await db.commit()
        return cursor.lastrowid


async def get_pending_scheduled(limit: int = 50) -> list:
    """Возвращает сообщения готовые к отправке."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, owner_id, chat_id, text, business_connection_id
            FROM scheduled_messages
            WHERE status = 'pending'
            AND send_at <= datetime('now')
            ORDER BY send_at ASC
            LIMIT ?
        """, (limit,)) as c:
            return await c.fetchall()


async def mark_scheduled_sent(msg_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scheduled_messages SET status = 'sent' WHERE id = ?",
            (msg_id,)
        )
        await db.commit()


async def mark_scheduled_failed(msg_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scheduled_messages SET status = 'failed' WHERE id = ?",
            (msg_id,)
        )
        await db.commit()


async def get_user_scheduled(owner_id: int, limit: int = 10) -> list:
    """Список запланированных сообщений пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, chat_id, text, send_at, status
            FROM scheduled_messages
            WHERE owner_id = ? AND status = 'pending'
            ORDER BY send_at ASC
            LIMIT ?
        """, (owner_id, limit)) as c:
            return await c.fetchall()


async def cancel_scheduled(msg_id: int, owner_id: int) -> bool:
    """Отменяет запланированное сообщение. Возвращает True если удалось."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE scheduled_messages SET status = 'cancelled'
            WHERE id = ? AND owner_id = ? AND status = 'pending'
        """, (msg_id, owner_id))
        await db.commit()
        return cursor.rowcount > 0


async def save_business_connection_id(user_id: int, connection_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET business_connection_id = ? WHERE user_id = ?",
            (connection_id, user_id)
        )
        await db.commit()


async def get_today_messages(user_id: int, chat_id: int) -> list[dict]:
    """Возвращает сообщения за сегодня для сводки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT role, content, created_at FROM messages
            WHERE user_id = ? AND chat_id = ?
            AND DATE(created_at) = DATE('now')
            ORDER BY created_at ASC
        """, (user_id, chat_id)) as c:
            rows = await c.fetchall()
            return [{"role": r[0], "content": r[1], "time": r[2][11:16]} for r in rows]


# ── Офлайн режим ──────────────────────────────────────────────────────────────

async def set_offline_mode(user_id: int, enabled: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET offline_mode = ? WHERE user_id = ?",
            (1 if enabled else 0, user_id)
        )
        # При выключении — сбрасываем всех уведомлённых
        if not enabled:
            await db.execute(
                "DELETE FROM offline_notified WHERE user_id = ?",
                (user_id,)
            )
        await db.commit()


async def is_offline_notified(user_id: int, chat_id: int) -> bool:
    """Уже отправляли офлайн-сообщение этому собеседнику?"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM offline_notified WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ) as c:
            return await c.fetchone() is not None


async def mark_offline_notified(user_id: int, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO offline_notified (user_id, chat_id) VALUES (?, ?)",
            (user_id, chat_id)
        )
        await db.commit()


async def clear_offline_notified_chat(user_id: int, chat_id: int) -> None:
    """Сбрасываем флаг когда владелец сам написал этому человеку."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM offline_notified WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        await db.commit()


# ── Эскалация ─────────────────────────────────────────────────────────────

async def set_escalated(user_id: int, chat_id: int, escalated: bool) -> None:
    """Помечает чат как эскалированный (бот не отвечает)."""
    async with aiosqlite.connect(DB_PATH) as db:
        if escalated:
            await db.execute("""
                INSERT INTO escalated_chats (user_id, chat_id, escalated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    escalated_at = CURRENT_TIMESTAMP
            """, (user_id, chat_id))
        else:
            await db.execute(
                "DELETE FROM escalated_chats WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
        await db.commit()


async def get_escalated(user_id: int, chat_id: int) -> bool:
    """Проверяет, находится ли чат в режиме эскалации."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM escalated_chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        ) as c:
            return await c.fetchone() is not None
