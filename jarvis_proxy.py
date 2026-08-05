import os
import io
import re
import json
import base64
import warnings
from datetime import datetime
import requests
import psutil
from flask import Flask, request, Response, jsonify, send_file, send_from_directory
from flask_cors import CORS

try:
    from PIL import ImageGrab
    SCREEN_CAPTURE_AVAILABLE = True
except ImportError:
    SCREEN_CAPTURE_AVAILABLE = False
    print("[WARNING] Pillow library not found. Screen reading will be disabled. Run 'pip install Pillow'")

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # legacy name fallback

app = Flask(__name__)
CORS(app)

# ==========================================
# CONFIGURATION
# ==========================================
FISH_API_KEY = ""
FISH_VOICE_ID = ""

MEMORY_PATH = "jarvis_memory.jsonl"
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11435/api/generate")
# We use standard 3.2 for text, and 3.2-vision when analyzing the screen
DEFAULT_TEXT_MODEL = "llama3.2"
DEFAULT_VISION_MODEL = "llama3.2-vision" 

LOCATION_HINTS = [
    "where is", "where are", "take me to", "locate", "map of", "fly to",
    "show me on the map", "show me the city", "show me the country", "where am i", "near me", "around me",
]

# ==========================================
# SCREEN UNDERSTANDING MODULE
# ==========================================
def capture_screen_base64():
    """Captures the current desktop screen and encodes it for the Vision LLM."""
    if not SCREEN_CAPTURE_AVAILABLE:
        return None
    try:
        # Grab all screens
        screenshot = ImageGrab.grab(all_screens=True)
        # Convert to RGB if necessary (removes alpha channel)
        if screenshot.mode in ("RGBA", "P"):
            screenshot = screenshot.convert("RGB")
        # Downscale slightly to prevent massive payload sizes slowing down the LLM
        screenshot.thumbnail((1920, 1080))
        
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=80)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_str
    except Exception as e:
        print(f"[Screen Capture Error]: {e}")
        return None

def is_screen_prompt(prompt):
    lower = prompt.lower().strip()
    screen_triggers = [
        "what am i looking at", "on my screen", "read my screen", 
        "this cad model", "this drawing", "my screen", "look at this",
        "what is this on my screen", "explain this code"
    ]
    return any(trigger in lower for trigger in screen_triggers)

# ==========================================
# APPLICATION CONTROL MODULE
# ==========================================
def extract_app_command(prompt):
    lower = prompt.lower().strip()
    if lower.startswith("open ") or lower.startswith("launch ") or lower.startswith("start "):
        app_name = lower.split(" ", 1)[1].strip()
        app_name = re.sub(r"[^\w\s]", "", app_name)
        return app_name
    return None

def launch_local_application(app_name):
    """Attempts to launch common engineering and standard applications on Windows."""
    app_map = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "vs code": "code",
        "vscode": "code",
        "solidworks": "SLDWORKS",
        "matlab": "matlab",
        "discord": "discord",
        "file explorer": "explorer",
        "explorer": "explorer",
        "notepad": "notepad",
        "calculator": "calc",
        "command prompt": "cmd",
        "terminal": "wt",
        "fusion 360": "fusion360",
        "autocad": "acad"
    }
    
    target = app_map.get(app_name, app_name)
    try:
        # 'start' command works natively on Windows for apps in the system PATH
        os.system(f"start {target}")
        return True
    except Exception as e:
        print(f"[App Launch Error]: {e}")
        return False

# ==========================================
# CONVERSATIONAL DETECTOR
# ==========================================
def is_conversational_prompt(prompt):
    lower = prompt.lower().strip()
    
    research_triggers = ["what is", "who is", "tell me about", "latest", "news about", "search", "explain how"]
    if any(trigger in lower for trigger in research_triggers):
        return False
        
    chat_triggers = [
        "hey jarvis", "hi jarvis", "hello", "morning", "evening", 
        "trouble", "help me", "cad", "model", "design", "build", 
        "code", "script", "error", "idea", "brainstorm", "partner",
        "how are you", "thanks", "thank you"
    ]
    
    if any(trigger in lower for trigger in chat_triggers) or len(lower.split()) <= 4:
        return True
    return False

