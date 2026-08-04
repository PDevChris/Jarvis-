(function () {
  function getSelectionText() {
    const selection = window.getSelection();
    return selection ? selection.toString().trim() : "";
  }

  function capturePageContext() {
    const title = document.title || "";
    const url = window.location.href || "";
    const selection = getSelectionText();
    const bodyText = (document.body?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 12000);
    const headings = Array.from(document.querySelectorAll("h1, h2, h3")).slice(0, 12).map((node) => node.textContent.trim()).filter(Boolean);

    return {
      title,
      url,
      selection,
      body_text: bodyText,
      headings,
    };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === "JARVIS_CAPTURE_PAGE") {
      sendResponse(capturePageContext());
    }
  });
})();