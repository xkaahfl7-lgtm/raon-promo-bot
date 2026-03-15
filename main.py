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

bot = commands.Bot(command_prefix="!", intents=intents)


def now():
    return datetime.now(KST)


def get_month_start():
    dt = now()
    return date(dt.year, dt.month, 1)


def get_month_end(month_start):
    last = calendar.monthrange(month_start.year, month_start.month)[1]
    return date(month_start.year, month_start.month, last)


def month_label(month_start):
    end = get_month_end(month_start)
    return f"{month_start.month:02d}월 {month_start.day:02d}일 ~ {end.month:02d}월 {end.day:02d}일 기록현황"


def load():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "rank_message": None,
            "month_start": str(get_month_start())
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def update_board(guild):
    data = load()
    users = data["users"]

    rank_channel = bot.get_channel(RANK_CHANNEL)

    month_start = date.fromisoformat(data["month_start"])
    label = month_label(month_start)

    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )

    lines = [f"🏆 {label}", ""]

    if not sorted_users:
        lines.append("데이터 없음")

    else:
        lines.append("📊 홍보 횟수")
        for user_id, info in sorted_users:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else info["name"]
            lines.append(f"{name} — {info['count']}회")

        lines.append("")
        lines.append("🏆 홍보 랭킹")

        for i, (user_id, info) in enumerate(sorted_users[:10], start=1):
            member = guild.get_member(int(user_id))
            name = member.display_name if member else info["name"]
            lines.append(f"{i}위 {name} — {info['count']}회")

    text = "\n".join(lines)

    if data["rank_message"]:
        try:
            msg = await rank_channel.fetch_message(data["rank_message"])
            await msg.edit(content=text)
            return
        except:
            pass

    msg = await rank_channel.send(text)
    data["rank_message"] = msg.id
    save(data)


@bot.event
async def on_ready():
    print("홍보봇 실행")
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await update_board(guild)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    images = [
        a for a in message.attachments
        if a.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        )
    ]

    if not images:
        return

    count = min(len(images), 10)

    data = load()

    uid = str(message.author.id)

    if uid not in data["users"]:
        data["users"][uid] = {
            "count": 0,
            "name": message.author.display_name
        }

    data["users"][uid]["count"] += count
    data["users"][uid]["name"] = message.author.display_name

    save(data)

    log = bot.get_channel(LOG_CHANNEL)
    await log.send(
        f"{message.author.display_name}님이 홍보글을 올렸습니다. (+{count})"
    )

    await update_board(message.guild)


@tasks.loop(minutes=1)
async def month_check():

    data = load()

    month_start = date.fromisoformat(data["month_start"])
    end = get_month_end(month_start)

    now_dt = now()

    if now_dt.date() == end and now_dt.hour == 23:

        users = data["users"]

        sorted_users = sorted(
            users.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        if sorted_users:

            first = sorted_users[0]
            uid = first[0]
            count = first[1]["count"]
            name = first[1]["name"]

            reward = bot.get_channel(REWARD_CHANNEL)

            await reward.send(
                f"🎉 {month_label(month_start)}\n\n"
                f"🥇 1위 <@{uid}> ({name})\n"
                f"총 홍보 횟수 {count}회\n\n"
                f"보상 : 현실 보상 5만원\n"
                f"축하드립니다! 🎊"
            )

        data["users"] = {}
        data["rank_message"] = None

        next_month = date(
            month_start.year + (month_start.month // 12),
            (month_start.month % 12) + 1,
            1
        )

        data["month_start"] = str(next_month)

        save(data)

        guild = bot.get_guild(GUILD_ID)
        await update_board(guild)


month_check.start()

bot.run(TOKEN)
