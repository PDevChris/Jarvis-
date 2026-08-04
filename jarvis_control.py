import os
import io
import re
import subprocess
import requests
import psutil
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from duckduckgo_search import DDGS

app = Flask(__name__)
CORS(app)

conversation_history = []

def search_web_and_images(query):
    text_data = ""
    image_urls = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                text_data = "\n".join([f"{r.get('title','')}: {r.get('body','')}" for r in results])
            
            img_results = list(ddgs.images(query, max_results=6))
            if img_results:
                for img in img_results:
                    url = img.get('thumbnail') or img.get('image')
                    if url and url.startswith("http"):
                        image_urls.append(url)
    except Exception as e:
        pass
    return text_data, image_urls

@app.route('/api/image')
def proxy_image():
    url = request.args.get('url')
    if not url: return "No URL provided", 400
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, stream=True, timeout=5)
        return send_file(io.BytesIO(r.content), mimetype=r.headers.get('content-type', 'image/jpeg'))
    except Exception as e:
        return str(e), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    global conversation_history
    data = request.get_json()
    user_prompt = data.get("prompt", "").strip()
    
    if not user_prompt:
        return jsonify({"status": "error", "message": "Empty prompt."})

    lower_prompt = user_prompt.lower()

    # Universal App Launcher
    if lower_prompt.startswith("open ") or lower_prompt.startswith("launch ") or lower_prompt.startswith("start "):
        app_name = re.sub(r'^(open|launch|start)\s+', '', lower_prompt).strip()
        app_name_clean = re.sub(r'[^a-z0-9 ]', '', app_name)
        target = app_name_clean.split()[0]
        os.system(f'start {target}')
        return jsonify({"status": "success", "response": f"Launching {app_name}, sir.", "images": [], "category": "SYSTEM"})

    # Telemetry
    if "system status" in lower_prompt or "cpu" in lower_prompt or "memory" in lower_prompt:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        return jsonify({"status": "success", "response": f"CPU usage is {cpu} percent. Memory is {ram} percent.", "images": [], "category": "TELEMETRY"})

    # Smart Location Parser
    web_context = ""
    found_images = []
    category = "GENERAL"
    query_title = user_prompt

    loc_keywords = ["live view of", "map of", "where is", "fly to", "location of", "show me the country", "show me the city"]
    
    for kw in loc_keywords:
        if kw in lower_prompt:
            category = "LOCATION"
            idx = lower_prompt.find(kw) + len(kw)
            extracted_loc = user_prompt[idx:].strip()
            query_title = re.sub(r'[^\w\s]', '', extracted_loc).strip() # Strips out "Hey Jarvis" and leaves "Japan"
            break

    if category == "GENERAL":
        is_conversational = any(phrase in lower_prompt for phrase in ["how are you", "hello", "hi", "who are you", "thanks"])
        if not is_conversational:
            if any(k in lower_prompt for k in ["gravity", "physics", "concept", "explain"]): category = "CONCEPT"
            elif any(k in lower_prompt for k in ["spacex", "starship", "nasa", "rocket", "design"]): category = "RESEARCH"
            elif any(k in lower_prompt for k in ["news", "latest", "president", "weather"]): category = "NEWS"

    if category not in ["GENERAL", "LOCATION", "SYSTEM"]:
        web_info, found_images = search_web_and_images(user_prompt)
        if web_info:
            web_context = f"\n[LIVE WEB DATA]:\n{web_info}\nStrictly summarize this in a maximum of 2 sentences."

    system_instruction = "You are J.A.R.V.I.S. Respond with extreme conciseness. Your response MUST NEVER exceed 2 sentences. DO NOT use parentheses or brackets. Keep it direct and futuristic."
    
    if category == "LOCATION":
        prompt_for_ollama = f"The user asked to see a live view or map of {query_title}. In exactly 1 sentence, confirm that you are accessing the orbital satellite feed for {query_title}."
    else:
        prompt_for_ollama = f"{system_instruction}\nUser: {user_prompt} {web_context}"
    
    conversation_history.append({"role": "user", "content": prompt_for_ollama})
    if len(conversation_history) > 6: conversation_history = conversation_history[-6:]

    try:
        ollama_response = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": "jarvis", "messages": conversation_history, "stream": False},
            timeout=15
        )
        bot_reply = ollama_response.json().get("message", {}).get("content", "I am unable to process that at the moment, sir.")
        bot_reply = re.sub(r'\(.*?\)|\[.*?\]', '', bot_reply).strip()
        bot_reply = " ".join(bot_reply.split())

        conversation_history[-1]["content"] = user_prompt 
        conversation_history.append({"role": "assistant", "content": bot_reply})

        return jsonify({
            "status": "success", 
            "response": bot_reply,
            "images": found_images,
            "query_title": query_title.upper(),
            "category": category
        })
    except Exception as e:
        return jsonify({"status": "error", "response": "Mainframe offline, sir.", "images": [], "category": "ERROR"})

if __name__ == '__main__':
    print("🤖 J.A.R.V.I.S. System Control Proxy online at http://localhost:5000")
    app.run(port=5000)
