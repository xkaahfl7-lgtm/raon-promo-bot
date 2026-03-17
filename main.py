import discord
from discord.ext import commands
import os
import sqlite3
import re
import unicodedata
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235
PROMO_CHANNEL = 1465360797311172730
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419

DB_FILE = "promo.db"
KST = ZoneInfo("Asia/Seoul")

# 새로 시작할 때 들어갈 시작값
BASELINE = {
    "IGㆍ봉식": 97,
    "AMㆍ우진": 66,
    "@alroo💥": 8,
    "STAFFㆍ⭐호랭": 6,
    "STAFFㆍ⭐백구": 3,
}

PREFERRED_DISPLAY = {
    "봉식": "IGㆍ봉식",
    "우진": "AMㆍ우진",
    "alroo": "@alroo💥",
    "호랭": "STAFFㆍ⭐호랭",
    "백구": "STAFFㆍ⭐백구",
}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_name(name: str) -> str:
    if not name:
        return ""

    text = unicodedata.normalize("NFKC", str(name)).strip().lower()
    text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
    text = text.replace("(", "").replace(")", "")
    text = text.replace("⭐", "")
    text = re.sub(r'^@+', '', text)

    text = re.sub(
        r'^(gm|dgm|am|im|ig|staff|dev|admin|mod)[\s\-_ㆍ·|/\\]*',
        '',
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r'\s+', '', text)
    text = re.sub(r'[^0-9a-z가-힣]', '', text)

    alias_map = {
        "봉식": "봉식",
        "bongsik": "봉식",
        "우진": "우진",
        "woojin": "우진",
        "ujin": "우진",
        "alroo": "alroo",
        "호랭": "호랭",
        "백구": "백구",
    }

    return alias_map.get(text, text)


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()

        cur.execute("SELECT value FROM meta WHERE key = 'baseline_applied'")
        row = cur.fetchone()

        if not row:
            for idx, (name, count) in enumerate(BASELINE.items(), start=1):
                cur.execute("""
                    INSERT OR REPLACE INTO users (user_id, display_name, count)
                    VALUES (?, ?, ?)
                """, (f"baseline_{idx}", name, count))

            cur.execute("""
                INSERT OR REPLACE INTO meta (key, value)
                VALUES ('baseline_applied', 'done')
            """)

            conn.commit()


def is_processed(message_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,))
        return cur.fetchone() is not None


def mark_processed(message_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,)
        )
        conn.commit()


def add_count(user_id: str, display_name: str, count: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row:
            new_count = int(row["count"]) + int(count)
            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (display_name, new_count, user_id))
        else:
            cur.execute("""
                INSERT INTO users (user_id, display_name, count)
                VALUES (?, ?, ?)
            """, (user_id, display_name, int(count)))

        conn.commit()


def get_all_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, display_name, count FROM users")
        return cur.fetchall()


def build_rows():
    grouped = {}

    for row in get_all_users():
        user_id = str(row["user_id"])
        display_name = row["display_name"]
        count = int(row["count"])

        key = normalize_name(display_name)
        if not key:
            key = f"user_{user_id}"

        if key not in grouped:
            grouped[key] = {
                "display_name": display_name,
                "count": 0
            }

        grouped[key]["count"] += count

        if key in PREFERRED_DISPLAY:
            grouped[key]["display_name"] = PREFERRED_DISPLAY[key]

    rows = []
    for key, value in grouped.items():
        rows.append({
            "key": key,
            "display_name": value["display_name"],
            "count": value["count"]
        })

    rows.sort(key=lambda x: (-x["count"], x["display_name"]))
    return rows


def build_board_text():
    rows = build_rows()

    lines = ["🏆 홍보 랭킹", ""]

    if not rows:
        lines.append("데이터 없음")
    else:
        lines.append("📊 홍보 횟수")
        for row in rows:
            lines.append(f"{row['display_name']} — {row['count']}회")

        lines.append("")
        lines.append("🏆 홍보 랭킹")
        for idx, row in enumerate(rows[:10], start=1):
            lines.append(f"{idx}위 {row['display_name']} — {row['count']}회")

    return "\n".join(lines)[:1900]


async def send_log(text: str):
    print(text)
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text)
        except Exception:
            pass


async def update_board():
    channel = bot.get_channel(RANK_CHANNEL)
    if not channel:
        await send_log("오류 | 랭킹 채널 없음")
        return

    text = build_board_text()

    try:
        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.edit(content=text)
                return
        await channel.send(text)
    except Exception as e:
        await send_log(f"오류 | 랭킹 업데이트 실패 | {e}")


def count_images(message: discord.Message) -> int:
    count = 0

    for attachment in message.attachments:
        filename = attachment.filename.lower()
        if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
            count += 1

    for embed in message.embeds:
        if embed.image or embed.thumbnail:
            count += 1

    return min(count, 30)


@bot.event
async def on_ready():
    init_db()
    await send_log("🤖 RAON 홍보봇이 정상적으로 실행되었습니다.")
    await update_board()
    print(f"로그인 완료: {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None or message.guild.id != GUILD_ID:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    message_id = str(message.id)
    if is_processed(message_id):
        return

    image_count = count_images(message)
    if image_count <= 0:
        return

    try:
        add_count(str(message.author.id), message.author.display_name, image_count)
        mark_processed(message_id)
        await send_log(f"홍보 인증 | {message.author.display_name} (+{image_count})")
        await update_board()
    except Exception as e:
        await send_log(f"오류 | 홍보 집계 실패 | {message.author.display_name} | {e}")

    await bot.process_commands(message)


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("환경변수 TOKEN 이 비어 있습니다.")

    bot.run(TOKEN)
