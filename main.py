#!/usr/bin/env python3

import os
import uuid
import threading
import base64
import requests
import urllib3
import dns.resolver
import time
import subprocess

from dotenv import load_dotenv
from Cryptodome.Util.Padding import unpad
from Cryptodome.Cipher import AES

import telebot
import yt_dlp

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ------------------ PRO MAX BOT v10.1 SUPER FAST ------------------
# ULTRA SPEED EDITION (Download + Upload optimized)
# 
# 🔥 DOWNLOAD SPEED BOOST:
#   • Auto-detects & uses aria2c (16 connections) → 5-10x faster than default
#   • Fallback to yt-dlp high-concurrent fragments (16 threads)
#   • Larger chunk size + optimized headers
#   • More retries & fragment retries
# 
# 📤 UPLOAD SPEED BOOST:
#   • Reduced fake upload animation delay (feels faster)
#   • Telegram streaming enabled + optimized send calls
#   • No unnecessary sleeps during upload
# 
# All previous v10 features + full playlist + cancel + queue remain 100% stable.
# 
# ✨ NEW COMMANDS ADDED (v10.2):
#   • /rec <M3U8_link> <seconds> <filename>  → Record live HLS/M3U8 stream for exact duration (ffmpeg powered)
#   • /mediainfo <url>                       → Full ffprobe media data (streams, format, bitrate, codec, etc.)

urllib3.disable_warnings()

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']

# ------------------ ENV ------------------

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DOWNLOAD_FOLDER = "DL"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

queue = []
downloading = False
MAX_QUEUE = 20

video_cache = {}
last_update_time = {}
active_downloads = {}

# ------------------ CHECK FOR aria2c (SUPER FAST DOWNLOADER) ------------------

