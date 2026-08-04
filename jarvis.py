import asyncio
import json
import sqlite3
import requests
import speech_recognition as sr
import pyttsx3
import websockets

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.1"
SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., an advanced virtual AI assistant. Address the user as 'sir'. "
    "Be concise and witty. Keep responses under 2 sentences."
)

# --- 1. MEMORY SYSTEM ---
conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, message TEXT)")
conn.commit()

def save_message(role, message):
    cursor.execute("INSERT INTO conversations (role, message) VALUES (?, ?)", (role, message))
    conn.commit()

def load_history(limit=10):
    cursor.execute("SELECT role, message FROM conversations ORDER BY id DESC LIMIT ?", (limit,))
    return list(reversed(cursor.fetchall()))

def build_context():
    history = load_history()
    context = SYSTEM_PROMPT + "\n\n--- HISTORY ---\n"
    for role, message in history:
        context += f"{role}: {message}\n"
    return context

# --- 2. ENGINE INIT ---
engine = pyttsx3.init() # Auto-detects Windows engine
engine.setProperty('rate', 175)

recognizer = sr.Recognizer()
connected_clients = set()

def speak(text):
    print(f"J.A.R.V.I.S.: {text}")
    engine.say(text)
    engine.runAndWait()

async def broadcast_to_hud(data):
    if connected_clients:
        message = json.dumps(data)
        await asyncio.gather(*[client.send(message) for client in connected_clients], return_exceptions=True)

async def process_query(prompt):
    await broadcast_to_hud({"status": "PROCESSING...", "active": True})
    save_message("You", prompt)
    
    full_prompt = build_context() + f"You: {prompt}\nJarvis:"
    try:
        response = requests.post(OLLAMA_URL, json={"model": MODEL_NAME, "prompt": full_prompt, "stream": False}, timeout=20)
        if response.status_code == 200:
            reply = response.json().get("response", "I encountered an error, sir.").strip()
            save_message("Jarvis", reply)
            await broadcast_to_hud({"status": "SPEAKING...", "transcript": f"J.A.R.V.I.S.: {reply}", "active": True})
            speak(reply)
    except Exception as e:
        print(f"Error: {e}")
    await broadcast_to_hud({"status": "SAY 'JARVIS' TO WAKE", "active": False})

async def voice_listener():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        while True:
            try:
                await broadcast_to_hud({"status": "LISTENING...", "active": False})
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
                text = recognizer.recognize_google(audio).lower()
                if "jarvis" in text:
                    query = text.replace("jarvis", "").strip()
                    await broadcast_to_hud({"status": "ACTIVE", "transcript": f"USER: {text}", "active": True})
                    if not query: speak("At your service, sir.")
                    else: await process_query(query)
            except: continue

async def ws_handler(websocket):
    connected_clients.add(websocket)
    try: await websocket.wait_closed()
    finally: connected_clients.remove(websocket)

async def main():
    server = await websockets.serve(ws_handler, "localhost", 8765)
    await asyncio.gather(server.wait_closed(), voice_listener())

if __name__ == "__main__":
    asyncio.run(main())
