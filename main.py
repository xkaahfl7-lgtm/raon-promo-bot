import discord
from discord.ext import commands
import json
import os

TOKEN = os.getenv("TOKEN")
PROMO_CHANNEL_ID = 1465360797311172730   # 홍보-인증 채널
LOG_CHANNEL_ID = 1481661104580067419     # 홍보-로그 채널

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "promo_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@bot.event
async def on_ready():
    print(f"🤖 홍보봇 실행 완료: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != PROMO_CHANNEL_ID:
        await bot.process_commands(message)
        return

    if not message.attachments:
        await bot.process_commands(message)
        return

    image_count = 0
    for attachment in message.attachments:
        name = attachment.filename.lower()
        if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            image_count += 1

    if image_count == 0:
        await bot.process_commands(message)
        return

    data = load_data()
    user_id = str(message.author.id)

    if user_id not in data:
        data[user_id] = {
            "name": message.author.display_name,
            "count": 0
        }

    data[user_id]["name"] = message.author.display_name
    data[user_id]["count"] += image_count
    save_data(data)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="📢 홍보 인증 로그",
            color=0x00ff00
        )
        embed.add_field(name="인증자", value=message.author.mention, inline=False)
        embed.add_field(name="이번 인증 수", value=f"{image_count}회", inline=True)
        embed.add_field(name="누적 횟수", value=f"{data[user_id]['count']}회", inline=True)
        embed.add_field(name="채널", value=message.channel.mention, inline=False)
        await log_channel.send(embed=embed)

    await bot.process_commands(message)

@bot.command()
async def 홍보랭킹(ctx):
    data = load_data()
    sorted_users = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)

    msg = "🏆 홍보 랭킹\n\n"
    for i, (_, info) in enumerate(sorted_users[:10], start=1):
        msg += f"{i}위 - {info['name']} : {info['count']}회\n"

    await ctx.send(msg)

if not TOKEN:
    raise ValueError("TOKEN 환경변수가 비어 있습니다.")

bot.run(TOKEN)
