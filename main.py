import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235

PROMO_CHANNEL = 1465360797311172730
COUNT_CHANNEL = 1481209117824651384
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419
REWARD_CHANNEL = 1481209215849726075  # 여기에 홍보-보상 채널 ID 넣기

DATA_FILE = "promo_data.json"
KST = ZoneInfo("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def now_kst() -> datetime:
    return datetime.now(KST)


def get_week_start(dt: datetime | None = None) -> date:
    if dt is None:
        dt = now_kst()
    return (dt.date() - timedelta(days=dt.weekday()))


def get_next_week_start(start_day: date) -> date:
    return start_day + timedelta(days=7)


def week_label(start_day: date) -> str:
    end_day = get_next_week_start(start_day)
    return f"{start_day.month:02d}월 {start_day.day:02d}일 ~ {end_day.month:02d}월 {end_day.day:02d}일 기록현황"


def default_data():
    return {
        "users_total": {},             # 누적
        "users_weekly": {},            # 주간
        "count_message_id": None,      # 홍보-횟수 현재판
        "current_rank_message_id": None,  # 진행중 홍보 랭킹판
        "current_week_start": str(get_week_start()),
        "last_finalized_week": None
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return default_data()

    # 구버전 호환
    if raw and "users_total" not in raw:
        converted = default_data()
        for user_id, count in raw.items():
            converted["users_total"][str(user_id)] = {
                "count": int(count),
                "name": "Unknown"
            }
            converted["users_weekly"][str(user_id)] = {
                "count": int(count),
                "name": "Unknown"
            }
        return converted

    data = default_data()
    data["users_total"] = raw.get("users_total", {})
    data["users_weekly"] = raw.get("users_weekly", {})
    data["count_message_id"] = raw.get("count_message_id")
    data["current_rank_message_id"] = raw.get("current_rank_message_id")
    data["current_week_start"] = raw.get("current_week_start", str(get_week_start()))
    data["last_finalized_week"] = raw.get("last_finalized_week")
    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


async def send_log(text: str):
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text)
        except Exception:
            pass


def get_member_name(guild: discord.Guild, user_id: int, fallback: str = "Unknown") -> str:
    member = guild.get_member(user_id)
    if member:
        return member.display_name
    return fallback


async def get_or_create_message(channel: discord.TextChannel, message_id: int | None, default_text: str):
    if message_id:
        try:
            return await channel.fetch_message(message_id)
        except Exception:
            pass
    return await channel.send(default_text)


def build_count_text(guild: discord.Guild, data) -> str:
    start_day = date.fromisoformat(data["current_week_start"])
    label = week_label(start_day)

    weekly = data["users_weekly"]
    if not weekly:
        return f"📊 {label}\n\n데이터 없음"

    sorted_users = sorted(
        weekly.items(),
        key=lambda x: x[1].get("count", 0),
        reverse=True
    )

    lines = [f"📊 {label}", ""]
    for user_id, info in sorted_users:
        name = get_member_name(guild, int(user_id), info.get("name", "Unknown"))
        lines.append(f"{name} — {info.get('count', 0)}회")

    return "\n".join(lines)


def build_rank_text(guild: discord.Guild, data) -> str:
    start_day = date.fromisoformat(data["current_week_start"])
    label = week_label(start_day)

    weekly = data["users_weekly"]
    if not weekly:
        return f"🏆 {label}\n\n진행중 홍보 랭킹\n\n데이터 없음"

    sorted_users = sorted(
        weekly.items(),
        key=lambda x: x[1].get("count", 0),
        reverse=True
    )

    lines = [f"🏆 {label}", "", "진행중 홍보 랭킹", ""]
    for idx, (user_id, info) in enumerate(sorted_users, start=1):
        name = get_member_name(guild, int(user_id), info.get("name", "Unknown"))
        lines.append(f"{idx}위 {name} — {info.get('count', 0)}회")

    return "\n".join(lines)


def build_final_rank_text(guild: discord.Guild, data, start_day: date) -> str:
    label = week_label(start_day)
    weekly = data["users_weekly"]

    sorted_users = sorted(
        weekly.items(),
        key=lambda x: x[1].get("count", 0),
        reverse=True
    )

    lines = [f"🏆 {label}", "", "주간 홍보 랭킹 마감", ""]
    if not sorted_users:
        lines.append("데이터 없음")
        return "\n".join(lines)

    for idx, (user_id, info) in enumerate(sorted_users[:10], start=1):
        name = get_member_name(guild, int(user_id), info.get("name", "Unknown"))
        lines.append(f"{idx}위 {name} — {info.get('count', 0)}회")

    return "\n".join(lines)


async def update_boards(guild: discord.Guild):
    data = load_data()

    count_channel = bot.get_channel(COUNT_CHANNEL)
    rank_channel = bot.get_channel(RANK_CHANNEL)

    if not count_channel or not rank_channel:
        return

    count_text = build_count_text(guild, data)
    rank_text = build_rank_text(guild, data)

    count_msg = await get_or_create_message(
        count_channel,
        data.get("count_message_id"),
        count_text
    )
    try:
        await count_msg.edit(content=count_text)
    except Exception:
        pass
    data["count_message_id"] = count_msg.id

    rank_msg = await get_or_create_message(
        rank_channel,
        data.get("current_rank_message_id"),
        rank_text
    )
    try:
        await rank_msg.edit(content=rank_text)
    except Exception:
        pass
    data["current_rank_message_id"] = rank_msg.id

    save_data(data)


async def finalize_week(guild: discord.Guild):
    data = load_data()

    current_week_start = date.fromisoformat(data["current_week_start"])
    final_text = build_final_rank_text(guild, data, current_week_start)

    rank_channel = bot.get_channel(RANK_CHANNEL)
    reward_channel = bot.get_channel(REWARD_CHANNEL) if REWARD_CHANNEL else None

    # 현재 진행중 랭킹 메시지를 "마감 결과"로 바꿔서 그대로 남김
    final_msg = None
    current_rank_message_id = data.get("current_rank_message_id")
    if current_rank_message_id and rank_channel:
        try:
            final_msg = await rank_channel.fetch_message(current_rank_message_id)
            await final_msg.edit(content=final_text)
        except Exception:
            final_msg = await rank_channel.send(final_text)
    elif rank_channel:
        final_msg = await rank_channel.send(final_text)

    weekly = data["users_weekly"]
    sorted_users = sorted(
        weekly.items(),
        key=lambda x: x[1].get("count", 0),
        reverse=True
    )

    if sorted_users and reward_channel:
        top_3 = []
        for idx, (user_id, info) in enumerate(sorted_users[:3], start=1):
            name = get_member_name(guild, int(user_id), info.get("name", "Unknown"))
            top_3.append((idx, name, info.get("count", 0)))

        reward_lines = [
            f"🎉 {week_label(current_week_start)}",
            "",
            "주간 홍보 랭킹이 마감되었습니다.",
            ""
        ]

        for idx, name, count in top_3:
            reward_lines.append(f"{idx}위 {name} — {count}회")

        first_name = top_3[0][1]
        first_count = top_3[0][2]

        reward_lines.extend([
            "",
            f"🥇 1위 {first_name}님 축하드립니다!",
            f"이번 주 홍보 1등 보상은 **현실 보상 5만원**입니다.",
            f"총 홍보 횟수: {first_count}회"
        ])

        try:
            await reward_channel.send("\n".join(reward_lines))
        except Exception as e:
            await send_log(f"오류 | 보상 메시지 전송 실패 | {e}")

    data["last_finalized_week"] = str(current_week_start)
    data["users_weekly"] = {}
    data["current_week_start"] = str(get_next_week_start(current_week_start))
    data["current_rank_message_id"] = None
    save_data(data)

    await update_boards(guild)
    await send_log(f"주간 홍보 랭킹 마감 완료 | {week_label(current_week_start)}")


async def ensure_rollover(guild: discord.Guild):
    data = load_data()
    stored_week_start = date.fromisoformat(data["current_week_start"])
    current_real_week_start = get_week_start()

    # 봇이 꺼져있다가 다음 주가 되었으면 이전 주 마감 처리
    if stored_week_start < current_real_week_start:
        await finalize_week(guild)


@bot.event
async def on_ready():
    print(f"홍보봇 실행됨: {bot.user}")
    await send_log("홍보봇 활성화")
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await ensure_rollover(guild)
        await update_boards(guild)

    if not sunday_finalize_loop.is_running():
        sunday_finalize_loop.start()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    if message.guild.id != GUILD_ID:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    image_attachments = []
    for attachment in message.attachments:
        content_type = attachment.content_type or ""
        filename = attachment.filename.lower()

        if content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
            image_attachments.append(attachment)

    if not image_attachments:
        return

    image_count = len(image_attachments)
    if image_count > 10:
        image_count = 10

    data = load_data()
    user_id = str(message.author.id)
    username = message.author.display_name

    if user_id not in data["users_total"]:
        data["users_total"][user_id] = {"count": 0, "name": username}
    if user_id not in data["users_weekly"]:
        data["users_weekly"][user_id] = {"count": 0, "name": username}

    data["users_total"][user_id]["count"] += image_count
    data["users_total"][user_id]["name"] = username

    data["users_weekly"][user_id]["count"] += image_count
    data["users_weekly"][user_id]["name"] = username

    save_data(data)

    await send_log(f"{username}님이 홍보글을 올렸습니다. (+{image_count})")
    await update_boards(message.guild)


@tasks.loop(minutes=1)
async def sunday_finalize_loop():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    now = now_kst()
    data = load_data()
    stored_week_start = date.fromisoformat(data["current_week_start"])

    # 매주 일요일 23:00 자동 마감
    if now.weekday() == 6 and now.hour == 23 and data.get("last_finalized_week") != str(stored_week_start):
        await finalize_week(guild)


bot.run(TOKEN)
