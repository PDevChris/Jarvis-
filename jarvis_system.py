import os
import webbrowser
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# Replace with your fresh API key from https://fish.audio/
FISH_API_KEY = "6d8584dea4c84fa5aa34b7a43ec774c2"
FISH_VOICE_ID = "41f0953d7a6b4c078445c7e65d620eeb" # Paul Bettany / JARVIS

HUD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STARK INDUSTRIES — J.A.R.V.I.S. OS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --hud-cyan: #00f0ff;
    --hud-blue: #0077ff;
    --hud-amber: #ff9900;
    --hud-bg: #010812;
    --hud-glass: rgba(1, 12, 28, 0.82);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  html, body {
    background: var(--hud-bg);
    height: 100vh; width: 100vw;
    overflow: hidden;
    font-family: 'Share Tech Mono', monospace;
    color: var(--hud-cyan);
    user-select: none;
  }

  canvas { position: absolute; top: 0; left: 0; width: 100vw; height: 100vh; }
  #bgCanvas { z-index: 1; }

  .crt-overlay {
    position: fixed; inset: 0; z-index: 3; pointer-events: none;
    background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.3) 50%),
                linear-gradient(90deg, rgba(255, 0, 0, 0.02), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.02));
    background-size: 100% 3px, 6px 100%;
  }

  .top-sequence-bar {
    position: fixed; top: 10px; left: 20px; right: 20px; z-index: 5;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; letter-spacing: 2px;
    border-bottom: 1px solid rgba(0, 240, 255, 0.3); padding-bottom: 6px;
  }
  .seq-nums span { margin-right: 10px; opacity: 0.5; }
  .seq-nums span.active { opacity: 1; font-weight: bold; text-shadow: 0 0 8px var(--hud-cyan); border-bottom: 2px solid var(--hud-cyan); }

  .stark-expo-logo {
    position: fixed; top: 200px; left: 160px; z-index: 4;
    font-family: 'Orbitron', sans-serif; font-weight: 900;
    font-size: 24px; letter-spacing: 4px; line-height: 0.95;
    color: var(--hud-cyan); text-shadow: 0 0 12px var(--hud-cyan); opacity: 0.8;
  }
  .stark-expo-logo span { font-size: 11px; letter-spacing: 2px; display: block; font-weight: 400; }

  .weather-panel {
    position: fixed; top: 55px; right: 20px; width: 220px; z-index: 5;
    background: var(--hud-glass); border: 1px solid rgba(0, 240, 255, 0.3);
    padding: 12px; font-size: 10px; line-height: 1.5;
  }
  .weather-title { font-family: 'Orbitron'; font-size: 11px; font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid rgba(0, 240, 255, 0.2); }

  .code-terminal {
    position: fixed; top: 60px; left: 20px; width: 220px; z-index: 5;
    background: var(--hud-glass); border: 1px solid rgba(0, 240, 255, 0.3);
    padding: 10px; font-size: 9px; line-height: 1.4; height: 130px; overflow: hidden;
  }

  .center-holo-wrapper {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
    z-index: 6; text-align: center; pointer-events: none; width: 500px;
  }

  .glitch-wordmark {
    font-family: 'Orbitron', sans-serif; font-size: 44px; font-weight: 900;
    font-style: italic; letter-spacing: 8px; color: #eaffff;
    text-shadow: 0 0 15px var(--hud-cyan), 0 0 30px var(--hud-cyan);
    animation: textGlitch 4s infinite; margin-top: 195px;
  }

  @keyframes textGlitch {
    0%, 90%, 100% { transform: translate(0, 0); opacity: 1; }
    92% { transform: translate(-3px, 1px); opacity: 0.8; }
    94% { transform: translate(3px, -1px); opacity: 0.9; }
    96% { transform: translate(-1px, -2px); opacity: 0.7; }
  }

  #statusText { font-size: 12px; letter-spacing: 3px; margin-top: 4px; text-shadow: 0 0 8px var(--hud-cyan); }
  #transcript { font-size: 12px; margin-top: 8px; opacity: 0.95; color: var(--hud-cyan); text-shadow: 0 0 8px var(--hud-cyan); }

  .bottom-bar {
    position: fixed; bottom: 15px; left: 20px; right: 20px; z-index: 5;
    display: flex; justify-content: space-between; align-items: flex-end; font-size: 11px;
  }
  .stark-brand { font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: 900; letter-spacing: 6px; }

  #startOverlay {
    position: fixed; inset: 0; z-index: 20;
    background: rgba(1, 8, 18, 0.94);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    cursor: pointer;
  }
  .start-btn {
    border: 1px solid var(--hud-cyan); padding: 16px 32px;
    background: rgba(0, 240, 255, 0.08); font-family: 'Orbitron', sans-serif;
    font-size: 14px; letter-spacing: 3px; color: var(--hud-cyan);
    box-shadow: 0 0 25px rgba(0, 240, 255, 0.2); transition: 0.3s;
  }
  #startOverlay:hover .start-btn { background: var(--hud-cyan); color: #000; box-shadow: 0 0 35px var(--hud-cyan); }
