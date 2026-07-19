"""
Quick Translator API Server
Endpoints:
  POST /ocr      - image → text (Tesseract)
  POST /optimize - text → corrected text (Ollama gemma3:4b)
  GET  /health   - service status
"""
import base64
import io
import json
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Quick Translator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ───────────────────────────────────────────────────────
class OCRRequest(BaseModel):
    image_b64: str          # base64 encoded PNG/JPEG
    lang: str = "eng+chi_tra"


class OCRResponse(BaseModel):
    text: str


class OptimizeRequest(BaseModel):
    text: str


class OptimizeResponse(BaseModel):
    corrected: str


# ── Helpers ──────────────────────────────────────────────────────
def _ollama_running() -> bool:
    try:
        s = socket.create_connection(("localhost", 11434), timeout=2)
        s.close()
        return True
    except Exception:
        return False


def _ensure_ollama():
    if _ollama_running():
        return
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if _ollama_running():
            return
        time.sleep(0.5)
    raise RuntimeError("Ollama 啟動逾時")


# ── Routes ───────────────────────────────────────────────────────
@app.get("/health")
def health():
    import shutil
    tess = shutil.which("tesseract") is not None
    oll  = _ollama_running()
    return {
        "status": "ok",
        "tesseract": tess,
        "ollama": oll,
    }


@app.post("/ocr", response_model=OCRResponse)
def ocr(req: OCRRequest):
    try:
        img_bytes = base64.b64decode(req.image_b64)
    except Exception:
        raise HTTPException(400, "invalid base64 image")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(img_bytes)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["tesseract", tmp_path, "stdout", "-l", req.lang, "--psm", "3"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(500, f"Tesseract error: {result.stderr}")
        text = result.stdout.strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return OCRResponse(text=text)


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    if not req.text.strip():
        raise HTTPException(400, "text is empty")

    _ensure_ollama()

    prompt = (
        "Fix any spelling and grammar errors in the following English text. "
        "Return ONLY the corrected text with no explanation, "
        "no quotes, and no extra commentary:\n\n" + req.text
    )

    payload = json.dumps({
        "model": "gemma3:4b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()

    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = json.loads(resp.read())
            corrected = data["message"]["content"].strip()
    except Exception as e:
        raise HTTPException(500, f"Ollama error: {e}")

    return OptimizeResponse(corrected=corrected)
