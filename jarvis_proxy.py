import os
import io
import re
import json
import base64
import warnings
import platform
from datetime import datetime
import requests
import psutil
from flask import Flask, request, Response, jsonify, send_file, send_from_directory
from flask_cors import CORS

# --- VISION CAPTURE ---
try:
    from PIL import ImageGrab
    SCREEN_CAPTURE_AVAILABLE = True
except ImportError:
    SCREEN_CAPTURE_AVAILABLE = False
    print("[WARNING] Pillow library not found. Screen reading disabled. Run 'pip install Pillow'")

# --- WEB SEARCH ---
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # legacy name fallback

# --- STOCK MARKET ---
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# ==========================================
# CONFIGURATION
# ==========================================
FISH_API_KEY = ""
FISH_VOICE_ID = ""

MEMORY_PATH = "jarvis_memory.jsonl"
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

DEFAULT_TEXT_MODEL = "llama3.2"
DEFAULT_VISION_MODEL = "llama3.2-vision" 

LOCATION_HINTS = [
    "where is", "where are", "take me to", "locate", "map of", "fly to",
    "show me on the map", "show me the city", "show me the country", "where am i", "near me", "around me"
]

# ==========================================
# SCREEN UNDERSTANDING MODULE
# ==========================================
def capture_screen_base64():
    if not SCREEN_CAPTURE_AVAILABLE: return None
    try:
        screenshot = ImageGrab.grab(all_screens=True)
        if screenshot.mode in ("RGBA", "P"): screenshot = screenshot.convert("RGB")
        screenshot.thumbnail((1920, 1080))
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=80)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        return None

def is_screen_prompt(prompt):
    screen_triggers = ["what am i looking at", "on my screen", "read my screen", "this cad model", "this drawing", "my screen", "look at this", "what is this on my screen", "explain this code"]
    return any(trigger in prompt.lower().strip() for trigger in screen_triggers)

# ==========================================
# APPLICATION CONTROL MODULE
# ==========================================
def extract_app_command(prompt):
    lower = prompt.lower().strip()
    if lower.startswith("open ") or lower.startswith("launch ") or lower.startswith("start "):
        parts = lower.split(" ", 1)
        if len(parts) > 1: return re.sub(r"[^\w\s]", "", parts[1].strip())
    return None

def launch_local_application(app_name):
    app_map = {"chrome": "chrome", "vs code": "code", "vscode": "code", "solidworks": "SLDWORKS", "matlab": "matlab", "discord": "discord", "file explorer": "explorer", "explorer": "explorer", "notepad": "notepad", "calculator": "calc", "terminal": "wt", "fusion 360": "fusion360", "autocad": "acad"}
    target = app_map.get(app_name.lower(), app_name)
    try:
        sys_name = platform.system()
        if sys_name == "Windows": os.system(f"start {target}")
        elif sys_name == "Darwin": os.system(f"open -a {target}")
        else: os.system(f"xdg-open {target} &")
        return True
    except Exception: return False

# ==========================================
# INTELLIGENT ROUTER
# ==========================================
def determine_intent(prompt):
    lower = prompt.lower().strip()
    word_count = len(lower.split())

    if extract_app_command(prompt): return "APP_CONTROL"
    if is_screen_prompt(prompt): return "SCREEN_READ"
    if any(hint in lower for hint in LOCATION_HINTS): return "LOCATION"
        
    market_triggers = ["stock", "price", "shares", "market", "invest", "ticker", "finance", "earnings"]
    if any(trigger in lower for trigger in market_triggers): return "MARKET_RESEARCH"

    short_chat_triggers = ["hi", "hello", "hey", "thanks", "thank you", "morning", "evening", "bye", "goodbye", "how are you", "whats up", "what's up", "good", "nice", "cool", "awesome"]
    if lower in short_chat_triggers or (word_count <= 4 and any(w in lower for w in short_chat_triggers)):
        return "SHORT_CHAT"

    engineering_triggers = ["cad", "model", "design", "build", "code", "script", "error", "idea", "brainstorm", "tolerance", "mechanics", "robot", "python", "solidworks", "help me"]
    if any(trigger in lower for trigger in engineering_triggers): return "ENGINEERING"

    research_triggers = ["what is", "who is", "tell me about", "latest", "news", "search", "explain how"]
    if any(trigger in lower for trigger in research_triggers): return "RESEARCH"

    return "CONVERSATION"

def extract_possible_ticker(prompt):
    words = re.findall(r'\b[A-Z]{1,5}\b', prompt)
    ignore = {"WHAT", "HOW", "WHY", "IS", "THE", "IN", "ON", "AT", "TO", "FOR", "JARVIS", "STOCK", "PRICE", "BUY", "SELL"}
    for w in words:
        if w not in ignore: return w
    return None

