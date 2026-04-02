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

# 시작값
BASELINE = {
    "GUIDE🐣ㆍ봉식": 376,   # 576 - 200
    "AMㆍ우진": 529,        # 519 + 10
    "STAFFㆍ⭐이민우": 101,
    "STAFFㆍ⭐윤콩": 74,
    "@alroo💥": 52,         # 8 + 44
}

# 표시명 우선값
PREFERRED_DISPLAY = {
    "봉식": "GUIDE🐣ㆍ봉식",
    "우진": "AMㆍ우진",
    "이민우": "STAFFㆍ⭐이민우",
    "윤콩": "STAFFㆍ⭐윤콩",
    "alroo": "@alroo💥",
    "알루": "@alroo💥",
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


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
    return text


def normalize_name(name: str) -> str:
    if not name:
        return ""

    raw = normalize_text(name)

    cleaned = raw
    cleaned = cleaned.replace("⭐", "")
    cleaned = cleaned.replace("🐣", "")
    cleaned = cleaned.replace("💥", "")
    cleaned = re.sub(r'^@+', '', cleaned)

    compact = re.sub(r'[\s\-_ㆍ·|/\\()\[\]{}]+', '', cleaned)
    compact = re.sub(r'^(gm|dgm|am|im|ig|guide|staff|dev|admin|mod)+', '', compact, flags=re.IGNORECASE)
    compact = re.sub(r'[^0-9a-z가-힣]', '', compact)

    alias_map = {
        "봉식": "봉식",
        "bongsik": "봉식",
        "우진": "우진",
        "woojin": "우진",
        "ujin": "우진",
        "이민우": "이민우",
        "윤콩": "윤콩",
        "알루": "alroo",
        "alroo": "alroo",
        "혁이": "혁이",
        "호랭": "호랭",
        "백구": "백구",
    }

    return alias_map.get(compact, compact)


def is_old_ig_bongsik(display_name: str) -> bool:
    if not display_name:
        return False
    raw = normalize_text(display_name)
    return ("봉식" in raw) and ("ig" in raw) and ("guide" not in raw)


def is_removed(display_name: str) -> bool:
    key = normalize_name(display_name)
    if key in {"혁이", "호랭", "백구"}:
        return True
    if is_old_ig_bongsik(display_name):
        return True
    return False


def get_preferred_display(name: str) -> str:
    normalized = normalize_name(name)
    return PREFERRED_DISPLAY.get(normalized, name)


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

        cleanup_removed_users()


def cleanup_removed_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, display_name FROM users")
        rows = cur.fetchall()

        deleted = 0
        for row in rows:
            if is_removed(row["display_name"]):
                cur.execute("DELETE FROM users WHERE user_id = ?", (row["user_id"],))
                deleted += 1

        conn.commit()
        return deleted


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
    if is_removed(display_name):
        return False

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        preferred_name = get_preferred_display(display_name)

        if row:
            new_count = int(row["count"]) + int(count)
            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (preferred_name, new_count, user_id))
        else:
            cur.execute("""
                INSERT INTO users (user_id, display_name, count)
                VALUES (?, ?, ?)
            """, (user_id, preferred_name, int(count)))

        conn.commit()
        return True


def find_user_id_by_name(name: str):
    target = normalize_name(name)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, display_name FROM users")
        rows = cur.fetchall()

    for row in rows:
        if normalize_name(row["display_name"]) == target:
            return str(row["user_id"]), row["display_name"]

    return None, None


def manual_adjust_by_name(name: str, amount: int):
    if is_removed(name):
        return False, "삭제 대상 유저는 추가/차감할 수 없습니다."

    user_id, found_name = find_user_id_by_name(name)
    preferred_name = get_preferred_display(name)

    with get_conn() as conn:
        cur = conn.cursor()

        if user_id:
            cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            current = int(row["count"]) if row else 0
            new_count = current + amount

            if new_count < 0:
                new_count = 0

            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (preferred_name, new_count, user_id))
        else:
            if amount < 0:
                return False, "없는 유저는 차감할 수 없습니다."

            manual_id = f"manual_{normalize_name(name)}"
            cur.execute("""
                INSERT OR REPLACE INTO users (user_id, display_name, count)
                VALUES (?, ?, ?)
            """, (manual_id, preferred_name, amount))

        conn.commit()

    return True, preferred_name


def set_count_by_name(name: str, amount: int):
    if is_removed(name):
        return False, "삭제 대상 유저는 설정할 수 없습니다."

    if amount < 0:
        return False, "수량은 0 이상만 가능합니다."

    user_id, found_name = find_user_id_by_name(name)
    preferred_name = get_preferred_display(name)

    with get_conn() as conn:
        cur = conn.cursor()

        if user_id:
            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (preferred_name, amount, user_id))
        else:
            manual_id = f"manual_{normalize_name(name)}"
            cur.execute("""
                INSERT OR REPLACE INTO users (user_id, display_name, count)
                VALUES (?, ?, ?)
            """, (manual_id, preferred_name, amount))

        conn.commit()

    return True, preferred_name


