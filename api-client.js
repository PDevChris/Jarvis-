// Centralized JARVIS API client — retry, health-check, and connection-state management.
(function () {
  const BASE = "http://localhost:8000";
  let _connected = false;
  let _healthTimer = null;
  const _connectCbs = [];
  const _disconnectCbs = [];

  // Core fetch wrapper with timeout and per-request retry
  async function _req(path, init = {}, retries = 1) {
    const ms = init.jarvisTimeout ?? 12000;
    const opts = { ...init };
    delete opts.jarvisTimeout;

    for (let i = 0; i <= retries; i++) {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), ms);
        const res = await fetch(BASE + path, { ...opts, signal: ctrl.signal });
        clearTimeout(t);

        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try { msg = (await res.clone().json()).error || msg; } catch (_) {}
          throw Object.assign(new Error(msg), { httpStatus: res.status });
        }

        // Mark connected on first successful request
        if (!_connected) _setConnected(true);
        return res;
      } catch (err) {
        const isNetwork = err.name === "AbortError" || err.message?.includes("Failed to fetch");
        if (isNetwork && _connected) _setConnected(false);
        if (isNetwork && i < retries) {
          await new Promise(r => setTimeout(r, 700 * (i + 1)));
          continue;
        }
        throw err;
      }
    }
  }

  function _setConnected(val) {
    if (_connected === val) return;
    _connected = val;
    (val ? _connectCbs : _disconnectCbs).forEach(fn => fn());
  }

  async function _poll() {
    try {
      const res = await fetch(BASE + "/health", { signal: AbortSignal.timeout(2500) });
      _setConnected(res.ok);
    } catch (_) {
      _setConnected(false);
    } finally {
      _healthTimer = setTimeout(_poll, _connected ? 15000 : 2000);
    }
  }

  window.apiClient = {
    get connected() { return _connected; },

    onConnect(fn) { _connectCbs.push(fn); },
    onDisconnect(fn) { _disconnectCbs.push(fn); },

    startPolling() {
      if (!_healthTimer) _poll();
    },

    async assistant(prompt, extra = {}) {
      const res = await _req("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, ...extra }),
      });
      return res.json();
    },

    async tts(text) {
      const res = await _req("/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        jarvisTimeout: 16000,
      });
      return res.blob();
    },

    // Fire-and-forget — backend memory is optional, never throw
    saveMemory(role, text) {
      _req("/memory/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, text }),
        jarvisTimeout: 4000,
      }, 0).catch(() => {});
    },

    async recallMemory(limit = 8) {
      const res = await _req(`/memory/recent?limit=${limit}`);
      return (await res.json()).entries || [];
    },

    async locationInfo(payload) {
      const res = await _req("/api/location-info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        jarvisTimeout: 10000,
      });
      return res.json();
    },
  };
})();
