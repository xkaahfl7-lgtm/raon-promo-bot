import discord
from discord.ext import commands, tasks
import os
import sqlite3
import calendar
import re
import unicodedata
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

# 기존 누적값(초기 복구값)
# 여기 적힌 값은 "별도 유저"로 저장하지 않고
# 보드 만들 때 실제 유저 기록과 합산됩니다.
BASELINE_COUNTS = {
    "봉식": 44,
    "우진": 36,
    "@𝖆𝖑𝖗𝖔𝖔💥": 8,
}

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


def month_label(month_start):
    month_end = get_month_end(month_start)
    return f"{month_start.month:02d}월 {month_start.day:02d}일 ~ {month_end.month:02d}월 {month_end.day:02d}일 기록현황"


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    with get_conn() as conn:
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
                display_name TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                last_seen TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY
            )
        """)

        conn.commit()

    ensure_column_exists("users", "display_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column_exists("users", "last_seen", "TEXT")
    migrate_old_name_column_if_needed()

    if get_meta("month_start") is None:
        set_meta("month_start", str(get_month_start()))

    if get_meta("rank_message_id") is None:
        set_meta("rank_message_id", "")

    if get_meta("last_finalized_month") is None:
        set_meta("last_finalized_month", "")


def ensure_column_exists(table_name: str, column_name: str, column_type_sql: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = [row["name"] for row in cur.fetchall()]
        if column_name not in columns:
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type_sql}")
            conn.commit()


def migrate_old_name_column_if_needed():
    """
    예전 users(name) 구조를 users(display_name) 구조로 자동 보정
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cur.fetchall()]

        if "name" in columns:
            try:
                cur.execute("""
                    UPDATE users
                    SET display_name = name
                    WHERE (display_name IS NULL OR display_name = '')
                """)
                conn.commit()
            except Exception:
                pass


def get_meta(key: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()


def clear_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM users")
        conn.commit()


def clear_processed_messages():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM processed_messages")
        conn.commit()


def is_message_processed(message_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,))
        row = cur.fetchone()
        return row is not None


def mark_message_processed(message_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,)
        )
        conn.commit()


def upsert_user_count(user_id: str, display_name: str, add_count: int):
    now_iso = now().isoformat()

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row:
            new_count = int(row["count"]) + int(add_count)
            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?, last_seen = ?
                WHERE user_id = ?
            """, (display_name, new_count, now_iso, user_id))
        else:
            cur.execute("""
                INSERT INTO users (user_id, display_name, count, last_seen)
                VALUES (?, ?, ?, ?)
            """, (user_id, display_name, int(add_count), now_iso))

        conn.commit()


def get_all_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, display_name, count, last_seen
            FROM users
        """)
        return cur.fetchall()


def normalize_person_key(name: str) -> str:
    """
    중복 이름 자동 정리용 핵심 함수
    예:
    IGㆍ봉식 -> 봉식
    AMㆍ우진 -> 우진
    @𝖆𝖑𝖗𝖔𝖔💥 -> alroo
    """
    if not name:
        return ""

    text = unicodedata.normalize("NFKC", str(name)).strip().lower()

    # 앞쪽 직급/역할 제거
    # 예: IGㆍ봉식 / AM·우진 / STAFF_누구 / DEV-누구
    text = re.sub(
        r'^(gm|dgm|am|im|ig|staff|dev|admin|mod)[\s\-_ㆍ·|/\\]*',
        '',
        text,
        flags=re.IGNORECASE
    )

    # 맨 앞 @ 제거
    text = re.sub(r'^@+', '', text)

    # 특수문자 제거
    text = re.sub(r'[^0-9a-z가-힣]', '', text)

    return text


def choose_better_display_name(old_name: str, new_name: str) -> str:
    """
    표시명은 가능하면 실제 최신 닉네임 느낌이 나는 쪽으로 유지
    """
    if not old_name:
        return new_name
    if not new_name:
        return old_name

    # 직급 포함 이름을 우선으로
    old_score = score_display_name(old_name)
    new_score = score_display_name(new_name)

    if new_score > old_score:
        return new_name
    return old_name


