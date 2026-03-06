import os
import uuid
from typing import Dict, Any

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from werkzeug.utils import secure_filename

import requests
from bs4 import BeautifulSoup


# Load environment variables
load_dotenv()

# Read Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not set.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# Default Gemini model
DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME_DEFAULT", "gemini-1.5-flash")


# Flask app setup
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# In-memory storage
sources: Dict[str, Dict[str, Any]] = {}
current_source_id: str | None = None


# -----------------------------
# PDF TEXT EXTRACTION
# -----------------------------
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


# -----------------------------
# URL TEXT EXTRACTION
# -----------------------------
def extract_text_from_url(url: str) -> str:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())

    return text[:15000]


# -----------------------------
# HOME PAGE
# -----------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# -----------------------------
# PDF UPLOAD
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    global current_source_id, sources

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    filename = secure_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "error": "Only PDF allowed"}), 400

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)

    try:
        text_content = extract_text_from_pdf(save_path)
    except Exception as e:
        return jsonify({"success": False, "error": f"PDF read failed: {e}"}), 500

    source_id = str(uuid.uuid4())

    sources[source_id] = {
        "id": source_id,
        "name": filename,
        "type": "pdf",
        "text": text_content,
    }

    current_source_id = source_id

    return jsonify({"success": True, "filename": filename, "sourceId": source_id})


# -----------------------------
# ADD URL
# -----------------------------
@app.route("/add_url", methods=["POST"])
def add_url():
    global current_source_id, sources

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "URL required"}), 400

    try:
        text_content = extract_text_from_url(url)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

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


# -----------------------------
# LIBRARY
# -----------------------------
@app.route("/library", methods=["GET"])
def library():

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


# -----------------------------
# CHAT WITH GEMINI
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    global current_source_id, sources

    data = request.get_json(silent=True) or {}

    question = (data.get("question") or "").strip()
    requested_model = (data.get("model") or "").strip() or DEFAULT_MODEL_NAME
    source_id = (data.get("sourceId") or "").strip() or current_source_id

    if not question:
        return jsonify({"success": False, "error": "Question required"}), 400

    if not source_id or source_id not in sources:
        return jsonify(
            {
                "success": False,
                "error": "Upload a document or add a URL first.",
            }
        ), 400

    if not GEMINI_API_KEY:
        return jsonify(
            {
                "success": False,
                "error": "GEMINI_API_KEY not configured.",
            }
        ), 500

    source = sources[source_id]
    context_text = source.get("text", "")

    try:

        model = genai.GenerativeModel(requested_model)

        prompt = (
            "You are an AI research assistant that answers only using the given context.\n\n"
            f"Source name: {source.get('name')}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            "If the answer is not in the context say: "
            "'I'm not sure based on the provided source.'"
        )

        response = model.generate_content(prompt)

        answer = getattr(response, "text", "").strip()

        if not answer:
            answer = "No response generated."

    except Exception as e:
        return jsonify({"success": False, "error": f"Model error: {e}"}), 500

    return jsonify({"success": True, "answer": answer})


# -----------------------------
# RUN SERVER
# -----------------------------
app = app