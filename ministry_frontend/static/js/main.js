/* Shared frontend logic — Ministry Offline RAG Chatbot
   Design note: the original Stitch export used AI-generated fictional
   "staff photos" as avatar placeholders. We replace those everywhere with
   deterministic initials avatars, which (a) needs no photo consent from
   real staff, (b) needs no external images, and (c) looks intentional
   rather than like a stand-in. */

const AVATAR_PALETTE = ["#001f40", "#0a3a6b", "#b3730a", "#1e7f4f", "#7a3b8f", "#c81e3a"];

function initialsFromName(name) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

function colorForName(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length];
}

function renderAvatars() {
  document.querySelectorAll("[data-avatar-name]").forEach((el) => {
    const name = el.getAttribute("data-avatar-name") || "?";
    el.textContent = initialsFromName(name);
    el.style.background = colorForName(name);
  });
}

function showToast(message, kind = "info") {
  let toast = document.getElementById("app-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "app-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove("show"), 3200);
}

document.addEventListener("DOMContentLoaded", renderAvatars);