def rename_user(old_name: str, new_name: str):
    if is_removed(new_name):
        return False, "삭제 대상 이름으로 변경할 수 없습니다."

    old_user_id, old_found_name = find_user_id_by_name(old_name)
    if not old_user_id:
        return False, "기존 닉네임을 찾지 못했습니다."

    new_preferred = get_preferred_display(new_name)
    new_key = normalize_name(new_name)

    existing_new_id, existing_new_name = find_user_id_by_name(new_name)

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT count FROM users WHERE user_id = ?", (old_user_id,))
        old_row = cur.fetchone()
        old_count = int(old_row["count"]) if old_row else 0

        if existing_new_id and existing_new_id != old_user_id:
            cur.execute("SELECT count FROM users WHERE user_id = ?", (existing_new_id,))
            new_row = cur.fetchone()
            new_count = int(new_row["count"]) if new_row else 0

            merged = old_count + new_count

            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (new_preferred, merged, existing_new_id))

            cur.execute("DELETE FROM users WHERE user_id = ?", (old_user_id,))
        else:
            cur.execute("""
                UPDATE users
                SET display_name = ?
                WHERE user_id = ?
            """, (new_preferred, old_user_id))

        conn.commit()

    return True, new_preferred


def get_all_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, display_name, count FROM users")
        return cur.fetchall()


def build_rows():
    grouped = {}

    for row in get_all_users():
        display_name = row["display_name"]
        count = int(row["count"])

        if is_removed(display_name):
            continue

        normalized = normalize_name(display_name)
        if not normalized:
            normalized = display_name

        group_key = normalized

        if group_key not in grouped:
            grouped[group_key] = {
                "display_name": get_preferred_display(display_name),
                "count": 0
            }

        grouped[group_key]["count"] += count
        grouped[group_key]["display_name"] = get_preferred_display(display_name)

    rows = list(grouped.values())
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
        except Exception as e:
            print(f"로그 전송 실패: {e}")


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
    removed_count = cleanup_removed_users()
    await send_log(f"🤖 RAON 홍보봇이 정상적으로 실행되었습니다. | 정리된 삭제 대상: {removed_count}명")
    await update_board()
    print(f"로그인 완료: {bot.user}")


@bot.command(name="추가")
@commands.has_permissions(administrator=True)
async def add_manual(ctx, nickname: str, amount: int):
    if amount <= 0:
        await ctx.send("수량은 1 이상만 가능합니다.")
        return

    ok, result = manual_adjust_by_name(nickname, amount)
    if not ok:
        await ctx.send(result)
        return

    await send_log(f"수동 추가 | 관리자: {ctx.author.display_name} | 대상: {result} | +{amount}")
    await update_board()
    await ctx.send(f"✅ {result} 에게 {amount}회 추가 완료")


@bot.command(name="차감")
@commands.has_permissions(administrator=True)
async def subtract_manual(ctx, nickname: str, amount: int):
    if amount <= 0:
        await ctx.send("수량은 1 이상만 가능합니다.")
        return

    ok, result = manual_adjust_by_name(nickname, -amount)
    if not ok:
        await ctx.send(result)
        return

    await send_log(f"수동 차감 | 관리자: {ctx.author.display_name} | 대상: {result} | -{amount}")
    await update_board()
    await ctx.send(f"✅ {result} 에게서 {amount}회 차감 완료")


@bot.command(name="설정")
@commands.has_permissions(administrator=True)
async def set_manual(ctx, nickname: str, amount: int):
    ok, result = set_count_by_name(nickname, amount)
    if not ok:
        await ctx.send(result)
        return

    await send_log(f"수동 설정 | 관리자: {ctx.author.display_name} | 대상: {result} | {amount}회로 설정")
    await update_board()
    await ctx.send(f"✅ {result} 수량을 {amount}회로 설정 완료")


@bot.command(name="이름변경")
@commands.has_permissions(administrator=True)
async def rename_manual(ctx, old_name: str, new_name: str):
    ok, result = rename_user(old_name, new_name)
    if not ok:
        await ctx.send(result)
        return

    await send_log(f"이름 변경 | 관리자: {ctx.author.display_name} | {old_name} → {result}")
    await update_board()
    await ctx.send(f"✅ {old_name} 닉네임을 {result} 으로 변경 완료")


@add_manual.error
@subtract_manual.error
@set_manual.error
@rename_manual.error
async def manual_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("관리자만 사용할 수 있습니다.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("사용법을 다시 확인해주세요.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("수량은 숫자로 입력해주세요.")
    else:
        await send_log(f"명령어 오류 | {type(error).__name__} | {error}")
        await ctx.send("명령어 처리 중 오류가 발생했습니다.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

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
        if is_removed(message.author.display_name):
            await send_log(f"제외됨 | {message.author.display_name} | 삭제 대상 유저")
            mark_processed(message_id)
            return

        success = add_count(str(message.author.id), message.author.display_name, image_count)
        if success:
            mark_processed(message_id)
            await send_log(f"홍보 인증 | {message.author.display_name} (+{image_count})")
            await update_board()

    except Exception as e:
        await send_log(f"오류 | 홍보 집계 실패 | {message.author.display_name} | {e}")


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("환경변수 TOKEN 이 비어 있습니다.")

    bot.run(TOKEN)