def has_aria2c():
    try:
        subprocess.check_call(['aria2c', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

ARIA2C_AVAILABLE = has_aria2c()

if not ARIA2C_AVAILABLE:
    print("⚠️  aria2c NOT found! Download will be slower.")
    print("   Install it for SUPER FAST speed:")
    print("   VPS:    sudo apt install aria2 -y")
    print("   Termux: pkg install aria2")
else:
    print("🚀 aria2c detected → MAXIMUM download speed enabled!")

# ------------------ CHECK FOR ffmpeg (REC + MEDIAINFO) ------------------

def has_ffmpeg():
    try:
        subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

FFMPEG_AVAILABLE = has_ffmpeg()

if not FFMPEG_AVAILABLE:
    print("⚠️  ffmpeg/ffprobe NOT found! /rec and /mediainfo will not work.")
    print("   Install it for REC + Media Data:")
    print("   VPS:    sudo apt install ffmpeg -y")
    print("   Termux: pkg install ffmpeg")
else:
    print("🚀 ffmpeg detected → REC mode + full Media Info enabled!")

# ------------------ ADMIN SYSTEM ------------------

admins = set()
admins.add(OWNER_ID)

def is_admin(user_id):
    return user_id in admins

# ------------------ AES DECRYPT ------------------

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

# ------------------ SIZE FORMAT ------------------

def human(n):
    if not n:
        return "0B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f}{unit}"
        n /= 1024
    return f"{n:.2f}TB"

# ------------------ THUMBNAIL ------------------

def download_thumbnail(url):
    if not url:
        return None
    path = os.path.join(DOWNLOAD_FOLDER, f"thumb_{uuid.uuid4()}.jpg")
    try:
        r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200 and len(r.content) > 1000:
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except:
        pass
    return None

# ------------------ FORMAT FETCH ------------------

def get_available_formats(url):
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    is_playlist = bool(info.get('entries') and len(info.get('entries', [])) > 1)
    title = info.get("title", "Video")

    formats = info.get("formats", [])
    result = []

    for f in formats:
        if f.get("vcodec") != "none" and f.get("height"):
            size = f.get("filesize") or f.get("filesize_approx") or 0
            size_str = human(size) if size > 0 else "?"
            result.append({
                "id": f["format_id"],
                "height": f["height"],
                "size": size_str,
            })

    seen = set()
    cleaned = []
    for f in sorted(result, key=lambda x: x["height"], reverse=True):
        if f["height"] not in seen:
            seen.add(f["height"])
            cleaned.append(f)

    return cleaned[:8], title, info, is_playlist

# ------------------ UI v10.1 PREMIUM ------------------

def ui(chat_id, msg_id, stage, percent, cur, total, speed="N/A", eta="N/A"):
    try:
        key = f"{chat_id}_{msg_id}"
        now = time.time()
        if key in last_update_time and now - last_update_time[key] < 0.8:
            return
        last_update_time[key] = now

        bar_len = 14
        filled = int((percent / 100) * bar_len)
        bar = "▰" * filled + "▱" * (bar_len - filled)

        text = (
            f"✨ <b>DL AND REC BOT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            
            f"🚀 <i>{stage}</i>\n\n"
            
            f"〔{bar}〕\n"
            f"➤ <b>{percent:.1f}% Complete</b>\n\n"
            
            f"📦 <b>Progress :</b> {cur} / {total}\n"
            f"⚡ <b>Speed    :</b> {speed}\n"
            f"⏳ <b>ETA      :</b> {eta}\n\n"
            
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 <i>Premium Performance Mode</i>"
        )

        bot.edit_message_text(text, chat_id, msg_id)
    except:
        pass
        
# ------------------ PROGRESS HOOK ------------------

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
        "📥 Downloading (SUPER FAST)...",
        percent,
        human(done),
        human(total),
        f"{round(speed/1024/1024,2)} MB/s" if speed else "N/A",
        f"{int(eta)}s" if eta else "N/A"
    )

# ------------------ QUALITY MENU ------------------

def show_quality_menu(chat_id, msg_id, url):
    formats, title, info, is_playlist = get_available_formats(url)

    video_cache[chat_id] = {
        "url": url,
        "formats": {f["id"]: f for f in formats},
        "title": title,
        "info": info,
        "is_playlist": is_playlist
    }

    markup = InlineKeyboardMarkup(row_width=1)

    if is_playlist:
        markup.add(InlineKeyboardButton("📋 Download FULL Playlist (All Videos)", callback_data=f"pl|full|{chat_id}"))

    markup.add(InlineKeyboardButton("🔥 Highest Quality", callback_data=f"vf|best|{chat_id}"))

    for f in formats:
        btn_text = f"🎬 {f['height']}p"
        if f.get("size") and f["size"] != "?":
            btn_text += f" • {f['size']}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"vf|{f['id']}|{chat_id}"))

    markup.add(InlineKeyboardButton("🎵 Audio Only (MP3 192kbps)", callback_data=f"af|audio|{chat_id}"))

    bot.edit_message_text(
        f"🎯 Select Quality:\n\n{'📋 Playlist detected – ' if is_playlist else ''}🎬 {title}",
        chat_id,
        msg_id,
        reply_markup=markup
    )

# ------------------ QUEUE ------------------

def process_queue():
    global downloading
    if downloading or not queue:
        return
    downloading = True
    item = queue.pop(0)
    threading.Thread(target=download_video, args=item, daemon=True).start()

# ------------------ DOWNLOAD CORE v10.1 (SUPER FAST) ------------------

def download_video(url, chat_id, msg_id, format_id=None, is_audio=False, retry=0):
    global downloading

    cancel_event = threading.Event()
    active_downloads[msg_id] = cancel_event

    file_id = str(uuid.uuid4())
    if is_audio:
        final_filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.mp3")
        outtmpl = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")
    else:
        final_filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.mp4")
        outtmpl = final_filepath

    thumbnail_path = None
    try:
        bot.edit_message_text("⚡ Starting PRO MAX ENGINE v10.1 (SUPER FAST)...", chat_id, msg_id)

        ydl_opts = {
            'progress_hooks': [lambda d: progress_hook(d, chat_id, msg_id)],
            'retries': 15,
            'fragment_retries': 15,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            'outtmpl': outtmpl,
            'concurrent_fragment_downloads': 16,
            'http_chunk_size': 10 * 1024 * 1024,
        }

        if ARIA2C_AVAILABLE and not is_audio:
            ydl_opts.update({
                'external_downloader': 'aria2c',
                'external_downloader_args': {
                    'default': [
                        '-x', '16', '-s', '16', '-j', '16',
                        '--min-split-size=1M',
                        '--max-connection-per-server=16',
                        '--optimize-concurrent-downloads=true',
                        '--split=16',
                        '--max-tries=0',
                        '--continue=true'
                    ]
                }
            })
            print(f"🚀 Using aria2c for {url[:50]}... (16 connections)")
        else:
            print(f"⚡ Using high-concurrent fragments for {url[:50]}...")

        if is_audio:
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif format_id == "best":
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            video_format = format_id if format_id else "bv*"
            ydl_opts['format'] = f"{video_format}+bestaudio/best"
            ydl_opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = info.get("title", "Media")
        duration = info.get("duration", 0)
        views = info.get("view_count", 0)
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "N/A"

        thumb_url = info.get("thumbnail")
        thumbnail_path = download_thumbnail(thumb_url)

        file_size = os.path.getsize(final_filepath)

        if file_size > 1980 * 1024 * 1024:
            bot.send_message(chat_id, f"❌ File too large ({human(file_size)})\nTelegram limit: 1980MB")
            return

        for p in [20, 45, 65, 80, 92, 100]:
            if cancel_event.is_set():
                raise Exception("Cancelled by user")
            ui(chat_id, msg_id, "📤 Uploading to Telegram (FAST)...", p,
               human(file_size * (p/100)), human(file_size),
               "Sending...", "Almost done...")
            time.sleep(0.22)

        caption = f"🎬 {title}\n📊 {views:,} views | ⏱ {duration_str}\n🚀 PRO MAX BOT v10.1 SUPER FAST"

        if is_audio:
            with open(final_filepath, "rb") as f:
                bot.send_audio(chat_id, f, caption=caption, title=title)
        else:
            if thumbnail_path:
                with open(thumbnail_path, "rb") as thumb:
                    with open(final_filepath, "rb") as f:
                        bot.send_video(chat_id, f, caption=caption, supports_streaming=True, thumb=thumb)
            else:
                with open(final_filepath, "rb") as f:
                    bot.send_video(chat_id, f, caption=caption, supports_streaming=True)

        bot.delete_message(chat_id, msg_id)

    except Exception as e:
        if "Cancelled by user" in str(e):
            bot.send_message(chat_id, "❌ Download cancelled by user")
        elif retry < 3:
            bot.edit_message_text(f"⚠️ Retry {retry+1}/3 (SUPER FAST mode)...", chat_id, msg_id)
            time.sleep(3)
            return download_video(url, chat_id, msg_id, format_id, is_audio, retry + 1)
        else:
            bot.send_message(chat_id, f"❌ Failed:\n{str(e)[:400]}")
    finally:
        for path in [final_filepath, thumbnail_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        active_downloads.pop(msg_id, None)

    downloading = False
    process_queue()

# ------------------ UPDATED: M3U8 RECORDER v10.3 (Multi-Audio Selection) ------------------

def get_stream_info(m3u8_url):
    """Get video + all audio tracks info using ffprobe"""
    if not FFMPEG_AVAILABLE:
        return None, []

    try:
        probe_cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', m3u8_url
        ]
        result = subprocess.check_output(probe_cmd, stderr=subprocess.STDOUT, timeout=25)
        data = json.loads(result.decode('utf-8', errors='replace'))

        video_streams = []
        audio_streams = []

        for stream in data.get('streams', []):
            codec_type = stream.get('codec_type')
            index = stream.get('index')

            if codec_type == 'video':
                width = stream.get('width', '?')
                height = stream.get('height', '?')
                codec = stream.get('codec_name', 'unknown').upper()
                video_streams.append({
                    'index': index,
                    'quality': f"{width}×{height} • {codec}" if width != '?' and height != '?' else codec
                })

            elif codec_type == 'audio':
                lang = stream.get('tags', {}).get('language', 'und')
                title = stream.get('tags', {}).get('title', '')
                codec = stream.get('codec_name', 'Audio').upper()
                
                audio_name = title if title else (lang.upper() if lang != 'und' else f"Audio {index}")
                audio_streams.append({
                    'index': index,
                    'name': audio_name,
                    'lang': lang.upper() if lang != 'und' else 'UND',
                    'codec': codec
                })

        # Take first video stream (usually index 0)
        main_video = video_streams[0] if video_streams else None
        return main_video, audio_streams

    except Exception as e:
        print(f"ffprobe error: {e}")
        return None, []


def record_stream_multi(m3u8_url, duration, filename, chat_id, msg_id, selected_audio_indices=None):
    try:
        if not FFMPEG_AVAILABLE:
            bot.send_message(chat_id, "❌ ffmpeg not installed.")
            return

        filepath = os.path.join(DOWNLOAD_FOLDER, f"{filename}.mp4")

        bot.edit_message_text(
            f"📼 <b>PRO MAX REC MODE v10.3</b>\n\n"
            f"🔗 {m3u8_url[:70]}...\n"
            f"⏱ Recording {duration} seconds...\n"
            f"🎵 Multi-Audio Mode",
            chat_id, msg_id
        )

        # Build ffmpeg command with selected audio tracks
        cmd = ['ffmpeg', '-y', '-i', m3u8_url, '-t', str(duration), '-c', 'copy']

        # Map video (usually stream 0)
        cmd.extend(['-map', '0:v:0'])

        # Map selected audio tracks
        if selected_audio_indices:
            for idx in selected_audio_indices:
                cmd.extend(['-map', f'0:a:{idx}'])
        else:
            # Default: map all audio if none selected (or first one)
            cmd.extend(['-map', '0:a?'])

        cmd.extend([
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            filepath
        ])

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )

        # Live recording progress
        start_time = time.time()
        while process.poll() is None:
            elapsed = min(int(time.time() - start_time), duration)
            percent = min(int((elapsed / duration) * 100), 100)

            ui(chat_id, msg_id, 
               f"📼 <b>RECORDING LIVE (Multi-Audio)...</b>\n"
               f"⏱ {elapsed}/{duration} seconds", 
               percent, f"{elapsed}s", f"{duration}s", 
               "Recording...", "Please wait")
            time.sleep(2)

        stdout, stderr = process.communicate(timeout=30)

        if process.returncode != 0:
            error_preview = stderr[-800:] if stderr else "Unknown error"
            bot.send_message(chat_id, f"❌ Recording failed:\n<pre>{error_preview}</pre>", parse_mode="HTML")
            return

        if not os.path.exists(filepath) or os.path.getsize(filepath) < 10*1024:
            bot.send_message(chat_id, "❌ Recorded file is empty or too small")
            return

        file_size = os.path.getsize(filepath)

        if file_size > 50 * 1024 * 1024:
            bot.send_message(chat_id, f"❌ File too large ({human(file_size)})\nTelegram limit: 50MB")
            os.remove(filepath)
            return

        # ==================== Probe final file for info ====================
        actual_duration = duration
        quality_text = "Unknown"
        audio_list = []

        try:
            probe_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                        '-show_format', '-show_streams', filepath]
            probe_out, _ = subprocess.Popen(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate(timeout=15)

            if probe_out:
                data = json.loads(probe_out)
                if 'format' in data and 'duration' in data['format']:
                    actual_duration = round(float(data['format']['duration']))

                for stream in data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        w = stream.get('width', '?')
                        h = stream.get('height', '?')
                        c = stream.get('codec_name', 'unknown').upper()
                        quality_text = f"{w}×{h} • {c}" if w != '?' and h != '?' else c

                    elif stream.get('codec_type') == 'audio':
                        lang = stream.get('tags', {}).get('language', 'und')
                        title = stream.get('tags', {}).get('title', '')
                        name = title if title else (lang.upper() if lang != 'und' else 'Audio')
                        audio_list.append(name)

        except:
            pass

        # ==================== Final Filename with BDIX + 12-hour Time ====================
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%I:%M:%S %p")   # 12-hour with AM/PM

        name_without_ext = os.path.splitext(filename)[0]
        final_filename = f"{name_without_ext}.{date_str}.{time_str.replace(':', '-')}.BDIX.mkv"

        # Upload progress
        for p in [20, 45, 65, 80, 92, 100]:
            uploaded = int(file_size * (p / 100))
            ui(chat_id, msg_id, 
               f"📤 <b>UPLOADING...</b>\n"
               f"📁 {final_filename}\n"
               f"📦 {human(uploaded)} / {human(file_size)}", 
               p, human(uploaded), human(file_size),
               "Uploading...", "Almost done...")
            time.sleep(0.25)

        # Caption
        audio_text = ", ".join(audio_list) if audio_list else "Unknown"

        caption = (
            f"Filename: <code>{final_filename}</code>\n"
            f"Quality: {quality_text}\n"
            f"Audio: {audio_text}\n"
            f"Date: {date_str}\n"
            f"Time: {time_str}\n\n"
            f"🚀 PRO MAX BOT v10.3"
        )

        with open(filepath, "rb") as f:
            bot.send_video(chat_id, f, caption=caption, supports_streaming=True)

        bot.delete_message(chat_id, msg_id)

    except Exception as e:
        bot.send_message(chat_id, f"❌ REC error: {str(e)[:400]}")
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass


# ------------------ UPDATED /rec COMMAND HANDLER ------------------

import json
import datetime   # Make sure these are at the top with other imports

@bot.message_handler(commands=['rec'])
def cmd_rec(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return bot.reply_to(message, "❌ Not allowed")

    try:
        parts = message.text.split()

        # Check for -m flag
        use_multi = False
        if len(parts) > 1 and parts[1] == '-m':
            use_multi = True
            parts.pop(1)  # remove -m flag

        if len(parts) < 4:
            usage = "❌ Usage:\n"
            usage += "/rec <M3U8_link> <seconds> <filename>\n"
            usage += "/rec -m <M3U8_link> <seconds> <filename>  ← Multi Audio Selection"
            return bot.reply_to(message, usage)

        m3u8_url = decrypt_url(parts[1])
        try:
            rec_time = int(parts[2])
            if rec_time < 1:
                raise ValueError
        except:
            return bot.reply_to(message, "❌ <seconds> must be a positive integer")

        filename = parts[3].strip().replace(" ", "_")[:50]

        msg = bot.reply_to(
    message,
    "✨ <b>PRO MAX ENGINE</b>\n"
    "━━━━━━━━━━━━━━\n\n"
    "🔍 <i>Analyzing stream…</i>\n\n"
    "Please wait..."
)

        if use_multi:
            # Multi-audio mode - show selection buttons
            video_info, audio_streams = get_stream_info(m3u8_url)

            if not audio_streams:
                bot.edit_message_text("❌ No audio tracks found or failed to analyze stream.", 
                                    message.chat.id, msg.message_id)
                return

            # Save data for callback
            video_cache[message.chat.id] = {
                "m3u8_url": m3u8_url,
                "duration": rec_time,
                "filename": filename,
                "msg_id": msg.message_id,
                "audio_streams": audio_streams,
                "video_info": video_info
            }

            markup = InlineKeyboardMarkup(row_width=1)
            for i, audio in enumerate(audio_streams):
                btn_text = f"🎵 {audio['name']} ({audio['lang']}) • {audio['codec']}"
                markup.add(InlineKeyboardButton(btn_text, callback_data=f"rec_audio|{i}|{message.chat.id}"))

            markup.add(InlineKeyboardButton("✅ Record with ALL Audio Tracks", callback_data=f"rec_audio|all|{message.chat.id}"))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data=f"rec_cancel|{message.chat.id}"))

            bot.edit_message_text(
                f"🎯 <b>Multi-Audio Selection</b>\n\n"
                f"Select audio track(s) to record:\n"
                f"📼 {filename}\n"
                f"⏱ {rec_time} seconds",
                message.chat.id, msg.message_id, reply_markup=markup
            )

        else:
            # Normal single mode
            bot.edit_message_text(f"📼 Starting normal recording for {rec_time}s → {filename}.mp4", 
                                message.chat.id, msg.message_id)
            threading.Thread(
                target=record_stream_multi,
                args=(m3u8_url, rec_time, filename, message.chat.id, msg.message_id, None),
                daemon=True
            ).start()

    except Exception as e:
        bot.reply_to(message, f"❌ REC usage error: {str(e)[:150]}")


