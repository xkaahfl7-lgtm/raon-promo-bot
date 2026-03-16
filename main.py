import discord
from discord.ext import commands, tasks
import os
import sqlite3
import calendar
from datetime import datetime, date
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235

PROMO_CHANNEL = 1465360797311172730
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419
REWARD_CHANNEL = 1481209215849726075

DB_FILE = "promo_data.db"
KST = ZoneInfo("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def now():
    return datetime.now(KST)


def get_month_start(dt=None):
    if dt is None:
        dt = now()
    return date(dt.year, dt.month, 1)


def get_month_end(month_start):
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return date(month_start.year, month_start.month, last_day)


def get_next_month_start(month_start):
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def month_label(month_start):
    month_end = get_month_end(month_start)
    return f"{month_start.month:02d}월 {month_start.day:02d}일 ~ {month_end.month:02d}월 {month_end.day:02d}일 기록현황"


def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY
        )
    """)

    conn.commit()

    if get_meta("month_start") is None:
        set_meta("month_start", str(get_month_start()))

    if get_meta("rank_message_id") is None:
        set_meta("rank_message_id", "")

    if get_meta("last_finalized_month") is None:
        set_meta("last_finalized_month", "")

    conn.close()


def get_meta(key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_meta(key: str, value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, value))
    conn.commit()
    conn.close()


def get_users_sorted():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, count FROM users ORDER BY count DESC, name ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def upsert_user_count(user_id: str, name: str, add_count: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row:
        new_count = int(row[0]) + add_count
        cur.execute(
            "UPDATE users SET name = ?, count = ? WHERE user_id = ?",
            (name, new_count, user_id)
        )
    else:
        cur.execute(
            "INSERT INTO users (user_id, name, count) VALUES (?, ?, ?)",
            (user_id, name, add_count)
        )

    conn.commit()
    conn.close()


def clear_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users")
    conn.commit()
    conn.close()


def is_message_processed(message_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_message_processed(message_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
        (message_id,)
    )
    conn.commit()
    conn.close()


async def send_log(text):
    print(text)
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text)
        except Exception:
            pass


def get_name(guild, user_id, fallback="Unknown"):
    member = guild.get_member(int(user_id))
    if member:
        return member.display_name
    return fallback


def build_board_text(guild):
    month_start_str = get_meta("month_start")
    if not month_start_str:
        month_start_str = str(get_month_start())
        set_meta("month_start", month_start_str)

    month_start = date.fromisoformat(month_start_str)
    label = month_label(month_start)

    rows = get_users_sorted()
    lines = [f"🏆 {label}", ""]

    if not rows:
        lines.append("데이터 없음")
        return "\n".join(lines)

    lines.append("📊 홍보 횟수")
    for user_id, saved_name, count in rows:
        name = get_name(guild, user_id, saved_name or "Unknown")
        lines.append(f"{name} — {count}회")

    lines.append("")
    lines.append("🏆 홍보 랭킹")
    for idx, (user_id, saved_name, count) in enumerate(rows[:10], start=1):
        name = get_name(guild, user_id, saved_name or "Unknown")
        lines.append(f"{idx}위 {name} — {count}회")

    text = "\n".join(lines)
    if len(text) > 1900:
        return text[:1900]
    return text


async def update_board(guild):
    channel = bot.get_channel(RANK_CHANNEL)

    if not channel:
        await send_log("오류 | 랭킹 채널 없음")
        return

    text = build_board_text(guild)
    message_id = get_meta("rank_message_id")

    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=text)
            return
        except Exception:
            pass

    try:
        msg = await channel.send(text)
        set_meta("rank_message_id", str(msg.id))
    except Exception as e:
        await send_log(f"랭킹 생성 실패 | {e}")


def count_images(message):
    count = 0

    for attachment in message.attachments:
        filename = attachment.filename.lower()
        if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
            count += 1

    for embed in message.embeds:
        if embed.image or embed.thumbnail:
            count += 1

    return min(count, 30)


async def backfill_promo_messages(guild, limit=200):
    channel = bot.get_channel(PROMO_CHANNEL)

    if not channel:
        await send_log("오류 | 홍보 채널 없음")
        return

    recovered_messages = 0
    recovered_images = 0

    async for message in channel.history(limit=limit, oldest_first=True):
        if message.author.bot:
            continue

        if message.guild is None:
            continue

        if message.guild.id != GUILD_ID:
            continue

        image_count = count_images(message)
        if image_count <= 0:
            continue

        if is_message_processed(str(message.id)):
            continue

        user_id = str(message.author.id)
        username = message.author.display_name

        upsert_user_count(user_id, username, image_count)
        mark_message_processed(str(message.id))

        recovered_messages += 1
        recovered_images += image_count

    await update_board(guild)
    await send_log(
        f"누락 복구 완료 | 최근 {limit}개 메시지 검사 | "
        f"복구 메시지 {recovered_messages}개 | 복구 이미지 {recovered_images}개"
    )


@bot.event
async def on_ready():
    init_db()
    print(f"홍보봇 실행됨: {bot.user}")
    await send_log("홍보봇 활성화")

    guild = bot.get_guild(GUILD_ID)
    if guild:
        await backfill_promo_messages(guild, limit=200)
        await update_board(guild)

    if not month_check.is_running():
        month_check.start()


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    if message.guild.id != GUILD_ID:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    image_count = count_images(message)

    if image_count <= 0:
        return

    if is_message_processed(str(message.id)):
        return

    user_id = str(message.author.id)
    username = message.author.display_name

    upsert_user_count(user_id, username, image_count)
    mark_message_processed(str(message.id))

    await send_log(f"{username} 홍보 인증 (+{image_count})")
    await update_board(message.guild)

    await bot.process_commands(message)


@tasks.loop(minutes=1)
async def month_check():
    # 월 변경 감지용
    month_start_str = get_meta("month_start")
    if not month_start_str:
        set_meta("month_start", str(get_month_start()))
        return

    saved_month_start = date.fromisoformat(month_start_str)
    current_month_start = get_month_start()

    if saved_month_start == current_month_start:
        return

    guild = bot.get_guild(GUILD_ID)

    # 새 달 시작 시 데이터 초기화
    clear_users()
    set_meta("month_start", str(current_month_start))
    set_meta("rank_message_id", "")

    if guild:
        await send_log(f"월 변경 감지 | {current_month_start.month:02d}월 기록으로 초기화")
        await update_board(guild)


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("환경변수 TOKEN 이 비어 있습니다. Railway Variables에 TOKEN을 넣어주세요.")

    bot.run(TOKEN)
