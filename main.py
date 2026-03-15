import discord
from discord.ext import commands, tasks
import json
import os
import calendar
from datetime import datetime, date
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235

PROMO_CHANNEL = 1465360797311172730
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419
REWARD_CHANNEL = 1481209215849726075

DATA_FILE = "promo_data.json"
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


def default_data():
    return {
        "users": {},
        "rank_message_id": None,
        "month_start": str(get_month_start()),
        "last_finalized_month": None
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_data()


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


async def send_log(text):
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


def build_board_text(guild, data):
    month_start = date.fromisoformat(data["month_start"])
    label = month_label(month_start)

    users = data["users"]
    sorted_users = sorted(users.items(), key=lambda x: x[1]["count"], reverse=True)

    lines = [f"🏆 {label}", ""]

    if not sorted_users:
        lines.append("데이터 없음")
        return "\n".join(lines)

    lines.append("📊 홍보 횟수")
    for user_id, info in sorted_users:
        name = get_name(guild, user_id, info.get("name", "Unknown"))
        lines.append(f"{name} — {info['count']}회")

    lines.append("")
    lines.append("🏆 홍보 랭킹")
    for idx, (user_id, info) in enumerate(sorted_users[:10], start=1):
        name = get_name(guild, user_id, info.get("name", "Unknown"))
        lines.append(f"{idx}위 {name} — {info['count']}회")

    return "\n".join(lines)


async def update_board(guild):
    data = load_data()
    channel = bot.get_channel(RANK_CHANNEL)

    if not channel:
        return

    text = build_board_text(guild, data)

    message_id = data.get("rank_message_id")
    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(content=text)
            return
        except Exception:
            pass

    msg = await channel.send(text)
    data["rank_message_id"] = msg.id
    save_data(data)


async def finalize_month(guild):
    data = load_data()
    month_start = date.fromisoformat(data["month_start"])
    users = data["users"]

    sorted_users = sorted(users.items(), key=lambda x: x[1]["count"], reverse=True)

    rank_channel = bot.get_channel(RANK_CHANNEL)
    reward_channel = bot.get_channel(REWARD_CHANNEL)

    # 기존 진행중 메시지를 최종 랭킹으로 남기기
    final_lines = [f"🏆 {month_label(month_start)}", "", "월간 홍보 랭킹 마감", ""]
    if not sorted_users:
        final_lines.append("데이터 없음")
    else:
        for idx, (user_id, info) in enumerate(sorted_users[:10], start=1):
            name = get_name(guild, user_id, info.get("name", "Unknown"))
            final_lines.append(f"{idx}위 {name} — {info['count']}회")

    final_text = "\n".join(final_lines)

    if rank_channel:
        try:
            current_msg_id = data.get("rank_message_id")
            if current_msg_id:
                msg = await rank_channel.fetch_message(current_msg_id)
                await msg.edit(content=final_text)
            else:
                await rank_channel.send(final_text)
        except Exception:
            await rank_channel.send(final_text)

    # 보상 메시지
    if sorted_users and reward_channel:
        top3 = []
        for idx, (user_id, info) in enumerate(sorted_users[:3], start=1):
            name = get_name(guild, user_id, info.get("name", "Unknown"))
            top3.append((idx, user_id, name, info["count"]))

        first_idx, first_user_id, first_name, first_count = top3[0]

        reward_lines = [
            f"🎉 {month_label(month_start)}",
            "",
            "월간 홍보 랭킹이 마감되었습니다.",
            ""
        ]

        for idx, _, name, count in top3:
            reward_lines.append(f"{idx}위 {name} — {count}회")

        reward_lines.extend([
            "",
            f"🥇 1위 <@{first_user_id}> ({first_name})님 축하드립니다!",
            "이번 달 홍보 1등 보상은 **현실 보상 5만원**입니다.",
            f"총 홍보 횟수: {first_count}회",
            "",
            "축하드립니다! 🎊"
        ])

        try:
            await reward_channel.send("\n".join(reward_lines))
        except Exception as e:
            await send_log(f"오류 | 보상 메시지 전송 실패 | {e}")

    # 다음 달로 초기화
    data["users"] = {}
    data["rank_message_id"] = None
    data["last_finalized_month"] = str(month_start)
    data["month_start"] = str(get_next_month_start(month_start))
    save_data(data)

    await update_board(guild)
    await send_log(f"월간 홍보 랭킹 마감 완료 | {month_label(month_start)}")


async def ensure_rollover(guild):
    data = load_data()
    stored_month_start = date.fromisoformat(data["month_start"])
    current_month_start = get_month_start()

    if stored_month_start < current_month_start:
        await finalize_month(guild)


@bot.event
async def on_ready():
    print(f"홍보봇 실행됨: {bot.user}")
    await send_log("홍보봇 활성화")

    guild = bot.get_guild(GUILD_ID)
    if guild:
        await ensure_rollover(guild)
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

    image_attachments = []
    for attachment in message.attachments:
        content_type = attachment.content_type or ""
        filename = attachment.filename.lower()

        if content_type.startswith("image/") or filename.endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        ):
            image_attachments.append(attachment)

    if not image_attachments:
        return

    image_count = len(image_attachments)
    if image_count > 10:
        image_count = 10

    data = load_data()
    user_id = str(message.author.id)
    username = message.author.display_name

    if user_id not in data["users"]:
        data["users"][user_id] = {
            "count": 0,
            "name": username
        }

    data["users"][user_id]["count"] += image_count
    data["users"][user_id]["name"] = username

    save_data(data)

    await send_log(f"{username}님이 홍보글을 올렸습니다. (+{image_count})")
    await update_board(message.guild)


@tasks.loop(minutes=1)
async def month_check():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    data = load_data()
    month_start = date.fromisoformat(data["month_start"])
    month_end = get_month_end(month_start)
    current = now()

    if (
        current.date() == month_end
        and current.hour == 23
        and data.get("last_finalized_month") != str(month_start)
    ):
        await finalize_month(guild)


bot.run(TOKEN)