def score_display_name(name: str) -> int:
    score = 0
    text = unicodedata.normalize("NFKC", str(name)).strip()

    if re.search(r'^(GM|DGM|AM|IM|IG|STAFF|DEV)[\s\-_ㆍ·|/\\]*', text, re.IGNORECASE):
        score += 10
    if len(text) >= 2:
        score += 1
    if "@" in text:
        score += 1
    return score


def build_aggregated_rows():
    """
    user_id별 저장 데이터 + BASELINE_COUNTS 를
    사람 기준으로 자동 합산해서 표시용 랭킹 생성
    """
    grouped = {}

    # 1) baseline 먼저 넣기
    for raw_name, base_count in BASELINE_COUNTS.items():
        key = normalize_person_key(raw_name)
        if not key:
            continue

        grouped[key] = {
            "display_name": raw_name,
            "count": int(base_count),
            "user_ids": set(),
            "last_seen": ""
        }

    # 2) 실제 DB 유저 합산
    rows = get_all_users()
    for row in rows:
        user_id = str(row["user_id"])
        display_name = row["display_name"]
        count = int(row["count"])
        last_seen = row["last_seen"] or ""

        key = normalize_person_key(display_name)
        if not key:
            key = f"user_{user_id}"

        if key not in grouped:
            grouped[key] = {
                "display_name": display_name,
                "count": 0,
                "user_ids": set(),
                "last_seen": last_seen
            }

        grouped[key]["count"] += count
        grouped[key]["user_ids"].add(user_id)
        grouped[key]["display_name"] = choose_better_display_name(
            grouped[key]["display_name"],
            display_name
        )

        if last_seen > grouped[key]["last_seen"]:
            grouped[key]["last_seen"] = last_seen

    # 3) 정렬
    result = []
    for key, value in grouped.items():
        result.append({
            "person_key": key,
            "display_name": value["display_name"],
            "count": int(value["count"]),
            "last_seen": value["last_seen"]
        })

    result.sort(key=lambda x: (-x["count"], x["display_name"]))
    return result


async def send_log(text):
    print(text)
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text)
        except Exception:
            pass


def build_board_text():
    month_start_str = get_meta("month_start")
    if not month_start_str:
        month_start_str = str(get_month_start())
        set_meta("month_start", month_start_str)

    month_start = date.fromisoformat(month_start_str)
    label = month_label(month_start)

    rows = build_aggregated_rows()

    lines = [f"🏆 {label}", ""]

    if not rows:
        lines.append("데이터 없음")
        return "\n".join(lines)

    lines.append("📊 홍보 횟수")
    for row in rows:
        lines.append(f"{row['display_name']} — {row['count']}회")

    lines.append("")
    lines.append("🏆 홍보 랭킹")
    for idx, row in enumerate(rows[:10], start=1):
        lines.append(f"{idx}위 {row['display_name']} — {row['count']}회")

    text = "\n".join(lines)
    if len(text) > 1900:
        return text[:1900]
    return text


async def update_board():
    channel = bot.get_channel(RANK_CHANNEL)

    if not channel:
        await send_log("오류 | 랭킹 채널 없음")
        return

    text = build_board_text()
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


@bot.event
async def on_ready():
    init_db()
    print(f"홍보봇 실행됨: {bot.user}")
    await send_log("🤖 RAON 홍보봇이 정상적으로 실행되었습니다.")
    await update_board()

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

    try:
        upsert_user_count(user_id, username, image_count)
        mark_message_processed(str(message.id))
        await send_log(f"홍보 인증 | {username} (+{image_count})")
        await update_board()
    except Exception as e:
        await send_log(f"오류 | 홍보 집계 실패 | {username} | {e}")

    await bot.process_commands(message)


@tasks.loop(minutes=1)
async def month_check():
    month_start_str = get_meta("month_start")
    if not month_start_str:
        set_meta("month_start", str(get_month_start()))
        return

    saved_month_start = date.fromisoformat(month_start_str)
    current_month_start = get_month_start()

    if saved_month_start == current_month_start:
        return

    clear_users()
    clear_processed_messages()

    set_meta("month_start", str(current_month_start))
    set_meta("rank_message_id", "")

    await send_log(f"월 변경 감지 | {current_month_start.month:02d}월 기록으로 초기화")
    await update_board()


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("환경변수 TOKEN 이 비어 있습니다. Railway Variables에 TOKEN을 넣어주세요.")

    bot.run(TOKEN)
