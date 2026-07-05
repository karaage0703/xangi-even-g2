#!/usr/bin/env python3
"""常駐 Whisper STT サーバ（Even G2 ブリッジ用）。

even_g2_bridge.py の /stt は本サーバに生 PCM を転送するだけ。
本サーバは起動時に Whisper モデルを 1 度だけ GPU に載せ、以後は推論のみ。
リクエストごとの「モデルロード ~3 秒」オフセットを消すための常駐化。

依存: openai-whisper / torch / numpy（transcriber_tool の venv に同梱済み）。
HTTP は標準ライブラリ http.server のみ。

  POST /transcribe   body = 生 PCM (s16le 16kHz mono) -> {"text": "..."}
  GET  /health       -> {"ok": true, "model": "...", "device": "..."}

環境変数:
  EVEN_STT_PORT    待受ポート（既定 8792）
  EVEN_STT_HOST    待受アドレス（既定 127.0.0.1、ローカル転送専用）
  EVEN_STT_MODEL   Whisper モデル（既定 base）
  EVEN_STT_LANG    言語（既定 ja）
  EVEN_STT_RATE    サンプルレート（既定 16000）
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import torch
import whisper

PORT = int(os.environ.get("EVEN_STT_PORT", "8792"))
HOST = os.environ.get("EVEN_STT_HOST", "127.0.0.1")
MODEL_NAME = os.environ.get("EVEN_STT_MODEL", "base")
LANG = os.environ.get("EVEN_STT_LANG", "ja")
RATE = int(os.environ.get("EVEN_STT_RATE", "16000"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_MODEL = None
_LOCK = threading.Lock()  # whisper の推論はスレッドセーフでないので直列化


def load_model():
    global _MODEL
    print(
        f"[stt] loading whisper '{MODEL_NAME}' on {DEVICE} ...", file=sys.stderr
    )
    t0 = time.monotonic()
    _MODEL = whisper.load_model(MODEL_NAME, device=DEVICE)
    print(
        f"[stt] model ready in {time.monotonic() - t0:.1f}s", file=sys.stderr
    )


def transcribe(pcm: bytes) -> str:
    if not pcm or _MODEL is None:
        return ""
    # s16le -> float32 [-1, 1]。長さが奇数バイトなら末尾を切る。
    if len(pcm) % 2:
        pcm = pcm[:-1]
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    with _LOCK:
        result = _MODEL.transcribe(
            audio, language=LANG, fp16=(DEVICE == "cuda")
        )
    return (result.get("text") or "").strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: N802
        sys.stderr.write("[stt] %s\n" % (fmt % args))

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/health"):
            self._send(200, {"ok": _MODEL is not None, "model": MODEL_NAME, "device": DEVICE})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            text = transcribe(raw)
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})
            return
        secs = len(raw) / 2 / RATE if raw else 0
        print(f"[stt] {len(raw)}B (~{secs:.1f}s) -> {text[:60]!r}", file=sys.stderr)
        self._send(200, {"text": text})


def main():
    load_model()
    print(
        f"[stt] listening on {HOST}:{PORT} (model={MODEL_NAME}, device={DEVICE})",
        file=sys.stderr,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