# ==========================================
# PERSISTENT MEMORY ENGINE
# ==========================================
def load_memory(limit=10):
    if not os.path.exists(MEMORY_PATH):
        return []
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        return lines[-limit:]
    except Exception:
        return []

def save_memory_entry(role, text):
    entry = {"role": role, "text": text, "timestamp": datetime.now().isoformat()}
    try:
        with open(MEMORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[Memory Error]: {e}")


def extract_location_query(prompt):
    lower = prompt.lower().strip()
    if any(token in lower for token in ["where am i", "my location", "around me", "near me", "what is nearby"]):
        return ""

    patterns = [
        "where is ", "locate ", "find ", "show me the location of ", "take me to ", "map of ",
        "show me on the map ", "show me the city ", "show me the country ", "where are ",
        "show me ",
    ]
    for pattern in patterns:
        if pattern in lower:
            start = lower.find(pattern) + len(pattern)
            candidate = re.sub(r"[^\w\s-]", "", prompt[start:]).strip()
            if candidate and candidate.lower() not in {"information about", "a picture", "the weather", "the news"}:
                candidate = re.sub(r"\b(on the map|the map|the city|the country)\b", "", candidate, flags=re.IGNORECASE)
                candidate = re.sub(r"\s+", " ", candidate).strip(" -")
                return candidate

    cleaned = re.sub(r"\b(on the map|the map|the city|the country)\b", "", prompt, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\s-]", "", cleaned).strip()
    return cleaned.strip()


def is_location_prompt(prompt):
    lower = prompt.lower().strip()
    return any(hint in lower for hint in LOCATION_HINTS)


def should_probe_show_me_location(prompt):
    lower = prompt.lower().strip()
    if not lower.startswith("show me "):
        return False
    return not any(re.search(rf"\b{token}\b", lower) for token in [
        "image", "images", "picture", "pictures", "photo", "photos", "article", "articles",
        "website", "webpage", "page", "about", "news", "video", "videos", "how", "why",
    ])


def summarize_location(display_name, query, wiki_text, nearby, weather):
    if wiki_text:
        return wiki_text

    primary = (display_name or query or "this location").split(",")[0].strip()
    nearby_summary = ""
    if nearby:
        nearby_summary = f" Nearby reference points include {', '.join(nearby[:2])}."

    weather_summary = ""
    if weather.get("condition") and weather.get("temperature") is not None:
        weather_summary = f" Current weather is {weather['condition']} at {weather['temperature']} degrees Fahrenheit."

    return f"{primary} location lock acquired.{weather_summary}{nearby_summary}".strip()


def fetch_assistant_reply(system_instruction, prompt_for_ollama, fallback_reply, images=None):
    # Switch to the vision model if an image is provided
    model_to_use = DEFAULT_VISION_MODEL if images else DEFAULT_TEXT_MODEL
    
    payload = {
        "model": model_to_use,
        "system": system_instruction,
        "prompt": prompt_for_ollama,
        "stream": False,
        "options": {"num_predict": 120}
    }
    
    if images:
        payload["images"] = images

    try:
        ollama_response = requests.post(
            os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            json=payload,
            timeout=25 # Increased timeout for vision processing
        )
        bot_reply = ollama_response.json().get("response", fallback_reply)
        bot_reply = re.sub(r"\(.*?\)|\[.*?\]", "", bot_reply).strip()
        return " ".join(bot_reply.split()) or fallback_reply
    except Exception as exc:
        print(f"[Backend Error - Ollama]: {exc}")
        return fallback_reply


def compact_warning_message(exc):
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    if "403" in message or "Ratelimit" in message or "rate" in message.lower():
        return "rate limited"
    return message

# ==========================================
# MULTI-PROVIDER SEARCH & IMAGE FALLBACK
# ==========================================
def fetch_live_data_and_images(query):
    text_context = ""
    news_context = ""
    image_urls = []

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with DDGS() as ddgs:
                try:
                    results = list(ddgs.text(query, max_results=3))
                    if results:
                        text_context = "\n".join([f"{r.get('title','')}: {r.get('body','')}" for r in results])
                except Exception as exc:
                    print(f"[DDGS Text Notice]: {compact_warning_message(exc)}")

                try:
                    news_results = list(ddgs.news(query, max_results=3))
                    if news_results:
                        news_context = "\n".join([f"Date: {r.get('date', '')} | News: {r.get('title','')}" for r in news_results])
                except Exception as exc:
                    print(f"[DDGS News Notice]: {compact_warning_message(exc)}")

                try:
                    img_results = list(ddgs.images(query, max_results=6))
                    if img_results:
                        for img in img_results:
                            url = img.get('thumbnail') or img.get('image')
                            if url and url.startswith("http"):
                                image_urls.append(url)
                except Exception as exc:
                    print(f"[DDGS Images Notice]: {compact_warning_message(exc)}")
    except Exception as exc:
        print(f"[DDGS Notice]: {compact_warning_message(exc)}")

    if not image_urls:
        try:
            wiki_res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}", timeout=4)
            if wiki_res.ok:
                wiki_data = wiki_res.json()
                if "thumbnail" in wiki_data and wiki_data["thumbnail"].get("source"):
                    image_urls.append(wiki_data["thumbnail"]["source"])
                if not text_context and "extract" in wiki_data:
                    text_context = wiki_data["extract"]
        except Exception as e:
            print(f"[Wikipedia Fallback Notice]: {e}")
        
    return text_context, news_context, image_urls

