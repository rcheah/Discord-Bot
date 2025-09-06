import discord
import aiohttp
import asyncio
import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()
SCRIM_WEBHOOK_URL = os.getenv("SCRIM_WEBHOOK_URL")

DB_PATH = "data/scrims.db"
MESSAGE_ID_FILE = "data/webhook/message_ids.json"
os.makedirs(os.path.dirname(MESSAGE_ID_FILE), exist_ok=True)

def save_message_ids(ids):
    with open(MESSAGE_ID_FILE, "w") as f:
        json.dump(ids, f)

def load_message_ids():
    try:
        with open(MESSAGE_ID_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return []

async def format_signups():
    """Erstellt Scrim Übersicht inkl. finalisierte LUs mit optischer Trennung"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    timestamp = int(datetime.now().timestamp())
    now_hour = datetime.now().hour
    team_order = ["🔴 Ruby", "🔵 Sapphire", "🟢 Emerald", "🟠 Mixed", "🟣 MK8D"]

    content_blocks = ["**Scrim Zusagen**"]

    # --- Offene Signups ---
    cur.execute("SELECT hour, team, role, user_ids FROM signups")
    rows = cur.fetchall()

    if not rows:
        content_blocks.append("Keine Zusagen")
    else:
        grouped = {}
        for row in rows:
            # Nur Stunden in der Zukunft berücksichtigen
            if int(row["hour"]) < now_hour:
                continue
            key = (row["hour"], row["team"])
            if key not in grouped:
                grouped[key] = {"main": [], "sub": []}
            grouped[key][row["role"]] = json.loads(row["user_ids"]) if row["user_ids"] else []

        sorted_keys = sorted(
            grouped.keys(),
            key=lambda x: (int(x[0]), team_order.index(x[1]) if x[1] in team_order else 999)
        )

        current_hour = None
        for hour, team in sorted_keys:
            roles = grouped[(hour, team)]
            if hour != current_hour:
                if current_hour is not None:
                    content_blocks.append("")  # Leerzeile zwischen Stunden
                content_blocks.append(f"**{hour} Uhr**")
                current_hour = hour

            main_ids = roles.get("main", [])
            sub_ids = roles.get("sub", [])
            main_list = " ".join(f"<@{uid}>" for uid in main_ids) if main_ids else "—"
            sub_list = " ".join(f"<@{uid}>" for uid in sub_ids) if sub_ids else "—"
            count = len(main_ids) + len(sub_ids)
            content_blocks.append(f"**{team}** ({count}): {main_list} | Sub: {sub_list}")

    # --- Fett und ohne Trennlinie für finalisierte LUs ---
    content_blocks.append("")  # Leerzeile über Line Ups
    content_blocks.append("**✅ Line-Ups:**")  # direkt darunter starten

    # --- Finalisierte LUs ---
    cur.execute("""
        SELECT m.id, m.created_at, m.hour, m.host, m.opponent, m.open, s.team, s.user_id
        FROM scrim_meta m
        JOIN scrim s ON m.id = s.id
        WHERE m.finalized = 1
        ORDER BY m.id
    """)
    rows = cur.fetchall()

    # Gruppieren nach Scrim-ID
    scrims = {}
    for row in rows:
        sid = row["id"]
        if sid not in scrims:
            scrims[sid] = {
                "created_at": row["created_at"],
                "hour": row["hour"],
                "team": row["team"],
                "host": row["host"],
                "opponent": row["opponent"],
                "open": row["open"],
                "users": []
            }
        scrims[sid]["users"].append(row["user_id"])

    for sid, data in scrims.items():
        # nur LUs für heute oder später anzeigen
        if datetime.strptime(data["created_at"], "%d.%m.%Y") < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
            continue

        # Spieler alphabetisch sortieren anhand scrim_scores.name
        conn2 = sqlite3.connect(DB_PATH)
        cur2 = conn2.cursor()
        users_sorted = []
        for uid in data["users"]:
            cur2.execute("SELECT name FROM scrim_scores WHERE user_id=?", (str(uid),))
            row = cur2.fetchone()
            if row:
                users_sorted.append((row[0], uid))
            else:
                users_sorted.append((str(uid), uid))
        conn2.close()

        users_sorted.sort(key=lambda x: x[0].lower())
        users_line = " ".join(f"<@{uid}>" for name, uid in users_sorted)
        opponent_text = f" vs. {data['opponent']}" if data["opponent"] else ""
        
        content_blocks.append(
            f"**Scrim#{sid} {data['team']}{opponent_text} am {data['created_at']} um {data['hour']} Uhr**\n"
            f"LU: {users_line}\nHost: {data['host']} | Open: {data['open']}\n"
        )

    conn.close()
    content_blocks.append(f"Letzte Aktualisierung: <t:{timestamp}:R>")
    return "\n".join(content_blocks)

async def refresh_webhook():
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(SCRIM_WEBHOOK_URL, session=session)

        content = await format_signups()
        message_ids = load_message_ids()

        # Split content if too long
        messages = []
        while content:
            chunk = content[:2000]
            last_split = chunk.rfind("\n")
            if last_split == -1:
                last_split = 2000
            messages.append(content[:last_split])
            content = content[last_split:].lstrip()

        try:
            new_ids = []
            for i, chunk in enumerate(messages):
                if i < len(message_ids):
                    try:
                        msg = await webhook.fetch_message(message_ids[i])
                        await msg.edit(content=chunk)
                        new_ids.append(msg.id)
                    except discord.NotFound:
                        msg = await webhook.send(chunk, wait=True)
                        new_ids.append(msg.id)
                else:
                    msg = await webhook.send(chunk, wait=True)
                    new_ids.append(msg.id)

            # Alte extra Nachrichten löschen
            for msg_id in message_ids[len(messages):]:
                try:
                    msg = await webhook.fetch_message(msg_id)
                    await msg.delete()
                except discord.NotFound:
                    continue

            save_message_ids(new_ids)
        except Exception as e:
            print(f"[Webhook Error] {e}")

async def webhook_updater(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await refresh_webhook()
        except Exception as e:
            print(f"[Updater Error] {e}")
        await asyncio.sleep(15)
