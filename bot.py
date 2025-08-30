import os
import threading
import time
import requests
import urllib.parse
from flask import Flask, request, redirect
from bs4 import BeautifulSoup
import telebot
from telebot import types

# ----------------- تنظیمات -----------------
TOKEN = os.environ.get("BOT_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
CHANNEL_IDS = [int(cid.strip()) for cid in os.environ.get("CHANNEL_IDS", "").split(",") if cid.strip()]
KOYEB_DOMAIN = os.environ.get("KOYEB_DOMAIN")  # مثال: yourapp.koyeb.app

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ----------------- لینک‌های موقت -----------------
links = {}  # {token: (real_url, expire_time)}

def create_temp_link(real_url, expire_seconds=600):
    token = str(int(time.time() * 1000))
    expire_time = time.time() + expire_seconds
    links[token] = (real_url, expire_time)
    return f"https://{KOYEB_DOMAIN}/go?f={token}"

@app.route("/go")
def go():
    token = request.args.get("f")
    if not token or token not in links:
        return "❌ لینک نامعتبر یا منقضی شده", 404
    url, expire = links[token]
    if time.time() > expire:
        del links[token]
        return "❌ لینک منقضی شده", 404
    return redirect(url, code=302)

# ----------------- تابع استخراج لینک واقعی -----------------
def get_download_link(search_query):
    query = search_query.replace(" ", "+")
    search_url = f"https://donyayeserial.com/?s={query}"
    
    r = requests.get(search_url)
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    first_result = soup.find("h2", class_="entry-title")
    if not first_result:
        return None

    link_page = first_result.find("a")["href"]
    r2 = requests.get(link_page)
    if r2.status_code != 200:
        return None

    soup2 = BeautifulSoup(r2.text, "html.parser")
    download_btn = soup2.find("a", href=True, text=lambda t: "دانلود" in t)
    if download_btn:
        return download_btn["href"]
    
    return None

# ----------------- چک عضویت -----------------
def is_member(user_id):
    for cid in CHANNEL_IDS:
        try:
            member = bot.get_chat_member(cid, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# ----------------- OMDb -----------------
def omdb_search(query):
    q = urllib.parse.quote(query)
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s={q}"
    r = requests.get(url).json()
    return r.get("Search", []) if r.get("Response")=="True" else []

def omdb_details(imdb_id):
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&i={imdb_id}&plot=full"
    return requests.get(url).json()

# ----------------- ربات -----------------
@bot.message_handler(func=lambda m: True)
def handle_query(m):
    uid = m.from_user.id
    if not is_member(uid):
        join_text = "\n".join([f"🔗 کانال: {cid}" for cid in CHANNEL_IDS])
        bot.send_message(uid, f"🔒 باید عضو همه کانال‌ها بشی:\n{join_text}")
        return

    query = m.text.strip()
    bot.send_message(uid, "⏳ در حال جستجو...")
    results = omdb_search(query)
    if not results:
        bot.send_message(uid, "❌ نتیجه‌ای پیدا نشد. اسم دقیق‌تر وارد کن.")
        return

    markup = types.InlineKeyboardMarkup()
    for item in results[:10]:
        label = f"{item['Title']} ({item['Year']})"
        cb = f"select|{item['imdbID']}"
        markup.add(types.InlineKeyboardButton(label, callback_data=cb))
    bot.send_message(uid, "🎬 نتایج پیدا شد — یکی رو انتخاب کن:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("select|"))
def callback_select(call):
    uid = call.from_user.id
    imdb_id = call.data.split("|")[1]
    movie = omdb_details(imdb_id)
    if movie.get("Response") != "True":
        bot.send_message(uid, "❌ خطا در دریافت اطلاعات.")
        return

    title = movie.get("Title", "Unknown")
    year = movie.get("Year", "")
    plot = movie.get("Plot", "بدون توضیح")
    poster = movie.get("Poster")

    caption = f"🎬 {title} ({year})\n\n{plot}"
    if poster and poster != "N/A":
        bot.send_photo(uid, poster, caption=caption)
    else:
        bot.send_message(uid, caption)

    download_url = get_download_link(title)
    if download_url:
        secure_link = create_temp_link(download_url, expire_seconds=600)
        bot.send_message(uid, f"🔗 لینک امن دانلود:\n{secure_link}")
    else:
        bot.send_message(uid, "❌ لینک دانلود پیدا نشد.")

# ----------------- اجرای همزمان -----------------
def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