# ------------------ NEW: MEDIAINFO COMMAND (v10.2) ------------------

@bot.message_handler(commands=['mediainfo'])
def cmd_mediainfo(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return bot.reply_to(message, "❌ Not allowed")

    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            return bot.reply_to(message, "❌ Usage: /mediainfo <M3U8_link or video URL>")

        url = decrypt_url(parts[1])

        msg = bot.reply_to(message, "🔍 Fetching full media data with ffprobe...")

        if not FFMPEG_AVAILABLE:
            bot.edit_message_text("❌ ffmpeg/ffprobe not installed", message.chat.id, msg.message_id)
            return

        probe_cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format', '-show_streams',
            url
        ]

        result = subprocess.check_output(probe_cmd, stderr=subprocess.STDOUT, timeout=40)
        info_json = result.decode('utf-8', errors='replace')

        # Truncate to fit Telegram message (4096 char limit)
        preview = info_json[:3800] + "\n... (truncated)" if len(info_json) > 3800 else info_json

        bot.edit_message_text(
            f"<b>📊 PRO MAX Media Data Info</b>\n\n"
            f"🔗 <code>{url[:80]}...</code>\n\n"
            f"<pre>{preview}</pre>",
            message.chat.id, msg.message_id, parse_mode="HTML"
        )

    except subprocess.TimeoutExpired:
        bot.edit_message_text("❌ ffprobe timeout (stream too slow)", message.chat.id, msg.message_id)
    except Exception as e:
        bot.reply_to(message, f"❌ MediaInfo error: {str(e)[:250]}")

