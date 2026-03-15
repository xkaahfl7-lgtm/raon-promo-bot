import discord
from discord.ext import commands
import json
import os
from typing import Dict, Any

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235

PROMO_CHANNEL = 1465360797311172730
COUNT_CHANNEL = 1481209117824651384
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419

DATA_FILE = "promo_data.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def default_data() -> Dict[str, Any]:
    return {
        "users": {},
        "count_message_id": None,
        "rank_message_id": None
    }


def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return default_data()

    # 예전 데이터 형식 호환
    # {"12345": 3, "67890": 5}
    if raw and "users" not in raw:
        converted = default_data()
        for user_id, count in raw.items():
            converted["users"][str(user_id)] = {
                "count": int(count),
                "name": "Unknown"
            }
        return converted

    # 새 형식 보정
    data = default_data()
    data["count_message_id"] = raw.get("count_message_id")
    data["rank_message_id"] = raw.get("rank_message_id")

    users = raw.get("users", {})
    for user_id, info in users.items():
        if isinstance(info, dict):
            data["users"][str(user_id)] = {
                "count": int(info.get("count", 0)),
                "name": info.get("name", "Unknown")
            }
        else:
            data["users"][str(user_id)] = {
                "count": int(info),
                "name": "Unknown"
            }

    return data


def save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_display_name(guild: discord.Guild, user_id: int, fallback: str = "Unknown") -> str:
    member = guild.get_member(user_id)
    if member:
        return member.display_name
    return fallback


async def get_or_create_board_message(channel: discord.TextChannel, message_id: int | None, default_text: str) -> discord.Message:
    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
            return msg
        except Exception:
            pass

    return await channel.send(default_text)


async def update_boards(guild: discord.Guild) -> None:
    data = load_data()

    count_channel = bot.get_channel(COUNT_CHANNEL)
    rank_channel = bot.get_channel(RANK_CHANNEL)

    if not count_channel or not rank_channel:
        return

    users = data.get("users", {})
    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("count", 0),
        reverse=True
    )

    # 홍보-횟수 내용
    if sorted_users:
        count_lines = []
        for user_id, info in sorted_users:
            name = get_display_name(guild, int(user_id), info.get("name", "Unknown"))
            count_lines.append(f"{name} — {info.get('count', 0)}회")
        count_text = "\n".join(count_lines)
    else:
        count_text = "데이터 없음"

    # 홍보-랭킹 내용
    if sorted_users:
        rank_lines = ["📊 홍보 랭킹\n"]
        for idx, (user_id, info) in enumerate(sorted_users, start=1):
            name = get_display_name(guild, int(user_id), info.get("name", "Unknown"))
            rank_lines.append(f"{idx}위 {name} — {info.get('count', 0)}회")
        rank_text = "\n".join(rank_lines)
    else:
        rank_text = "📊 홍보 랭킹\n\n데이터 없음"

    # 메시지 1개만 유지
    count_msg = await get_or_create_board_message(
        count_channel,
        data.get("count_message_id"),
        count_text
    )
    try:
        await count_msg.edit(content=count_text)
    except Exception:
        pass
    data["count_message_id"] = count_msg.id

    rank_msg = await get_or_create_board_message(
        rank_channel,
        data.get("rank_message_id"),
        rank_text
    )
    try:
        await rank_msg.edit(content=rank_text)
    except Exception:
        pass
    data["rank_message_id"] = rank_msg.id

    save_data(data)


@bot.event
async def on_ready():
    print(f"홍보봇 실행됨: {bot.user}")

    guild = bot.get_guild(GUILD_ID)
    if guild:
        await update_boards(guild)


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

    # 이미지 첨부만 카운트
    image_attachments = []
    for attachment in message.attachments:
        content_type = attachment.content_type or ""
        filename = attachment.filename.lower()

        if content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
            image_attachments.append(attachment)

    if not image_attachments:
        return

    image_count = len(image_attachments)

    # 한 번에 최대 10장 인정
    if image_count > 10:
        image_count = 10

    data = load_data()
    users = data["users"]

    user_id = str(message.author.id)
    username = message.author.display_name

    if user_id not in users:
        users[user_id] = {
            "count": 0,
            "name": username
        }

    users[user_id]["count"] += image_count
    users[user_id]["name"] = username

    save_data(data)

    # 로그 채널 기록
    log_channel = bot.get_channel(LOG_CHANNEL)
    if log_channel:
        try:
            await log_channel.send(f"{username}님이 홍보글을 올렸습니다. (+{image_count})")
        except Exception:
            pass

    await update_boards(message.guild)


bot.run(TOKEN)
