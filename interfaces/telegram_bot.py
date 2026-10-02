# interfaces/telegram_bot.py
#
# Telegram interface. Runs in the MAIN thread (run_polling needs that).
# The agent runs in worker threads, and the approver bridges back to the event loop.

import asyncio
import concurrent.futures
import logging
import uuid

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
)

from config import TELEGRAM_TOKEN, TELEGRAM_USER_ID, APPROVAL_TIMEOUT_SECONDS
from core import notifier, safety
from core.agent import Agent
from core.commands import handle_command

CHUNK_SIZE = 4000   # Telegram rejects messages longer than 4096 characters

# One agent (one conversation history) for your Telegram chat.
# The terminal has its own, so the two conversations do not mix.
agent = Agent()

# The agent is not thread-safe, so only ONE request may use it at a time.
agent_lock = asyncio.Lock()

# Shared with the worker threads: the event loop and the app are filled in post_init().
_state = {"loop": None, "app": None}

# approval_id -> Future. A Future is a box that the worker thread waits on, and the
# button handler fills with True/False when you tap.
_pending = {}


# ===========================================================================
# Helpers
# ===========================================================================

def chunk_text(text: str, size: int = CHUNK_SIZE) -> list:
    """Split a long reply into Telegram-sized pieces."""
    text = text or "(no reply)"
    return [text[i:i + size] for i in range(0, len(text), size)]


async def keep_typing(bot, chat_id: int, stop: asyncio.Event) -> None:
    """Show 'typing...' while the agent works. Telegram hides it after ~5 seconds,
    so we resend it every 4 seconds until 'stop' is set."""
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass                                    # a failed indicator is not important
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass                                    # 4 seconds passed: loop and resend


# ===========================================================================
# The approver (runs in a WORKER thread, called by tools via safety.py)
# ===========================================================================

def telegram_approver(description: str) -> bool:
    loop = _state["loop"]
    app = _state["app"]
    if loop is None or app is None:
        return False                                # not ready: fail safe

    approval_id = uuid.uuid4().hex[:8]              # short random id for this request
    answer = concurrent.futures.Future()            # the worker will wait on this
    _pending[approval_id] = answer

    text = "RUBI NEEDS YOUR APPROVAL\n\n" + description
    if len(text) > 3800:
        text = text[:3800] + "\n...[cut]"           # stay under Telegram's limit

    # callback_data is sent back to us when a button is tapped (max 64 bytes).
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, allow", callback_data=f"ok:{approval_id}"),
        InlineKeyboardButton("No, deny", callback_data=f"no:{approval_id}"),
    ]])

    # We are in a worker thread, but the bot lives on the event loop thread.
    # run_coroutine_threadsafe schedules the coroutine there and gives us a Future.
    try:
        sent = asyncio.run_coroutine_threadsafe(
            app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=text, reply_markup=keyboard),
            loop,
        ).result(timeout=20)
    except Exception:
        _pending.pop(approval_id, None)
        return False                                # could not even ask (offline?) -> deny

    try:
        # Block this worker thread until you tap a button (or the timeout passes).
        return bool(answer.result(timeout=APPROVAL_TIMEOUT_SECONDS))
    except concurrent.futures.TimeoutError:
        # No answer in time: treat as DENIED and remove the buttons.
        try:
            asyncio.run_coroutine_threadsafe(
                app.bot.edit_message_text(
                    chat_id=TELEGRAM_USER_ID,
                    message_id=sent.message_id,
                    text=text + "\n\nNo answer in time: DENIED",
                ),
                loop,
            ).result(timeout=10)
        except Exception:
            pass
        return False
    finally:
        _pending.pop(approval_id, None)             # always clean up


def telegram_sink(title: str, text: str) -> None:
    """Notifier sink: also deliver reminders to your phone."""
    loop = _state["loop"]
    app = _state["app"]
    if loop is None or app is None:
        return
    asyncio.run_coroutine_threadsafe(
        app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"{title}: {text}"),
        loop,
    ).result(timeout=15)    # if this raises, notifier prints the error and carries on


# ===========================================================================
# Handlers (async, run on the event loop)
# ===========================================================================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    # Only one request at a time (the agent keeps ONE conversation).
    if agent_lock.locked():
        await message.reply_text("Still working on your previous request. Please wait a moment.")
        return

    async with agent_lock:
        # Tell safety.py to ask via Telegram for everything this request triggers.
        # asyncio.to_thread copies the current context, so the worker thread sees this.
        safety.set_approver(telegram_approver)

        stop = asyncio.Event()
        typing_task = asyncio.create_task(keep_typing(context.bot, update.effective_chat.id, stop))
        try:
            # Run the blocking agent in a worker thread so the event loop stays free
            # (it must stay free to receive your button taps!).
            reply = await asyncio.to_thread(agent.chat, message.text)
        except Exception as error:
            reply = f"Something went wrong: {error}"
        finally:
            stop.set()
            await typing_task

    for part in chunk_text(reply):
        await message.reply_text(part)              # plain text on purpose: no formatting errors