# ==========================================
# MEMORY ROUTES (FIXES THE 405 ERRORS)
# ==========================================
def load_memory(limit=10):
    if not os.path.exists(MEMORY_PATH): return []
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()][-limit:]
    except Exception: return []

def save_memory_entry(role, text):
    try:
        with open(MEMORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": role, "text": text, "timestamp": datetime.now().isoformat()}) + "\n")
    except Exception: pass

@app.route("/memory/save", methods=["POST"])
def memory_save_route():
    data = request.get_json() or {}
    save_memory_entry(data.get("role", "user"), data.get("text", ""))
    return jsonify({"status": "ok"})

@app.route("/memory/recent", methods=["GET"])
def memory_recent_route():
    limit = int(request.args.get("limit", "8"))
    return jsonify({"entries": load_memory(limit)})

# ==========================================
# LOCATION HELPERS
# ==========================================
def extract_location_query(prompt):
    lower = prompt.lower().strip()
    if any(token in lower for token in ["where am i", "my location", "near me"]): return ""
    patterns = ["where is ", "locate ", "find ", "take me to ", "map of ", "show me the city ", "where are ", "show me "]
    for pattern in patterns:
        if pattern in lower:
            start = lower.find(pattern) + len(pattern)
            candidate = re.sub(r"[^\w\s-]", "", prompt[start:]).strip()
            if candidate and candidate.lower() not in {"information about", "a picture", "the weather", "the news"}:
                return re.sub(r"\s+", " ", re.sub(r"\b(on the map|the map|the city|the country)\b", "", candidate, flags=re.IGNORECASE)).strip(" -")
    return re.sub(r"[^\w\s-]", "", re.sub(r"\b(on the map|the map)\b", "", prompt, flags=re.IGNORECASE)).strip()

def summarize_location(display_name, query, wiki_text, nearby, weather):
    if wiki_text: return wiki_text
    primary = (display_name or query or "this location").split(",")[0].strip()
    nearby_summary = f" Nearby reference points include {', '.join(nearby[:2])}." if nearby else ""
    weather_summary = f" Current weather is {weather['condition']} at {weather['temperature']} degrees Fahrenheit." if weather.get("condition") else ""
    return f"{primary} location lock acquired.{weather_summary}{nearby_summary}".strip()

def fetch_assistant_reply(system_instruction, prompt_for_ollama, fallback_reply, images=None, max_tokens=120):
    payload = {
        "model": DEFAULT_VISION_MODEL if images else DEFAULT_TEXT_MODEL,
        "system": system_instruction,
        "prompt": prompt_for_ollama,
        "stream": False,
        "options": {"num_predict": max_tokens}
    }
    if images: payload["images"] = images
    try:
        ollama_response = requests.post(os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL), json=payload, timeout=30)
        bot_reply = ollama_response.json().get("response", fallback_reply)
        return " ".join(re.sub(r"\(.*?\)|\[.*?\]", "", bot_reply).strip().split()) or fallback_reply
    except Exception: return fallback_reply

# ==========================================
# WEB & DATA FETCHING
# ==========================================
def fetch_live_data_and_images(query):
    text_context, news_context, image_urls = "", "", []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with DDGS() as ddgs:
                try:
                    results = list(ddgs.text(query, max_results=3))
                    if results: text_context = "\n".join([f"{r.get('title','')}: {r.get('body','')}" for r in results])
                except Exception: pass

                try:
                    news_results = list(ddgs.news(query, max_results=4))
                    if news_results: news_context = "\n".join([f"Date: {r.get('date', '')} | News: {r.get('title','')}" for r in news_results])
                except Exception: pass

                try:
                    img_results = list(ddgs.images(query, max_results=6))
                    if img_results: image_urls = [img.get('image') for img in img_results if img.get('image')]
                except Exception: pass
    except Exception: pass

    if not image_urls:
        try:
            wiki_res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}", timeout=4)
            if wiki_res.ok:
                wiki_data = wiki_res.json()
                if "thumbnail" in wiki_data and wiki_data["thumbnail"].get("source"): image_urls.append(wiki_data["thumbnail"]["source"])
                if not text_context and "extract" in wiki_data: text_context = wiki_data["extract"]
        except Exception: pass
        
    return text_context, news_context, [u for u in image_urls if u and u.startswith("http")]

@app.route("/api/image")
def proxy_image():
    url = request.args.get("url")
    if not url: return "No URL provided", 400
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=5)
        return send_file(io.BytesIO(r.content), mimetype=r.headers.get("content-type", "image/jpeg"))
    except Exception as e: return str(e), 500

