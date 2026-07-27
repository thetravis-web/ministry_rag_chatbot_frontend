let activeSessionId = null;

function appendMessage({ sender, text, sources }) {
  const thread = document.getElementById("chat-thread");
  const wrap = document.createElement("div");
  wrap.className = "chat-msg " + (sender === "user" ? "chat-msg-user" : "chat-msg-bot");

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);

  if (sources && sources.length) {
    const src = document.createElement("div");
    src.className = "chat-sources";
    src.innerHTML =
      "<span class='chat-sources-label'>Sources:</span> " +
      sources
        .map(
          (source) =>
            `<button type="button" class="source-chip" data-document-id="${source.document_id || ""}" data-page="${source.page}">${source.document} - p.${source.page}</button>`
        )
        .join(" ");
    wrap.appendChild(src);
  }

  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
}

function setSending(isSending) {
  const btn = document.getElementById("chat-send-btn");
  const input = document.getElementById("chat-input");
  if (btn) btn.disabled = isSending;
  if (input) input.disabled = isSending;
}

async function sendChatMessage(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;

  appendMessage({ sender: "user", text });
  input.value = "";
  setSending(true);

  const thinking = document.createElement("div");
  thinking.className = "chat-msg chat-msg-bot";
  thinking.id = "chat-thinking";
  thinking.innerHTML = "<div class='chat-bubble chat-thinking'>Retrieving relevant documents...</div>";
  document.getElementById("chat-thread").appendChild(thinking);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, session_id: activeSessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Chat request failed");
    activeSessionId = data.session_id || activeSessionId;
    document.getElementById("chat-thinking")?.remove();
    appendMessage({ sender: "bot", text: data.answer, sources: data.sources });
  } catch (err) {
    document.getElementById("chat-thinking")?.remove();
    appendMessage({ sender: "bot", text: err.message || "Something went wrong reaching the knowledge base. Please try again." });
  } finally {
    setSending(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  if (form) form.addEventListener("submit", sendChatMessage);

  const newChatBtn = document.getElementById("new-chat-btn");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
      activeSessionId = null;
      const thread = document.getElementById("chat-thread");
      thread.querySelectorAll(".chat-msg:not(:first-child)").forEach((node) => node.remove());
      document.getElementById("chat-input")?.focus();
      showToast("New chat started");
    });
  }

  document.addEventListener("click", (event) => {
    const chip = event.target.closest(".source-chip");
    if (!chip) return;
    const documentId = chip.getAttribute("data-document-id");
    if (documentId) window.open(`/documents/${documentId}`, "_blank", "noopener");
  });
});
