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
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


@bot.event
async def on_ready():
    print(f"봇 로그인 완료 : {bot.user}")


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id != PROMO_CHANNEL:
        return

    if not message.attachments:
        return

    data = load_data()

    user_id = str(message.author.id)

    if user_id not in data:
        data[user_id] = 0

    data[user_id] += 1

    save_data(data)

    member = message.guild.get_member(message.author.id)
    username = member.display_name if member else message.author.name

    count_channel = bot.get_channel(COUNT_CHANNEL)
    await count_channel.send(f"{username} — {data[user_id]}회")

    log_channel = bot.get_channel(LOG_CHANNEL)
    await log_channel.send(f"{username} 홍보 인증 +1")

    await update_rank(message.guild)

    await bot.process_commands(message)


async def update_rank(guild):

    data = load_data()

    rank_channel = bot.get_channel(RANK_CHANNEL)

    sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)

    text = "📊 홍보 랭킹\n\n"

    rank = 1

    for user_id, count in sorted_users[:10]:

        member = guild.get_member(int(user_id))

        if member:
            name = member.display_name
        else:
            name = "Unknown"

        text += f"{rank}위 {name} — {count}회\n"

        rank += 1

    await rank_channel.send(text)


bot.run(TOKEN)