</style>
</head>
<body>

<canvas id="bgCanvas"></canvas>
<div class="crt-overlay"></div>

<div id="startOverlay">
  <div class="start-btn">INITIALIZE STARK INDUSTRIES OS</div>
  <div style="font-size: 10px; margin-top: 12px; letter-spacing: 2px; opacity: 0.7;">CLICK ONCE TO ENGAGE AUDIO & MIC LINK</div>
</div>

<div class="top-sequence-bar">
  <div class="seq-nums">
    <span>01</span><span>02</span><span>03</span><span>04</span><span>05</span><span>06</span>
    <span>07</span><span>08</span><span>09</span><span>10</span><span>11</span><span>12</span>
    <span class="active">21</span><span>22</span><span>23</span><span>24</span><span>25</span>
  </div>
  <div>LOCATION: MOSCOW, RUSSIA | <span id="clockDisplay">23:52:00</span></div>
</div>

<div class="code-terminal">
  <div style="color:var(--hud-amber); font-weight:bold; margin-bottom:4px;">// SYSTEM CORE MONITOR</div>
  <div id="codeContent"></div>
</div>

<div class="stark-expo-logo">
  STARK EXPO
  <span>2010.</span>
</div>

<div class="weather-panel">
  <div class="weather-title">WEATHER / MOSCOW</div>
  <div>TEMP: 13°C (CLEAR)</div>
  <div>HUMIDITY: 77%</div>
  <div>WIND: 3 KM/H (SSW)</div>
  <div style="margin-top: 8px; border-top: 1px dashed rgba(0,240,255,0.2); padding-top: 4px;">
    FORECAST: SUNNY (23° / 11°)
  </div>
</div>

<div class="center-holo-wrapper">
  <div class="glitch-wordmark">JARVIS</div>
  <div id="statusText">SYSTEM STANDBY</div>
  <div id="transcript">"At your service, sir."</div>
</div>

<div class="bottom-bar">
  <div>
    <div>SYS_LOAD: 31% | TEMP: 28°C</div>
    <div>IP: 91.219.164.5</div>
  </div>
  <div class="stark-brand">STARK INDUSTRIES</div>
</div>

