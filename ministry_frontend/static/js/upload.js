/* Upload Documents logic — drag & drop + queue rendering.
   Posts to POST /api/upload (multipart/form-data). The mock backend in
   app.py accepts the file, fakes a short "processing" delay representing
   loader -> chunk -> embed -> store, and returns a status the UI reflects.
   This matches the Sequence Diagram 2 (ingestion flow) steps 1-8. */

function humanFileSize(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i++;
  }
  return `${bytes.toFixed(1)} ${units[i]}`;
}

function queueRow(file) {
  const row = document.createElement("div");
  row.className = "upload-row";
  row.innerHTML = `
    <div class="upload-row-main">
      <span class="material-symbols-outlined upload-row-icon">description</span>
      <div>
        <div class="upload-row-name">${file.name}</div>
        <div class="upload-row-meta">${humanFileSize(file.size)} · queued</div>
      </div>
    </div>
    <div class="upload-row-progress"><div class="upload-row-progress-bar" style="width:0%"></div></div>
  `;
  return row;
}

async function handleFiles(fileList) {
  const queue = document.getElementById("upload-queue");
  const category = document.getElementById("upload-category")?.value || "Uncategorized";

  for (const file of fileList) {
    const row = queueRow(file);
    queue.prepend(row);
    const bar = row.querySelector(".upload-row-progress-bar");
    const meta = row.querySelector(".upload-row-meta");

    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", category);

    let pct = 0;
    const tick = setInterval(() => {
      pct = Math.min(pct + 12, 90);
      bar.style.width = pct + "%";
    }, 180);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      clearInterval(tick);
      bar.style.width = "100%";
      meta.textContent = `${humanFileSize(file.size)} · ${data.status} · ${data.chunks} chunks embedded`;
      showToast(`${file.name} uploaded and indexed`);
    } catch (e) {
      clearInterval(tick);
      meta.textContent = `${humanFileSize(file.size)} · failed`;
      row.classList.add("upload-row-error");
      showToast(`${file.name} failed to upload`, "error");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  if (!dropzone) return;

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dropzone-active");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dropzone-active");
    })
  );
  dropzone.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));
});