@app.route("/api/image")
def proxy_image():
    """Proxies image requests to prevent CORS/hotlink blocks."""
    url = request.args.get("url")
    if not url: return "No URL provided", 400
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, stream=True, timeout=5)
        return send_file(io.BytesIO(r.content), mimetype=r.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        return str(e), 500

# ==========================================
# QUERY & INTENT PARSER
# ==========================================
@app.route("/api/location-info", methods=["POST"])
def location_info():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not query and (latitude is None or longitude is None):
        return jsonify({"status": "error", "message": "No location query or coordinates provided."})

    try:
        if latitude is not None and longitude is not None:
            geocode_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&addressdetails=1&accept-language=en"
        else:
            geocode_url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(query)}&addressdetails=1&limit=1&accept-language=en"
        geocode_res = requests.get(geocode_url, timeout=6)
        geocode_res.raise_for_status()
        geocode_data = geocode_res.json()

        if isinstance(geocode_data, list):
            place = geocode_data[0] if geocode_data else None
            lat = float(place["lat"]) if place else None
            lon = float(place["lon"]) if place else None
            display_name = place.get("display_name", query) if place else query
        else:
            place = geocode_data
            lat = float(place.get("lat", latitude)) if place.get("lat") is not None else latitude
            lon = float(place.get("lon", longitude)) if place.get("lon") is not None else longitude
            display_name = place.get("display_name", query)

        weather = {}
        if lat is not None and lon is not None:
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&temperature_unit=fahrenheit"
            weather_res = requests.get(weather_url, timeout=6)
            if weather_res.ok:
                weather_payload = weather_res.json().get("current", {})
                weather = {
                    "temperature": weather_payload.get("temperature_2m"),
                    "condition": weather_code_to_text(weather_payload.get("weather_code")),
                }

        wiki_text = ""
        image_urls = []
        try:
            wiki_search = requests.get(
                "https://en.wikipedia.org/w/api.php?action=opensearch&search=" + requests.utils.quote(query or display_name) + "&limit=1&namespace=0&format=json&origin=*",
                timeout=6,
            )
            if wiki_search.ok:
                wiki_data = wiki_search.json()
                title = wiki_data[1][0] if len(wiki_data) > 1 and wiki_data[1] else None
                if title:
                    summary_res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}", timeout=6)
                    if summary_res.ok:
                        summary_data = summary_res.json()
                        wiki_text = summary_data.get("extract", "")
                    media_res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/media-list/{requests.utils.quote(title)}", timeout=6)
                    if media_res.ok:
                        media_data = media_res.json()
                        image_urls = [
                            ("https:" + item["srcset"][-1]["src"]) if item.get("srcset") else ""
                            for item in (media_data.get("items") or [])
                            if item.get("type") == "image" and item.get("srcset")
                        ]
                        image_urls = [u for u in image_urls if u]
        except Exception:
            pass

        nearby = []
        if lat is not None and lon is not None:
            nearby_url = f"https://nominatim.openstreetmap.org/search?format=json&lat={lat}&lon={lon}&zoom=14&limit=5&addressdetails=1&accept-language=en"
            nearby_res = requests.get(nearby_url, timeout=6)
            if nearby_res.ok:
                for item in nearby_res.json()[:5]:
                    nearby.append(item.get("display_name", "Nearby location"))

        links = [
            {"label": "Open in Maps", "url": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=14/{lat}/{lon}"} if lat is not None and lon is not None else None,
            {"label": "Search Web", "url": f"https://www.google.com/search?q={requests.utils.quote(query or display_name)}"} if (query or display_name) else None,
        ]
        links = [link for link in links if link]

        description = summarize_location(display_name, query, wiki_text, nearby, weather)

        return jsonify({
            "status": "success",
            "title": display_name or query or "Location",
            "description": description,
            "coords": {"lat": lat, "lon": lon},
            "weather": weather,
            "images": image_urls[:6],
            "nearby": nearby,
            "links": links,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)})


