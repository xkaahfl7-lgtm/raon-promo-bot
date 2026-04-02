import discord
from discord.ext import commands
import os
import sqlite3
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235
PROMO_CHANNEL = 1465360797311172730
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419

DB_FILE = "promo.db"
KST = ZoneInfo("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ❌ 제외할 유저 (퇴사자)
REMOVED = ["혁이", "호랭", "백구"]

def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                count INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                message_id TEXT PRIMARY KEY
            )
        """)

def is_removed(name):
    return any(x in name for x in REMOVED)

def add_count(user_id, name, count):
    if is_removed(name):
        return

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row:
            conn.execute(
                "UPDATE users SET display_name=?, count=? WHERE user_id=?",
                (name, row["count"] + count, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?)",
                (user_id, name, count)
            )

def get_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users").fetchall()

def build_board():
    users = get_users()
    users = [u for u in users if not is_removed(u["display_name"])]
    users.sort(key=lambda x: -x["count"])

    text = "🏆 홍보 랭킹\n\n📊 홍보 횟수\n"
    for u in users:
        text += f"{u['display_name']} — {u['count']}회\n"

    text += "\n🏆 홍보 랭킹\n"
    for i, u in enumerate(users[:10], 1):
        text += f"{i}위 {u['display_name']} — {u['count']}회\n"

    return text[:1900]

async def update_board():
    channel = bot.get_channel(RANK_CHANNEL)
    if not channel:
        return

    text = build_board()

    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(content=text)
            return

    await channel.send(text)

async def log(msg):
    print(msg)
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        await channel.send(msg)

def is_processed(mid):
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM processed WHERE message_id=?",
            (mid,)
        ).fetchone()

def mark(mid):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed VALUES (?)",
            (mid,)
        )

def count_images(message):
    return len([a for a in message.attachments if a.filename.endswith(("png","jpg","jpeg","webp","gif"))])

@bot.event
async def on_ready():
    init_db()
    await log("🤖 홍보봇 실행 완료")
    await update_board()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild.id != GUILD_ID:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    if is_processed(str(message.id)):
        return

    count = count_images(message)
    if count == 0:
        return

    try:
        add_count(str(message.author.id), message.author.display_name, count)
        mark(str(message.id))

        await log(f"홍보 +{count} | {message.author.display_name}")

        await update_board()

    except Exception as e:
        await log(f"❌ 오류: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