async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /status may probe the network for a moment, so run it off the event loop.
    reply = await asyncio.to_thread(handle_command, agent, update.effective_message.text)
    await update.effective_message.reply_text(reply)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("I only understand text messages for now.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Ignore button taps from anyone except you (buttons only go to your chat,
    # but we check anyway: never trust, always verify).
    if query.from_user.id != TELEGRAM_USER_ID:
        await query.answer()
        return

    action, _, approval_id = (query.data or "").partition(":")
    answer = _pending.get(approval_id)

    # Old buttons (after a timeout or a restart) must not do anything.
    if answer is None or answer.done():
        await query.answer("This request has expired.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)   # remove stale buttons
        except Exception:
            pass
        return

    approved = (action == "ok")
    try:
        answer.set_result(approved)                 # wakes up the waiting worker thread
    except concurrent.futures.InvalidStateError:
        pass                                        # it was answered/expired a split second ago

    await query.answer("Approved" if approved else "Denied")
    await query.edit_message_text(
        query.message.text + ("\n\nYOU APPROVED" if approved else "\n\nYOU DENIED")
    )


async def on_stranger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Someone else messaged the bot. Do NOT reply (that would confirm the bot is alive).
    Only write it to the audit log."""
    user = update.effective_user
    who = f"user_id={user.id} username={user.username}" if user else "unknown"
    safety.log_action("telegram_access", who, "BLOCKED")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[telegram] error: {context.error}")


async def post_init(application: Application) -> None:
    """Runs once when the bot has started (we are now inside the event loop)."""
    _state["loop"] = asyncio.get_running_loop()
    _state["app"] = application
    notifier.add_sink(telegram_sink)                # reminders also go to Telegram

    # The command menu that appears when you type "/" in the chat.
    await application.bot.set_my_commands([
        BotCommand("status", "Show which brain is in use"),
        BotCommand("brain", "auto, groq or ollama"),
        BotCommand("clear", "Forget this conversation"),
        BotCommand("help", "Show commands"),
    ])


# ===========================================================================
# Starting the bot
# ===========================================================================

def can_start() -> bool:
    """True if both the token and your user ID are configured."""
    return bool(TELEGRAM_TOKEN and TELEGRAM_USER_ID)


def _run_setup_mode() -> None:
    """
    Used once, when TELEGRAM_USER_ID is not set yet. The bot does NOTHING except tell
    whoever messages it their own numeric user ID. No agent, no tools.
    """
    async def reply_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await update.effective_message.reply_text(
            f"Your Telegram user ID is: {user.id}\n\n"
            f"Put this line in your .env file:\nTELEGRAM_USER_ID={user.id}\n"
            f"Then stop Rubi (Ctrl+C) and start it again."
        )

    print("SETUP MODE: TELEGRAM_USER_ID is not set.")
    print("Open Telegram, send any message to your bot, and copy the ID it replies with.")
    print("Then add it to .env and restart. Press Ctrl+C to stop.\n")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE & filters.ChatType.PRIVATE, reply_id
    ))
    app.run_polling(drop_pending_updates=True)


def run() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)   # hide the noisy per-poll lines

    if not TELEGRAM_TOKEN:
        print("Telegram: TELEGRAM_TOKEN is missing in .env (create a bot with @BotFather).")
        return
    if not TELEGRAM_USER_ID:
        _run_setup_mode()
        return

    # The ONLY people allowed: you, in a private chat.
    allowed = filters.User(user_id=TELEGRAM_USER_ID) & filters.ChatType.PRIVATE

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        # IMPORTANT: lets button taps be processed while on_text is still waiting.
        # Without this, approvals would deadlock (see "Idea B" at the top of the guide).
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Handlers are checked in the order they are added. The first match wins.
    app.add_handler(MessageHandler(allowed & filters.COMMAND, on_command))
    app.add_handler(MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(allowed & ~filters.TEXT & ~filters.COMMAND, on_other))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(~allowed, on_stranger))   # everyone else: log, never reply
    app.add_error_handler(on_error)

    print("Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling(
        # SAFETY: ignore any messages that arrived while Rubi was off. Otherwise old
        # requests could suddenly run when Rubi starts.
        drop_pending_updates=True,
        # If there is no internet at startup, keep retrying instead of crashing.
        bootstrap_retries=-1,
    )