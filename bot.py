import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import os
import uuid
import threading
import requests
from PIL import Image
import subprocess
import base64

# 🔐 SETTINGS
BOT_TOKEN = "8753953837:AAGCOnpbPzk7Qti7i-M62TuIT17OAeaIuQU"
OWNER_ID = 8535204714

bot = telebot.TeleBot(BOT_TOKEN)
DOWNLOAD_FOLDER = "DL"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

user_links = {}
queue = []
downloading = False

# ------------------ ADMIN SYSTEM ------------------
ADMINS_FILE = "admins.txt"
if not os.path.exists(ADMINS_FILE):
    with open(ADMINS_FILE, "w") as f:
        pass

def load_admins():
    with open(ADMINS_FILE, "r") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_admins(admins):
    with open(ADMINS_FILE, "w") as f:
        for admin in admins:
            f.write(f"{admin}\n")

admins = load_admins()

def is_admin(message):
    return message.chat.id in admins or message.chat.id == OWNER_ID

# ------------------ THUMB ------------------
def get_thumb(url, file_id):
    path = f"{DOWNLOAD_FOLDER}/{file_id}.jpg"
    try:
        r = requests.get(url, timeout=10)
        with open(path, "wb") as f:
            f.write(r.content)
        img = Image.open(path)
        img.thumbnail((320, 320))
        img.save(path, "JPEG")
        return path
    except:
        return None

# ------------------ PROGRESS ------------------
def progress_hook(d, chat_id, msg_id):
    if d['status'] != 'downloading':
        return
    percent = d.get('_percent_str', '')
    speed = d.get('_speed_str', '')
    eta = d.get('_eta_str', '')
    text = f"📥 {percent}\n⚡ {speed}\n⏳ {eta}"
    try:
        bot.edit_message_text(text, chat_id, msg_id)
    except:
        pass

# ------------------ URL DECRYPT ------------------
def decrypt_url(url):
    try:
        decoded = base64.b64decode(url).decode("utf-8")
        if decoded.startswith("http"):
            return decoded
    except:
        pass
    return url