<script>
  let currentState = "IDLE";
  const statusText = document.getElementById("statusText");
  const transcriptText = document.getElementById("transcript");
  const startOverlay = document.getElementById("startOverlay");

  let audioCtx = null;

  function initAudioEngine() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    startAmbientReactorHum();
  }

  function playBeep(freq = 880, type = "sine", duration = 0.08) {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type; osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.04, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0005, audioCtx.currentTime + duration);
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.start(); osc.stop(audioCtx.currentTime + duration);
  }

  function playTechSweep() {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(250, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1200, audioCtx.currentTime + 0.2);
    gain.gain.setValueAtTime(0.03, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0005, audioCtx.currentTime + 0.2);
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.start(); osc.stop(audioCtx.currentTime + 0.2);
  }

  function startAmbientReactorHum() {
    if (!audioCtx) return;
    const gain = audioCtx.createGain();
    gain.gain.value = 0.008;
    gain.connect(audioCtx.destination);
    [55, 110].forEach(freq => {
      const osc = audioCtx.createOscillator();
      osc.type = "sine"; osc.frequency.value = freq;
      osc.connect(gain); osc.start();
    });
  }

  let chatterInterval = null;
  function startProcessingChatter() {
    stopProcessingChatter();
    chatterInterval = setInterval(() => {
      if (!audioCtx) return;
      playBeep(900 + Math.random() * 800, "square", 0.03);
    }, 80);
  }
  function stopProcessingChatter() {
    if (chatterInterval) { clearInterval(chatterInterval); chatterInterval = null; }
  }

  async function speak(text, onComplete) {
    currentState = "SPEAKING";
    statusText.textContent = "AUDIO OUTPUT...";
    transcriptText.textContent = "J.A.R.V.I.S.: " + text;
    playTechSweep();

    try {
      const res = await fetch("http://localhost:5001/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text })
      });

      if (!res.ok) throw new Error("TTS Proxy Error");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);

      audio.onended = () => {
        URL.revokeObjectURL(url);
        currentState = "IDLE";
        statusText.textContent = "SYSTEM READY";
        if (onComplete) onComplete();
      };
      audio.onerror = () => fallbackBrowserTTS(text, onComplete);
      audio.play();
    } catch (e) {
      fallbackBrowserTTS(text, onComplete);
    }
  }

  function fallbackBrowserTTS(text, onComplete) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05; utterance.pitch = 0.95;
    utterance.onend = () => {
      currentState = "IDLE";
      statusText.textContent = "SYSTEM READY";
      if (onComplete) onComplete();
    };
    speechSynthesis.speak(utterance);
  }

  async function queryOllama(promptText) {
    currentState = "THINKING";
    statusText.textContent = "PROCESSING QUERY...";
    transcriptText.textContent = "You: " + promptText;
    startProcessingChatter();

    try {
      const response = await fetch("http://localhost:11434/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "llama3.2",
          system: "You are J.A.R.V.I.S. Keep responses under 15 words. Address user as sir. Year is 2026.",
          prompt: promptText,
          stream: true,
          options: { num_predict: 40 }
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\\n");

        for (const line of lines) {
          if (!line) continue;
          const json = JSON.parse(line);
          fullResponse += json.response;
          transcriptText.textContent = "J.A.R.V.I.S.: " + fullResponse;
        }
      }

      stopProcessingChatter();
      speak(fullResponse, () => startListening());

    } catch (err) {
      stopProcessingChatter();
      speak("I cannot access my core backend, sir.", () => startListening());
    }
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = SpeechRecognition ? new SpeechRecognition() : null;

  if (recognition) {
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (e) => {
      if (currentState === "SPEAKING" || currentState === "THINKING") return;
      const heard = e.results[e.results.length - 1][0].transcript.trim();
      if (heard) queryOllama(heard);
    };

    recognition.onend = () => {
      try { recognition.start(); } catch(e) {}
    };
  }

  function startListening() {
    if (!recognition) return;
    currentState = "LISTENING";
    statusText.textContent = "LISTENING...";
    try { recognition.start(); } catch(e) {}
  }

  startOverlay.addEventListener("click", () => {
    startOverlay.style.display = "none";
    initAudioEngine();
    speak("Systems fully operational, sir.", () => startListening());
  });

  const bgCanvas = document.getElementById("bgCanvas");
  const bgCtx = bgCanvas.getContext("2d");

  function resize() {
    bgCanvas.width = window.innerWidth;
    bgCanvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  const sphereParticles = Array.from({ length: 240 }, () => ({
    theta: Math.random() * Math.PI * 2,
    phi: Math.acos(Math.random() * 2 - 1),
    radius: 130 + Math.random() * 20,
    size: Math.random() * 1.8 + 0.6
  }));

  let rotX = 0, rotY = 0, angle1 = 0, angle2 = 0;

  function renderBackground() {
    bgCtx.fillStyle = "#010812";
    bgCtx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);

    const cx = bgCanvas.width / 2;
    const cy = bgCanvas.height / 2;

    let mult = currentState === "THINKING" ? 2.5 : 1.0;
    rotX += 0.005 * mult;
    rotY += 0.008 * mult;
    angle1 += 0.004 * mult;
    angle2 -= 0.006 * mult;

    bgCtx.save();
    bgCtx.translate(cx, cy);

    bgCtx.rotate(angle1);
    bgCtx.strokeStyle = "rgba(0, 240, 255, 0.35)";
    bgCtx.lineWidth = 1.5;
    bgCtx.setLineDash([12, 8]);
    bgCtx.beginPath(); bgCtx.arc(0, 0, 220, 0, Math.PI * 2); bgCtx.stroke();

    bgCtx.rotate(angle2);
    bgCtx.strokeStyle = "rgba(0, 240, 255, 0.5)";
    bgCtx.lineWidth = 2;
    bgCtx.setLineDash([]);
    for (let i = 0; i < 36; i++) {
      const a = (i * Math.PI * 2) / 36;
      bgCtx.beginPath();
      bgCtx.moveTo(Math.cos(a) * 190, Math.sin(a) * 190);
      bgCtx.lineTo(Math.cos(a) * 200, Math.sin(a) * 200);
      bgCtx.stroke();
    }
    bgCtx.restore();

    bgCtx.save();
    bgCtx.translate(cx, cy);

    sphereParticles.forEach(p => {
      let x = p.radius * Math.sin(p.phi) * Math.cos(p.theta + rotY);
      let y = p.radius * Math.sin(p.phi) * Math.sin(p.theta + rotY);
      let z = p.radius * Math.cos(p.phi);

      let y1 = y * Math.cos(rotX) - z * Math.sin(rotX);
      let z1 = y * Math.sin(rotX) + z * Math.cos(rotX);

      let scale = 250 / (250 + z1);
      let px = x * scale;
      let py = y1 * scale;
      let alpha = (z1 + p.radius) / (2 * p.radius);

      bgCtx.fillStyle = currentState === "SPEAKING" 
        ? `rgba(255, 153, 0, ${alpha * 0.8})` 
        : `rgba(0, 240, 255, ${alpha * 0.8})`;
      bgCtx.beginPath();
      bgCtx.arc(px, py, p.size * scale, 0, Math.PI * 2);
      bgCtx.fill();
    });
    bgCtx.restore();

    [100, 220, 340].forEach((yOffset) => {
      bgCtx.strokeStyle = "rgba(0, 240, 255, 0.35)";
      bgCtx.lineWidth = 2;
      bgCtx.beginPath();
      bgCtx.arc(100, yOffset + 40, 32, 0, Math.PI * 2);
      bgCtx.stroke();
    });

    requestAnimationFrame(renderBackground);
  }
  renderBackground();

  const codeLines = [
    "#INCLUDE <JARVIS_CORE>",
    "TEMPLATE <TYPENAME VECTOR>",
    "GOLD SYSTEM_INIT(STATUS_OK);",
    "STATIC_IDENTIFIER(0x892F);",
    "DATA LINK = 431.1290.247;"
  ];
  const codeContent = document.getElementById("codeContent");
  setInterval(() => {
    let content = "";
    for (let i = 0; i < 5; i++) {
      const idx = Math.floor(Math.random() * codeLines.length);
      content += `<div>${codeLines[idx]}</div>`;
    }
    codeContent.innerHTML = content;
  }, 1600);

  setInterval(() => {
    document.getElementById("clockDisplay").textContent = new Date().toTimeString().split(' ')[0];
  }, 1000);
</script>
</body>
</html>
"""

# ROUTE 1: SERVES THE COMPLETE HUD AT http://localhost:5001/
@app.route("/")
def index():
    return Response(HUD_HTML, mimetype="text/html")

# ROUTE 2: TTS PROXY FOR FISH AUDIO
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = requests.post(
            "https://api.fish.audio/v1/tts",
            headers={
                "Authorization": f"Bearer {FISH_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "reference_id": FISH_VOICE_ID,
                "model": "s2.1-pro-free",
                "format": "mp3",
                "prosody": {"speed": 1.05, "volume": 0}
            },
            timeout=15
        )
        response.raise_for_status()
        return Response(response.content, mimetype="audio/mpeg")

    except requests.exceptions.RequestException as e:
        print(f"[Fish Audio Error]: {e}")
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    print("--------------------------------------------------")
    print(" J.A.R.V.I.S. OS ONLINE | http://localhost:5001")
    print(" Serving interface & Fish Audio proxy on Port 5001")
    print("--------------------------------------------------")
    webbrowser.open("http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
