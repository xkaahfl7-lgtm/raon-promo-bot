import discord
from discord.ext import commands
import json
import os

TOKEN = os.getenv("TOKEN")

PROMO_CHANNEL_ID = 1465360797311172730
LOG_CHANNEL_ID = 1481661104580067419
RANK_CHANNEL_ID = 1481209156508586055  # 홍보-랭킹 채널 ID 넣기

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

async def update_ranking():
    channel = bot.get_channel(RANK_CHANNEL_ID)
    if not channel:
        return

    data = load_data()

    sorted_users = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)

    msg = "📊 홍보 횟수\n"
    for _, info in sorted_users:
        msg += f"{info['name']} — {info['count']}회\n"

    msg += "\n🏆 TOP 10\n"
    for i, (_, info) in enumerate(sorted_users[:10], start=1):
        msg += f"{i}위 {info['name']} — {info['count']}회\n"

    async for m in channel.history(limit=10):
        if m.author == bot.user:
            await m.edit(content=msg)
            return

    await channel.send(msg)

@bot.event
async def on_ready():
    print(f"🤖 홍보봇 실행 완료: {bot.user}")
    await update_ranking()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if message.channel.id != PROMO_CHANNEL_ID:
        return

    if not message.attachments:
        return

    data = load_data()
    user_name = message.author.display_name

    if user_name not in data:
        data[user_name] = {"name": user_name, "count": 0}

    data[user_name]["count"] += len(message.attachments)
    save_data(data)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"📢 {user_name} 홍보 {len(message.attachments)}회 / 총 {data[user_name]['count']}회")

    await update_ranking()

# 관리자 명령어

@bot.command()
async def 추가(ctx, name: str, amount: int):
    data = load_data()
    if name not in data:
        data[name] = {"name": name, "count": 0}
    data[name]["count"] += amount
    save_data(data)
    await update_ranking()
    await ctx.send("추가 완료")

@bot.command()
async def 차감(ctx, name: str, amount: int):
    data = load_data()
    if name in data:
        data[name]["count"] = max(0, data[name]["count"] - amount)
        save_data(data)
        await update_ranking()
        await ctx.send("차감 완료")

@bot.command()
async def 설정(ctx, name: str, amount: int):
    data = load_data()
    data[name] = {"name": name, "count": amount}
    save_data(data)
    await update_ranking()
    await ctx.send("설정 완료")

@bot.command()
async def 이름변경(ctx, old: str, new: str):
    data = load_data()
    if old in data:
        data[new] = data.pop(old)
        data[new]["name"] = new
        save_data(data)
        await update_ranking()
        await ctx.send("이름변경 완료")

@bot.command()
async def 삭제(ctx, name: str):
    data = load_data()
    if name in data:
        del data[name]
        save_data(data)
        await update_ranking()
        await ctx.send("삭제 완료")

if not TOKEN:
    raise ValueError("TOKEN 없음")

bot.run(TOKEN)
