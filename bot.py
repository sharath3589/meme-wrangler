posting_log = []  # in-memory log


import asyncio
import os
import logging
from datetime import datetime, time, timedelta
import aiosqlite
from typing import Optional
import io
import pytz

from telegram import Update, Message, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IST timezone
IST = pytz.timezone('Asia/Kolkata')

DB_PATH = os.environ.get("MEMEBOT_DB", "memes.db")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # @channelusername or -100<id>

SLOTS = [time(11, 0), time(16, 0), time(21, 0)]

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_file_id TEXT NOT NULL,
                mime_type TEXT,
                scheduled_ts INTEGER NOT NULL,
                posted INTEGER DEFAULT 0,
                created_ts INTEGER NOT NULL
            )
            """
        )
        # Ensure preview_file_id column exists (migration)
        async with db.execute("PRAGMA table_info(memes)") as cur:
            cols = await cur.fetchall()
        col_names = [c[1] for c in cols]
        if 'preview_file_id' not in col_names:
            await db.execute("ALTER TABLE memes ADD COLUMN preview_file_id TEXT")
        # Ensure caption column exists (migration)
        if 'caption' not in col_names:
            await db.execute("ALTER TABLE memes ADD COLUMN caption TEXT")
        await db.commit()

async def compute_next_slot(after_dt: Optional[datetime] = None) -> datetime:
    """Return the next slot datetime from after_dt (exclusive). If after_dt is None, use now() in IST.
    All calculations and returns are in IST timezone."""
    if after_dt is None:
        # Get current time in IST
        after_dt = datetime.now(IST)
    else:
        # Ensure after_dt is timezone-aware and in IST
        if after_dt.tzinfo is None:
            after_dt = IST.localize(after_dt)
        else:
            after_dt = after_dt.astimezone(IST)
    
    # check same-day slots in IST
    today = after_dt.date()
    for slot in SLOTS:
        candidate = IST.localize(datetime.combine(today, slot))
        if candidate > after_dt:
            return candidate
    # otherwise next day's first slot
    next_day = today + timedelta(days=1)
    return IST.localize(datetime.combine(next_day, SLOTS[0]))

async def get_last_scheduled_ts(db) -> Optional[int]:
    async with db.execute("SELECT scheduled_ts FROM memes WHERE posted=0 ORDER BY scheduled_ts DESC LIMIT 1") as cur:
        row = await cur.fetchone()
        return row[0] if row else None

async def schedule_meme(owner_file_id: str, mime_type: str, caption: Optional[str] = None) -> datetime:
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        # Always schedule after the latest scheduled meme, even if it's far in the future
        last_ts = await get_last_scheduled_ts(db)
        if last_ts is None:
            # no pending memes, schedule relative to now in IST
            ref_dt = datetime.now(IST)
        else:
            # Convert timestamp to IST-aware datetime
            ref_dt = datetime.fromtimestamp(last_ts, tz=IST)
        next_dt = await compute_next_slot(ref_dt)

        # Try to get a preview file_id (for photo: smallest size, for video: thumbnail, for animation: itself)
        preview_file_id = None
        # context is not available here, so preview is best-effort: use owner_file_id for now
        preview_file_id = owner_file_id

        await db.execute(
            "INSERT INTO memes (owner_file_id, mime_type, scheduled_ts, created_ts, preview_file_id, caption) VALUES (?, ?, ?, ?, ?, ?)",
            (owner_file_id, mime_type, int(next_dt.timestamp()), int(datetime.now(IST).timestamp()), preview_file_id, caption),
        )
        await db.commit()
    return next_dt

async def pop_due_memes_and_post(context: ContextTypes.DEFAULT_TYPE):
    now_ts = int(datetime.now(IST).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        # Check if caption column exists
        async with db.execute("PRAGMA table_info(memes)") as cur:
            cols = await cur.fetchall()
        col_names = [c[1] for c in cols]
        has_caption = 'caption' in col_names
        
        if has_caption:
            async with db.execute("SELECT id, owner_file_id, mime_type, caption FROM memes WHERE posted=0 AND scheduled_ts<=? ORDER BY scheduled_ts ASC", (now_ts,)) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute("SELECT id, owner_file_id, mime_type FROM memes WHERE posted=0 AND scheduled_ts<=? ORDER BY scheduled_ts ASC", (now_ts,)) as cur:
                rows = await cur.fetchall()
                
        for row in rows:
            if has_caption:
                mid, file_id, mime, caption = row
            else:
                mid, file_id, mime = row
                caption = None
                
            try:
                sent = False
                # Try video first when appropriate
                if mime and mime.startswith("video"):
                    try:
                        await context.bot.send_video(CHANNEL_ID, file_id, caption=caption)
                        sent = True
                    except Exception as e_video:
                        logger.warning("send_video failed for id=%s: %s", mid, e_video)
                if not sent:
                    # try as photo/animation
                    try:
                        await context.bot.send_photo(CHANNEL_ID, file_id, caption=caption)
                        sent = True
                    except Exception as e_photo:
                        logger.warning("send_photo failed for id=%s: %s", mid, e_photo)
                        # fallback to sending as document
                        try:
                            await context.bot.send_document(CHANNEL_ID, file_id, caption=caption)
                            sent = True
                        except Exception as e_doc:
                            logger.warning("send_document failed for id=%s: %s", mid, e_doc)
                            # raise the last exception to be caught below
                            raise e_doc

                if sent:
                    await db.execute("UPDATE memes SET posted=1 WHERE id=?", (mid,))
                    await db.commit()
                    logger.info("Posted meme id=%s", mid)
                    posting_log.append(f"[SUCCESS] Posted meme id={mid} at {datetime.now(IST).isoformat(sep=' ')}")
                    if len(posting_log) > 100:
                        posting_log.pop(0)
            except Exception as e:
                logger.exception("Failed to post meme id=%s: %s", mid, e)
                posting_log.append(f"[FAIL] Meme id={mid} at {datetime.now(IST).isoformat(sep=' ')}: {type(e).__name__}: {e}")
                if len(posting_log) > 100:
                    posting_log.pop(0)
async def scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        # Check if preview_file_id and caption columns exist to avoid sqlite errors on older DBs
        async with db.execute("PRAGMA table_info(memes)") as pcur:
            cols = await pcur.fetchall()
        col_names = [c[1] for c in cols]
        has_preview = 'preview_file_id' in col_names
        has_caption = 'caption' in col_names
        
        if has_preview and has_caption:
            query = "SELECT id, scheduled_ts, mime_type, preview_file_id, caption FROM memes WHERE posted=0 ORDER BY scheduled_ts ASC"
        elif has_preview:
            query = "SELECT id, scheduled_ts, mime_type, preview_file_id FROM memes WHERE posted=0 ORDER BY scheduled_ts ASC"
        else:
            query = "SELECT id, scheduled_ts, mime_type FROM memes WHERE posted=0 ORDER BY scheduled_ts ASC"
            
        async with db.execute(query) as cur:
            rows = await cur.fetchall()

    if not rows:
        await update.message.reply_text("No scheduled memes.")
        return

    # For each scheduled item, try to send a preview robustly (direct send, then download+reupload)
    for row in rows:
        if has_preview and has_caption:
            mid, ts, mtype, preview_id, user_caption = row
        elif has_preview:
            mid, ts, mtype, preview_id = row
            user_caption = None
        else:
            mid, ts, mtype = row
            preview_id = None
            user_caption = None

        # Fallback: if preview_id is missing/null, use owner_file_id
        async with aiosqlite.connect(DB_PATH) as db:
            await init_db()
            async with db.execute("SELECT owner_file_id FROM memes WHERE id=?", (mid,)) as cur:
                owner_row = await cur.fetchone()
        owner_file_id = owner_row[0] if owner_row else None
        file_id = preview_id if preview_id else owner_file_id

        # Build caption with ID, time, type and user's caption if present
        caption_parts = [f"ID: {mid}", f"Time: {datetime.fromtimestamp(ts, tz=IST).strftime('%Y-%m-%d %H:%M:%S IST')}", f"Type: {mtype}"]
        if user_caption:
            caption_parts.append(f"Caption: {user_caption}")
        caption = ", ".join(caption_parts)

        sent = False
        # Try direct sends with fallbacks
        try:
            if mtype and mtype.startswith('video'):
                try:
                    if file_id:
                        await context.bot.send_video(update.effective_chat.id, file_id, caption=caption)
                        sent = True
                except Exception as e:  # direct video failed
                    logger.debug("scheduled: direct send_video failed for id=%s: %s", mid, e)

            if not sent and file_id:
                try:
                    await context.bot.send_photo(update.effective_chat.id, file_id, caption=caption)
                    sent = True
                except Exception as e:
                    logger.debug("scheduled: direct send_photo failed for id=%s: %s", mid, e)
                    try:
                        await context.bot.send_document(update.effective_chat.id, file_id, caption=caption)
                        sent = True
                    except Exception as e2:
                        logger.debug("scheduled: direct send_document failed for id=%s: %s", mid, e2)

            if not sent and file_id:
                # Attempt download + reupload
                try:
                    file = await context.bot.get_file(file_id)
                    bio = io.BytesIO()
                    await file.download(out=bio)
                    bio.seek(0)
                    if mtype and mtype.startswith('video'):
                        await context.bot.send_video(update.effective_chat.id, InputFile(bio, filename=f"meme_{mid}.mp4"), caption=caption)
                    else:
                        try:
                            await context.bot.send_photo(update.effective_chat.id, InputFile(bio, filename=f"meme_{mid}.jpg"), caption=caption)
                        except Exception:
                            bio.seek(0)
                            await context.bot.send_document(update.effective_chat.id, InputFile(bio, filename=f"meme_{mid}"), caption=caption)
                    sent = True
                except Exception as e:
                    logger.debug("scheduled: download+reupload failed for id=%s: %s", mid, e)

        except Exception as e:
            logger.exception("Unexpected error while previewing scheduled id=%s: %s", mid, e)

        if not sent:
            # If all attempts fail, send a text placeholder
            await update.message.reply_text(caption)
async def unschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    if not context.args or not all(arg.isdigit() for arg in context.args):
        await update.message.reply_text("Usage: /unschedule <id1> <id2> ...")
        return
    meme_ids = [int(arg) for arg in context.args]
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        for meme_id in meme_ids:
            await db.execute("DELETE FROM memes WHERE id=? AND posted=0", (meme_id,))
        await db.commit()
    await update.message.reply_text(f"Unscheduled memes with IDs: {', '.join(str(mid) for mid in meme_ids)} (if they existed and were not posted yet).")


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Preview a scheduled meme by id. Tries direct send, then downloads and reuploads as a document if needed."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /preview <id>")
        return
    meme_id = int(context.args[0])
    # immediate ack so owner knows the command was received
    try:
        await update.message.reply_text(f"Previewing meme {meme_id}...")
    except Exception:
        logger.debug("Could not send ack reply for preview %s", meme_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        async with db.execute("SELECT owner_file_id, mime_type FROM memes WHERE id=?", (meme_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        await update.message.reply_text(f"No meme found with ID {meme_id}.")
        return
    file_id, mime = row
    chat_id = update.effective_chat.id
    # Try direct sends with fallbacks
    try:
        if mime and mime.startswith("video"):
            await context.bot.send_video(chat_id, file_id, caption=f"Preview ID {meme_id}")
            return
        try:
            await context.bot.send_photo(chat_id, file_id, caption=f"Preview ID {meme_id}")
            return
        except Exception as e_photo:
            logger.debug("Direct send_photo failed for preview id=%s: %s", meme_id, e_photo)
            # try send_document quick fallback
            try:
                await context.bot.send_document(chat_id, file_id, caption=f"Preview ID {meme_id}")
                return
            except Exception as e_doc:
                logger.debug("Direct send_document failed for preview id=%s: %s", meme_id, e_doc)
        # If direct fails, download and reupload
        file = await context.bot.get_file(file_id)
        bio = io.BytesIO()
        await file.download(out=bio)
        bio.seek(0)
        # pick send method based on mime
        if mime and mime.startswith("video"):
            await context.bot.send_video(chat_id, InputFile(bio, filename=f"meme_{meme_id}.mp4"), caption=f"Preview ID {meme_id}")
        else:
            # try as photo first, then document
            try:
                await context.bot.send_photo(chat_id, InputFile(bio, filename=f"meme_{meme_id}.jpg"), caption=f"Preview ID {meme_id}")
            except Exception:
                bio.seek(0)
                await context.bot.send_document(chat_id, InputFile(bio, filename=f"meme_{meme_id}"), caption=f"Preview ID {meme_id}")
    except Exception as e:
        logger.exception("Preview failed for id=%s: %s", meme_id, e)
        await update.message.reply_text(f"Failed to preview meme {meme_id}: {type(e).__name__}: {e}")

async def logcmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    if not posting_log:
        await update.message.reply_text("No posting events yet.")
        return
    await update.message.reply_text("Last posting events:\n" + "\n".join(posting_log[-10:]))

async def periodic_poster(application):
    while True:
        try:
            await pop_due_memes_and_post(application)
        except Exception:
            logger.exception("Error in poster loop")
        await asyncio.sleep(30)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I schedule memes to the configured channel.")

async def helpcmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a detailed help message with all commands."""
    help_text = (
        """
<b>🤖 <u>Meme Wrangler Bot Command Reference</u> 🤖</b>

<b>General:</b>
  <b>/start</b> — Show a welcome message.
  <b>/help</b> — Show this help message.

<b>Scheduling Memes:</b>
  <b>Send a photo/video/animation</b> (as a DM to the bot):
    Schedules it for the next available slot (11:00, 16:00, 21:00 IST).
    Add a caption to include it with the post.
    <i>Example:</i> Send a meme to the bot in DM with or without caption.

  <b>/scheduled</b> — List all scheduled memes with previews and their IDs, times, and types.

  <b>/unschedule &lt;id1&gt; [&lt;id2&gt; ...]</b> — Remove one or more memes from the schedule (by ID).
    <i>Example:</i> <code>/unschedule 3 5 7</code>

  <b>/postnow [id]</b> — Immediately post the next scheduled meme, or a specific meme by ID.
    <i>Example:</i> <code>/postnow</code> or <code>/postnow 6</code>

  <b>/preview &lt;id&gt;</b> — Preview a scheduled meme by its ID.
    <i>Example:</i> <code>/preview 4</code>

  <b>/log</b> — Show the last 10 posting events (success/failure log).

<b>Advanced Scheduling:</b>
  <b>/scheduleat id: &lt;id&gt; &lt;HH:MM&gt;</b> — Reschedule a single meme to a specific time (24h, IST).
    <i>Example:</i> <code>/scheduleat id: 6 16:20</code>

  <b>/scheduleat ids: &lt;start&gt;-&lt;end&gt; &lt;YYYY-MM-DD&gt;</b> — Reschedule a range of memes to a date, assigning slots (11:00, 16:00, 21:00 IST) in order.
    <i>Example:</i> <code>/scheduleat ids: 5-10 2025-10-19</code>

<b>Notes:</b>
• <b>Only the owner</b> (set by OWNER_ID) can use admin commands.
• All times are in <b>IST (Asia/Kolkata)</b>.
• Meme IDs are shown in <b>/scheduled</b> previews.
• Use <b>/preview</b> to check a meme before posting.

<b>✨ Enjoy effortless meme scheduling! ✨</b>
        """
    )
    await update.message.reply_text(help_text, parse_mode="HTML", disable_web_page_preview=True)

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg: Message = update.message
    user_id = msg.from_user.id
    if user_id != OWNER_ID:
        await msg.reply_text("Sorry, only the owner can send memes to schedule.")
        return

    # Determine the best file id and mime
    file_id = None
    mime = None
    caption = msg.caption  # Get caption if present
    
    if msg.photo:
        # highest resolution
        file = msg.photo[-1]
        file_id = file.file_id
        mime = 'image'
    elif msg.video:
        file_id = msg.video.file_id
        mime = 'video'
    elif msg.animation:
        file_id = msg.animation.file_id
        mime = 'image'  # gifs treated as image
    else:
        await msg.reply_text("Please send a photo, animation (GIF) or video.")
        return

    scheduled_dt = await schedule_meme(file_id, mime, caption)
    # scheduled_dt is already in IST timezone
    await msg.reply_text(f"Scheduled for: {scheduled_dt.strftime('%Y-%m-%d %H:%M:%S IST')}")