# ------------------ DOWNLOAD ------------------
def download_video(url, chat_id, msg_id, quality):
    global downloading
    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.mp4")
    try:
        bot.edit_message_text("⚡ Downloading...", chat_id, msg_id)

        if ".m3u8" in url:
            format_code = "best"
        elif quality == "auto":
            format_code = "bestvideo+bestaudio/best"
        else:
            format_code = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"

        ydl_opts = {
            'format': format_code,
            'outtmpl': filepath,
            'noplaylist': True,
            'external_downloader': 'aria2c',
            'external_downloader_args': ['-x','16','-s','16','-k','1M'],
            'concurrent_fragment_downloads': 5,
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
            'format_sort': ['res', 'ext:mp4:m4a'],
            'progress_hooks': [lambda d: progress_hook(d, chat_id, msg_id)]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not os.path.exists(filepath):
            bot.edit_message_text("❌ Failed", chat_id, msg_id)
            downloading = False
            process_queue()
            return

        title = info.get("title", "Video")
        thumb_url = info.get("thumbnail")
        thumb_path = get_thumb(thumb_url, file_id) if thumb_url else None

        bot.edit_message_text("📤 Uploading...", chat_id, msg_id)
        with open(filepath, "rb") as f:
            try:
                if thumb_path and os.path.exists(thumb_path):
                    with open(thumb_path, "rb") as t:
                        bot.send_video(chat_id, f, caption=f"🎬 {title}",
                                       supports_streaming=True, timeout=600, thumb=t)
                else:
                    bot.send_video(chat_id, f, caption=f"🎬 {title}",
                                   supports_streaming=True, timeout=600)
            except:
                bot.send_document(chat_id, f, timeout=600)

        os.remove(filepath)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        bot.delete_message(chat_id, msg_id)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error:\n{e}")
    downloading = False
    process_queue()

# ------------------ QUEUE ------------------
def process_queue():
    global downloading
    if downloading or not queue:
        return
    downloading = True
    url, chat_id, msg_id, quality = queue.pop(0)
    threading.Thread(target=download_video, args=(url, chat_id, msg_id, quality)).start()

# ------------------ FETCH QUALITIES ------------------
def fetch_qualities(url):
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = info.get("formats", [])
    qualities = sorted({f.get("height") for f in formats if f.get("height")}, reverse=True)
    return qualities, info

# ------------------ /dl COMMAND ------------------
@bot.message_handler(commands=['dl'])
def cmd_dl(message):
    if not is_admin(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /dl <URL>")
        return

    raw_url = args[1].strip()
    url = decrypt_url(raw_url)

    if raw_url != url:
        bot.reply_to(message, "🔓 Link decrypted successfully!")

    msg = bot.reply_to(message, "🔍 Processing link...")
    try:
        if ".m3u8" in url or url.endswith(".mp4"):
            bot.edit_message_text("📥 Added to queue...", message.chat.id, msg.message_id)
            queue.append((url, message.chat.id, msg.message_id, "auto"))
            process_queue()
            return

        qualities, info = fetch_qualities(url)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⚡ AUTO", callback_data="auto"))

        row = []
        for q in qualities:
            row.append(InlineKeyboardButton(f"{q}p", callback_data=str(q)))
            if len(row) == 2:
                markup.add(*row)
                row = []

        if row:
            markup.add(*row)

        user_links[message.chat.id] = url
        bot.edit_message_text("🎯 Select quality:", message.chat.id, msg.message_id, reply_markup=markup)

    except Exception as e:
        bot.edit_message_text(f"❌ Error:\n{e}", message.chat.id, msg.message_id)

# ------------------ /rec COMMAND ------------------
@bot.message_handler(commands=['rec'])
def cmd_rec(message):
    if not is_admin(message):
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        bot.reply_to(message, "❌ Usage:\n/rec <M3U8_URL> <duration_sec> <filename>")
        return
    url = args[1].strip()
    try:
        duration = int(args[2].strip())
    except:
        bot.reply_to(message, "❌ Duration must be a number (seconds)")
        return
    filename = args[3].strip().replace(" ", "_")
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    msg = bot.reply_to(message, f"🎥 Recording...\n⏱ {duration}s\n📁 {filename}")

    def record_stream():
        try:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", url,
                "-map", "0",
                "-c", "copy",
                "-t", str(duration),
                "-fflags", "+genpts",
                "-avoid_negative_ts", "make_zero",
                "-progress", "pipe:1",
                filepath
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("out_time_ms="):
                    out_ms = int(line.split("=")[1])
                    seconds = out_ms // 1000000
                    percent = min(int((seconds / duration) * 100), 100)
                    bar = "█" * (percent // 5) + "─" * (20 - (percent // 5))
                    try:
                        bot.edit_message_text(f"⏳ Recording: {seconds}s / {duration}s\n[{bar}] {percent}%", message.chat.id, msg.message_id)
                    except:
                        pass
            process.wait()

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                bot.edit_message_text("📤 Uploading...", message.chat.id, msg.message_id)
                with open(filepath, "rb") as f:
                    bot.send_video(message.chat.id, f, caption=f"🎬 {filename}",
                                   timeout=600, supports_streaming=True)
                os.remove(filepath)
            else:
                bot.edit_message_text("❌ Recording failed", message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error:\n{e}", message.chat.id, msg.message_id)

    threading.Thread(target=record_stream).start()

# ------------------ /start ADVANCED ------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.chat.id
    name = message.from_user.first_name or "User"

    if user_id == OWNER_ID:
        role = "Owner 👑"
    elif user_id in admins:
        role = "Admin ⚡"
    else:
        bot.reply_to(message, "❌ You are not authorized to use this bot.")
        return

    text = (
        f"👋 হ্যালো {name}!\n"
        f"🔑 Your Role: {role}\n\n"
        "📌 Bot Commands Quick Access:\n"
        "• /dl <URL> - ভিডিও ডাউনলোড\n"
        "• /rec <M3U8_URL> <duration_sec> <filename> - লাইভ রেকর্ডিং\n"
    )

    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("⚡ Download Video", callback_data="menu_dl"),
        InlineKeyboardButton("🎥 Record Stream", callback_data="menu_rec")
    )
    if user_id == OWNER_ID:
        markup.add(
            InlineKeyboardButton("➕ Add Admin", callback_data="menu_addadmin"),
            InlineKeyboardButton("❌ Remove Admin", callback_data="menu_removeadmin")
        )
    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def start_menu_callback(call):
    if call.data == "menu_dl":
        bot.send_message(call.message.chat.id, "📥 Send /dl <URL> to download a video")
    elif call.data == "menu_rec":
        bot.send_message(call.message.chat.id, "🎥 Send /rec <M3U8_URL> <duration_sec> <filename> to record stream")
    elif call.data == "menu_addadmin" and call.message.chat.id == OWNER_ID:
        bot.send_message(call.message.chat.id, "➕ Send /addadmin <user_id> to add a new admin")
    elif call.data == "menu_removeadmin" and call.message.chat.id == OWNER_ID:
        bot.send_message(call.message.chat.id, "❌ Send /removeadmin <user_id> to remove an admin")
    else:
        bot.answer_callback_query(call.id, "❌ Unauthorized action")

# ------------------ /addadmin ------------------
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if message.chat.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /addadmin <user_id>")
        return
    try:
        user_id = int(args[1])
        admins.add(user_id)
        save_admins(admins)
        bot.reply_to(message, f"✅ Added admin: {user_id}")
    except:
        bot.reply_to(message, "❌ Invalid user_id")

# ------------------ /removeadmin ------------------
@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    if message.chat.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /removeadmin <user_id>")
        return
    try:
        user_id = int(args[1])
        admins.discard(user_id)
        save_admins(admins)
        bot.reply_to(message, f"✅ Removed admin: {user_id}")
    except:
        bot.reply_to(message, "❌ Invalid user_id")

# ------------------ CALLBACK HANDLER FOR DL ------------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.message.chat.id not in admins and call.message.chat.id != OWNER_ID:
        return
    url = user_links.get(call.message.chat.id)
    quality = call.data
    bot.edit_message_text("📥 Added to queue...", call.message.chat.id, call.message.message_id)
    queue.append((url, call.message.chat.id, call.message.message_id, quality))
    process_queue()

print("🚀 PRIVATE ULTRA BOT RUNNING...")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
