// ============ CORE STATE ============
  let currentState = "IDLE";
  let isActiveSession = false;
  let initialized = false;

  const centerText = document.getElementById("centerText");
  const statusText = document.getElementById("statusText");
  const transcript = document.getElementById("transcript");
  const diagLogEl = document.getElementById("diagLog");
  const holoWorkspace = document.getElementById("holoWorkspace");
  const floatingPanelTemplate = document.getElementById("floatingPanelTemplate");

  document.querySelectorAll("[data-close-panel]").forEach((button) => {
    button.addEventListener("click", () => closeHoloPanel(button.dataset.closePanel));
  });

  const isExtension = typeof chrome !== "undefined" && !!chrome.runtime?.id;
  let floatingWindowIndex = 0;
  let activeMapMarker = null;

  // ============ CONNECTION STATE ============
  const connStatus = document.getElementById("connStatus");
  const connText = document.getElementById("connText");

  apiClient.onConnect(() => {
    connText.textContent = "JARVIS ONLINE";
    connStatus.querySelector(".conn-dot").style.background = "var(--hud-cyan)";
    connStatus.querySelector(".conn-dot").style.animation = "none";
    connStatus.style.borderColor = "rgba(0,225,255,0.35)";
    connStatus.style.color = "var(--hud-cyan)";
    setTimeout(() => connStatus.classList.add("online"), 1800);
    if (bootStarted) logDiagnostic("> backend reconnected", false);
  });

  apiClient.onDisconnect(() => {
    connStatus.classList.remove("online");
    connText.textContent = "CONNECTING TO JARVIS CORE...";
    const dot = connStatus.querySelector(".conn-dot");
    dot.style.background = "var(--hud-orange)";
    dot.style.animation = "blinkDot 0.9s ease-in-out infinite";
    connStatus.style.borderColor = "rgba(255,51,0,0.45)";
    connStatus.style.color = "var(--hud-orange)";
    logDiagnostic("> backend offline — retrying...", true);
  });

  apiClient.startPolling();

  function openHoloPanel(id) {
    const panel = document.getElementById(id);
    panel.classList.add("visible");
    panel.style.left = "50%";
    panel.style.top = "50%";
    panel.style.transform = "translate(-50%, -50%) scale(1)";
  }
  function closeHoloPanel(id) { document.getElementById(id).classList.remove("visible"); }

  // --- WINDOW MANAGEMENT & PHYSICS ---
  let activeFloatingWindows = [];

  function dismissWindow(panel) {
    panel.classList.add("window-dismiss");
    setTimeout(() => {
      activeFloatingWindows = activeFloatingWindows.filter(w => w !== panel);
      panel.remove();
    }, 220);
  }

  function registerPanelChrome(panel) {
    const closeBtn = panel.querySelector(".holo-panel-close");
    if (closeBtn) closeBtn.addEventListener("click", () => dismissWindow(panel));

    const pinBtn = panel.querySelector(".holo-pin-btn");
    if (pinBtn) {
      pinBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isPinned = panel.dataset.pinned === "true";
        panel.dataset.pinned = String(!isPinned);
        pinBtn.classList.toggle("pinned", !isPinned);
        pinBtn.textContent = !isPinned ? "PINNED 📌" : "PIN 📌";
      });
    }
    makePanelDraggable(panel);
  }

  function createFloatingWindow(config) {
    const fragment = floatingPanelTemplate.content.cloneNode(true);
    const panel = fragment.querySelector(".holo-panel");
    const title = fragment.querySelector(".holo-panel-title");
    const body = fragment.querySelector(".holo-body-text");

    panel.dataset.windowIndex = String(floatingWindowIndex++);
    panel.dataset.pinned = "false";
    panel.dataset.phaseX = Math.random() * Math.PI * 2;
    panel.dataset.phaseY = Math.random() * Math.PI * 2;
    title.textContent = config.title;

    if (typeof config.content === "string") body.innerHTML = config.content;
    else body.replaceWith(config.content);

    holoWorkspace.appendChild(fragment);
    const createdPanel = holoWorkspace.lastElementChild;
    
    const cascadeX = Math.max(20, window.innerWidth / 2 - 220 + (Math.random() * 80 - 40));
    const cascadeY = Math.max(80, window.innerHeight / 2 - 180 + (Math.random() * 60 - 30));
    
    createdPanel.style.left = `${config.left ?? cascadeX}px`;
    createdPanel.style.top = `${config.top ?? cascadeY}px`;
    createdPanel.style.transform = "scale(1) translate(0px, 0px)";
    
    registerPanelChrome(createdPanel);
    activeFloatingWindows.push(createdPanel);
    playPing();
    return createdPanel;
  }

  function makePanelDraggable(panel) {
    const header = panel.querySelector(".holo-panel-header");
    if (!header) return;
    
    let dragging = false;
    let startX = 0, startY = 0, originLeft = 0, originTop = 0, vx = 0, vy = 0, lastTime = 0;

    header.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".holo-panel-actions") || event.target.closest(".holo-panel-close")) return;
      dragging = true;
      panel.classList.add("dragging");
      startX = event.clientX; startY = event.clientY;
      const rect = panel.getBoundingClientRect();
      originLeft = rect.left; originTop = rect.top;
      vx = 0; vy = 0; lastTime = performance.now();
      header.setPointerCapture(event.pointerId);
    });

    header.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      const now = performance.now(), dt = Math.max((now - lastTime) / 1000, 0.001);
      const deltaX = event.clientX - startX, deltaY = event.clientY - startY;
      const currentLeft = originLeft + deltaX, currentTop = originTop + deltaY;
      
      vx = (event.clientX - (startX + (currentLeft - originLeft))) / dt;
      vy = (event.clientY - (startY + (currentTop - originTop))) / dt;
      lastTime = now;
      
      panel.style.left = `${currentLeft}px`;
      panel.style.top = `${currentTop}px`;
      panel.style.transform = "scale(1) translate(0px, 0px)";
    });

    const finishDrag = () => {
      if (!dragging) return;
      dragging = false; panel.classList.remove("dragging");
      const rect = panel.getBoundingClientRect(), threshold = 60;
      
      if (rect.right < threshold || rect.left > window.innerWidth - threshold || rect.bottom < threshold || rect.top > window.innerHeight - threshold) {
        dismissWindow(panel); return;
      }
      if (Math.abs(vx) > 150 || Math.abs(vy) > 150) {
        const targetLeft = rect.left + vx * 0.12, targetTop = rect.top + vy * 0.12;
        if (targetLeft + rect.width < threshold || targetLeft > window.innerWidth - threshold || targetTop + rect.height < threshold || targetTop > window.innerHeight - threshold) {
            panel.style.transition = "left 300ms ease-out, top 300ms ease-out";
            panel.style.left = `${targetLeft}px`; panel.style.top = `${targetTop}px`;
            dismissWindow(panel); return;
        }
        panel.style.transition = "left 300ms ease-out, top 300ms ease-out";
        panel.style.left = `${Math.max(10, Math.min(window.innerWidth - rect.width - 10, targetLeft))}px`;
        panel.style.top = `${Math.max(10, Math.min(window.innerHeight - rect.height - 10, targetTop))}px`;
        setTimeout(() => { panel.style.transition = ""; }, 300);
      }
    };
    header.addEventListener("pointerup", finishDrag);
    header.addEventListener("pointercancel", finishDrag);
  }

  document.querySelectorAll(".holo-panel").forEach(panel => makePanelDraggable(panel));

  function cleanupUnpinnedWindows() {
    setTimeout(() => {
      activeFloatingWindows.forEach(panel => { if (panel.dataset.pinned !== "true") dismissWindow(panel); });
    }, 3500);
  }

  function animateIdleWindows() {
    const time = performance.now() * 0.001;
    activeFloatingWindows.forEach(panel => {
      if (!panel.classList.contains("dragging") && !panel.classList.contains("window-dismiss")) {
        const dx = Math.sin(time * 0.8 + parseFloat(panel.dataset.phaseX || 0)) * 5;
        const dy = Math.sin(time * 0.6 + parseFloat(panel.dataset.phaseY || 0)) * 8;
        panel.style.transform = `scale(1) translate(${dx}px, ${dy}px)`;
      }
    });
    requestAnimationFrame(animateIdleWindows);
  }
  requestAnimationFrame(animateIdleWindows);

  // ============ SOUND CLIPS ============
  function playClip(src, volume) { const a = new Audio(src); a.volume = volume || 0.5; a.play().catch(() => {}); }
  function playPing() { playClip("sfx_ping.mp3", 0.5); }
  function playSweep() { playClip("sfx_sweep.mp3", 0.4); }
  function playTick() { playClip("sfx_tick.mp3", 0.35); }
  function playHoloOpen() { playClip("sfx_binary_blip.mp3", 0.42); }
  function playNotify() { playClip("sfx_binary_intro.mp3", 0.38); }

  let chatterInterval = null;
  function startProcessingChatter() { stopProcessingChatter(); chatterInterval = setInterval(playTick, 160); }
  function stopProcessingChatter() { if (chatterInterval) { clearInterval(chatterInterval); chatterInterval = null; } }

  let audioCtx = null;
  function initAudioEngine() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const gain = audioCtx.createGain(); gain.gain.value = 0.01; gain.connect(audioCtx.destination);
    [55, 82.5].forEach(freq => { const osc = audioCtx.createOscillator(); osc.type = "sine"; osc.frequency.value = freq; osc.connect(gain); osc.start(); });
  }

  // ============ CLAP-TO-WAKE ============
  async function armClapDetector() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser(); analyser.fftSize = 512; source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      let lastClapTime = 0;
      function checkClap() {
        if (bootStarted) {
          stream.getTracks().forEach(t => t.stop());
          try { ctx.close(); } catch(e) {}
          return;
        }
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length, now = Date.now();
        if (avg > 55 && now - lastClapTime > 1200) {
          lastClapTime = now;
          stream.getTracks().forEach(t => t.stop());
          try { ctx.close(); } catch(e) {}
          bootSystem();
          return;
        }
        if (!bootStarted) requestAnimationFrame(checkClap);
      }
      checkClap();
    } catch (err) {
      statusText.textContent = "MIC ACCESS DENIED"; transcript.textContent = "Grant microphone access then reload JARVIS.";
    }
  }
  armClapDetector();

  let bootStarted = false;
  function playWakeSequence(callback) {
    const ring = document.getElementById("wakeRing"), label = document.getElementById("wakeLabel");
    ring.classList.remove("play"); label.classList.remove("play");
    void ring.offsetWidth; void label.offsetWidth; 
    setTimeout(() => label.classList.add("play"), 80); ring.classList.add("play");
    setTimeout(() => { ring.classList.remove("play"); label.classList.remove("play"); callback?.(); }, 1500);
  }

  function bootSystem() {
    if (bootStarted) return;
    bootStarted = true; statusText.classList.remove("standby"); transcript.textContent = "";
    initAudioEngine(); playSweep(); playNotify();
    playWakeSequence(() => speak("Online, sir.", () => startListening()));
  }

  // ============ TTS VOICE SELECTION (DANIEL PRIORITY) ============
  let jarvisVoice = null;
  function loadVoice() {
    if (typeof speechSynthesis === "undefined") return null;
    const voices = speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;
    
    jarvisVoice = voices.find(v => v.name.includes("Daniel"))
      || voices.find(v => v.name.includes("Google UK English Male"))
      || voices.find(v => v.lang === "en-GB" && v.name.toLowerCase().includes("male"))
      || voices.find(v => v.name.includes("George"))
      || voices.find(v => v.lang === "en-GB")
      || voices[0];
    return jarvisVoice;
  }
  if (typeof speechSynthesis !== "undefined") {
    speechSynthesis.onvoiceschanged = loadVoice;
    loadVoice();
  }

  function speakBrowserVoice(text, onComplete) {
    if (typeof speechSynthesis === "undefined") {
      if (onComplete) onComplete();
      return;
    }
    speechSynthesis.cancel();
    stopListening(); // Mute mic while speaking
    
    const utterance = new SpeechSynthesisUtterance(text);
    const v = loadVoice();
    if (v) utterance.voice = v;
    
    utterance.pitch = 1.0;
    utterance.rate = 1.05;

    utterance.onend = () => {
      currentState = "IDLE";
      statusText.textContent = "SYSTEM READY";
      cleanupUnpinnedWindows();
      if (onComplete) onComplete();
      startListening(); // Resume listening after speaking
    };
    utterance.onerror = (e) => {
      currentState = "IDLE";
      statusText.textContent = "SYSTEM READY";
      if (onComplete) onComplete();
      startListening();
    };

    speechSynthesis.speak(utterance);
  }

  function logDiagnostic(message, isWarning) {
    const line = document.createElement("div"); line.className = "diag-line";
    if (isWarning) line.style.color = "var(--hud-orange)";
    line.textContent = message; diagLogEl.appendChild(line);
    setTimeout(() => line.remove(), 6000);
    while (diagLogEl.children.length > 4) diagLogEl.removeChild(diagLogEl.firstChild);
  }

  async function speak(text, onComplete) {
    currentState = "SPEAKING"; 
    statusText.textContent = "AUDIO OUTPUT..."; 
    transcript.textContent = "JARVIS: " + text;
    stopListening(); // Mute mic while speaking

    try {
      const blob = await apiClient.tts(text); 
      const url = URL.createObjectURL(blob);
      const audioEl = new Audio(url);
      audioEl.onended = () => { 
        URL.revokeObjectURL(url); 
        currentState = "IDLE"; 
        statusText.textContent = "SYSTEM READY"; 
        cleanupUnpinnedWindows(); 
        if (onComplete) onComplete(); 
        startListening(); 
      };
      audioEl.onerror = () => speakBrowserVoice(text, onComplete);
      audioEl.play();
    } catch (_) { 
      // Silently fallback to Browser Voice (Daniel) on any error
      speakBrowserVoice(text, onComplete); 
    }
  }

  // ============ SPEECH RECOGNITION (CONTROLLED MIC LIFECYCLE) ============
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = SpeechRecognitionCtor ? new SpeechRecognitionCtor() : null;
  let isListening = false;
  let recognitionRestartTimer = null;

  if (recognition) {
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (e) => {
      if (currentState === "SPEAKING" || currentState === "THINKING") return;
      const heard = e.results[e.results.length - 1][0].transcript.trim();
      if (heard) {
        stopListening();
        processQuery(heard);
      }
    };

    recognition.onerror = (event) => {
      // Ignore routine errors to keep console clean
    };

    recognition.onend = () => {
      isListening = false;
      if (bootStarted && currentState === "IDLE") {
        clearTimeout(recognitionRestartTimer);
        recognitionRestartTimer = setTimeout(() => {
          startListening();
        }, 400);
      }
    };
  }

  function startListening() {
    if (!recognition || !bootStarted || currentState === "SPEAKING" || currentState === "THINKING") return;
    if (isListening) return;
    try {
      recognition.start();
      isListening = true;
      currentState = "LISTENING";
      statusText.textContent = "LISTENING...";
    } catch (e) {
      isListening = false;
    }
  }

  function stopListening() {
    if (!recognition) return;
    isListening = false;
    clearTimeout(recognitionRestartTimer);
    try {
      recognition.stop();
    } catch (e) {}
  }

  // ============ INTENT DETECTION & HELPERS ============
  const LOCATION_PATTERN = /\b(where is|where are|where am i|take me to|show me|locate|map of|fly to|near me|around me)\b/i;
  function extractLocationQuery(text) { return text.replace(/jarvis[:,]?/i, "").replace(LOCATION_PATTERN, "").replace(/\b(on the map|the map|the city|the country)\b/gi, "").replace(/\s+/g, " ").trim(); }
  function isCurrentLocationRequest(text) { return /\b(where am i|my location|near me|around me)\b/i.test(text); }

  async function getCurrentCoordinates() {
    if (!navigator.geolocation) return null;
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition((pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }), () => resolve(null), { enableHighAccuracy: true, timeout: 5000, maximumAge: 30000 });
    });
  }

  function renderImageGrid(images) {
    if (!images?.length) return "";
    return `<div class="holo-image-grid">${images.slice(0, 6).map(src => `<img src="${src}" class="holo-img" onerror="this.style.display='none'" />`).join("")}</div>`;
  }
  function renderLinkGrid(links) {
    if (!links?.length) return "";
    return `<div class="tab-link-grid">${links.map(link => `<a class="tab-link" href="${link.url}" target="_blank" rel="noreferrer">${link.label}</a>`).join("")}</div>`;
  }

  // --- UNIFIED HOLOGRAPHIC WINDOW BUILDER ---
  function openResearchWindows(question, payload) {
    const research = payload.research || {};
    let combinedContent = "";

    if (research.summary) {
      combinedContent += `<div class="holo-section-label">// ANALYSIS</div>`;
      combinedContent += `<div style="margin-bottom: 12px; color: #dfffff;">${research.summary.replace(/\n/g, '<br>')}</div>`;
    }
    if (research.page?.excerpt) {
      combinedContent += `<div class="holo-section-label">// VISUAL CONTEXT DETECTED</div>`;
      combinedContent += `<div style="margin-bottom: 12px; color: #00e1ff; font-style: italic;">${research.page.excerpt}</div>`;
    }
    if (research.news) {
      combinedContent += `<div class="holo-section-label">// RECENT INTELLIGENCE</div>`;
      const newsItems = research.news.split("\n").filter(Boolean).map(item => `<div>${item}</div>`).join("");
      combinedContent += `<div class="holo-bullet-list" style="margin-bottom: 12px;">${newsItems}</div>`;
    }
    if (research.images?.length) {
      combinedContent += `<div class="holo-section-label">// VISUAL DATA</div>`;
      combinedContent += renderImageGrid(research.images);
    }
    if (research.links?.length) {
      combinedContent += `<div class="holo-section-label">// EXTERNAL DATALINKS</div>`;
      combinedContent += renderLinkGrid(research.links);
    }

    if (combinedContent) {
      let windowTitle = "INTELLIGENCE";
      if (payload.category === "MARKET_RESEARCH") windowTitle = "MARKET ANALYSIS";
      if (payload.category === "SCREEN_READ") windowTitle = "VISUAL TELEMETRY";

      createFloatingWindow({
        title: windowTitle,
        content: combinedContent
      });
      playHoloOpen();
    }
  }

  function clearExistingMapMarker() { if (activeMapMarker) { activeMapMarker.remove(); activeMapMarker = null; } }

  // ---- Location panel & Cinematic Globe ----
  let globeMap = null;
  let spinAnimation = null;

  function ensureGlobeMap() {
    if (globeMap) return globeMap;
    globeMap = new maplibregl.Map({
      container: 'globeMapContainer',
      style: {
        version: 8,
        sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256 } },
        layers: [{ id: 'osm-layer', type: 'raster', source: 'osm', minzoom: 0, maxzoom: 19 }]
      },
      center: [-90, 30], zoom: 0.5, pitch: 0, bearing: 0,
      renderWorldCopies: false 
    });
    
    globeMap.on('style.load', () => { 
      try { globeMap.setProjection({ type: 'globe' }); } catch (e) {} 
    });
    return globeMap;
  }

  function startGlobeSpin() {
    if (!globeMap) return;
    const center = globeMap.getCenter();
    center.lng -= 1.5; 
    globeMap.easeTo({ center, duration: 50, easing: n => n });
    spinAnimation = requestAnimationFrame(startGlobeSpin);
  }

  function stopGlobeSpin() {
    if (spinAnimation) {
      cancelAnimationFrame(spinAnimation);
      spinAnimation = null;
    }
  }

  async function tryLocationIntent(question) {
    const place = extractLocationQuery(question);
    const currentCoords = isCurrentLocationRequest(question) ? await getCurrentCoordinates() : null;
    if (!place && !currentCoords) return false;

    document.getElementById("globeTitle").textContent = (place || "CURRENT LOCATION").toUpperCase();
    document.getElementById("globeCoords").textContent = "SEARCHING...";
    document.getElementById("globeDescription").textContent = "—"; 
    document.getElementById("globeWeather").textContent = "—";
    
    openHoloPanel("globePanel"); 
    playHoloOpen();
    
    const map = ensureGlobeMap(); 
    setTimeout(() => map.resize(), 100);
    
    stopGlobeSpin();
    map.jumpTo({ center: [-90, 20], zoom: 0.5, pitch: 0, bearing: 0 });
    startGlobeSpin();

    try {
      const payload = currentCoords ? { latitude: currentCoords.latitude, longitude: currentCoords.longitude, query: "Current location" } : { query: place };
      const data = await apiClient.locationInfo(payload);
      
      if (data.status === "success") {
        const coords = data.coords || {};
        document.getElementById("globeTitle").textContent = (data.title || place).toUpperCase();
        document.getElementById("globeCoords").textContent = `LAT ${Number(coords.lat || 0).toFixed(4)}° / LON ${Number(coords.lon || 0).toFixed(4)}°`;
        document.getElementById("globeDescription").textContent = `${data.description || "Location data ready."}`;
        document.getElementById("globeWeather").textContent = (data.weather && data.weather.condition) ? `${data.weather.condition} · ${data.weather.temperature}°F` : "WEATHER DATA UNAVAILABLE";
        
        if (coords.lat !== undefined && coords.lon !== undefined) {
          clearExistingMapMarker();
          stopGlobeSpin(); // INSTANTLY stop the spin once target locked
          
          map.flyTo({ 
            center: [coords.lon, coords.lat], 
            zoom: 13.5, 
            pitch: 65, 
            bearing: Math.random() * 60 - 30, 
            speed: 0.9, 
            curve: 1.7, 
            essential: true 
          });
          
          const markerEl = document.createElement("div"); 
          markerEl.style.width = "14px"; 
          markerEl.style.height = "14px"; 
          markerEl.style.borderRadius = "50%"; 
          markerEl.style.background = "#ff3300"; 
          markerEl.style.boxShadow = "0 0 18px #ff3300";
          activeMapMarker = new maplibregl.Marker({ element: markerEl }).setLngLat([coords.lon, coords.lat]).addTo(map);
        }
      } else {
        document.getElementById("globeCoords").textContent = "TARGET UNREACHABLE";
        stopGlobeSpin();
      }
    } catch (e) { 
      document.getElementById("globeCoords").textContent = "GEOCODING ERROR"; 
      stopGlobeSpin();
    }
    return true;
  }

  // Silently handles chrome extension errors in Codespaces
  async function getPageContext() {
    if (!isExtension) return null;
    return new Promise((resolve) => { 
      try {
        chrome.runtime.sendMessage({ type: "JARVIS_PAGE_CONTEXT" }, (response) => { 
          if (chrome.runtime.lastError) resolve(null);
          else resolve(response?.pageContext || null); 
        }); 
      } catch (e) {
        resolve(null);
      }
    }); 
  }

  function saveToMemory(role, text) { apiClient.saveMemory(role, text); }

  // ============ QUERY PROCESSING ============
  async function processQuery(question) {
    currentState = "THINKING"; isActiveSession = true; centerText.classList.add("active");
    transcript.textContent = "You: " + question; statusText.textContent = "PROCESSING QUERY...";
    startProcessingChatter(); saveToMemory("user", question);

    const pageContext = /\b(this webpage|this page|on screen|what am i looking at)\b/i.test(question) ? await getPageContext() : null;

    try {
      const locationContext = isCurrentLocationRequest(question) ? await getCurrentCoordinates() : null;
      const payload = await apiClient.assistant(question, { page_context: pageContext, location_context: locationContext });
      
      if (payload.status !== "success") throw new Error(payload.message || "Assistant request failed.");

      stopProcessingChatter();
      transcript.textContent = "JARVIS: " + payload.response;

      if (payload.category === "LOCATION") {
        await tryLocationIntent(question);
      } else if (["RESEARCH", "MARKET_RESEARCH", "SCREEN_READ"].includes(payload.category)) {
        if (payload.research && (payload.research.summary || payload.research.images?.length)) {
          openResearchWindows(question, payload);
        }
      } 

      saveToMemory("jarvis", payload.response);
      speak(payload.response, () => { 
        statusText.textContent = "SYSTEM ACTIVE"; 
        centerText.classList.remove("active"); 
        isActiveSession = false; 
      });
    } catch (err) {
      stopProcessingChatter();
      const offline = err.message?.includes("Failed to fetch") || !apiClient.connected;
      const reason = offline ? "BACKEND OFFLINE" : (err.name === "AbortError" ? "TIMED OUT" : "ERROR");
      statusText.textContent = reason; transcript.textContent = offline ? "Reconnecting to JARVIS..." : err.message;
      logDiagnostic("> " + reason + (offline ? "" : ": " + err.message), true);
      centerText.classList.remove("active"); isActiveSession = false; currentState = "IDLE";
      const diagnosis = offline ? "Backend offline, sir. I will reconnect automatically." : "Processing error, sir. Please try again.";
      speak(diagnosis, () => startListening());
    }
  }

  // ============ BACKGROUND CANVAS ============
  const bgCanvas = document.getElementById("bgCanvas"), bgCtx = bgCanvas.getContext("2d");
  const dataCanvas = document.getElementById("dataCanvas"), dctx = dataCanvas.getContext("2d");
  const reactorCanvas = document.getElementById("reactorCanvas"), rctx = reactorCanvas.getContext("2d");

  function resizeCanvases() { [bgCanvas, dataCanvas, reactorCanvas].forEach(c => { c.width = window.innerWidth; c.height = window.innerHeight; }); }
  window.addEventListener("resize", resizeCanvases); resizeCanvases();

  const particles = Array.from({ length: 100 }, () => ({ x: Math.random() * window.innerWidth, y: Math.random() * window.innerHeight, size: Math.random() * 2 + 0.5, speedY: -(Math.random() * 0.9 + 0.15), driftX: (Math.random() - 0.5) * 0.3, opacity: Math.random() * 0.7 + 0.2 }));
  let gridOffset = 0;

  function renderBackground() {
    bgCtx.fillStyle = "#020813"; bgCtx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);
    bgCtx.strokeStyle = "rgba(0,225,255,0.05)"; bgCtx.lineWidth = 1; gridOffset = (gridOffset + 0.5) % 40;
    for (let x = 0; x < bgCanvas.width; x += 40) { bgCtx.beginPath(); bgCtx.moveTo(x, 0); bgCtx.lineTo(x, bgCanvas.height); bgCtx.stroke(); }
    for (let y = gridOffset; y < bgCanvas.height; y += 40) { bgCtx.beginPath(); bgCtx.moveTo(0, y); bgCtx.lineTo(bgCanvas.width, y); bgCtx.stroke(); }
    particles.forEach(p => {
      p.y += p.speedY; p.x += p.driftX;
      if (p.y < 0) p.y = bgCanvas.height; if (p.x < 0) p.x = bgCanvas.width; if (p.x > bgCanvas.width) p.x = 0;
      bgCtx.fillStyle = isActiveSession ? "rgba(255,51,0," + p.opacity + ")" : "rgba(0,225,255," + p.opacity + ")";
      bgCtx.beginPath(); bgCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2); bgCtx.fill();
    });
    requestAnimationFrame(renderBackground);
  }
  renderBackground();

  const dataPanels = [{ x: 0.08, y: 0.62, w: 150, h: 60, kind: "bars" }, { x: 0.84, y: 0.62, w: 150, h: 60, kind: "wave" }];
  function renderDataLayer() {
    dctx.clearRect(0, 0, dataCanvas.width, dataCanvas.height);
    const mainColor = isActiveSession ? "#ff3300" : "#00e1ff";
    dctx.strokeStyle = mainColor; dctx.fillStyle = mainColor; dctx.globalAlpha = 0.5;
    dataPanels.forEach(panel => {
      const px = panel.x * dataCanvas.width, py = panel.y * dataCanvas.height;
      dctx.strokeRect(px, py, panel.w, panel.h);
      if (panel.kind === "bars") {
        for (let i = 0; i < 12; i++) {
          const h = (Math.sin(Date.now() / 300 + i * 0.7) * 0.5 + 0.5) * (panel.h - 10);
          dctx.fillRect(px + 6 + i * ((panel.w - 12) / 12), py + panel.h - 5 - h, 4, h);
        }
      } else {
        dctx.beginPath();
        for (let i = 0; i < 60; i++) {
          const x = px + (i / 60) * panel.w;
          const amp = currentState === "SPEAKING" ? Math.random() : Math.sin(Date.now() / 400 + i * 0.3) * 0.3 + 0.3;
          const y = py + panel.h / 2 - amp * (panel.h / 2 - 4);
          if (i === 0) dctx.moveTo(x, y); else dctx.lineTo(x, y);
        }
        dctx.stroke();
      }
    });
    dctx.globalAlpha = 1;
    requestAnimationFrame(renderDataLayer);
  }
  renderDataLayer();

  let angle1 = 0, angle2 = 0;
  function renderReactor() {
    rctx.clearRect(0, 0, reactorCanvas.width, reactorCanvas.height);
    const cx = reactorCanvas.width / 2, cy = reactorCanvas.height / 2;
    const mult = currentState === "THINKING" ? 2.2 : currentState === "SPEAKING" ? 1.6 : 1.0;
    angle1 += 0.003 * mult; angle2 -= 0.006 * mult;
    const mainColor = isActiveSession ? "#ff3300" : "#00e1ff";

    rctx.save(); rctx.translate(cx, cy); rctx.rotate(angle1);
    rctx.strokeStyle = mainColor; rctx.globalAlpha = 0.35; rctx.lineWidth = 8; rctx.setLineDash([16, 10]);
    rctx.beginPath(); rctx.arc(0, 0, 200, 0, Math.PI * 2); rctx.stroke();

    rctx.rotate(angle2); rctx.globalAlpha = 0.55; rctx.lineWidth = 2; rctx.setLineDash([]);
    for (let i = 0; i < 36; i++) { const a = (i * Math.PI * 2) / 36; rctx.beginPath(); rctx.moveTo(Math.cos(a) * 172, Math.sin(a) * 172); rctx.lineTo(Math.cos(a) * 184, Math.sin(a) * 184); rctx.stroke(); }

    const rTri = 105; rctx.globalAlpha = 0.9; rctx.lineWidth = 4; rctx.strokeStyle = mainColor; rctx.beginPath();
    for (let i = 0; i < 3; i++) { const a = (i * Math.PI * 2) / 3 - Math.PI / 2; const x = Math.cos(a) * rTri, y = Math.sin(a) * rTri; if (i === 0) rctx.moveTo(x, y); else rctx.lineTo(x, y); }
    rctx.closePath(); rctx.stroke();

    const grad = rctx.createRadialGradient(0, 0, 10, 0, 0, 125);
    grad.addColorStop(0, mainColor); grad.addColorStop(0.7, isActiveSession ? "rgba(255,51,0,0.15)" : "rgba(0,119,255,0.15)"); grad.addColorStop(1, "transparent");
    rctx.fillStyle = grad; rctx.globalAlpha = 1; rctx.fill(); rctx.restore();
    requestAnimationFrame(renderReactor);
  }
  renderReactor();

  let simState = { cpu: 40, mem: 55, net: 70 };
  setInterval(() => {
    Object.keys(simState).forEach(k => { simState[k] += (Math.random() - 0.5) * 10; simState[k] = Math.max(15, Math.min(98, simState[k])); });
    document.getElementById("cpuValText").textContent = Math.round(simState.cpu) + "%";
    document.getElementById("memValText").textContent = Math.round(simState.mem) + "%";
    document.getElementById("netValText").textContent = Math.round(simState.net) + "%";
  }, 1800);

  const cpuGraphCanvas = document.getElementById("cpuGraphCanvas"), cgctx = cpuGraphCanvas.getContext("2d");
  let cpuGraphData = Array.from({ length: 40 }, () => 40);
  setInterval(() => {
    cpuGraphData.shift(); cpuGraphData.push(simState.cpu);
    cgctx.clearRect(0, 0, 210, 28); cgctx.strokeStyle = "#00e1ff"; cgctx.lineWidth = 1.5; cgctx.beginPath();
    for (let i = 0; i < cpuGraphData.length; i++) { const x = (i / cpuGraphData.length) * 210, y = 28 - (cpuGraphData[i] / 100) * 28; if (i === 0) cgctx.moveTo(x, y); else cgctx.lineTo(x, y); }
    cgctx.stroke();
  }, 300);

  async function fetchWeather() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const latitude = pos.coords.latitude, longitude = pos.coords.longitude;
      try {
        const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m,weather_code&temperature_unit=fahrenheit`);
        const data = await res.json();
        document.getElementById("weatherTemp").textContent = Math.round(data.current.temperature_2m) + "°F";
        document.getElementById("weatherLocation").textContent = `LAT ${latitude.toFixed(2)} / LON ${longitude.toFixed(2)}`;
      } catch (e) { }
    }, () => {});
  }
  fetchWeather(); setInterval(fetchWeather, 10 * 60 * 1000);

  function randomHexLine() { let line = ""; for (let i = 0; i < 6; i++) line += Math.floor(Math.random() * 256).toString(16).padStart(2, "0").toUpperCase() + " "; return line; }
  function buildStream(el, lines) { let content = ""; for (let i = 0; i < lines; i++) content += randomHexLine() + "<br>"; el.innerHTML = content + content; }
  const streamLeftEl = document.getElementById("streamLeft"), streamRightEl = document.getElementById("streamRight");
  buildStream(streamLeftEl, 40); buildStream(streamRightEl, 40);
  streamLeftEl.style.animationDuration = "18s"; streamRightEl.style.animationDuration = "22s";
  setInterval(() => { buildStream(streamLeftEl, 40); buildStream(streamRightEl, 40); }, 6000);

  const tickerMessages = ["ALL SYSTEMS NOMINAL", "NETWORK INTEGRITY 100%", "OLLAMA LINK STABLE", "MEMORY BUFFER OPTIMAL", "AWAITING VOICE COMMAND", "AUDIO INPUT CALIBRATED", "SECURITY PROTOCOLS ACTIVE"];
  const tickerEl = document.getElementById("tickerText");
  function refreshTicker() { tickerEl.textContent = [...tickerMessages].sort(() => Math.random() - 0.5).join("   //   "); }
  refreshTicker(); setInterval(refreshTicker, 15000);

  const diagMessages = ["> scanning subsystems...", "> memory buffer synced", "> voice channel stable", "> thermal levels nominal", "> network handshake OK", "> parsing input stream", "> latency: 42ms"];
  setInterval(() => {
    const line = document.createElement("div"); line.className = "diag-line"; line.textContent = diagMessages[Math.floor(Math.random() * diagMessages.length)];
    diagLogEl.appendChild(line); setTimeout(() => line.remove(), 4000);
    while (diagLogEl.children.length > 4) diagLogEl.removeChild(diagLogEl.firstChild);
  }, 1500);