# ------------------ CALLBACK v10.1 (DL Command + Playlist) ------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith(("vf|", "af|", "pl|")))
def handle_quality(call):
    try:
        parts = call.data.split("|")
        qtype = parts[0]
        chat_id = int(parts[2])

        data = video_cache.get(chat_id)
        if not data:
            return

        url = data["url"]

        if qtype == "pl":
            bot.edit_message_text("📋 Fetching playlist videos (SUPER FAST)...", chat_id, call.message.message_id)
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    playlist_info = ydl.extract_info(url, download=False)
                entries = playlist_info.get('entries', [])
                if not entries:
                    bot.send_message(chat_id, "❌ No videos found in playlist")
                    return

                bot.send_message(chat_id, f"✅ Playlist loaded: {len(entries)} videos\n🚀 Starting FULL SUPER FAST download...")

                for idx, entry in enumerate(entries, 1):
                    video_url = entry.get('url') or entry.get('webpage_url')
                    if not video_url:
                        continue
                    title = entry.get('title', f"Video {idx}")[:60]

                    msg = bot.send_message(chat_id, f"🎬 Playlist video {idx}/{len(entries)}\n{title}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("⛔ Cancel This Video", callback_data=f"cancel|{msg.message_id}"))
                    bot.edit_message_text(f"🎬 Processing playlist video {idx}/{len(entries)}...", chat_id, msg.message_id, reply_markup=markup)

                    queue.append((video_url, chat_id, msg.message_id, None, False))
                    process_queue()
                    time.sleep(0.8)

            except Exception as e:
                bot.send_message(chat_id, f"❌ Playlist error: {str(e)[:200]}")
            return

        if qtype == "vf":
            format_id = parts[1]
            is_audio = False
            status_text = "✅ Quality selected"
        else:
            format_id = None
            is_audio = True
            status_text = "🎵 Audio selected"

        bot.edit_message_text(f"{status_text}\n🚀 Starting SUPER FAST download...", chat_id, call.message.message_id)

        msg = bot.send_message(chat_id, "🔍 Processing...")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⛔ Cancel Download", callback_data=f"cancel|{msg.message_id}"))
        bot.edit_message_text("🔍 Processing...", chat_id, msg.message_id, reply_markup=markup)

        queue.append((url, chat_id, msg.message_id, format_id, is_audio))
        process_queue()

    except:
        pass


# ------------------ CANCEL CALLBACK (DL + REC) ------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel|"))
def handle_cancel(call):
    try:
        msg_id = int(call.data.split("|")[1])
        if msg_id in active_downloads:
            active_downloads[msg_id].set()
            bot.answer_callback_query(call.id, "⛔ Cancelling...")
        else:
            bot.answer_callback_query(call.id, "No active download", show_alert=True)
    except:
        pass


# ==================== NEW: Multi-Audio REC Callback (v10.3) ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith(("rec_audio|", "rec_cancel|")))
def handle_rec_audio(call):
    try:
        parts = call.data.split("|")
        action = parts[0]
        chat_id = int(parts[-1])

        data = video_cache.get(chat_id)
        if not data:
            return bot.answer_callback_query(call.id, "Session expired")

        if action == "rec_cancel":
            bot.edit_message_text("❌ Recording cancelled by user", chat_id, data["msg_id"])
            video_cache.pop(chat_id, None)
            return

        if action == "rec_audio":
            selected = parts[1]
            bot.answer_callback_query(call.id, "Starting recording...")

            if selected == "all":
                selected_indices = None          # All audio tracks
            else:
                selected_indices = [int(selected)]   # Single audio track

            bot.edit_message_text(
                f"📼 Starting recording with selected audio...\n"
                f"⏱ {data['duration']} seconds",
                chat_id, data["msg_id"]
            )

            threading.Thread(
                target=record_stream_multi,
                args=(data["m3u8_url"], data["duration"], data["filename"], 
                      chat_id, data["msg_id"], selected_indices),
                daemon=True
            ).start()

            video_cache.pop(chat_id, None)

    except Exception as e:
        print(f"REC callback error: {e}")

# ------------------ COMMANDS ------------------

@bot.message_handler(commands=['dl'])
def cmd_dl(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return bot.reply_to(message, "❌ Not allowed")

    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            return bot.reply_to(message, "❌ Usage: /dl <encoded_url>")
        url = decrypt_url(parts[1])
        msg = bot.reply_to(message, "🔍 Fetching qualities...")
        show_quality_menu(message.chat.id, msg.message_id, url)
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)[:150]}")

