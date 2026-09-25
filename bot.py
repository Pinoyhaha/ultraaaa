import logging
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
TZ = ZoneInfo("Asia/Manila")
DB_PATH = os.environ.get("DB_PATH", "activity.db")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def now():
    return datetime.now(TZ)


def today():
    return now().date().isoformat()


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            joined_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS activity (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id, day)
        );
        """)


def name_of(user):
    full = " ".join(x for x in [user.first_name, user.last_name] if x).strip()
    return full or user.username or str(user.id)


def is_supported(message):
    return bool(message and (message.video or message.document))


def record_activity(chat_id, user_id, name):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO activity(chat_id,user_id,day) VALUES(?,?,?)", (chat_id, user_id, today()))
        con.execute("UPDATE members SET name=?, active=1 WHERE chat_id=? AND user_id=?", (name, chat_id, user_id))


def add_member(chat_id, user_id, name):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO members(chat_id,user_id,name,joined_date,active) VALUES(?,?,?,?,1)", (chat_id, user_id, name, today()))
        con.execute("UPDATE members SET name=?, active=1 WHERE chat_id=? AND user_id=?", (name, chat_id, user_id))


def mark_left(chat_id, user_id):
    with db() as con:
        con.execute("UPDATE members SET active=0 WHERE chat_id=? AND user_id=?", (chat_id, user_id))


def active_names(chat_id):
    with db() as con:
        rows = con.execute("""
            SELECT DISTINCT m.name FROM members m
            JOIN activity a ON a.chat_id=m.chat_id AND a.user_id=m.user_id
            WHERE m.chat_id=? AND m.active=1 AND a.day=? ORDER BY lower(m.name)
        """, (chat_id, today())).fetchall()
    return [r["name"] for r in rows]


def inactive_rows(chat_id):
    with db() as con:
        return con.execute("""
            SELECT m.user_id, m.name FROM members m
            WHERE m.chat_id=? AND m.active=1 AND NOT EXISTS (
                SELECT 1 FROM activity a WHERE a.chat_id=m.chat_id AND a.user_id=m.user_id AND a.day=?
            ) ORDER BY lower(m.name)
        """, (chat_id, today())).fetchall()


async def is_admin(update):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    member = await chat.get_member(user.id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "enabled" if ADMIN_CHAT_ID else "disabled (set ADMIN_CHAT_ID)"
    await update.effective_message.reply_text(
        "Telegram Activity Bot\n\n"
        "/message - today's video/file activity\n"
        "/kick - preview inactive members\n"
        "/kick_confirm - confirm pending kicks\n"
        "/scan - show video delivery status\n\n"
        f"Temporary video saving and admin delivery: {status}\n"
        "Videos are deleted from local storage after successful delivery."
    )


async def deliver_video(message, context):
    if not ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID is not configured")
        return False
    if not message.video:
        return False

    temp_path = None
    try:
        telegram_file = await context.bot.get_file(message.video.file_id)
        with tempfile.NamedTemporaryFile(prefix="telegram_video_", suffix=".mp4", delete=False) as temp:
            temp_path = temp.name
        await telegram_file.download_to_drive(custom_path=temp_path)

        with open(temp_path, "rb") as video_file:
            await context.bot.send_video(
                chat_id=ADMIN_CHAT_ID,
                video=video_file,
                caption=message.caption,
                caption_entities=message.caption_entities,
                supports_streaming=True,
            )
        log.info("Delivered video %s to admin %s", message.message_id, ADMIN_CHAT_ID)
        return True
    except Exception:
        log.exception("Video delivery failed for message %s", message.message_id)
        return False
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
                log.info("Deleted temporary video file %s", temp_path)
            except Exception:
                log.exception("Could not delete temporary file %s", temp_path)


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or user.is_bot or not is_supported(message):
        return
    record_activity(chat.id, user.id, name_of(user))
    if message.video:
        await deliver_video(message, context)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.effective_message.reply_text("Admins only.")
        return
    if not ADMIN_CHAT_ID:
        await update.effective_message.reply_text("Video delivery is disabled. Set ADMIN_CHAT_ID in Railway.")
        return
    await update.effective_message.reply_text(
        "Automatic video delivery is enabled. New videos are downloaded temporarily, sent to the admin, and deleted afterward.\n\n"
        "Telegram's regular Bot API does not allow this command to scan the entire old group history."
    )


async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    change = update.chat_member
    if not change:
        return
    old, new = change.old_chat_member.status, change.new_chat_member.status
    user, chat_id = change.new_chat_member.user, change.chat.id
    if new in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED} and old in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and not user.is_bot:
        add_member(chat_id, user.id, name_of(user))
    elif new in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        mark_left(chat_id, user.id)


async def message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.effective_message.reply_text("Admins only.")
        return
    names = active_names(update.effective_chat.id)
    lines = [f"DAILY ACTIVITY - {today()}", "", f"Active members: {len(names)}"]
    lines.extend(f"{i}. {n}" for i, n in enumerate(names, 1))
    if not names:
        lines.append("No video or file activity recorded yet.")
    await update.effective_message.reply_text("\n".join(lines))


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.effective_message.reply_text("Admins only.")
        return
    rows = inactive_rows(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text("No eligible inactive members today.")
        return
    context.chat_data["pending_kicks"] = [r["user_id"] for r in rows]
    names = "\n".join(f"{i}. {r['name']}" for i, r in enumerate(rows, 1))
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Confirm kick", callback_data="kick_yes"), InlineKeyboardButton("Cancel", callback_data="kick_no")]])
    await update.effective_message.reply_text(f"Inactive members for {today()}:\n\n{names}\n\nConfirm removal?", reply_markup=keyboard)


async def kick_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await kick_command(update, context)


async def kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await is_admin(update):
        await query.edit_message_text("Admins only.")
        return
    if query.data == "kick_no":
        await query.edit_message_text("Kick cancelled.")
        return
    user_ids = context.chat_data.pop("pending_kicks", [])
    if not user_ids:
        await query.edit_message_text("No pending kick list. Run /kick again.")
        return
    removed = failed = 0
    for user_id in user_ids:
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user_id)
            await context.bot.unban_chat_member(update.effective_chat.id, user_id, only_if_banned=True)
            mark_left(update.effective_chat.id, user_id)
            removed += 1
        except Exception:
            log.exception("Could not remove user %s", user_id)
            failed += 1
    await query.edit_message_text(f"Kick complete. Removed: {removed}; failed: {failed}.")


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("message", message_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("kick_confirm", kick_confirm_command))
    app.add_handler(CallbackQueryHandler(kick_callback, pattern=r"^kick_(yes|no)$"))
    app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, track))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
