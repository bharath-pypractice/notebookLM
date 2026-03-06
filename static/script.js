const uploadForm = document.getElementById("upload-form");
const pdfInput = document.getElementById("pdf-file");
const uploadStatus = document.getElementById("upload-status");
const sourcesList = document.getElementById("sources-list");
const connectedSources = document.getElementById("connected-sources");
const summaryContent = document.getElementById("summary-content");
const summaryStatus = document.getElementById("summary-status");
const sessionInsight = document.getElementById("session-insight");
const urlInput = document.getElementById("source-url");
const importUrlBtn = document.getElementById("import-url-btn");

const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatWindow = document.getElementById("chat-window");
const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const menuButton = document.getElementById("menu-button");

let activeSource = null;
let librarySources = [];
let isSending = false;

// ⭐ Gemini model
let currentModel = "gemini-2.5-flash";


function appendMessage(sender, text) {

  const row = document.createElement("div");
  row.className = `message-row ${sender}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;

  row.appendChild(bubble);
  chatWindow.appendChild(row);

  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendTyping() {
  const row = document.createElement("div");
  row.className = "message-row ai";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble message-bubble--typing";
  bubble.innerHTML = `<span class="typing-dots" aria-label="AI is typing"><i></i><i></i><i></i></span>`;
  row.appendChild(bubble);
  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return row;
}

function openSidebar() {
  if (!sidebar || !sidebarOverlay) return;
  sidebar.classList.add("sidebar--open");
  sidebarOverlay.classList.add("sidebar-overlay--open");
  sidebarOverlay.setAttribute("aria-hidden", "false");
}

function closeSidebar() {
  if (!sidebar || !sidebarOverlay) return;
  sidebar.classList.remove("sidebar--open");
  sidebarOverlay.classList.remove("sidebar-overlay--open");
  sidebarOverlay.setAttribute("aria-hidden", "true");
}

if (menuButton) {
  menuButton.addEventListener("click", () => {
    if (!sidebar) return;
    if (sidebar.classList.contains("sidebar--open")) closeSidebar();
    else openSidebar();
  });
}

if (sidebarOverlay) {
  sidebarOverlay.addEventListener("click", closeSidebar);
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSidebar();
});


function renderSources() {

  sourcesList.innerHTML = "";
  connectedSources.innerHTML = "";

  librarySources.forEach((source) => {

    const card = document.createElement("div");
    card.className = "source-card";

    if (activeSource && source.id === activeSource.id) {
      card.classList.add("source-card--active");
    }

    card.innerHTML = `
      <div class="source-name">${source.name}</div>
      <div class="source-status">${source.status}</div>
    `;

    card.addEventListener("click", () => {
      activeSource = source;
      renderSources();
    });

    sourcesList.appendChild(card);

    const chip = document.createElement("li");
    chip.className = "chip";
    chip.textContent = source.name;
    connectedSources.appendChild(chip);

  });

  sessionInsight.textContent =
    `${librarySources.length} source(s) connected to your notebook.`;
}


async function requestAutoSummary() {

  if (!activeSource) return;

  summaryStatus.textContent = "Summarizing source...";
  summaryContent.textContent = "Reading document...";

  try {

    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: "Give a short summary in 5 bullet points.",
        model: currentModel,
        sourceId: activeSource.id
      })
    });

    const data = await response.json();

    if (!data.success) {
      summaryStatus.textContent = "Summary error";
      summaryContent.textContent = data.error;
      return;
    }

    summaryStatus.textContent = "Summary ready";
    summaryContent.textContent = data.answer;

  } catch (error) {

    console.error(error);

    summaryStatus.textContent = "Summary error";
    summaryContent.textContent = "Error generating summary.";

  }

}


uploadForm.addEventListener("submit", async (event) => {

  event.preventDefault();

  if (!pdfInput.files.length) {

    uploadStatus.textContent = "Please select a PDF";
    return;

  }

  const file = pdfInput.files[0];

  const formData = new FormData();
  formData.append("file", file);

  uploadStatus.textContent = "Uploading...";

  try {

    const response = await fetch("/upload", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!data.success) {

      uploadStatus.textContent = data.error;
      return;

    }

    uploadStatus.textContent = `Indexed: ${data.filename}`;

    const newSource = {

      id: data.sourceId,
      name: data.filename,
      status: "Indexed",
      type: "pdf"

    };

    librarySources.push(newSource);

    activeSource = newSource;

    renderSources();

    await requestAutoSummary();

  } catch (error) {

    console.error(error);

    uploadStatus.textContent = "Upload failed";

  }

});


chatForm.addEventListener("submit", async (event) => {

  event.preventDefault();

  const question = chatInput.value.trim();

  if (!question) return;

  if (!activeSource) {

    appendMessage("ai", "Upload a source first.");
    return;

  }

  if (isSending) return;

  isSending = true;

  chatInput.value = "";

  appendMessage("user", question);

  const typingRow = appendTyping();

  try {

    const response = await fetch("/chat", {

      method: "POST",

      headers: {
        "Content-Type": "application/json"
      },

      body: JSON.stringify({

        question: question,
        model: currentModel,
        sourceId: activeSource.id

      })

    });

    const data = await response.json();

    typingRow.remove();

    if (!data.success) {

      appendMessage("ai", data.error);
      return;

    }

    appendMessage("ai", data.answer);

  } catch (error) {

    console.error(error);

    typingRow.remove();
    appendMessage("ai", "Server error.");

  }

  isSending = false;

});

// Upload drag & drop visual feedback
const fileLabel = document.querySelector(".file-label");
if (fileLabel) {
  ["dragenter", "dragover"].forEach((evt) => {
    fileLabel.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      fileLabel.classList.add("file-label--drag");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    fileLabel.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      fileLabel.classList.remove("file-label--drag");
    });
  });
}


if (importUrlBtn) {

  importUrlBtn.addEventListener("click", async () => {

    const url = urlInput.value.trim();

    if (!url) return;

    uploadStatus.textContent = "Fetching URL...";

    try {

      const response = await fetch("/add_url", {

        method: "POST",

        headers: {
          "Content-Type": "application/json"
        },

        body: JSON.stringify({ url })

      });

      const data = await response.json();

      if (!data.success) {

        uploadStatus.textContent = data.error;
        return;

      }

      const newSource = {

        id: data.sourceId,
        name: data.name,
        status: "Indexed",
        type: "url"

      };

      librarySources.push(newSource);

      activeSource = newSource;

      renderSources();

      await requestAutoSummary();

    } catch (error) {

      console.error(error);

      uploadStatus.textContent = "URL import failed";

    }

  });

}