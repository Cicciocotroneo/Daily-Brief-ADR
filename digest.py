import os
import requests
import feedparser
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CALENDAR_ICS_URL = os.getenv("CALENDAR_ICS_URL")

# --- 1. METEO MILANO (DINAMICO SULLE ORE SUCCESSIVE) ---
def get_wmo_icon(code):
    if code == 0:
        return "☀️ Sereno"
    elif code in [1, 2]:
        return "🌤️ Poco nuvoloso"
    elif code == 3:
        return "☁️ Coperto"
    elif code in [45, 48]:
        return "🌫️ Nebbia"
    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "🌧️ Pioggia"
    elif code in [71, 73, 75, 77, 85, 86]:
        return "🌨️ Neve"
    elif code in [95, 96, 99]:
        return "⛈️ Temporale"
    return "⛅ Variabile"

def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=45.4642&longitude=9.1900"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&hourly=temperature_2m,weather_code,precipitation_probability"
        "&timezone=Europe%2FRome"
    )
    res = requests.get(url).json()
    daily = res.get("daily", {})
    hourly = res.get("hourly", {})

    t_min = daily.get("temperature_2m_min", ["-"])[0]
    t_max = daily.get("temperature_2m_max", ["-"])[0]
    rain_max = daily.get("precipitation_probability_max", ["-"])[0]

    now = datetime.now(ZoneInfo("Europe/Rome"))
    current_hour = now.hour

    # Fasce orarie monitorate nella giornata
    all_target_hours = ["08:00", "13:00", "16:00", "19:00", "22:00"]
    target_hours = [h for h in all_target_hours if int(h.split(":")[0]) > current_hour]

    check_date = now.date().isoformat()
    # Se tutte le ore di oggi sono passate (es. esecuzione a notte fonda), guarda la mattina successiva
    if not target_hours:
        target_hours = ["08:00", "13:00"]
        check_date = (now.date() + timedelta(days=1)).isoformat()

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weather_code", [])
    rain_probs = hourly.get("precipitation_probability", [])

    hourly_reports = []
    for target in target_hours:
        full_target_time = f"{check_date}T{target}"
        if full_target_time in times:
            idx = times.index(full_target_time)
            temp = temps[idx]
            code = codes[idx]
            rain = rain_probs[idx]
            icon_desc = get_wmo_icon(code)
            hourly_reports.append(f"• <b>{target}</b>: {icon_desc} {temp}°C (🌧️ {rain}%)")

    return {
        "t_min": t_min,
        "t_max": t_max,
        "rain_max": rain_max,
        "hourly_text": "\n".join(hourly_reports) if hourly_reports else "Nessuna previsione oraria residua."
    }

# --- 2. AGENDA DEL GIORNO ---
def get_calendar_events():
    if not CALENDAR_ICS_URL:
        return [("—", "Nessun calendario configurato")]
    try:
        res = requests.get(CALENDAR_ICS_URL)
        cal = Calendar.from_ical(res.text)
        today = datetime.now(ZoneInfo("Europe/Rome")).date()
        events = []

        for component in cal.walk('vevent'):
            dtstart = component.get('dtstart').dt
            if isinstance(dtstart, datetime):
                # Porta al fuso locale per calcolare correttamente data e ora
                dtstart_local = dtstart.astimezone(ZoneInfo("Europe/Rome"))
                dtstart_date = dtstart_local.date()
                time_str = dtstart_local.strftime("%H:%M")
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

# --- 3. NOTIZIE ---
def get_news_category(rss_url):
    feed = feedparser.parse(rss_url)
    items = []
    for entry in feed.entries[:3]:
        title = entry.title.split(" - ")[0]
        items.append((title, entry.link))
    return items

def get_all_news():
    feeds = {
        "📰 Cronaca Nazionale": "https://news.google.com/rss/headlines/section/topic/NATION?hl=it&gl=IT&ceid=IT:it",
        "🏛️ Politica": "https://news.google.com/rss/search?q=politica&hl=it&gl=IT&ceid=IT:it",
        "⚽ Sport": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=it&gl=IT&ceid=IT:it",
        "💻 Tecnologia": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=it&gl=IT&ceid=IT:it",
        "📍 Cronaca Salerno": "https://news.google.com/rss/search?q=Salerno+cronaca&hl=it&gl=IT&ceid=IT:it",
        "🇱🇻 Salernitana": "https://news.google.com/rss/search?q=Salernitana&hl=it&gl=IT&ceid=IT:it"
    }
    return {category: get_news_category(url) for category, url in feeds.items()}

# --- 4. GENERAZIONE SCHEDA SU TELEGRAPH ---
def create_telegraph_page(today_str, weather, events, news):
    acc = requests.post(
        "https://api.telegra.ph/createAccount",
        json={"short_name": "DailyBriefing", "author_name": "GitHub Bot"}
    ).json()
    token = acc["result"]["access_token"]

    weather_nodes = [
        {"tag": "p", "children": [f"🌡️ Min: {weather['t_min']}°C | Max: {weather['t_max']}°C (Prob. pioggia max: {weather['rain_max']}%)"]}
    ]
    if weather["hourly_text"]:
        lines = weather["hourly_text"].replace("<b>", "").replace("</b>", "").split("\n")
        weather_nodes.append({
            "tag": "ul",
            "children": [{"tag": "li", "children": [l.replace("• ", "")]} for l in lines]
        })

    content_nodes = [
        {"tag": "h4", "children": ["📍 Meteo Milano"]},
        *weather_nodes,
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

# --- 5. INVIO MESSAGGIO TELEGRAM ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

def main():
    now = datetime.now(ZoneInfo("Europe/Rome"))
    today_str = now.strftime("%d/%m/%Y")
    hour_str = now.strftime("%H:%M")

    weather = get_weather()
    events = get_calendar_events()
    news = get_all_news()

    page_url = create_telegraph_page(today_str, weather, events, news)

    summary_msg = (
        f"☀️ <b>Briefing delle {hour_str} ({today_str})</b>\n\n"
        f"📍 <b>Meteo Milano</b>\n"
        f"🌡️ Min: {weather['t_min']}°C | Max: {weather['t_max']}°C\n"
        f"{weather['hourly_text']}\n\n"
        f"📅 <b>Appuntamenti:</b> {len(events)} in programma\n\n"
        f"👉 <a href='{page_url}'>Apri la scheda completa</a>"
    )

    send_telegram(summary_msg)

if __name__ == "__main__":
    main()
