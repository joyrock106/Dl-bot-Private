#!/usr/bin/env python3

import os
import uuid
import threading
import base64
import httpx
import requests
import urllib3
import dns.resolver
import time

from dotenv import load_dotenv
from Cryptodome.Util.Padding import unpad
from Cryptodome.Cipher import AES

import telebot
import yt_dlp

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

------------------ FIX ------------------

urllib3.disable_warnings()

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

------------------ ENV ------------------

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

bot = telebot.TeleBot(BOT_TOKEN)

DOWNLOAD_FOLDER = "DL"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

queue = []
downloading = False
MAX_QUEUE = 5

video_cache = {}
last_update_time = {}

------------------ AES DECRYPT ------------------

def aes_decrypt(data, key=b'0123456789abcdef'):
try:
raw = base64.b64decode(data)
cipher = AES.new(key, AES.MODE_ECB)
return unpad(cipher.decrypt(raw), 16).decode()
except:
return data

def decrypt_url(url):
try:
decoded = base64.b64decode(url).decode()
if decoded.startswith("http"):
return decoded
except:
pass
return aes_decrypt(url)

------------------ SIZE FORMAT ------------------

def human(n):
if not n:
return "0B"
for unit in ["B", "KB", "MB", "GB"]:
if n < 1024:
return f"{n:.2f}{unit}"
n /= 1024
return f"{n:.2f}TB"

------------------ THUMB DOWNLOAD FIX ------------------

def download_thumbnail(url):
if not url:
return None

path = os.path.join(DOWNLOAD_FOLDER, f"{uuid.uuid4()}.jpg")  

try:  
    r = requests.get(url, timeout=10)  
    if r.status_code == 200:  
        with open(path, "wb") as f:  
            f.write(r.content)  
        return path  
except:  
    pass  

return None

------------------ FORMAT FETCH ------------------

def get_available_formats(url):
with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
info = ydl.extract_info(url, download=False)

formats = info.get("formats", [])  
result = []  

for f in formats:  
    if f.get("vcodec") != "none" and f.get("height"):  
        result.append({  
            "id": f["format_id"],  
            "height": f["height"],  
        })  

seen = set()  
cleaned = []  

for f in sorted(result, key=lambda x: x["height"], reverse=True):  
    if f["height"] not in seen:  
        seen.add(f["height"])  
        cleaned.append(f)  

return cleaned[:6], info.get("title", "Video"), info

------------------ UI ------------------

def ui(chat_id, msg_id, stage, percent, cur, total, speed="N/A", eta="N/A"):
try:
key = f"{chat_id}_{msg_id}"
now = time.time()

if key in last_update_time and now - last_update_time[key] < 1.2:  
        return  

    last_update_time[key] = now  

    bar_len = 12  
    filled = int((percent / 100) * bar_len)  
    bar = "█" * filled + "░" * (bar_len - filled)  

    text = (  
        f"⠇ <b>PRO MAX ENGINE</b>\n\n"  
        f"{stage}\n\n"  
        f"[{bar}] {percent:.1f}%\n\n"  
        f"📦 {cur} / {total}\n"  
        f"⚡ {speed}\n"  
        f"⏳ {eta}\n"  
    )  

    bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML")  

except:  
    pass

------------------ PROGRESS ------------------

def progress_hook(d, chat_id, msg_id):
if d.get("status") != "downloading":
return

total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1  
done = d.get("downloaded_bytes", 0)  

percent = (done / total) * 100  
speed = d.get("speed") or 0  
eta = d.get("eta") or 0  

ui(  
    chat_id,  
    msg_id,  
    "📥 Downloading...",  
    percent,  
    human(done),  
    human(total),  
    f"{round(speed/1024/1024,2)} MB/s" if speed else "N/A",  
    f"{eta}s" if eta else "N/A"  
)

------------------ QUALITY MENU ------------------

def show_quality_menu(chat_id, msg_id, url):
formats, title, info = get_available_formats(url)

video_cache[chat_id] = {  
    "url": url,  
    "formats": {f["id"]: f for f in formats},  
    "title": title,  
    "info": info  
}  

markup = InlineKeyboardMarkup()  

for f in formats:  
    markup.row(  
        InlineKeyboardButton(  
            f"🎬 {f['height']}p",  
            callback_data=f"vf|{f['id']}|{chat_id}"  
        )  
    )  