async def postnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return

    # If an ID is provided, post that meme; else, post the next scheduled meme
    meme_id = None
    if context.args and context.args[0].isdigit():
        meme_id = int(context.args[0])

    async with aiosqlite.connect(DB_PATH) as db:
        await init_db()
        if meme_id is not None:
            async with db.execute("SELECT id, owner_file_id, mime_type FROM memes WHERE posted=0 AND id=?", (meme_id,)) as cur:
                row = await cur.fetchone()
            if not row:
                await update.message.reply_text(f"No scheduled meme with ID {meme_id} to post.")
                return
        else:
            async with db.execute("SELECT id, owner_file_id, mime_type FROM memes WHERE posted=0 ORDER BY scheduled_ts ASC LIMIT 1") as cur:
                row = await cur.fetchone()
            if not row:
                await update.message.reply_text("No scheduled memes to post.")
                return
        mid, file_id, mime = row
        try:
            if mime and mime.startswith("video"):
                await context.bot.send_video(CHANNEL_ID, file_id)
            else:
                await context.bot.send_photo(CHANNEL_ID, file_id)
            await db.execute("UPDATE memes SET posted=1 WHERE id=?", (mid,))
            await db.commit()
            await update.message.reply_text(f"Posted meme with ID {mid} to channel.")
        except Exception as e:
            await update.message.reply_text(f"Failed to post meme: {e}")

