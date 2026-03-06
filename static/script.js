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
const micButton = document.getElementById("mic-button");
const themeSelect = document.getElementById("theme-select");
const modelSelect = document.getElementById("model-select");

let hasUploadedPdf = false;
let isSending = false;
let activeSource = null;
let librarySources = [];
let recognition = null;
let isListening = false;
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

function renderSources() {
  sourcesList.innerHTML = "";
  connectedSources.innerHTML = "";

  if (!activeSource || librarySources.length === 0) {
    sessionInsight.textContent = "No active sources. Upload a PDF or add a URL to begin.";
    return;
  }

  librarySources.forEach((source) => {
    const card = document.createElement("div");
    card.className = "source-card";
    if (source.id === activeSource.id) {
      card.classList.add("source-card--active");
    }
    card.dataset.sourceId = source.id;
    card.innerHTML = `
      <div class="source-icon ${source.type === "url" ? "url" : "pdf"}"></div>
      <div class="source-main">
        <div class="source-name">${source.name}</div>
        <div class="source-meta">${source.sizeLabel}</div>
      </div>
      <div class="source-status ${source.status.toLowerCase()}">
        ${source.status}
      </div>
    `;

    card.addEventListener("click", () => {
      activeSource = source;
      renderSources();
      summaryStatus.textContent = "Summary for selected source";
      summaryContent.textContent =
        source.summary ||
        "No stored summary yet for this source. Ask a question and treat the answer as your notes.";
    });

    sourcesList.appendChild(card);
  });

  librarySources.forEach((source) => {
    const chip = document.createElement("li");
    chip.className = "chip";
    chip.textContent = source.name;
    connectedSources.appendChild(chip);
  });

  sessionInsight.textContent = `${librarySources.length} source${
    librarySources.length === 1 ? "" : "s"
  } connected to your notebook. Click any source to focus it.`;
}

async function requestAutoSummary() {
  if (!activeSource) {
    return;
  }

  summaryStatus.textContent = "Summarizing source…";
  summaryContent.textContent = "The assistant is reading your document and preparing a concise summary.";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question:
          "Provide a brief research-style summary of the active source in 4–6 bullet points.",
        model: currentModel,
        sourceId: activeSource.id,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      const message = data && data.error ? data.error : "Failed to summarize source.";
      summaryStatus.textContent = "Summary unavailable";
      summaryContent.textContent = message;
      return;
    }

    summaryStatus.textContent = "Summary ready";
    const text = data.answer || "No summary generated.";
    summaryContent.textContent = text;
    activeSource.summary = text;
  } catch (error) {
    console.error(error);
    summaryStatus.textContent = "Summary error";
    summaryContent.textContent = "There was an issue generating the summary. You can still ask questions in the chat.";
  }
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!pdfInput.files || pdfInput.files.length === 0) {
    uploadStatus.textContent = "Please select a PDF file.";
    uploadStatus.style.color = "#f97373";
    return;
  }

  const file = pdfInput.files[0];
  const formData = new FormData();
  formData.append("file", file);

  uploadStatus.textContent = "Uploading and processing PDF...";
  uploadStatus.style.color = "#9ca3af";

  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      const message = data && data.error ? data.error : "Upload failed.";
      uploadStatus.textContent = message;
      uploadStatus.style.color = "#f97373";
      hasUploadedPdf = false;
      return;
    }

    hasUploadedPdf = true;
    uploadStatus.textContent = `Indexed: ${data.filename}`;
    uploadStatus.style.color = "#4ade80";

    const sizeLabel =
      file.size > 0
        ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
        : "Size unknown";

    const newSource = {
      id: data.sourceId,
      name: data.filename,
      sizeLabel,
      status: "Indexed",
      type: "pdf",
      summary: "",
    };
    librarySources.push(newSource);
    activeSource = newSource;

    renderSources();
    await requestAutoSummary();
  } catch (error) {
    console.error(error);
    uploadStatus.textContent = "Error uploading file. Check console.";
    uploadStatus.style.color = "#f97373";
    hasUploadedPdf = false;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = chatInput.value.trim();
  if (!question) {
    return;
  }

  if (!activeSource) {
    appendMessage("ai", "Please add a PDF or URL source first so I have context.");
    return;
  }

  if (isSending) {
    return;
  }

  isSending = true;
  chatInput.value = "";

  appendMessage("user", question);

  const thinkingRow = document.createElement("div");
  thinkingRow.className = "message-row ai";
  const thinkingBubble = document.createElement("div");
  thinkingBubble.className = "message-bubble";
  thinkingBubble.textContent = "Thinking...";
  thinkingRow.appendChild(thinkingBubble);
  chatWindow.appendChild(thinkingRow);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question, model: currentModel, sourceId: activeSource.id }),
    });

    const data = await response.json();

    thinkingRow.remove();

    if (!response.ok || !data.success) {
      const errorMsg = data && data.error ? data.error : "Something went wrong.";
      appendMessage("ai", `Error: ${errorMsg}`);
      isSending = false;
      return;
    }

    appendMessage("ai", data.answer || "No answer returned.");
  } catch (error) {
    console.error(error);
    thinkingRow.remove();
    appendMessage("ai", "Error calling the server. Check console.");
  } finally {
    isSending = false;
  }
});