bot.edit_message_text(  
    f"🎯 Select Quality:\n\n🎬 {title}",  
    chat_id,  
    msg_id,  
    reply_markup=markup  
)

------------------ QUEUE ------------------

def process_queue():
global downloading

if downloading or not queue:  
    return  

downloading = True  
url, chat_id, msg_id, format_id = queue.pop(0)  

threading.Thread(  
    target=download_video,  
    args=(url, chat_id, msg_id, format_id),  
    daemon=True  
).start()

------------------ FORMAT ------------------

def get_format(format_id):
return format_id if format_id else "bv*+ba/best"

------------------ DOWNLOAD CORE FIX ------------------

def download_video(url, chat_id, msg_id, format_id=None, retry=0):
global downloading

file_id = str(uuid.uuid4())  
filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.mp4")  

thumbnail_path = None  

try:  
    bot.edit_message_text("⚡ Starting Engine...", chat_id, msg_id)  

    ydl_opts = {  
        'format': get_format(format_id),  
        'merge_output_format': 'mp4',  
        'outtmpl': filepath,  
        'progress_hooks': [lambda d: progress_hook(d, chat_id, msg_id)],  
        'retries': 5,  
        'fragment_retries': 5,  
        'http_headers': {'User-Agent': 'Mozilla/5.0'}  
    }  

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
        info = ydl.extract_info(url, download=True)  

    title = info.get("title", "Video")  

    # FIXED THUMBNAIL  
    thumb_url = info.get("thumbnail")  
    thumbnail_path = download_thumbnail(thumb_url)  

    file_size = os.path.getsize(filepath)  

    # Upload animation  
    for p in [10, 30, 50, 70, 90, 100]:  
        ui(  
            chat_id,  
            msg_id,  
            "📤 Uploading...",  
            p,  
            human(file_size * (p/100)),  
            human(file_size),  
            "Sending...",  
            "Processing..."  
        )  
        time.sleep(0.4)  

    # SEND VIDEO FIX  
    if thumbnail_path:  
        with open(thumbnail_path, "rb") as thumb:  
            with open(filepath, "rb") as f:  
                bot.send_video(  
                    chat_id,  
                    f,  
                    caption=f"🎬 {title}",  
                    supports_streaming=True,  
                    thumb=thumb  
                )  
    else:  
        with open(filepath, "rb") as f:  
            bot.send_video(  
                chat_id,  
                f,  
                caption=f"🎬 {title}",  
                supports_streaming=True  
            )  

    bot.delete_message(chat_id, msg_id)  

    if thumbnail_path and os.path.exists(thumbnail_path):  
        os.remove(thumbnail_path)  

    os.remove(filepath)  

except Exception as e:  
    if retry < 3:  
        return download_video(url, chat_id, msg_id, format_id, retry+1)  

    bot.send_message(chat_id, f"❌ Failed:\n{e}")  

downloading = False  
process_queue()

------------------ CALLBACK ------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("vf|"))
def handle_quality(call):
try:
_, format_id, chat_id = call.data.split("|")
chat_id = int(chat_id)

data = video_cache.get(chat_id)  
    if not data:  
        return  

    url = data["url"]  

    bot.edit_message_text(  
        "✅ Quality selected\n🚀 Starting download...",  
        chat_id,  
        call.message.message_id  
    )  

    msg = bot.send_message(chat_id, "🔍 Processing...")  

    queue.append((url, chat_id, msg.message_id, format_id))  
    process_queue()  

except:  
    pass

------------------ COMMANDS ------------------

@bot.message_handler(commands=['dl'])
def cmd_dl(message):
if message.chat.id != OWNER_ID:
return bot.reply_to(message, "❌ Not allowed")

url = decrypt_url(message.text.split(maxsplit=1)[1])  
msg = bot.reply_to(message, "🔍 Fetching available quality...")  
show_quality_menu(message.chat.id, msg.message_id, url)

@bot.message_handler(commands=['start'])
def start(message):
if message.chat.id != OWNER_ID:
return bot.reply_to(message, "❌ Not allowed")

bot.reply_to(message, "🚀 PRO MAX STREAM BOT ACTIVE")

------------------ RUN ------------------

print("🚀 PRO MAX BOT RUNNING")
bot.infinity_polling()