@bot.message_handler(commands=['rec'])
def cmd_rec(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return bot.reply_to(message, "❌ Not allowed")

    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 4:
            return bot.reply_to(message, "❌ Usage: /rec <M3U8_link> <seconds> <filename>\n\nExample:\n/rec https://example.com/stream.m3u8 3600 my_recording")

        m3u8_url = decrypt_url(parts[1])
        try:
            rec_time = int(parts[2])
            if rec_time < 1:
                raise ValueError
        except:
            return bot.reply_to(message, "❌ <seconds> must be a positive integer")

        filename = parts[3].strip().replace(" ", "_")[:50]  # safe filename
        filepath = os.path.join(DOWNLOAD_FOLDER, f"{filename}.mp4")

        msg = bot.reply_to(message, f"📼 Starting REC for {rec_time}s → {filename}.mp4")
        threading.Thread(target=record_stream, args=(m3u8_url, rec_time, filepath, message.chat.id, msg.message_id), daemon=True).start()

    except Exception as e:
        bot.reply_to(message, f"❌ REC usage error: {str(e)[:120]}")

@bot.message_handler(commands=['queue'])
def cmd_queue(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    text = "<b>📋 PRO MAX Queue v10.1</b>\n\n"
    text += f"🔄 Currently downloading: {'Yes' if downloading else 'No'}\n"
    text += f"⏳ Items waiting: {len(queue)}\n\n"
    if queue:
        text += "Next in line:\n" + "\n".join([f"• Item {i+1}" for i in range(len(queue))])
    bot.reply_to(message, text)

@bot.message_handler(commands=['clearqueue'])
def cmd_clearqueue(message):
    if message.from_user.id != OWNER_ID:
        return bot.reply_to(message, "❌ Owner only")
    queue.clear()
    bot.reply_to(message, "🗑 Queue cleared!")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return bot.reply_to(message, "❌ Not allowed")
    bot.reply_to(message,
        "🚀 <b>PRO MAX BOT v10.2 SUPER FAST</b>\n\n"
        "/dl &lt;encoded_url&gt; → Start SUPER FAST download\n"
        "/rec &lt;M3U8&gt; &lt;seconds&gt; &lt;filename&gt; → Record live HLS stream\n"
        "/mediainfo &lt;url&gt; → Full ffprobe media data\n"
        "/queue → Show queue\n"
        "/clearqueue → Clear queue (owner)\n"
        "/help → This message\n\n"
        "✅ aria2c = 5-10x faster downloads\n"
        "✅ ffmpeg REC + MediaInfo\n"
        "✅ Full playlist support\n"
        "✅ Cancel button for each file"
    )

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id

    photo_url = "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEh1i2YzNy6ldpUOoInfvqCc4jGdo4tllIZ8iHTurkNaT-2SPTXZsf3VHWSQDDPAruafwIkf1MqGQujBqAnpq7A0rKiib9LZRea55Q2NmeFL2MjTfXA-g2U5DaP6Zm-NclTN0UfI-4Uh8aBfkY2xSz041ne94bu7xbFpAJ5lVgzaKg04dkYZ8caSCh26LWY/s1200/1000067709.jpg"

    # 🔘 Buttons
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💎 Upgrade", url="https://t.me/JOYDVL"),
        InlineKeyboardButton("📢 Updates", url="https://t.me/+sPggwQH5Vbc1N2Rl")
    )

    # ❌ Non-premium user
    if not is_admin(user_id):
        text = """🔐 *Premium Access Required*

━━━━━━━━━━━━━━━━━━━━━━━  
🚫 You are not authorized to use this bot

💎 Unlock Features:
• ⚡ Ultra Fast Download  
• 🎥 M3U8 Recording  
• ☁️ Auto Upload  
• 📊 Live Progress  

━━━━━━━━━━━━━━━━━━━━━━━  
👉 Click below to upgrade
"""
        return bot.send_photo(
            message.chat.id,
            photo=photo_url,
            caption=text,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # ✅ Premium user
    status = "🚀 <b>SUPER PREMIUM BOT ACTIVE</b>\n\n"

    status += "\n<b>🚀 Features</b>\n"
    status += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    status += "🎬 M3U8 Recording\n"
    status += "⚡ Ultra Fast Download\n"
    status += "📊 Live Progress Bar\n"
    status += "🎧 Multi Audio Support\n"
    status += "☁️ Auto Upload to Telegram\n"
    status += "🛑 Cancel Anytime\n"

    status += "\n<b>📌 Commands</b>\n"
    status += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    status += "🔹 <code>/dl link</code>\n"
    status += "🔹 <code>/rec link time filename</code>\n"
    status += "🔹 <code>/mediainfo link</code>\n"

    status += "\n🔥 <b>Enjoy Premium Power</b>"

    bot.send_photo(
        message.chat.id,
        photo=photo_url,
        caption=status,
        parse_mode="HTML",
        reply_markup=markup
    )

# ------------------ RUN ------------------

print("🚀 PRO MAX BOT v10.2 SUPER FAST STARTED")
print("   Download speed maximized with aria2c (if installed)")
print("   REC + MediaInfo powered by ffmpeg")
bot.infinity_polling()
