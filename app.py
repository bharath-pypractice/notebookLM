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
            text = page.extract_text() or ""
        except:
            text = ""

        texts.append(text)

    return "\n".join(texts)


# -----------------------------
# URL TEXT EXTRACTION
# -----------------------------

def extract_text_from_url(url):

    response = requests.get(url, timeout=15)
    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text().split())

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
        return jsonify({"success": False}), 400

    file = request.files["file"]

    filename = secure_filename(file.filename)

    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(path)

    text = extract_text_from_pdf(path)

    source_id = str(uuid.uuid4())

    sources[source_id] = {
        "id": source_id,
        "name": filename,
        "text": text
    }

    current_source_id = source_id

    return jsonify({
        "success": True,
        "sourceId": source_id,
        "filename": filename
    })


# -----------------------------
# ADD URL
# -----------------------------

@app.route("/add_url", methods=["POST"])
def add_url():

    global current_source_id

    data = request.get_json()

    url = data.get("url")

    text = extract_text_from_url(url)

    source_id = str(uuid.uuid4())

    sources[source_id] = {
        "id": source_id,
        "name": url,
        "text": text
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

    for s in sources.values():

        items.append({
            "id": s["id"],
            "name": s["name"]
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

    if not source_id or source_id not in sources:
        return jsonify({
            "success": False,
            "error": "Upload document first"
        }), 400

    context = sources[source_id]["text"][:8000]

    model = genai.GenerativeModel(DEFAULT_MODEL_NAME)

    prompt = f"""
Answer using only the provided context.

Context:
{context}

Question:
{question}

If not found say:
"I'm not sure based on the provided document."
"""

    try:
        response = model.generate_content(prompt)

        answer = getattr(response, "text", None)

        if not answer:
            answer = "No response generated."

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