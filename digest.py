import os
import requests
import feedparser
from datetime import datetime, date
from icalendar import Calendar

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CALENDAR_ICS_URL = os.getenv("CALENDAR_ICS_URL")

def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=45.4642&longitude=9.1900&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Europe%2FRome"
    )
    res = requests.get(url).json()
    daily = res.get("daily", {})
    return {
        "t_min": daily.get("temperature_2m_min", ["-"])[0],
        "t_max": daily.get("temperature_2m_max", ["-"])[0],
        "rain": daily.get("precipitation_probability_max", ["-"])[0]
    }

def get_calendar_events():
    if not CALENDAR_ICS_URL:
        return [("—", "Nessun calendario configurato")]
    try:
        res = requests.get(CALENDAR_ICS_URL)
        cal = Calendar.from_ical(res.text)
        today = date.today()
        events = []

        for component in cal.walk('vevent'):
            dtstart = component.get('dtstart').dt
            if isinstance(dtstart, datetime):
                dtstart_date = dtstart.date()
                time_str = dtstart.strftime("%H:%M")
            else:
                dtstart_date = dtstart
                time_str = "Tutto il giorno"

            if dtstart_date == today:
                summary = str(component.get('summary'))
                events.append((time_str, summary))

        events.sort(key=lambda x: x[0])
        return events if events else [("—", "Nessun impegno previsto")]
    except Exception as e:
        return [("!", f"Errore lettura calendario: {e}")]

def get_news_category(rss_url):
    feed = feedparser.parse(rss_url)
    items = []
    for entry in feed.entries[:3]:
        title = entry.title.split(" - ")[0]
        items.append((title, entry.link))
    return items

def get_all_news():
    feeds = {
        "📰 Cronaca": "https://news.google.com/rss/headlines/section/topic/NATION?hl=it&gl=IT&ceid=IT:it",
        "🏛️ Politica": "https://news.google.com/rss/search?q=politica&hl=it&gl=IT&ceid=IT:it",
        "⚽ Sport": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=it&gl=IT&ceid=IT:it",
        "💻 Tecnologia": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=it&gl=IT&ceid=IT:it"
    }
    return {category: get_news_category(url) for category, url in feeds.items()}

def create_telegraph_page(today_str, weather, events, news):
    acc = requests.post(
        "https://api.telegra.ph/createAccount",
        json={"short_name": "DailyBriefing", "author_name": "GitHub Bot"}
    ).json()
    token = acc["result"]["access_token"]

    content_nodes = [
        {"tag": "h4", "children": ["📍 Meteo Milano"]},
        {"tag": "p", "children": [f"🌡️ Min: {weather['t_min']}°C | Max: {weather['t_max']}°C\n🌧️ Probabilità pioggia: {weather['rain']}%"]},
        {"tag": "hr"},
        {"tag": "h4", "children": ["📅 Agenda di oggi"]},
        {
            "tag": "ul",
            "children": [
                {"tag": "li", "children": [f"{time} — {desc}"]}
                for time, desc in events
            ]
        },
        {"tag": "hr"}
    ]

    for category, articles in news.items():
        content_nodes.append({"tag": "h4", "children": [category]})
        content_nodes.append({
            "tag": "ul",
            "children": [
                {
                    "tag": "li",
                    "children": [
                        {
                            "tag": "a",
                            "attrs": {"href": url},
                            "children": [title]
                        }
                    ]
                }
                for title, url in articles
            ]
        })

    page = requests.post(
        "https://api.telegra.ph/createPage",
        json={
            "access_token": token,
            "title": f"Daily Briefing - {today_str}",
            "author_name": "Il tuo assistente",
            "content": content_nodes,
            "return_content": False
        }
    ).json()

    return page["result"]["url"]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

def main():
    today_str = datetime.now().strftime("%d/%m/%Y")
    weather = get_weather()
    events = get_calendar_events()
    news = get_all_news()

    page_url = create_telegraph_page(today_str, weather, events, news)

    summary_msg = (
        f"☀️ <b>Buongiorno! Ecco il tuo Daily Briefing del {today_str}</b>\n\n"
        f"📍 Milano: {weather['t_min']}°C / {weather['t_max']}°C (Pioggia: {weather['rain']}%)\n"
        f"📅 Appuntamenti: {len(events)} in programma\n\n"
        f"👉 <a href='{page_url}'>Apri la scheda completa</a>"
    )

    send_telegram(summary_msg)

if __name__ == "__main__":
    main()
