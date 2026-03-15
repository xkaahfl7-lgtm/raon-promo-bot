import discord
from discord.ext import commands
import json
import os

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1464381836099584235

PROMO_CHANNEL = 1465360797311172730
COUNT_CHANNEL = 1481209117824651384
RANK_CHANNEL = 1481209156508586055
LOG_CHANNEL = 1481661104580067419

DATA_FILE = "promo_data.json"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_data():
    try:
        with open(DATA_FILE,"r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f)

@bot.event
async def on_ready():
    print("홍보봇 실행됨")

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    images = [a for a in message.attachments if a.content_type and "image" in a.content_type]

    if not images:
        return

    count = len(images)

    if count > 10:
        count = 10

    data = load_data()

    user = str(message.author.id)

    data[user] = data.get(user,0) + count

    save_data(data)

    log_channel = bot.get_channel(LOG_CHANNEL)
    await log_channel.send(f"{message.author.display_name}님이 홍보글을 올렸습니다 (+{count})")

    await update_channels()

    await bot.process_commands(message)

async def update_channels():

    data = load_data()

    guild = bot.get_guild(GUILD_ID)

    count_channel = bot.get_channel(COUNT_CHANNEL)
    rank_channel = bot.get_channel(RANK_CHANNEL)

    text = ""
    ranking = ""

    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)

    rank = 1

    for user_id, score in sorted_data:

        member = guild.get_member(int(user_id))

        name = member.display_name if member else "Unknown"

        text += f"{name} — {score}회\n"
        ranking += f"{rank}위 {name} — {score}회\n"

        rank += 1

    async for m in count_channel.history(limit=20):
        await m.delete()

    async for m in rank_channel.history(limit=20):
        await m.delete()

    await count_channel.send(text if text else "데이터 없음")
    await rank_channel.send(ranking if ranking else "데이터 없음")

bot.run(TOKEN)