pdfInput.addEventListener("change", () => {
  if (!pdfInput.files || pdfInput.files.length === 0) {
    uploadStatus.textContent = "No source connected.";
    uploadStatus.style.color = "#9ca3af";
    hasUploadedPdf = false;
    return;
  }

  const file = pdfInput.files[0];
  uploadStatus.textContent = `Selected: ${file.name}`;
  uploadStatus.style.color = "#9ca3af";
});

if (importUrlBtn) {
  importUrlBtn.addEventListener("click", async () => {
    const url = (urlInput.value || "").trim();
    if (!url) {
      uploadStatus.textContent = "Please enter a URL to import.";
      uploadStatus.style.color = "#f97373";
      return;
    }

    uploadStatus.textContent = "Fetching and indexing URL…";
    uploadStatus.style.color = "#9ca3af";

    try {
      const response = await fetch("/add_url", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        const message = data && data.error ? data.error : "URL import failed.";
        uploadStatus.textContent = message;
        uploadStatus.style.color = "#f97373";
        return;
      }

      uploadStatus.textContent = `Indexed URL: ${data.name}`;
      uploadStatus.style.color = "#4ade80";

      const newSource = {
        id: data.sourceId,
        name: data.name,
        sizeLabel: "URL source",
        status: "Indexed",
        type: "url",
        summary: "",
      };
      librarySources.push(newSource);
      activeSource = newSource;

      renderSources();
      await requestAutoSummary();
    } catch (error) {
      console.error(error);
      uploadStatus.textContent = "Error importing URL. Check console.";
      uploadStatus.style.color = "#f97373";
    }
  });
}

// Voice input (Web Speech API, where available)
if (micButton) {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    micButton.disabled = true;
    micButton.classList.add("icon-button--disabled");
    micButton.title = "Voice input not supported in this browser.";
  } else {
    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.addEventListener("result", (event) => {
      const transcript = event.results[0][0].transcript;
      chatInput.value = transcript;
    });

    recognition.addEventListener("end", () => {
      isListening = false;
      micButton.classList.remove("icon-button--active");
    });

    micButton.addEventListener("click", () => {
      if (isListening) {
        recognition.stop();
        return;
      }

      try {
        recognition.start();
        isListening = true;
        micButton.classList.add("icon-button--active");
      } catch (err) {
        console.error(err);
        appendMessage(
          "ai",
          "Voice input could not start. Make sure the browser supports the microphone on this site (HTTPS is often required)."
        );
      }
    });
  }
}

function applyTheme(theme) {
  if (theme === "light") {
    document.body.classList.add("theme-light");
  } else {
    document.body.classList.remove("theme-light");
  }
}

function initSettings() {
  const storedTheme = window.localStorage.getItem("ra_theme");
  const theme = storedTheme === "light" ? "light" : "dark";
  applyTheme(theme);
  if (themeSelect) {
    themeSelect.value = theme;
    themeSelect.addEventListener("change", () => {
      const value = themeSelect.value === "light" ? "light" : "dark";
      applyTheme(value);
      window.localStorage.setItem("ra_theme", value);
    });
  }

  const storedModel = window.localStorage.getItem("ra_model");
  if (storedModel) {
    currentModel = storedModel;
  }
  if (modelSelect) {
    modelSelect.value = currentModel;
    modelSelect.addEventListener("change", () => {
      currentModel = modelSelect.value;
      window.localStorage.setItem("ra_model", currentModel);
    });
  }
}

initSettings();

