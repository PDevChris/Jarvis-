const JARVIS_CONNECTOR = "http://localhost:8000";

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "JARVIS_PAGE_CONTEXT") {
    getActiveTab().then((tab) => {
      if (!tab?.id) {
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

  if (message?.type === "JARVIS_ASSISTANT_REQUEST") {
    fetch(`${JARVIS_CONNECTOR}/api/assistant`, {
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