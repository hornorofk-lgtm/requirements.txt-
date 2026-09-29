"""
Group Admin ဇယားဘော့ 🗓️
Python 3.10+ / pip install "python-telegram-bot[job-queue]>=21"

ပတ်ဝန်းကျင် variable (environment) များ:
  BOT_TOKEN   - @BotFather ဆီက ရတဲ့ token
  GROUP_ID    - Group ရဲ့ chat id (group ထဲမှာ /groupid ပို့ရင် သိရပါတယ်)
  ADMIN_IDS   - run ရမယ့် admin တွေရဲ့ Telegram id, comma ခံပြီး (ဥပမာ 111,222,333)
  TZ_NAME     - timezone (default: Asia/Yangon)

Admin တွေက ဘော့ကို DM ထဲမှာ "14:00-18:00" ပုံစံနဲ့ အချိန်ပို့ရင် ဒီနေ့အတွက်
run မည့်အချိန်အဖြစ် မှတ်ပြီး group ထဲ အလိုအလျောက် ကြေညာပေးပါတယ်။
"""
import asyncio
import datetime as dt
import html
import os
import re
import sqlite3
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = int(os.environ["GROUP_ID"])
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Yangon"))
DIVIDER = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"

db = sqlite3.connect(os.getenv("DB_PATH", "group.db"), check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, name TEXT)")
db.execute(
    """CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER, date TEXT, start TEXT, end TEXT)"""
)
db.execute(
    """CREATE TABLE IF NOT EXISTS activity (
        admin_id INTEGER, date TEXT, ts TEXT)"""
)
db.execute(
    """CREATE TABLE IF NOT EXISTS member_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, ts TEXT)"""
)
db.commit()

SLOT_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def today_str() -> str:
    return dt.datetime.now(TZ).strftime("%Y-%m-%d")


def now_ts() -> str:
    return dt.datetime.now(TZ).strftime("%H:%M:%S")


