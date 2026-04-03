import discord
from discord.ext import commands
import json
import os

TOKEN = "여기에_봇토큰"
PROMO_CHANNEL_ID = 1234567890  # 홍보-인증 채널
LOG_CHANNEL_ID = 1234567890    # 홍보-로그 채널

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "promo_data.json"

# 데이터 불러오기
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# 데이터 저장
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@bot.event
async def on_ready():
    print(f"🤖 봇 실행 완료: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != PROMO_CHANNEL_ID:
        return

    # 이미지 없으면 무시
    if not message.attachments:
        return

    data = load_data()
    user_id = str(message.author.id)

    if user_id not in data:
        data[user_id] = {
            "name": message.author.name,
            "count": 0
        }

    data[user_id]["count"] += 1
    save_data(data)

    # 로그 전송
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="📢 홍보 인증 로그",
            description=f"{message.author.mention} 님이 홍보 인증을 했습니다!",
            color=0x00ff00
        )
        embed.add_field(name="누적 횟수", value=f"{data[user_id]['count']}회", inline=False)
        await log_channel.send(embed=embed)

    await bot.process_commands(message)

# 랭킹 명령어
@bot.command()
async def 홍보랭킹(ctx):
    data = load_data()

    sorted_users = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)

    msg = "🏆 홍보 랭킹\n\n"
    for i, (uid, info) in enumerate(sorted_users[:10], start=1):
        msg += f"{i}위 - {info['name']} : {info['count']}회\n"

    await ctx.send(msg)

bot.run(TOKEN)