import re

async def scheduleat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /scheduleat id: <id> <HH:MM> or /scheduleat ids: <start>-<end> <YYYY-MM-DD>")
        return

    argstr = ' '.join(context.args)
    # Single ID mode: /scheduleat id: 6 16:20
    m_single = re.match(r'id:\s*(\d+)\s+(\d{2}):(\d{2})$', argstr)
    # Range mode: /scheduleat ids: 5-10 2025-10-19
    m_range = re.match(r'ids:\s*(\d+)-(\d+)\s+(\d{4}-\d{2}-\d{2})$', argstr)

    if m_single:
        meme_id = int(m_single.group(1))
        hour = int(m_single.group(2))
        minute = int(m_single.group(3))
        # Validate time
        if not (0 <= hour < 24 and 0 <= minute < 60):
            await update.message.reply_text("Invalid time format. Use 24h HH:MM.")
            return
        # Schedule meme at specified time today (IST)
        now_ist = datetime.now(IST)
        sched_dt = IST.localize(datetime(now_ist.year, now_ist.month, now_ist.day, hour, minute))
        sched_ts = int(sched_dt.timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            await init_db()
            await db.execute("UPDATE memes SET scheduled_ts=? WHERE id=? AND posted=0", (sched_ts, meme_id))
            await db.commit()
        await update.message.reply_text(f"Rescheduled meme ID {meme_id} for {sched_dt.strftime('%Y-%m-%d %H:%M')} IST.")
        return

    elif m_range:
        start_id = int(m_range.group(1))
        end_id = int(m_range.group(2))
        date_str = m_range.group(3)
        from datetime import time as dtime
        base_date = IST.localize(datetime.strptime(date_str, '%Y-%m-%d'))
        # Assign slots in order: 11:00, 16:00, 21:00, repeat
        slot_times = [dtime(11,0), dtime(16,0), dtime(21,0)]
        ids = list(range(start_id, end_id+1))
        updates = []
        for idx, meme_id in enumerate(ids):
            slot = slot_times[idx % len(slot_times)]
            sched_dt = base_date.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
            sched_ts = int(sched_dt.timestamp())
            updates.append((sched_ts, meme_id))
        async with aiosqlite.connect(DB_PATH) as db:
            await init_db()
            for sched_ts, meme_id in updates:
                await db.execute("UPDATE memes SET scheduled_ts=? WHERE id=? AND posted=0", (sched_ts, meme_id))
            await db.commit()
        await update.message.reply_text(f"Rescheduled memes IDs {start_id}-{end_id} for {date_str} in slots 11:00, 16:00, 21:00 IST (cycled).")
        return

    else:
        await update.message.reply_text("Invalid format. Use /scheduleat id: <id> <HH:MM> or /scheduleat ids: <start>-<end> <YYYY-MM-DD>")

def main():
    if not BOT_TOKEN:
        raise SystemExit("Please set TELEGRAM_BOT_TOKEN environment variable")
    if not OWNER_ID or OWNER_ID == 0:
        raise SystemExit("Please set OWNER_ID environment variable to your Telegram user id")
    if not CHANNEL_ID:
        raise SystemExit("Please set CHANNEL_ID to target channel (username or id)")

    # Initialize DB first
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', helpcmd))
    app.add_handler(CommandHandler('postnow', postnow))
    app.add_handler(CommandHandler('scheduled', scheduled))
    app.add_handler(CommandHandler('unschedule', unschedule))
    app.add_handler(CommandHandler('preview', preview))
    app.add_handler(CommandHandler('log', logcmd))
    app.add_handler(CommandHandler('scheduleat', scheduleat))
    media_filter = filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.ANIMATION)
    app.add_handler(MessageHandler(media_filter, handle_media))

    # run background poster using post_init hook
    async def post_init(application):
        asyncio.create_task(periodic_poster(application))
    
    app.post_init = post_init

    logger.info("Starting bot...")
    app.run_polling()

if __name__ == '__main__':
    main()
