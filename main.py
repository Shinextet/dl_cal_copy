import os
import asyncio
import yt_dlp
import logging
import threading
import re
from flask import Flask
from moviepy import VideoFileClip
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- CONFIGURATIONS ---
# သင်အသုံးပြုမည့် တစ်ခုတည်းသော Bot Token
TOKEN = '8785132220:AAHcWzGm9wE6rL-Zir_5SAM-CU_HqbGrf4o'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- FLASK WEB SERVER (For Render/Uptime) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Online and Active!"

def run_flask():
    # Render အတွက် Port setup
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 မင်္ဂလာပါ! အားလုံးကို တစ်ခုတည်းမှာ စုစည်းပေးထားပါတယ်။\n\n"
        "✨ **ကျွန်တော် ဘာတွေလုပ်ပေးနိုင်လဲ?**\n"
        "1️⃣ TikTok Link ပေးရင် Video/Audio ဒေါင်းပေးမယ်။\n"
        "2️⃣ သင်္ချာပုစ္ဆာတွေ တွက်ပေးမယ် (ဥပမာ- 25*4)။\n"
        "3️⃣ စာထဲက ဂဏန်းရှည်တွေကို Copy ကူးရလွယ်အောင် ထုတ်ပေးမယ်။\n"
        "4️⃣ ဗီဒီယိုဖိုင် ပို့ပေးရင် MP3 ပြောင်းပေးမယ် (၅ မိနစ်အောက်)။"
    )

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    
    # 1. TikTok Downloader Check
    if "tiktok.com" in text:
        keyboard = [[
            InlineKeyboardButton("🎥 MP4 (Video)", callback_data=f"mp4|{text}"),
            InlineKeyboardButton("🎵 MP3 (Audio)", callback_data=f"mp3|{text}")
        ]]
        await update.message.reply_text("TikTok အတွက် ဘာဒေါင်းမလဲ?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 2. Calculator Check
    math_match = re.search(r'(\d+[\+\-\*\/]\d+)', text)
    if math_match:
        try:
            expr = math_match.group(1)
            result = eval(expr)
            await update.message.reply_text(f"🧮 ရလဒ်: {result}")
            return
        except:
            pass

    # 3. Number Extractor (ဂဏန်း ၄ လုံးနှင့်အထက်)
    numbers = re.findall(r'\d{4,}', text)
    if numbers:
        reply = " ".join([f"`{n}`" for n in numbers])
        await update.message.reply_text(reply, parse_mode='MarkdownV2')

async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if video.duration > 300:
        await update.message.reply_text("❌ ၅ မိနစ်ထက်ကျော်သော video များကို လက်မခံပါ။")
        return
    
    context.user_data['last_video_id'] = video.file_id
    await update.message.reply_text(
        "🎥 ဗီဒီယိုကို MP3 ပြောင်းမလား?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ပြောင်းမည်", callback_data="conv_mp3")]])
    )

async def convert_to_mp3_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_id = context.user_data.get('last_video_id')
    status = await query.edit_message_text("🔄 MP3 ပြောင်းနေပါပြီ...")
    
    v_path, a_path = f"{file_id}.mp4", f"{file_id}.mp3"
    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(v_path)
        clip = VideoFileClip(v_path)
        clip.audio.write_audiofile(a_path, logger=None)
        clip.close()
        with open(a_path, 'rb') as f:
            await context.bot.send_audio(chat_id=query.message.chat_id, audio=f)
        await status.delete()
    except Exception:
        await status.edit_text("❌ Error ဖြစ်သွားပါသည်။")
    finally:
        for p in [v_path, a_path]:
            if os.path.exists(p): os.remove(p)

async def tiktok_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice, url = query.data.split("|")
    status = await query.edit_message_text(f"⏳ {choice.upper()} ဒေါင်းနေပါပြီ...")

    ydl_opts = {
        'format': 'bestaudio/best' if choice == 'mp3' else 'best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }
    if choice == 'mp3':
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            fn = ydl.prepare_filename(info)
            if choice == 'mp3': fn = os.path.splitext(fn)[0] + ".mp3"
            
            with open(fn, 'rb') as f:
                if choice == 'mp4': await context.bot.send_video(chat_id=query.message.chat_id, video=f)
                else: await context.bot.send_audio(chat_id=query.message.chat_id, audio=f)
            await status.delete()
            if os.path.exists(fn): os.remove(fn)
    except:
        await status.edit_text("❌ TikTok ဒေါင်းလုပ် မအောင်မြင်ပါ။")

# --- MAIN RUNNER ---
if __name__ == '__main__':
    if not os.path.exists('downloads'): os.makedirs('downloads')
    
    # Flask Server ကို သပ်သပ် Thread နဲ့ Run မယ် (Render/Uptime အတွက်)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Bot Application Setup
    bot_app = ApplicationBuilder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_all_messages))
    bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video_upload))
    bot_app.add_handler(CallbackQueryHandler(tiktok_download_callback, pattern=r"^(mp4|mp3)\|"))
    bot_app.add_handler(CallbackQueryHandler(convert_to_mp3_callback, pattern="^conv_mp3$"))
    
    print("Combined Bot is Starting...")
    bot_app.run_polling()
