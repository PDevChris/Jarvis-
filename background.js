const JARVIS_URL = "http://localhost:8000";
let jarvisTabId = null;

async function openOrFocusJarvis() {
  if (jarvisTabId !== null) {
    try {
      const tab = await chrome.tabs.get(jarvisTabId);
      if (tab) {
        await chrome.windows.update(tab.windowId, { focused: true });
        await chrome.tabs.update(jarvisTabId, { active: true });
        return;
      }
    } catch (_) {
      jarvisTabId = null;
    }
  }

  const existing = await chrome.tabs.query({ url: JARVIS_URL + "/*" });
  if (existing.length > 0) {
    jarvisTabId = existing[0].id;
    await chrome.windows.update(existing[0].windowId, { focused: true });
    await chrome.tabs.update(jarvisTabId, { active: true });
    return;
  }

  const tab = await chrome.tabs.create({ url: JARVIS_URL, active: true });
  jarvisTabId = tab.id;
}

chrome.runtime.onStartup.addListener(openOrFocusJarvis);
chrome.runtime.onInstalled.addListener(openOrFocusJarvis);
chrome.action.onClicked.addListener(openOrFocusJarvis);

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === jarvisTabId) jarvisTabId = null;
});

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "JARVIS_PAGE_CONTEXT") {
    getActiveTab().then((tab) => {
      if (!tab?.id || tab.url?.startsWith(JARVIS_URL)) {
        sendResponse({ pageContext: null });
        return;
      }
      chrome.tabs.sendMessage(tab.id, { type: "JARVIS_CAPTURE_PAGE" }, (response) => {
        sendResponse({ pageContext: response || null });
      });
    });
    return true;
  }

  if (message?.type === "JARVIS_OPEN_URL" && message.url) {
    chrome.tabs.create({ url: message.url });
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === "JARVIS_GET_ACTIVE_TAB") {
    getActiveTab().then((tab) => {
      if (!tab || tab.url?.startsWith(JARVIS_URL)) {
        sendResponse({ tab: null });
        return;
      }
      sendResponse({ tab: { url: tab.url, title: tab.title, id: tab.id } });
    });
    return true;
  }

  if (message?.type === "JARVIS_ASSISTANT_REQUEST") {
    fetch(`${JARVIS_URL}/api/assistant`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload || {})
    })
      .then((res) => res.json())
      .then((payload) => sendResponse({ payload }))
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }
});