import os
import io
import re
import json
import subprocess
from datetime import datetime
import requests
import psutil
from flask import Flask, request, Response, jsonify, send_file
from flask_cors import CORS
from duckduckgo_search import DDGS

app = Flask(__name__)
CORS(app)

# ==========================================
# CONFIGURATION
# ==========================================
# Leave empty if you want to use Browser Web Speech API fallback
FISH_API_KEY = ""
FISH_VOICE_ID = ""

MEMORY_PATH = "jarvis_memory.jsonl"

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

# ==========================================
# MULTI-PROVIDER SEARCH & IMAGE FALLBACK
# ==========================================
def fetch_live_data_and_images(query):
    text_context = ""
    news_context = ""
    image_urls = []
    
    # 1. Primary: DuckDuckGo Live Search & Images
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                text_context = "\n".join([f"{r.get('title','')}: {r.get('body','')}" for r in results])
                
            news_results = list(ddgs.news(query, max_results=3))
            if news_results:
                news_context = "\n".join([f"Date: {r.get('date', '')} | News: {r.get('title','')}" for r in news_results])

            img_results = list(ddgs.images(query, max_results=6))
            if img_results:
                for img in img_results:
                    url = img.get('thumbnail') or img.get('image')
                    if url and url.startswith("http"):
                        image_urls.append(url)
    except Exception as e:
        print(f"[DuckDuckGo Notice]: {e}")

    # 2. Secondary Fallback: Wikipedia REST API for Visual Images
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
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_prompt = data.get("prompt", "").strip()
    
    if not user_prompt:
        return jsonify({"status": "error", "message": "Empty prompt."})

    lower_prompt = user_prompt.lower()
    save_memory_entry("user", user_prompt)

    # App Launcher
    if lower_prompt.startswith("open ") or lower_prompt.startswith("launch ") or lower_prompt.startswith("start "):
        app_name = re.sub(r"^(open|launch|start)\s+", "", lower_prompt).strip()
        target = re.sub(r"[^a-z0-9 ]", "", app_name).split()[0]
        try:
            os.system(f"start {target}")
            reply = f"Initializing {app_name.capitalize()}, sir."
        except Exception:
            reply = f"Unable to launch {app_name}, sir."
        save_memory_entry("jarvis", reply)
        return jsonify({"status": "success", "response": reply, "images": [], "category": "SYSTEM"})

    # Telemetry Check
    if "system status" in lower_prompt or "cpu" in lower_prompt or "memory" in lower_prompt:
        cpu = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory().percent
        reply = f"Core CPU usage is at {cpu} percent. Memory allocation is at {ram} percent."
        save_memory_entry("jarvis", reply)
        return jsonify({"status": "success", "response": reply, "images": [], "category": "TELEMETRY"})

    # Category Detection
    category = "GENERAL"
    query_title = user_prompt
    found_images = []
    web_context = ""

    loc_keywords = ["where is", "locate", "fly to", "location of", "show me on the map", "show me the city", "show me the country", "take me to", "map of"]
    for kw in loc_keywords:
        if kw in lower_prompt:
            category = "LOCATION"
            idx = lower_prompt.find(kw) + len(kw)
            query_title = re.sub(r"[^\w\s]", "", user_prompt[idx:]).strip()
            break

    if category == "GENERAL":
        is_conversational = any(p in lower_prompt for p in ["hello", "hi", "how are you", "who are you", "thanks"])
        if not is_conversational:
            category = "RESEARCH"

    if category == "RESEARCH":
        text_data, news_data, found_images = fetch_live_data_and_images(user_prompt)
        if text_data or news_data:
            web_context = f"\n[LIVE DATA]:\n{text_data}\n[RECENT NEWS]:\n{news_data}\n(Summarize concisely based on this live context)."

    recent_mem = load_memory(8)
    mem_str = " | ".join([f"{m['role']}: {m['text']}" for m in recent_mem])

    system_instruction = "You are J.A.R.V.I.S. Respond with extreme conciseness under 25 words. DO NOT use parentheses or brackets. Address user as sir. Incorporate memory context naturally. Current year is 2026."
    
    if category == "LOCATION":
        prompt_for_ollama = f"The user asked for the location of {query_title}. Confirm in 1 short sentence that you are initializing the 3D orbital satellite feed for {query_title}."
    else:
        prompt_for_ollama = f"{system_instruction}\n[Memory History: {mem_str}]\nUser: {user_prompt} {web_context}"

    try:
        ollama_response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "system": system_instruction,
                "prompt": prompt_for_ollama,
                "stream": False,
                "options": {"num_predict": 50}
            },
            timeout=12
        )
        bot_reply = ollama_response.json().get("response", "I am unable to process that at the moment, sir.")
        bot_reply = re.sub(r"\(.*?\)|\[.*?\]", "", bot_reply).strip()
        bot_reply = " ".join(bot_reply.split())

        save_memory_entry("jarvis", bot_reply)

        return jsonify({
            "status": "success",
            "response": bot_reply,
            "images": found_images,
            "query_title": query_title.upper(),
            "category": category,
            "has_news": bool(web_context)
        })
    except Exception as e:
        print(f"[Backend Error]: {e}")
        return jsonify({"status": "error", "response": "Mainframe offline, sir.", "images": [], "category": "ERROR"})

# ==========================================
# SAFE TTS ROUTE (Fixes 400 Errors)
# ==========================================
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "")
    
    if not text: 
        return jsonify({"error": "No text provided"}), 400
        
    # Check if keys are set before attempting external request
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

# Serve index.html directly from Flask
HUD_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")

@app.route("/")
def index():
    if os.path.exists(HUD_HTML_PATH):
        with open(HUD_HTML_PATH, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")
    return "index.html not found in directory.", 404

if __name__ == "__main__":
    print("--------------------------------------------------")
    print(" J.A.R.V.I.S. SERVER ONLINE | http://localhost:5001")
    print("--------------------------------------------------")
    app.run(host="0.0.0.0", port=5001, debug=False)
