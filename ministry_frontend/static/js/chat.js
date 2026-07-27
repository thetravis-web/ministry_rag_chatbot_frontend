/* Chat workspace logic.
   Talks to POST /api/chat â€” currently backed by a mock in app.py that
   returns a canned answer + citations after a short delay, so the whole
   flow is demo-able before the real RAG pipeline (LangChain + ChromaDB +
   Ollama/Phi-4-mini) exists. Swap the mock in app.py for the real call and
   nothing here needs to change, since the request/response shape already
   matches what the RAG Engine class is expected to return. */

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
          (s) =>
            `<button type="button" class="source-chip" data-doc="${s.document}" data-page="${s.page}">${s.document} Â· p.${s.page}</button>`
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
  thinking.innerHTML = "<div class='chat-bubble chat-thinking'>Retrieving relevant documentsâ€¦</div>";
  document.getElementById("chat-thread").appendChild(thinking);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });
    const data = await res.json();
    document.getElementById("chat-thinking")?.remove();
    appendMessage({ sender: "bot", text: data.answer, sources: data.sources });
  } catch (err) {
    document.getElementById("chat-thinking")?.remove();
    appendMessage({ sender: "bot", text: "Something went wrong reaching the knowledge base. Please try again." });
  } finally {
    setSending(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  if (form) form.addEventListener("submit", sendChatMessage);
});