def mention(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={uid}">{html.escape(name)}</a>'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🗓️ Group Admin ဇယားဘော့\n\n"
        "Admin တွေ - DM ထဲမှာ ဒီနေ့ run မယ့်အချိန်ကို ပို့ပါ\n"
        "ဥပမာ: 14:00-18:00\n\n"
        "/myid - ကိုယ့် Telegram id ကြည့်မယ်\n"
        "/groupid - (group ထဲမှာ ပို့ပါ) group id ကြည့်မယ်\n"
        "/today - ဒီနေ့ schedule ကြည့်မယ်"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Telegram id: {update.effective_user.id}")


async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Group id: {update.effective_chat.id}")


async def today_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.execute(
        "SELECT admins.name, slots.start, slots.end FROM slots "
        "JOIN admins ON admins.id = slots.admin_id WHERE slots.date=? ORDER BY slots.start",
        (today_str(),),
    ).fetchall()
    if not rows:
        await update.message.reply_text("ဒီနေ့အတွက် admin ဘယ်သူမှ အချိန်မတင်ရသေးပါ")
        return
    body = "\n".join(f"⏰ {s} - {e}  {n}" for n, s, e in rows)
    await update.message.reply_text(
        f"🗓️ <b>ဒီနေ့ schedule</b>\n{DIVIDER}\n{body}", parse_mode=ParseMode.HTML
    )


# ---------- Admin က DM ထဲမှာ အချိန်ပို့တာ ----------
async def dm_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return
    m = SLOT_RE.match(update.message.text)
    if not m:
        await update.message.reply_text("အချိန်ပုံစံ: 14:00-18:00 လို့ ပို့ပါ")
        return
    sh, sm, eh, em = m.groups()
    start_s = f"{int(sh):02d}:{sm}"
    end_s = f"{int(eh):02d}:{em}"
    name = update.effective_user.full_name
    date = today_str()

    db.execute("INSERT OR REPLACE INTO admins (id, name) VALUES (?, ?)", (uid, name))
    db.execute(
        "INSERT INTO slots (admin_id, date, start, end) VALUES (?, ?, ?, ?)",
        (uid, date, start_s, end_s),
    )
    db.commit()

    await update.message.reply_text(f"✅ မှတ်ထားပါပြီ - {start_s} - {end_s}")
    await context.bot.send_message(
        GROUP_ID,
        f"🗓️ <b>{html.escape(name)}</b> ဒီနေ့ run မည့်အချိန်\n"
        f"⏰ {start_s} - {end_s}",
        parse_mode=ParseMode.HTML,
    )

    start_dt = dt.datetime.strptime(f"{date} {start_s}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    if start_dt > dt.datetime.now(TZ) and context.job_queue:
        context.job_queue.run_once(
            mention_job, when=start_dt, data={"admin_id": uid, "name": name}
        )


async def mention_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    tag = mention(data["admin_id"], data["name"])
    for _ in range(3):
        await context.bot.send_message(
            GROUP_ID, f"🔔 {tag} run ချိန် ရောက်ပါပြီ!", parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(1)


# ---------- Group ထဲက admin message တွေကို "run" အဖြစ် မှတ်တမ်းတင်ခြင်း ----------
async def group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        db.execute(
            "INSERT INTO activity (admin_id, date, ts) VALUES (?, ?, ?)",
            (uid, today_str(), now_ts()),
        )
        db.commit()


# ---------- Member ဝင်/ထွက် ----------
async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    date, ts = today_str(), now_ts()
    if msg.new_chat_members:
        for _ in msg.new_chat_members:
            db.execute(
                "INSERT INTO member_events (date, type, ts) VALUES (?, 'join', ?)", (date, ts)
            )
    if msg.left_chat_member:
        db.execute(
            "INSERT INTO member_events (date, type, ts) VALUES (?, 'leave', ?)", (date, ts)
        )
    db.commit()


# ---------- ၁၂ နာရီတစ်ခါ အဝင်အထွက် report ----------
async def report_12h(context: ContextTypes.DEFAULT_TYPE):
    since = (dt.datetime.now(TZ) - dt.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(
        "SELECT type, COUNT(*) FROM member_events WHERE (date || ' ' || ts) >= ? GROUP BY type",
        (since,),
    ).fetchall()
    counts = {"join": 0, "leave": 0}
    for t, c in rows:
        counts[t] = c
    await context.bot.send_message(
        GROUP_ID,
        f"👥 <b>လွန်ခဲ့တဲ့ ၁၂ နာရီ</b>\n{DIVIDER}\n"
        f"➕ ဝင်လာသူ - <b>{counts['join']}</b>\n"
        f"➖ ထွက်သွားသူ - <b>{counts['leave']}</b>",
        parse_mode=ParseMode.HTML,
    )


# ---------- အပတ်စဉ် အစီရင်ခံစာ ----------
async def report_weekly(context: ContextTypes.DEFAULT_TYPE):
    now = dt.datetime.now(TZ)
    week_start = (now - dt.timedelta(days=6)).strftime("%Y-%m-%d")

    admins = db.execute("SELECT id, name FROM admins").fetchall()
    lines = []
    for aid, name in admins:
        slots = db.execute(
            "SELECT date, start, end FROM slots WHERE admin_id=? AND date >= ?",
            (aid, week_start),
        ).fetchall()
        total = len(slots)
        ran = 0
        for date, s, e in slots:
            cnt = db.execute(
                "SELECT COUNT(*) FROM activity WHERE admin_id=? AND date=? AND ts BETWEEN ? AND ?",
                (aid, date, f"{s}:00", f"{e}:59"),
            ).fetchone()[0]
            if cnt > 0:
                ran += 1
        mark = "✅" if total and ran == total else ("⚠️" if ran else "❌")
        lines.append(f"{mark} {html.escape(name)} - {ran}/{total} ကြိမ် run ခဲ့")
    admin_report = "\n".join(lines) or "admin မှတ်တမ်း မရှိသေးပါ"

    day_lines = []
    for i in range(7):
        d = (now - dt.timedelta(days=6 - i)).strftime("%Y-%m-%d")
        j = db.execute(
            "SELECT COUNT(*) FROM member_events WHERE date=? AND type='join'", (d,)
        ).fetchone()[0]
        l = db.execute(
            "SELECT COUNT(*) FROM member_events WHERE date=? AND type='leave'", (d,)
        ).fetchone()[0]
        day_lines.append(f"{d} - ➕{j}  ➖{l}")
    member_report = "\n".join(day_lines)

    text = (
        f"📊 <b>အပတ်စဉ် အစီရင်ခံစာ</b>\n{DIVIDER}\n"
        f"<b>Admin Run မှတ်တမ်း</b>\n{admin_report}\n\n"
        f"<b>အဖွဲ့ဝင် အဝင်အထွက် (နေ့စဉ်)</b>\n{member_report}"
    )
    await context.bot.send_message(GROUP_ID, text, parse_mode=ParseMode.HTML)


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("groupid", groupid))
    app.add_handler(CommandHandler("today", today_schedule))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, dm_text)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, group_text)
    )
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
            member_update,
        )
    )

    jq = app.job_queue
    jq.run_repeating(report_12h, interval=dt.timedelta(hours=12), first=dt.timedelta(seconds=15))
    jq.run_daily(report_weekly, time=dt.time(hour=21, minute=0, tzinfo=TZ), days=(6,))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