def weather_code_to_text(code):
    if code is None:
        return "Clear"
    if code == 0:
        return "Clear sky"
    if code <= 3:
        return "Partly cloudy"
    if code <= 48:
        return "Fog"
    if code <= 67:
        return "Rain"
    if code <= 77:
        return "Snow"
    if code <= 82:
        return "Showers"
    return "Thunderstorm"


@app.route("/memory/save", methods=["POST"])
def memory_save():
    data = request.get_json() or {}
    role = data.get("role", "user")
    text = (data.get("text") or "").strip()
    if text:
        save_memory_entry(role, text)
    return jsonify({"status": "ok"})


@app.route("/memory/recent")
def memory_recent():
    limit = int(request.args.get("limit", "8"))
    entries = load_memory(limit)
    return jsonify({"entries": entries})


@app.route("/api/research", methods=["POST"])
def research():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"status": "error", "message": "No query provided."})

    text_data, news_data, image_urls = fetch_live_data_and_images(query)
    summary = text_data or "I am gathering live intelligence for that topic."
    return jsonify({
        "status": "success",
        "query": query,
        "summary": summary,
        "news": news_data,
        "images": image_urls[:6],
        "links": [
            {"label": "Open web search", "url": f"https://www.google.com/search?q={requests.utils.quote(query)}"}
        ],
    })


@app.route("/api/page-context", methods=["POST"])
def page_context():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    url = (data.get("url") or "").strip()
    selection = (data.get("selection") or "").strip()
    body_text = (data.get("body_text") or "").strip()

    if not any([title, url, selection, body_text]):
        return jsonify({"status": "error", "message": "No page context provided."}), 400

    source_text = selection or body_text[:5000]
    research_query = title or url or "current webpage"
    live_data, news_data, image_urls = fetch_live_data_and_images(research_query)
    summary = live_data or f"The active webpage is titled {title or 'Untitled page'}."

    return jsonify({
        "status": "success",
        "title": title or "Current webpage",
        "url": url,
        "summary": summary,
        "images": image_urls[:6],
        "news": news_data,
        "content_excerpt": source_text[:2000],
    })

