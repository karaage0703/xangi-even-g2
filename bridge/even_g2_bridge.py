#!/usr/bin/env python3
"""Even Realities G2 <-> xangi bridge.

Even Hub の "Add Agent"（Name / URL / Token）から OpenAI 互換 POST を受けて、
xangi の Web Chat API (/api/chat, SSE) に橋渡しし、G2 の表示制約に整形して返す。

G2 / Even Hub 側の契約（reverse-eng + 先行ブリッジ実装より）:
  - POST <root> に `{ "model": "...", "messages": [{role, content}, ...] }`
  - Authorization: Bearer <token>
  - レスポンスは OpenAI chat.completion 形式（content がメガネに表示される）
  - 表示は ~400 字 / プレーンテキストのみ（Markdown 不可）/ タイムアウト ~30 秒

依存なし（Python 標準ライブラリのみ）。設定はすべて環境変数。
  EVEN_BRIDGE_TOKEN   受け付ける Bearer トークン（未設定なら認証スキップ・ローカル用）
  EVEN_BRIDGE_PORT    待受ポート（既定 8791）
  EVEN_BRIDGE_HOST    待受アドレス（既定 0.0.0.0）
  XANGI_BASE_URL      橋渡し先 xangi Web Chat（既定 http://127.0.0.1:3100）
  EVEN_MAX_CHARS      返答の最大文字数（既定 400）
  EVEN_DEADLINE_SEC   xangi 応答待ちの締切秒（既定 22、G2 の 30 秒より内側）
  EVEN_SESSION_FILE   OpenAI互換 root endpoint の会話継続用セッションID保存ファイル
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("EVEN_BRIDGE_TOKEN", "").strip()
PORT = int(os.environ.get("EVEN_BRIDGE_PORT", "8791"))
HOST = os.environ.get("EVEN_BRIDGE_HOST", "0.0.0.0")
XANGI_BASE_URL = os.environ.get("XANGI_BASE_URL", "http://127.0.0.1:3100").rstrip("/")
MAX_CHARS = int(os.environ.get("EVEN_MAX_CHARS", "400"))
DEADLINE_SEC = float(os.environ.get("EVEN_DEADLINE_SEC", "22"))
SESSION_FILE = os.environ.get(
    "EVEN_SESSION_FILE", os.path.join(os.path.dirname(__file__), ".session_id")
)
DISCORD_BOT_TOKEN = (
    os.environ.get("DISCORD_BOT_TOKEN", "") or os.environ.get("DISCORD_TOKEN", "")
).strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
DISCORD_DEFAULT_CHANNEL_ID = os.environ.get("DISCORD_DEFAULT_CHANNEL_ID", "").strip()
DISCORD_API_BASE = os.environ.get("DISCORD_API_BASE", "https://discord.com/api/v10").rstrip("/")
EVEN_DISCORD_SPEAKER_NAME = os.environ.get("EVEN_DISCORD_SPEAKER_NAME", "G2 User").strip()

# ---- STT 設定（メガネのマイク音声 -> テキスト）------------------------------
# 既定はローカル Whisper。常駐 STT サーバ（stt_server.py）にまず転送し、不在なら
# transcriber_tool の subprocess にフォールバックする。クラウド STT に替えたいときは
# transcribe_pcm() の中身だけ変えれば、アプリ側の /stt 契約は不変。
# 常駐サーバ URL（stt_server.py）。空文字にすると subprocess 直行。
STT_URL = os.environ.get("EVEN_STT_URL", "http://127.0.0.1:8792/transcribe").strip()
STT_CMD = os.environ.get("EVEN_STT_CMD", "").strip() or (
    shutil.which("transcriber_tool")
    or os.path.expanduser("~/.local/bin/transcriber_tool")
)
STT_MODEL = os.environ.get("EVEN_STT_MODEL", "base")
STT_LANG = os.environ.get("EVEN_STT_LANG", "ja")
STT_TIMEOUT = float(os.environ.get("EVEN_STT_TIMEOUT", "60"))
STT_RATE = int(os.environ.get("EVEN_STT_RATE", "16000"))  # G2 マイク = 16kHz mono s16le


# ---------------------------------------------------------------------------
# xangi セッション継続（G2 は会話の連続性を期待するので appSessionId を固定したい）
# ---------------------------------------------------------------------------
def load_session_id() -> str:
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_session_id(sid: str) -> None:
    if not sid:
        return
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(sid)
    except OSError as e:
        print(f"[bridge] WARN: failed to persist session id: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 整形: Markdown 除去 + 改行潰し + 文字数トリム（メガネ表示向け）
# ---------------------------------------------------------------------------
def clean_for_glasses(text: str, max_chars: int = MAX_CHARS) -> str:
    if not text:
        return ""
    t = text
    # コードフェンス / インラインコード
    t = re.sub(r"```[\w-]*\n?", "", t)
    t = t.replace("`", "")
    # 見出し記号・引用・リスト先頭記号
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s{0,3}[-*+]\s+", "・", t, flags=re.MULTILINE)
    # 強調 ** __ * _
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", t)
    # リンク [text](url) -> text、画像 ![..](..) は落とす
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    # 改行は空白に（メガネは横長表示なので段組みを崩す）
    t = re.sub(r"\n{2,}", " / ", t)
    t = t.replace("\n", " ")
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    if len(t) > max_chars:
        t = t[: max_chars - 1].rstrip() + "…"
    return t


# ---------------------------------------------------------------------------
# xangi /api/chat (SSE) を叩いて最終 done.response を取り出す
# ---------------------------------------------------------------------------
def ask_xangi(message: str, deadline: float) -> str:
    sid = load_session_id()
    payload = {"message": message}
    if sid:
        payload["appSessionId"] = sid
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{XANGI_BASE_URL}/api/chat",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    remaining = max(1.0, deadline - time.monotonic())
    final_text = ""
    last_partial = ""
    cur_event = ""
    with urllib.request.urlopen(req, timeout=remaining) as resp:
        for raw in resp:
            if time.monotonic() > deadline:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if line.startswith("event:"):
                cur_event = line[6:].strip()
                continue
            if line.startswith("data:"):
                body = line[5:].strip()
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                if cur_event == "text" and isinstance(obj.get("fullText"), str):
                    last_partial = obj["fullText"]
                elif cur_event == "done":
                    final_text = obj.get("response") or last_partial
                    sid_new = obj.get("sessionId")
                    if sid_new:
                        save_session_id(str(sid_new))
                    break
                elif cur_event == "error":
                    raise RuntimeError(obj.get("message", "xangi error"))
    # done に届かず締切で抜けた場合は途中までのテキストを返す
    return final_text or last_partial


# xangi 側が「最終テキスト空」のとき返すフォールバック文の断片。
# xangi の新規 web セッション初回ターンはこれを返しがちなので検知してリトライする。
_FALLBACK_MARKERS = (
    "うまく応答を組み立てられなかった",
    "応答が空でした",
    "質問をシンプルにして",
)


def looks_like_fallback(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return any(m in t for m in _FALLBACK_MARKERS)


def ask_xangi_with_retry(message: str, deadline: float) -> str:
    """1 回目がフォールバック/空で、締切に余裕があれば 1 度だけ再試行する。"""
    answer = ask_xangi(message, deadline)
    if looks_like_fallback(answer) and (deadline - time.monotonic()) > 6.0:
        print("[bridge] fallback detected, retrying once", file=sys.stderr)
        retry = ask_xangi(message, deadline)
        if not looks_like_fallback(retry):
            return retry
    return answer


def request_json(method: str, path: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{XANGI_BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def clean_session_message_content(content: object, max_chars: int = 120) -> str:
    if isinstance(content, dict):
        result = content.get("result")
        content = result if isinstance(result, str) else json.dumps(content, ensure_ascii=False)
    text = str(content or "")
    lines = []
    skip_rest = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[チャンネルルール"):
            skip_rest = True
        if skip_rest:
            continue
        if stripped.startswith("[runtime]"):
            continue
        if stripped.startswith("[プラットフォーム:"):
            continue
        if stripped.startswith("[チャンネル:"):
            continue
        if stripped.startswith("[発言者:"):
            continue
        if stripped.startswith("[現在時刻:"):
            continue
        lines.append(line)
    return clean_for_glasses("\n".join(lines), max_chars=max_chars)


def session_detail(session_id: str) -> dict:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    return request_json(
        "GET",
        f"/api/sessions/{urllib.parse.quote(sid, safe='')}",
        None,
        timeout=2.0,
    )


def session_latest_message(session_id: str) -> tuple[str, str]:
    try:
        detail = session_detail(session_id)
    except Exception as e:
        print(f"[bridge] WARN: session detail failed for {session_id}: {e}", file=sys.stderr)
        return "", ""
    messages = detail.get("messages", []) if isinstance(detail, dict) else []
    if not isinstance(messages, list):
        return "", ""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        text = clean_session_message_content(msg.get("content"), max_chars=120)
        if text:
            return role, text
    return "", ""


def terminal_session_detail(session_id: str, limit: int = 20) -> dict:
    detail = session_detail(session_id)
    messages = detail.get("messages", []) if isinstance(detail, dict) else []
    if not isinstance(messages, list):
        messages = []
    safe_limit = max(1, min(50, int(limit or 20)))
    cleaned = []
    for msg in messages[-safe_limit:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        text = clean_session_message_content(msg.get("content"), max_chars=1800)
        if not text:
            continue
        cleaned.append(
            {
                "id": str(msg.get("id") or ""),
                "role": role,
                "content": text,
                "createdAt": str(msg.get("createdAt") or ""),
            }
        )
    return {
        "id": str(detail.get("id") or session_id),
        "title": clean_for_glasses(str(detail.get("title") or session_id), max_chars=80),
        "platform": str(detail.get("platform") or ""),
        "messages": cleaned,
    }


def remaining_seconds(timeout_at: object) -> int:
    try:
        target = int(float(str(timeout_at or "0")))
    except ValueError:
        return 0
    if target <= 0:
        return 0
    return max(0, int(round((target - time.time() * 1000) / 1000)))


def create_terminal_session(title: str) -> dict:
    created = request_json("POST", "/api/sessions", {})
    session_id = str(created.get("sessionId") or "")
    if not session_id:
        raise RuntimeError("xangi sessionId missing")
    request_json(
        "PATCH",
        f"/api/sessions/{urllib.parse.quote(session_id, safe='')}",
        {"title": title or "Even G2 Terminal"},
    )
    thread_id = f"web:{session_id}"
    return {
        "session_id": session_id,
        "thread_id": thread_id,
        "events_url": f"/terminal/events?thread_id={urllib.parse.quote(thread_id, safe='')}",
        "inbox_url": "/terminal/inbox",
    }


def terminal_session_from_id(session_id: str) -> dict:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    thread_id = f"web:{sid}"
    return {
        "session_id": sid,
        "thread_id": thread_id,
        "events_url": f"/terminal/events?thread_id={urllib.parse.quote(thread_id, safe='')}",
        "inbox_url": "/terminal/inbox",
    }


def list_terminal_sessions(limit: int = 10) -> dict:
    data = request_json("GET", "/api/sessions", None, timeout=5.0)
    sessions = data.get("sessions", []) if isinstance(data, dict) else []
    safe_limit = max(1, min(20, int(limit or 10)))
    candidates = []
    for s in sessions:
        if not isinstance(s, dict):
            continue
        platform = str(s.get("platform") or "")
        # G2 から操作できる主対象は web session だが、作業監視用途では
        # Discord/Slack の進行状態も見たいので一覧には含める。
        if platform not in ("web", "discord", "slack"):
            continue
        sid = str(s.get("id") or "")
        title = clean_for_glasses(str(s.get("title") or sid), max_chars=80)
        if not sid:
            continue
        timeout_at = s.get("timeoutAt")
        candidates.append(
            {
                "id": sid,
                "title": title or sid,
                "platform": platform,
                "contextKey": str(s.get("contextKey") or ""),
                "updatedAt": str(s.get("updatedAt") or ""),
                "messageCount": int(s.get("messageCount") or 0),
                "status": "busy" if s.get("isActive") else "idle",
                "isActive": bool(s.get("isActive")),
                "timeoutAt": str(timeout_at or ""),
                "timeoutMs": int(s.get("timeoutMs") or 0),
                "remainingSec": remaining_seconds(timeout_at),
                "lastRole": "",
                "lastMessage": "",
            }
        )
    candidates.sort(key=session_sort_key, reverse=True)
    out = candidates[:safe_limit]
    for item in out:
        last_role, last_message = session_latest_message(item["id"])
        item["lastRole"] = last_role
        item["lastMessage"] = last_message
    return {
        "sessions": out,
        "new_session": {"id": "__new__", "title": "+ New Session"},
    }


def session_sort_key(item: dict) -> tuple[int, str, int]:
    platform_priority = 2 if item.get("platform") in ("discord", "slack") else 1
    return (
        platform_priority,
        str(item.get("updatedAt") or ""),
        1 if item.get("isActive") else 0,
    )


def terminal_session_summary(session_id: str) -> dict:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    data = request_json("GET", "/api/sessions", None, timeout=5.0)
    sessions = data.get("sessions", []) if isinstance(data, dict) else []
    if not isinstance(sessions, list):
        sessions = []
    for s in sessions:
        if isinstance(s, dict) and str(s.get("id") or "") == sid:
            return s
    # /api/sessions/:id does not currently include contextKey, but it still lets
    # callers distinguish missing sessions from transient list failures.
    detail = session_detail(sid)
    if isinstance(detail, dict) and detail.get("id"):
        return detail
    raise ValueError("session not found")


def send_terminal_message(body: dict) -> dict:
    session_id = str(body.get("appSessionId") or body.get("session_id") or "").strip()
    text = str(body.get("text") or "").strip()
    if not session_id:
        raise ValueError("appSessionId is required")
    if not text:
        raise ValueError("text is required")
    payload = {
        "appSessionId": session_id,
        "source": str(body.get("source") or "even-g2"),
        "text": text,
    }
    return request_json("POST", "/api/terminal/inbox", payload, timeout=5.0)


def post_terminal_session_message(body: dict) -> dict:
    session_id = str(body.get("session_id") or body.get("sessionId") or body.get("appSessionId") or "").strip()
    text = str(body.get("text") or body.get("content") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    if not text:
        raise ValueError("text is required")
    summary = terminal_session_summary(session_id)
    platform = str(summary.get("platform") or "web")
    if platform == "discord":
        channel_id = str(summary.get("contextKey") or "").strip()
        if not channel_id:
            raise ValueError("discord channel id missing")
        posted = discord_send_message(channel_id, format_g2_discord_post(text))
        try:
            deadline = time.monotonic() + DEADLINE_SEC
            prompt = (
                "[プラットフォーム: Discord]\n"
                f"[チャンネルID: {channel_id}]\n"
                "[入力元: Even G2 音声投稿]\n"
                f"{text}"
            )
            answer = ask_xangi_with_retry(prompt, deadline)
            cleaned = clean_for_glasses(answer, max_chars=1800) or "(応答が空でした)"
            reply = discord_send_message(channel_id, cleaned, reply_to_message_id=posted.get("id"))
            return {"ok": True, "posted": posted, "reply": reply}
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] WARN: discord reply failed after posting: {e}", file=sys.stderr)
            return {"ok": True, "posted": posted, "reply_error": str(e)}
    if platform == "web":
        return send_terminal_message(
            {
                "appSessionId": session_id,
                "source": str(body.get("source") or "even-g2"),
                "text": text,
            }
        )
    raise ValueError(f"{platform or 'unknown'} session is read-only")


# ---------------------------------------------------------------------------
# Discord Bot API（G2 からチャンネルを読み、確認後に投稿する）
# ---------------------------------------------------------------------------
def discord_request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 10.0,
) -> object:
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is not configured")
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{DISCORD_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "xangi-even-g2-bridge",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Discord HTTP {e.code}: {detail}") from e


def discord_guild_ids() -> list[str]:
    if DISCORD_GUILD_ID:
        return [DISCORD_GUILD_ID]
    guilds = discord_request("GET", "/users/@me/guilds")
    if not isinstance(guilds, list):
        return []
    return [str(g.get("id")) for g in guilds if isinstance(g, dict) and g.get("id")]


def discord_channels() -> dict:
    chans: list[dict] = []
    for gid in discord_guild_ids():
        raw_channels = discord_request("GET", f"/guilds/{urllib.parse.quote(gid, safe='')}/channels")
        if not isinstance(raw_channels, list):
            continue
        for ch in raw_channels:
            if not isinstance(ch, dict):
                continue
            if int(ch.get("type", -1)) not in (0, 5):
                continue
            name = str(ch.get("name") or "")
            cid = str(ch.get("id") or "")
            if not name or not cid:
                continue
            chans.append(
                {
                    "id": cid,
                    "name": name,
                    "guild_id": gid,
                    "position": int(ch.get("position") or 0),
                    "parent_id": str(ch.get("parent_id") or ""),
                }
            )
    chans.sort(key=lambda c: (c["guild_id"], c["position"], c["name"]))
    if DISCORD_DEFAULT_CHANNEL_ID:
        chans.sort(key=lambda c: 0 if c["id"] == DISCORD_DEFAULT_CHANNEL_ID else 1)
    return {
        "channels": chans,
        "default_channel_id": DISCORD_DEFAULT_CHANNEL_ID or (chans[0]["id"] if chans else ""),
    }


def discord_messages(channel_id: str, limit: int = 5) -> dict:
    if not re.fullmatch(r"\d{8,25}", channel_id or ""):
        raise ValueError("invalid channel_id")
    safe_limit = max(1, min(10, int(limit or 5)))
    raw_messages = discord_request(
        "GET",
        f"/channels/{urllib.parse.quote(channel_id, safe='')}/messages?limit={safe_limit}",
    )
    if not isinstance(raw_messages, list):
        raw_messages = []
    messages = []
    for msg in reversed(raw_messages):
        if not isinstance(msg, dict):
            continue
        author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
        content = clean_for_glasses(str(msg.get("content") or ""), max_chars=180)
        if not content and msg.get("attachments"):
            content = "(添付ファイル)"
        messages.append(
            {
                "id": str(msg.get("id") or ""),
                "author": str(author.get("global_name") or author.get("username") or "unknown"),
                "content": content or "(本文なし)",
                "timestamp": str(msg.get("timestamp") or ""),
            }
        )
    return {"messages": messages}


def format_g2_discord_post(content: str) -> str:
    name = EVEN_DISCORD_SPEAKER_NAME or "G2"
    return f"{name}: {content}"


def discord_send_message(
    channel_id: str,
    content: str,
    reply_to_message_id: str | None = None,
) -> dict:
    if not re.fullmatch(r"\d{8,25}", channel_id or ""):
        raise ValueError("invalid channel_id")
    text = str(content or "").strip()
    if not text:
        raise ValueError("content is required")
    text = text[:1900]
    body: dict = {"content": text, "allowed_mentions": {"parse": []}}
    if reply_to_message_id:
        body["message_reference"] = {
            "message_id": str(reply_to_message_id),
            "channel_id": channel_id,
            "fail_if_not_exists": False,
        }
    msg = discord_request(
        "POST",
        f"/channels/{urllib.parse.quote(channel_id, safe='')}/messages",
        body,
    )
    if not isinstance(msg, dict):
        return {"ok": True}
    return {
        "ok": True,
        "id": str(msg.get("id") or ""),
        "channel_id": str(msg.get("channel_id") or channel_id),
        "content": str(msg.get("content") or text),
    }


# ---------------------------------------------------------------------------
# OpenAI chat.completion レスポンス組み立て
# ---------------------------------------------------------------------------
def completion_json(content: str, model: str) -> bytes:
    obj = {
        "id": f"evenbridge-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "xangi",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def extract_user_message(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c.strip()
            if isinstance(c, list):  # OpenAI vision-style content parts
                parts = [p.get("text", "") for p in c if isinstance(p, dict)]
                return " ".join(parts).strip()
    return ""


# ---------------------------------------------------------------------------
# STT: 生 PCM (s16le 16kHz mono) を WAV 化してローカル Whisper で文字起こし
# ---------------------------------------------------------------------------
def transcribe_pcm(pcm: bytes) -> str:
    if not pcm:
        return ""
    # 1) 常駐 STT サーバ優先（モデル載せっぱなし、~0.1 秒）
    if STT_URL:
        try:
            req = urllib.request.Request(
                STT_URL, data=pcm, method="POST",
                headers={"Content-Type": "application/octet-stream"},
            )
            with urllib.request.urlopen(req, timeout=STT_TIMEOUT) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            if "error" in obj:
                raise RuntimeError(obj["error"])
            return (obj.get("text") or "").strip()
        except urllib.error.URLError as e:
            print(
                f"[bridge] STT server unreachable ({e}); fallback to subprocess",
                file=sys.stderr,
            )
    # 2) フォールバック: transcriber_tool subprocess（モデル毎回ロード ~3 秒）
    if not STT_CMD or not os.path.exists(STT_CMD):
        raise RuntimeError(
            f"STT コマンドが見つからない (EVEN_STT_CMD={STT_CMD!r})"
        )
    with tempfile.TemporaryDirectory(prefix="even_stt_") as d:
        wav_path = os.path.join(d, "in.wav")
        out_path = os.path.join(d, "out.txt")
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # 16-bit
            w.setframerate(STT_RATE)
            w.writeframes(pcm)
        cmd = [
            STT_CMD, "transcribe", wav_path,
            "--model-size", STT_MODEL,
            "--output", out_path,
            "--language", STT_LANG,
            "--device", "auto",
        ]
        try:
            subprocess.run(
                cmd, timeout=STT_TIMEOUT, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("STT タイムアウト")
        except subprocess.CalledProcessError as e:
            tail = (e.stderr or b"").decode("utf-8", "replace")[-300:]
            raise RuntimeError(f"STT 失敗: {tail}")
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: N802
        sys.stderr.write("[bridge] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Authorization, Content-Type"
        )
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str):
        print(f"[bridge] ERROR {code}: {msg}", file=sys.stderr)
        self._send(code, json.dumps({"error": {"message": msg}}).encode("utf-8"))

    def _authorized(self, allow_query_token: bool = False) -> bool:
        if not TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if allow_query_token:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            given = given or (qs.get("token", [""])[0]).strip()
        if given == TOKEN:
            return True
        self._err(401, "invalid token")
        return False

    def do_OPTIONS(self):  # noqa: N802 — WebView の CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Authorization, Content-Type"
        )
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        # ヘルスチェック
        if path in ("", "/", "/health") or path.endswith("/health"):
            self._send(200, json.dumps({"ok": True, "xangi": XANGI_BASE_URL}).encode())
            return
        if path.endswith("/terminal/events"):
            if not self._authorized(allow_query_token=True):
                return
            self._proxy_terminal_events(parsed)
            return
        if path.endswith("/terminal/sessions"):
            if not self._authorized():
                return
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int((qs.get("limit") or ["10"])[0])
                out = list_terminal_sessions(limit=limit)
            except Exception as e:  # noqa: BLE001
                self._err(502, f"xangi terminal sessions error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return
        if path.endswith("/terminal/session"):
            if not self._authorized():
                return
            qs = urllib.parse.parse_qs(parsed.query)
            session_id = (qs.get("session_id") or qs.get("sessionId") or [""])[0].strip()
            try:
                limit = int((qs.get("limit") or ["20"])[0])
                out = terminal_session_detail(session_id, limit=limit)
            except ValueError as e:
                self._err(400, str(e))
                return
            except Exception as e:  # noqa: BLE001
                self._err(502, f"xangi terminal session detail error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return
        if path.endswith("/discord/channels"):
            if not self._authorized():
                return
            try:
                out = discord_channels()
            except Exception as e:  # noqa: BLE001
                self._err(502, f"discord channels error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return
        if path.endswith("/discord/messages"):
            if not self._authorized():
                return
            qs = urllib.parse.parse_qs(parsed.query)
            channel_id = (qs.get("channel_id") or qs.get("channelId") or [""])[0].strip()
            try:
                limit = int((qs.get("limit") or ["5"])[0])
                out = discord_messages(channel_id, limit=limit)
            except ValueError as e:
                self._err(400, str(e))
                return
            except Exception as e:  # noqa: BLE001
                self._err(502, f"discord messages error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return
        self._err(404, "not found")

    def _proxy_terminal_events(self, parsed: urllib.parse.ParseResult):
        qs = urllib.parse.parse_qs(parsed.query)
        thread_id = (qs.get("thread_id") or qs.get("threadId") or [""])[0].strip()
        query = urllib.parse.urlencode({"thread_id": thread_id}) if thread_id else ""
        upstream = f"{XANGI_BASE_URL}/api/events/stream" + (f"?{query}" if query else "")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with urllib.request.urlopen(upstream, timeout=65) as resp:
                for raw in resp:
                    self.wfile.write(raw)
                    self.wfile.flush()
        except Exception as e:  # noqa: BLE001
            try:
                payload = {
                    "type": "agent.error",
                    "thread_id": thread_id,
                    "message": f"terminal events proxy error: {e}",
                    "ts": int(time.time()),
                }
                self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

    def do_POST(self):  # noqa: N802
        # body は認証より先に必ず読み切る（keep-alive 接続で未読 body が
        # 次リクエストの行として誤パースされるのを防ぐ）
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""

        # 認証
        if not self._authorized():
            return

        # STT エンドポイント: body は生 PCM (s16le 16kHz mono)、応答は {"text": ...}
        if self.path.rstrip("/").endswith("/stt"):
            try:
                text = transcribe_pcm(raw)
            except Exception as e:  # noqa: BLE001
                self._err(500, f"stt error: {e}")
                return
            print(
                f"[bridge] STT {len(raw)}B -> {text[:60]!r}", file=sys.stderr
            )
            self._send(200, json.dumps({"text": text}, ensure_ascii=False).encode())
            return

        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, json.JSONDecodeError):
            self._err(400, "invalid json")
            return

        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if path.endswith("/terminal/session"):
            try:
                existing_id = str(body.get("session_id") or body.get("sessionId") or "").strip()
                out = (
                    terminal_session_from_id(existing_id)
                    if existing_id
                    else create_terminal_session(str(body.get("title") or "Even G2 Terminal"))
                )
            except Exception as e:  # noqa: BLE001
                self._err(502, f"xangi terminal session error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return

        if path.endswith("/terminal/inbox"):
            try:
                out = send_terminal_message(body)
            except ValueError as e:
                self._err(400, str(e))
                return
            except Exception as e:  # noqa: BLE001
                self._err(502, f"xangi terminal inbox error: {e}")
                return
            self._send(202, json.dumps(out, ensure_ascii=False).encode())
            return

        if path.endswith("/terminal/post"):
            try:
                out = post_terminal_session_message(body)
            except ValueError as e:
                self._err(400, str(e))
                return
            except Exception as e:  # noqa: BLE001
                self._err(502, f"terminal post error: {e}")
                return
            self._send(202, json.dumps(out, ensure_ascii=False).encode())
            return

        if path.endswith("/discord/messages"):
            try:
                out = discord_send_message(
                    str(body.get("channel_id") or body.get("channelId") or ""),
                    str(body.get("content") or ""),
                )
            except ValueError as e:
                self._err(400, str(e))
                return
            except Exception as e:  # noqa: BLE001
                self._err(502, f"discord send error: {e}")
                return
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
            return

        user_msg = extract_user_message(body.get("messages", []))
        model = body.get("model", "xangi")
        if not user_msg:
            self._err(400, "no user message")
            return

        deadline = time.monotonic() + DEADLINE_SEC
        try:
            answer = ask_xangi_with_retry(user_msg, deadline)
        except urllib.error.URLError as e:
            self._send(200, completion_json(f"(xangi 接続エラー: {e.reason})", model))
            return
        except Exception as e:  # noqa: BLE001
            self._send(200, completion_json(f"(エラー: {e})", model))
            return

        cleaned = clean_for_glasses(answer) or "(応答が空でした)"
        print(f"[bridge] Q={user_msg[:60]!r} -> A={cleaned[:60]!r}", file=sys.stderr)
        self._send(200, completion_json(cleaned, model))


def prewarm():
    """起動時に xangi セッションを温めておく（初回ターンの 17 秒コールドスタート +
    空応答フォールバックを、ユーザーの最初の質問より前に消化しておく）。"""
    import threading

    def _run():
        try:
            ask_xangi("（接続テスト）準備OKならOKとだけ返して", time.monotonic() + 60.0)
            print("[bridge] prewarm done (session ready)", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] prewarm skipped: {e}", file=sys.stderr)

    threading.Thread(target=_run, daemon=True).start()


def main():
    print(
        f"[bridge] Even G2 <-> xangi bridge listening on {HOST}:{PORT}\n"
        f"          xangi   = {XANGI_BASE_URL}\n"
        f"          discord = {'ON' if DISCORD_BOT_TOKEN else 'OFF'}\n"
        f"          auth    = {'ON' if TOKEN else 'OFF (local only!)'}\n"
        f"          maxchar = {MAX_CHARS}, deadline = {DEADLINE_SEC}s",
        file=sys.stderr,
    )
    if os.environ.get("EVEN_PREWARM", "1") == "1":
        prewarm()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