@app.route("/api/location-info", methods=["POST"])
def location_info():
    data = request.get_json() or {}
    query, latitude, longitude = data.get("query", "").strip(), data.get("latitude"), data.get("longitude")
    if not query and (latitude is None or longitude is None): return jsonify({"status": "error", "message": "No location data provided."})

    try:
        if latitude is not None and longitude is not None: geocode_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&addressdetails=1&accept-language=en"
        else: geocode_url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(query)}&addressdetails=1&limit=1&accept-language=en"
        
        geocode_data = requests.get(geocode_url, timeout=6).json()
        place = geocode_data[0] if isinstance(geocode_data, list) and geocode_data else geocode_data if isinstance(geocode_data, dict) else None
        lat = float(place.get("lat", latitude)) if place and place.get("lat") else latitude
        lon = float(place.get("lon", longitude)) if place and place.get("lon") else longitude
        display_name = place.get("display_name", query) if place else query

        weather = {}
        if lat is not None and lon is not None:
            weather_res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&temperature_unit=fahrenheit", timeout=6)
            if weather_res.ok:
                weather_payload = weather_res.json().get("current", {})
                weather = {"temperature": weather_payload.get("temperature_2m"), "condition": "Clear" if weather_payload.get("weather_code") == 0 else "Cloudy/Rain"}

        _, _, image_urls = fetch_live_data_and_images(query or display_name)
        return jsonify({
            "status": "success", "title": display_name or query or "Location",
            "description": summarize_location(display_name, query, "", [], weather),
            "coords": {"lat": lat, "lon": lon}, "weather": weather, "images": image_urls[:6],
            "nearby": [], "links": [{"label": "Open in Maps", "url": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=14/{lat}/{lon}"}],
        })
    except Exception as exc: return jsonify({"status": "error", "message": str(exc)})

# ==========================================
# MAIN ASSISTANT LOGIC (THE BRAIN)
# ==========================================
@app.route("/api/assistant", methods=["POST"])
def assistant():
    data = request.get_json() or {}
    user_prompt = (data.get("prompt") or "").strip()
    page_context, location_context = data.get("page_context") or {}, data.get("location_context") or {}

    if not user_prompt: return jsonify({"status": "error", "message": "Empty prompt."}), 400

    category = determine_intent(user_prompt)
    research_bundle = {"summary": "", "news": "", "images": [], "links": [], "location": None, "page": None}
    encoded_screen = None

    if category == "APP_CONTROL":
        app_to_launch = extract_app_command(user_prompt)
        launch_local_application(app_to_launch)
        
    elif category == "SCREEN_READ":
        encoded_screen = capture_screen_base64()
            
    elif category == "LOCATION":
        location_query = extract_location_query(user_prompt)
        location_result = location_info_internal(query=location_query or user_prompt)
        research_bundle["location"] = location_result
        research_bundle["summary"] = (location_result or {}).get("description", "")
        research_bundle["images"] = (location_result or {}).get("images", [])
        
    elif category == "MARKET_RESEARCH":
        ticker_sym = extract_possible_ticker(user_prompt)
        text_data, news_data, image_urls = "", "", []
        if ticker_sym and YFINANCE_AVAILABLE:
            try:
                tkr = yf.Ticker(ticker_sym)
                info = tkr.info
                price = info.get("currentPrice", info.get("regularMarketPrice", "Unknown"))
                name = info.get("shortName", ticker_sym)
                summary = info.get("longBusinessSummary", "")[:600]
                text_data = f"Financial Data for {name} ({ticker_sym}): Current Price: ${price}. Summary: {summary}..."
                news_items = tkr.news
                if news_items: news_data = "\n".join([f"- {n.get('title')}" for n in news_items[:4]])
            except Exception: pass
                
        if not text_data:
            search_query = user_prompt.replace("Jarvis", "").strip() + " stock market financial news 2026"
            text_data, news_data, image_urls = fetch_live_data_and_images(search_query)
            
        research_bundle["summary"] = text_data or "Gathering financial telemetry..."
        research_bundle["news"] = news_data
        research_bundle["images"] = image_urls[:6]
        research_bundle["links"] = [{"label": "View Market Data", "url": f"https://finance.yahoo.com/quote/{ticker_sym}"}] if ticker_sym else []

    elif category == "RESEARCH":
        search_query = user_prompt.replace("Jarvis", "").strip() + " 2026 news updates"
        text_data, news_data, image_urls = fetch_live_data_and_images(search_query)
        research_bundle["summary"] = text_data or "I am pulling the requested data streams now, sir."
        research_bundle["news"] = news_data
        research_bundle["images"] = image_urls[:6]

    if ("webpage" in user_prompt.lower() or "page" in user_prompt.lower()) and page_context:
        research_bundle["page"] = {"title": page_context.get("title", "Current webpage"), "excerpt": page_context.get("selection") or page_context.get("body_text", "")[:1500]}

    # 3. BUILD PERSONA & 2026 TIME AWARENESS
    recent_mem = load_memory(8)
    mem_str = " | ".join([f"{m['role']}: {m['text']}" for m in recent_mem])
    
    context_parts = []
    if research_bundle.get("summary") and category not in ["SHORT_CHAT", "CONVERSATION", "ENGINEERING"]:
        context_parts.append(research_bundle["summary"])

    # This dynamically injects today's date, but forces the year to 2026!
    current_date = datetime.now().strftime(f"%A, %B %d, 2026")
    base_persona = f"You are JARVIS. The current date is {current_date}. "

    if category == "SHORT_CHAT":
        max_tokens = 40
        prompt_for_ollama = f"{base_persona}The user is engaging in casual chat. Respond naturally, politely, and strictly in 1 very short sentence.\nMemory: {mem_str}\nUser request: {user_prompt}"
        fallback_reply = "Hello, sir."
        
    elif category == "ENGINEERING":
        max_tokens = 150
        prompt_for_ollama = f"{base_persona}You are an expert engineering AI. Collaborate thoughtfully but concisely. Give a fast, practical response under 3 sentences.\nMemory: {mem_str}\nUser request: {user_prompt}"
        fallback_reply = "I am ready to assist with the engineering analysis, sir."

    elif category in ["RESEARCH", "MARKET_RESEARCH"]:
        max_tokens = 100
        prompt_for_ollama = f"{base_persona}Detailed research data is on the holographic display. DO NOT read the text out loud. Provide a fast, conversational 1-to-2 sentence verbal summary.\nMemory: {mem_str}\nUser request: {user_prompt}\nContext: {' '.join(context_parts)}"
        fallback_reply = "Research complete, sir. Presenting the intelligence on your display."
        
    elif category == "SCREEN_READ":
        max_tokens = 150
        prompt_for_ollama = f"{base_persona}Look at the image of the user's screen. Give a concise, 2-sentence explanation of what you see, focusing on engineering or code.\nMemory: {mem_str}\nUser request: {user_prompt}"
        fallback_reply = "Processing visual telemetry now, sir."

    elif category == "APP_CONTROL":
        max_tokens = 30
        prompt_for_ollama = f"{base_persona}Confirm that you are opening the requested application in exactly one sentence.\nUser request: {user_prompt}"
        fallback_reply = "Right away, sir."
        
    else: # CONVERSATION
        max_tokens = 60
        prompt_for_ollama = f"{base_persona}Speak naturally and concisely. Address the user as sir. Keep replies strictly under 2 sentences.\nMemory: {mem_str}\nUser request: {user_prompt}"
        fallback_reply = "I am here, sir."

    images_list = [encoded_screen] if encoded_screen else None
    reply = fetch_assistant_reply("", prompt_for_ollama, fallback_reply, images=images_list, max_tokens=max_tokens)
    
    if category in ["SHORT_CHAT", "CONVERSATION", "ENGINEERING", "APP_CONTROL"]:
        research_bundle = {}

    return jsonify({"status": "success", "category": category, "response": reply, "research": research_bundle})

def location_info_internal(query="", latitude=None, longitude=None):
    with app.test_request_context(json={"query": query, "latitude": latitude, "longitude": longitude}):
        response = location_info()
        payload = response.get_json() if hasattr(response, "get_json") else None
        return payload if payload and payload.get("status") == "success" else None

@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "")
    if not text: return jsonify({"error": "No text provided"}), 400
    if not FISH_API_KEY or not FISH_VOICE_ID: return jsonify({"error": "No API key"}), 400
    try:
        res = requests.post("https://api.fish.audio/v1/tts", headers={"Authorization": f"Bearer {FISH_API_KEY}", "Content-Type": "application/json"},
            json={"text": text, "reference_id": FISH_VOICE_ID, "model": "s2.1-pro-free", "format": "mp3"}, timeout=10)
        res.raise_for_status()
        return Response(res.content, mimetype="audio/mpeg")
    except Exception as e: return jsonify({"error": str(e)}), 502

@app.route("/health")
def health(): return jsonify({"status": "ok"})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HUD_HTML_PATH = os.path.join(BASE_DIR, "hud.html")

@app.route("/")
def index():
    if os.path.exists(HUD_HTML_PATH):
        with open(HUD_HTML_PATH, "r", encoding="utf-8") as f: return Response(f.read(), mimetype="text/html")
    return "hud.html not found.", 404

@app.route("/<path:filename>")
def static_assets(filename):
    safe = os.path.normpath(filename).lstrip("/\\")
    if ".." in safe: return "Forbidden", 403
    return send_from_directory(BASE_DIR, safe)

if __name__ == "__main__":
    print("--------------------------------------------------")
    print(" JARVIS SERVER ONLINE | http://localhost:8000")
    if SCREEN_CAPTURE_AVAILABLE: print(" [SYSTEM] Screen Capture Vision Module: ONLINE")
    print("--------------------------------------------------")
    app.run(host="0.0.0.0", port=8000, debug=False)