# ==========================================
# MAIN ASSISTANT LOGIC (THE BRAIN)
# ==========================================
@app.route("/api/assistant", methods=["POST"])
def assistant():
    data = request.get_json() or {}
    user_prompt = (data.get("prompt") or "").strip()
    page_context = data.get("page_context") or {}
    location_context = data.get("location_context") or {}

    if not user_prompt:
        return jsonify({"status": "error", "message": "Empty prompt."}), 400

    lower_prompt = user_prompt.lower()
    save_memory_entry("user", user_prompt)
    is_page_request = "webpage" in lower_prompt or "page" in lower_prompt or bool(page_context)

    # ---- INTENT ROUTER ----
    category = "RESEARCH"
    app_to_launch = extract_app_command(user_prompt)
    
    if app_to_launch:
        category = "APP_CONTROL"
    elif is_screen_prompt(user_prompt):
        category = "SCREEN_READ"
    elif is_location_prompt(user_prompt):
        category = "LOCATION"
    elif should_probe_show_me_location(user_prompt):
        probe_query = extract_location_query(user_prompt)
        probe_result = location_info_internal(query=probe_query) if probe_query else None
        if probe_result and probe_result.get("coords", {}).get("lat") is not None and probe_result.get("coords", {}).get("lon") is not None:
            category = "LOCATION"
    elif is_conversational_prompt(user_prompt):
        category = "CONVERSATION"

    research_bundle = {
        "summary": "",
        "news": "",
        "images": [],
        "links": [],
        "location": None,
        "page": None,
    }
    
    encoded_screen = None

    # ---- EXECUTE INTENT ACTIONS ----
    if category == "APP_CONTROL":
        success = launch_local_application(app_to_launch)
        research_bundle["summary"] = f"Action: Executing launch protocols for {app_to_launch}."
        
    elif category == "SCREEN_READ":
        encoded_screen = capture_screen_base64()
        if not encoded_screen:
            research_bundle["summary"] = "Screen capture failed or Pillow library is missing."
        else:
            research_bundle["summary"] = "Processing visual telemetry from primary displays."
            
    elif category == "LOCATION":
        location_query = extract_location_query(user_prompt)
        if location_context.get("latitude") is not None and location_context.get("longitude") is not None and not location_query:
            location_result = location_info_internal(latitude=location_context.get("latitude"), longitude=location_context.get("longitude"), query="Current location")
        else:
            location_result = location_info_internal(query=location_query or user_prompt)
        research_bundle["location"] = location_result
        research_bundle["summary"] = (location_result or {}).get("description", "")
        research_bundle["images"] = (location_result or {}).get("images", [])
        research_bundle["links"] = (location_result or {}).get("links", [])
        
    elif category == "RESEARCH":
        research_query = user_prompt.replace("Jarvis", "").replace("JARVIS", "").strip()
        text_data, news_data, image_urls = fetch_live_data_and_images(research_query)
        research_bundle["summary"] = text_data or "I am pulling the requested data streams now, sir."
        research_bundle["news"] = news_data
        research_bundle["images"] = image_urls[:6]
        research_bundle["links"] = [
            {"label": "Open web search", "url": f"https://www.google.com/search?q={requests.utils.quote(research_query)}"}
        ]
        
    elif category == "CONVERSATION":
        research_bundle["summary"] = "Internal processing complete."

    if is_page_request and page_context:
        page_summary = page_context.get("selection") or page_context.get("body_text", "")[:1500]
        research_bundle["page"] = {
            "title": page_context.get("title") or "Current webpage",
            "url": page_context.get("url") or "",
            "excerpt": page_summary,
        }

    # ---- BUILD PERSONA AND PROMPT ----
    recent_mem = load_memory(8)
    mem_str = " | ".join([f"{m['role']}: {m['text']}" for m in recent_mem])
    
    system_instruction = (
        "You are JARVIS, an intelligent engineering companion and technical partner inspired by Iron Man's AI. "
        "Speak naturally, concisely, and with grounded expertise. Address the user as sir. "
        "Think collaboratively with the user on engineering problems, mechanical design, circuitry, and physics. "
        "Keep replies highly direct and under 40 words unless explaining a specific technical concept."
    )

    context_parts = []
    if research_bundle.get("summary") and category not in ["CONVERSATION", "SCREEN_READ"]:
        context_parts.append(research_bundle["summary"])
    if research_bundle.get("news"):
        context_parts.append("Recent developments: " + research_bundle["news"])
    if research_bundle.get("page"):
        context_parts.append("Current page excerpt: " + research_bundle["page"]["excerpt"])

    if category == "LOCATION":
        target = ((research_bundle.get("location") or {}).get("title") or extract_location_query(user_prompt) or "target location")
        prompt_for_ollama = f"{system_instruction}\nMemory: {mem_str}\nUser request: {user_prompt}\nContext: {' '.join(context_parts)}\nRespond as if you have researched the location and are presenting it while opening a holographic globe focused on {target}."
        fallback_reply = f"Location acquired, sir. Bringing the globe online for {target}."
        
    elif category == "APP_CONTROL":
        prompt_for_ollama = f"{system_instruction}\nMemory: {mem_str}\nUser request: {user_prompt}\nRespond by concisely confirming you are launching the requested application."
        fallback_reply = f"Right away, sir. Launching {app_to_launch}."
        
    elif category == "SCREEN_READ":
        prompt_for_ollama = f"{system_instruction}\nMemory: {mem_str}\nUser request: {user_prompt}\nLook at the provided image of the user's screen. Explain what is visible, focusing on engineering, CAD, code, or context."
        fallback_reply = "Processing visual telemetry now, sir."
        
    elif category == "RESEARCH":
        prompt_for_ollama = f"{system_instruction}\nMemory: {mem_str}\nUser request: {user_prompt}\nContext: {' '.join(context_parts)}\nYou are a teacher and engineering partner. Explain this context in your own words conversationally. Do not just read the text."
        fallback_reply = "Research complete, sir. Presenting the relevant intelligence now."
        
    else:
        prompt_for_ollama = f"{system_instruction}\nMemory: {mem_str}\nUser request: {user_prompt}\nRespond directly, conversationally, and concisely."
        fallback_reply = "I am here and ready to assist, sir."

    # ---- FETCH REPLY ----
    images_list = [encoded_screen] if encoded_screen else None
    reply = fetch_assistant_reply(system_instruction, prompt_for_ollama, fallback_reply, images=images_list)
    save_memory_entry("jarvis", reply)

    return jsonify({
        "status": "success",
        "category": category,
        "response": reply,
        "research": research_bundle if category not in ["CONVERSATION", "APP_CONTROL"] else {},
    })


