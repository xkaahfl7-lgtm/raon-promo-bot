# 🔥 추가 (퇴사자 제거 목록)
REMOVED_USERS = ["혁이", "호랭", "백구", "봉식"]


def is_removed(name: str):
    base = normalize_name(name)
    return base in ["혁이", "호랭", "백구", "봉식"]


def add_count(user_id: str, display_name: str, count: int):
    # ❌ 퇴사자 차단
    if is_removed(display_name):
        return

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT count FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row:
            new_count = int(row["count"]) + int(count)
            cur.execute("""
                UPDATE users
                SET display_name = ?, count = ?
                WHERE user_id = ?
            """, (display_name, new_count, user_id))
        else:
            cur.execute("""
                INSERT INTO users (user_id, display_name, count)
                VALUES (?, ?, ?)
            """, (user_id, display_name, int(count)))

        conn.commit()


def build_rows():
    rows = get_all_users()
    result = {}

    for row in rows:
        user_id = str(row["user_id"])
        name = row["display_name"]
        count = int(row["count"])

        # ❌ 퇴사자 제거
        if is_removed(name):
            continue

        # 🔥 핵심: user_id 기준 통합
        if user_id not in result:
            result[user_id] = {
                "display_name": name,
                "count": 0
            }

        result[user_id]["count"] += count
        result[user_id]["display_name"] = name  # 최신 닉 반영

    final = list(result.values())
    final.sort(key=lambda x: -x["count"])
    return final


async def send_log(text: str):
    print(text)
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        try:
            await channel.send(f"📢 {text}")
        except Exception as e:
            print("로그 전송 실패:", e)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

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
        # 🔥 여기 로그 추가
        await send_log(f"📥 감지 | {message.author.display_name} | 이미지 {image_count}장")

        add_count(str(message.author.id), message.author.display_name, image_count)
        mark_processed(message_id)

        await send_log(f"✅ 처리완료 | {message.author.display_name} (+{image_count})")

        await update_board()

    except Exception as e:
        await send_log(f"❌ 오류 발생 | {message.author.display_name} | {e}")

    await bot.process_commands(message)
