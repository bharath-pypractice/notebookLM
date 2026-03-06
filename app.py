import os
import uuid
from typing import Dict, Any

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from werkzeug.utils import secure_filename

import requests
# from bs4 import BeautifulSoup  # pyright: ignore[reportMissingModuleSource]

# Load environment variables from .env
load_dotenv()

# Read Gemini API key from environment variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    # We don't crash the app, but will fail later when trying to call the model.
    print("Warning: GEMINI_API_KEY not set. Set it before using /chat.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# Default model can be overridden via env
DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME_DEFAULT", "gemini-2.5-flash")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# In-memory library of sources for this server process.
# Keyed by source_id, each entry contains: id, name, type, text.
sources: Dict[str, Dict[str, Any]] = {}
current_source_id: str | None = None


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    texts = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        texts.append(page_text)
    return "\n\n".join(texts)


def extract_text_from_url(url: str) -> str:
    """Fetch and extract readable text from a web page URL."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())
    # Cap length to keep prompts reasonable.
    return text[:15000]


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    global current_source_id, sources

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in request"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "error": "Only PDF files are supported"}), 400

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)

    try:
        text_content = extract_text_from_pdf(save_path)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read PDF: {e}"}), 500

    source_id = str(uuid.uuid4())
    sources[source_id] = {
        "id": source_id,
        "name": filename,
        "type": "pdf",
        "text": text_content,
    }
    current_source_id = source_id

    return jsonify({"success": True, "filename": filename, "sourceId": source_id})


@app.route("/add_url", methods=["POST"])
def add_url():
    global current_source_id, sources

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    try:
        text_content = extract_text_from_url(url)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    # Use a short label for display purposes.
    display_name = url
    if len(display_name) > 60:
        display_name = display_name[:57] + "..."

    source_id = str(uuid.uuid4())
    sources[source_id] = {
        "id": source_id,
        "name": display_name,
        "type": "url",
        "text": text_content,
    }
    current_source_id = source_id

    return jsonify({"success": True, "name": display_name, "sourceId": source_id})


@app.route("/library", methods=["GET"])
def library():
    """Return lightweight library metadata for the UI."""
    items = []
    for source in sources.values():
        items.append(
            {
                "id": source["id"],
                "name": source["name"],
                "type": source["type"],
            }
        )
    return jsonify({"success": True, "items": items})


@app.route("/chat", methods=["POST"])
def chat():
    global current_source_id, sources

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    requested_model = (data.get("model") or "").strip() or DEFAULT_MODEL_NAME
    source_id = (data.get("sourceId") or "").strip() or current_source_id

    if not question:
        return jsonify({"success": False, "error": "Question is required"}), 400

    if not source_id or source_id not in sources:
        return jsonify(
            {
                "success": False,
                "error": "No source content available. Please upload a document or add a URL first.",
            }
        ), 400

    if not GEMINI_API_KEY:
        return jsonify(
            {
                "success": False,
                "error": "GEMINI_API_KEY is not configured on the server.",
            }
        ), 500

    source = sources[source_id]
    context_text = source.get("text", "")

    try:
        model = genai.GenerativeModel(requested_model)
        prompt = (
            "You are an AI research assistant that answers questions based solely on the "
            "provided source content.\n\n"
            f"Source type: {source.get('type', 'unknown')}\n"
            f"Source name: {source.get('name', 'Untitled')}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            "Answer clearly and concisely. If the answer is not in the context, say "
            "\"I'm not sure based on the provided source.\""
        )
        response = model.generate_content(prompt)
        answer = getattr(response, "text", "").strip() or "No response generated."
    except Exception as e:
        return jsonify({"success": False, "error": f"Model error: {e}"}), 500

    return jsonify({"success": True, "answer": answer})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)