def location_info_internal(query="", latitude=None, longitude=None):
    data = {"query": query, "latitude": latitude, "longitude": longitude}
    with app.test_request_context(json=data):
        response = location_info()
        payload = response.get_json() if hasattr(response, "get_json") else None
        return payload if payload and payload.get("status") == "success" else None


def assistant_internal(payload):
    with app.test_request_context(json=payload):
        response = assistant()
        return response.get_json() if hasattr(response, "get_json") else response


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    payload = {
        "prompt": (data.get("prompt") or "").strip(),
        "page_context": data.get("page_context") or {},
        "location_context": data.get("location_context") or {},
    }
    result = assistant_internal(payload)
    if result.get("status") != "success":
        return jsonify(result), 400

    research = result.get("research") or {}
    return jsonify({
        "status": "success",
        "response": result.get("response", ""),
        "images": research.get("images", []),
        "query_title": ((research.get("location") or {}).get("title") or payload["prompt"]).upper(),
        "category": result.get("category", "RESEARCH"),
        "has_news": bool(research.get("news")),
        "research": research,
    })

# ==========================================
# SAFE TTS ROUTE
# ==========================================
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "")
    
    if not text: 
        return jsonify({"error": "No text provided"}), 400
        
    if not FISH_API_KEY or not FISH_VOICE_ID:
        return jsonify({"error": "Fish Audio keys unconfigured. Use browser TTS fallback."}), 400

    try:
        response = requests.post(
            "https://api.fish.audio/v1/tts",
            headers={"Authorization": f"Bearer {FISH_API_KEY}", "Content-Type": "application/json"},
            json={"text": text, "reference_id": FISH_VOICE_ID, "model": "s2.1-pro-free", "format": "mp3", "prosody": {"speed": 1.05, "volume": 0}},
            timeout=10
        )
        response.raise_for_status()
        return Response(response.content, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HUD_HTML_PATH = os.path.join(BASE_DIR, "hud.html")

_STATIC_EXTS = {".js", ".css", ".mp3", ".wav", ".ico", ".png", ".jpg", ".gif", ".svg", ".woff", ".woff2"}

@app.route("/")
def index():
    if os.path.exists(HUD_HTML_PATH):
        with open(HUD_HTML_PATH, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")
    return "hud.html not found in directory.", 404

@app.route("/<path:filename>")
def static_assets(filename):
    safe = os.path.normpath(filename).lstrip("/\\")
    if ".." in safe:
        return "Forbidden", 403
    if os.path.splitext(safe)[1].lower() not in _STATIC_EXTS:
        return "Not found", 404
    return send_from_directory(BASE_DIR, safe)

if __name__ == "__main__":
    print("--------------------------------------------------")
    print(" JARVIS SERVER ONLINE | http://localhost:8000")
    if SCREEN_CAPTURE_AVAILABLE:
        print(" [SYSTEM] Screen Capture Vision Module: ONLINE")
    print("--------------------------------------------------")
    app.run(host="0.0.0.0", port=8000, debug=False)
