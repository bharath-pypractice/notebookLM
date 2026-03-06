import os
import uuid
from typing import Dict, Any

import google.generativeai as genai
from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from werkzeug.utils import secure_filename
import requests
from bs4 import BeautifulSoup


# -----------------------------
# GEMINI CONFIG
# -----------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"


# -----------------------------
# FLASK SETUP
# -----------------------------

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# Vercel only allows temp storage
UPLOAD_FOLDER = "/tmp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# -----------------------------
# MEMORY STORAGE
# -----------------------------

sources: Dict[str, Dict[str, Any]] = {}
current_source_id = None


# -----------------------------
# PDF TEXT EXTRACTION
# -----------------------------

def extract_text_from_pdf(path: str):

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

def extract_text_from_url(url: str):

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())

    return text[:15000]


# -----------------------------
# HOME
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# UPLOAD PDF
# -----------------------------

@app.route("/upload", methods=["POST"])
def upload():

    global current_source_id

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    filename = secure_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "error": "Only PDF allowed"}), 400

    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    text_content = extract_text_from_pdf(path)

    source_id = str(uuid.uuid4())

    sources[source_id] = {
        "id": source_id,
        "name": filename,
        "type": "pdf",
        "text": text_content,
    }

    current_source_id = source_id

    return jsonify({
        "success": True,
        "filename": filename,
        "sourceId": source_id
    })


# -----------------------------
# ADD URL
# -----------------------------

@app.route("/add_url", methods=["POST"])
def add_url():

    global current_source_id

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"success": False, "error": "URL required"}), 400

    text_content = extract_text_from_url(url)

    source_id = str(uuid.uuid4())

    sources[source_id] = {
        "id": source_id,
        "name": url,
        "type": "url",
        "text": text_content
    }

    current_source_id = source_id

    return jsonify({
        "success": True,
        "sourceId": source_id
    })


# -----------------------------
# LIBRARY
# -----------------------------

@app.route("/library")
def library():

    items = []

    for source in sources.values():
        items.append({
            "id": source["id"],
            "name": source["name"],
            "type": source["type"]
        })

    return jsonify({
        "success": True,
        "items": items
    })


# -----------------------------
# CHAT
# -----------------------------

@app.route("/chat", methods=["POST"])
def chat():

    global current_source_id

    data = request.get_json()

    question = data.get("question")
    source_id = data.get("sourceId", current_source_id)

    if not question:
        return jsonify({"success": False, "error": "Question required"}), 400

    if not source_id or source_id not in sources:
        return jsonify({
            "success": False,
            "error": "Upload a document first"
        }), 400

    context_text = sources[source_id]["text"][:8000]

    model = genai.GenerativeModel(DEFAULT_MODEL_NAME)

    prompt = f"""
You are an AI assistant that answers only using the given context.

Context:
{context_text}

Question:
{question}

If the answer is not in the context say:
"I'm not sure based on the provided source."
"""

    try:
        response = model.generate_content(prompt)
        answer = getattr(response, "text", "No response generated")
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    return jsonify({
        "success": True,
        "answer": answer
    })

# -----------------------------
# VERCEL ENTRY
# -----------------------------

app = app