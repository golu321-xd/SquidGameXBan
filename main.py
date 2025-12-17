import os, json, time, requests, threading
from datetime import datetime
from flask import Flask
import discord
from discord.ext import commands

# ================= ENV =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", 8080))
OWNER_IDS = [int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x]

if not DISCORD_TOKEN or not OWNER_IDS:
    raise Exception("Missing DISCORD_TOKEN or OWNER_IDS")

# ================= FILES =================
BLOCKED_FILE = "blocked.json"
USERS_FILE = "users.json"

# ================= LOAD / SAVE =================
def load(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

BLOCKED = load(BLOCKED_FILE)
USERS = load(USERS_FILE)
WAITING = {}

# ================= EMBED =================
def make_embed(title, desc, color=0x2f3136):
    emb = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )
    emb.set_footer(text="Ban System • Online")
    return emb

# ================= ROBLOX =================
def get_user_info(uid):
    try:
        r = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5).json()
        return r.get("name", "Unknown"), r.get("displayName", "Unknown")
    except:
        return "Unknown", "Unknown"

# ================= CLEAN TEMP =================
def cleanup():
    changed = False
    for uid in list(BLOCKED.keys()):
        d = BLOCKED[uid]
        if not d["perm"] and time.time() > d["expire"]:
            del BLOCKED[uid]
            changed = True
    if changed:
        save(BLOCKED_FILE, BLOCKED)

# ================= DISCORD BOT =================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

def is_owner(ctx):
    return ctx.author.id in OWNER_IDS

@bot.event
async def on_ready():
    print("Discord Bot Online")

# ================= COMMANDS =================
@bot.command()
async def add(ctx, user_id: str):
    if not is_owner(ctx): return
    WAITING[ctx.author.id] = {"action": "add", "uid": user_id}
    u, d = get_user_info(user_id)
    await ctx.send(embed=make_embed(
        "🔨 PERMANENT BAN",
        f"**Name:** {d}\n**Username:** @{u}\n**ID:** `{user_id}`\n\n✍️ Type reason below",
        0xff0000
    ))

@bot.command()
async def tempban(ctx, user_id: str, mins: int):
    if not is_owner(ctx): return
    WAITING[ctx.author.id] = {"action": "temp", "uid": user_id, "mins": mins}
    u, d = get_user_info(user_id)
    await ctx.send(embed=make_embed(
        "⏱ TEMP BAN",
        f"**Name:** {d}\n**Username:** @{u}\n**ID:** `{user_id}`\n"
        f"**Duration:** `{mins} minutes`\n\n✍️ Type reason below",
        0xffa500
    ))

@bot.command()
async def remove(ctx, user_id: str):
    if not is_owner(ctx): return
    BLOCKED.pop(user_id, None)
    save(BLOCKED_FILE, BLOCKED)
    await ctx.send(embed=make_embed(
        "✅ UNBANNED",
        f"User `{user_id}` has been unbanned",
        0x00ff00
    ))

@bot.command()
async def list(ctx):
    if not is_owner(ctx): return
    cleanup()
    if not BLOCKED:
        await ctx.send(embed=make_embed("📭 No Bans", "No users banned.", 0x00ff00))
        return

    desc = ""
    for i, (uid, d) in enumerate(BLOCKED.items(), 1):
        u, n = get_user_info(uid)
        t = "PERM" if d["perm"] else f"{int((d['expire']-time.time())/60)}m left"
        desc += f"**{i}. {n} (@{u})**\nID: `{uid}` | `{t}`\nReason: {d['msg']}\n\n"

    await ctx.send(embed=make_embed("🚫 Blocked Users", desc, 0x5865F2))

@bot.command()
async def clear(ctx):
    if not is_owner(ctx): return
    BLOCKED.clear()
    save(BLOCKED_FILE, BLOCKED)
    await ctx.send(embed=make_embed("🧹 Cleared", "All bans cleared.", 0xff4444))

@bot.command()
async def users(ctx):
    if not is_owner(ctx): return
    if not USERS:
        await ctx.send(embed=make_embed("No Users", "No script users tracked."))
        return
    desc = ""
    for i, (uid, info) in enumerate(USERS.items(), 1):
        t = datetime.fromtimestamp(info["time"]).strftime("%d %b %I:%M %p")
        desc += f"**{i}. {info['display']} (@{info['username']})**\nTime: {t}\n\n"
    await ctx.send(embed=make_embed("👥 Script Users", desc))

@bot.event
async def on_message(msg):
    if msg.author.id in WAITING:
        data = WAITING[msg.author.id]
        uid = data["uid"]
        reason = msg.content

        if data["action"] == "add":
            BLOCKED[uid] = {"perm": True, "msg": reason}
            title, color = "✅ PERM BAN ADDED", 0xff0000
        else:
            BLOCKED[uid] = {
                "perm": False,
                "msg": reason,
                "expire": time.time() + data["mins"] * 60
            }
            title, color = "✅ TEMP BAN ADDED", 0xffa500

        save(BLOCKED_FILE, BLOCKED)
        del WAITING[msg.author.id]

        await msg.channel.send(embed=make_embed(
            title,
            f"**User ID:** `{uid}`\n**Reason:** {reason}",
            color
        ))
        return

    await bot.process_commands(msg)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Alive"

@app.route("/ping")
def ping():
    return "pong"

@app.route("/check/<uid>")
def check(uid):
    cleanup()
    d = BLOCKED.get(uid)
    if d and (d["perm"] or time.time() < d.get("expire", 0)):
        return "true"
    return "false"

@app.route("/track/<uid>/<username>/<display>")
def track(uid, username, display):
    USERS[uid] = {"username": username, "display": display, "time": time.time()}
    save(USERS_FILE, USERS)
    return "OK"

@app.route("/reason/<uid>")
def reason(uid):
    cleanup()
    d = BLOCKED.get(uid)
    return d.get("msg", "") if d else ""

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask).start()
bot.run(DISCORD_TOKEN)
