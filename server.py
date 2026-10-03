#!/usr/bin/env python3
"""
Video Downloader — localhost backend (127.0.0.1:8080)
Sirf tumhare apne device par chalta hai. Requires: yt-dlp (+ ffmpeg for MP3).
Run:  python3 server.py
Phir browser me kholo: http://localhost:8080
"""
import json
import os
import re
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "127.0.0.1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(os.path.dirname(BASE_DIR), "index.html")
DL_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DL_DIR, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()


def safe_name(s, maxlen=80):
    s = re.sub(r"[^\w\s\-.]", "_", s or "video", flags=re.UNICODE).strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:maxlen] or "video")


def ydl_opts(extra=None):
    o = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        # YouTube datacenter-IP restriction workaround: multiple player clients
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
    }
    if extra:
        o.update(extra)
    return o


def fetch_info(url):
    from yt_dlp import YoutubeDL
    with YoutubeDL(ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    fmts = []
    seen = set()
    for f in (info.get("formats") or []):
        if not f.get("url"):
            continue
        if f.get("vcodec") in (None, "none"):
            continue  # audio-only yahan nahi
        h = f.get("height") or 0
        ext = f.get("ext") or "mp4"
        key = (h, ext)
        if h and key in seen:
            continue
        if h:
            seen.add(key)
        size = f.get("filesize") or f.get("filesize_approx")
        fmts.append({
            "format_id": f["format_id"],
            "ext": ext,
            "quality": f"{h}p" if h else (f.get("format_note") or ext),
            "size": size,
        })
    def hkey(x):
        q = x["quality"]
        return int(q[:-1]) if q[:-1].isdigit() else 0
    fmts.sort(key=hkey, reverse=True)
    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "webpage_url": info.get("webpage_url"),
        "formats": fmts[:12],
    }


def download_job(job_id, url, format_id, want_mp3):
    try:
        from yt_dlp import YoutubeDL
        outtmpl = os.path.join(DL_DIR, f"{job_id}.%(ext)s")

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes", 0)
                pct = round(done * 100 / total, 1) if total else None
                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["progress"] = pct

        opts = ydl_opts({"outtmpl": outtmpl, "progress_hooks": [hook]})
        if want_mp3:
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            opts["format"] = format_id or "best"
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "video"
        found = None
        for fn in os.listdir(DL_DIR):
            if fn.startswith(job_id + "."):
                found = fn
                break
        with jobs_lock:
            if found:
                final = safe_name(title) + os.path.splitext(found)[1]
                os.rename(os.path.join(DL_DIR, found), os.path.join(DL_DIR, final))
                jobs[job_id].update(status="done", filename=final, progress=100)
            else:
                jobs[job_id].update(status="error", error="File download nahi ho payi")
    except Exception as e:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id].update(status="error", error=str(e)[:300])


def parse_subs(path):
    """VTT/SRT se saaf text nikaalo (timestamps/tags hatao, repeat lines hatao)."""
    lines = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line == "WEBVTT":
                continue
            if "-->" in line:
                continue
            if line.startswith(("NOTE", "STYLE", "REGION", "Kind:", "Language:")):
                continue
            line = re.sub(r"<[^>]+>", "", line)
            line = re.sub(r"\s+", " ", line).strip()
            if line and (not lines or lines[-1] != line):
                lines.append(line)
    return "\n".join(lines)


def fetch_transcript(url):
    """Video ke captions/subtitles se transcript nikaalo. Returns dict."""
    from yt_dlp import YoutubeDL
    import tempfile
    import glob as globmod

    with YoutubeDL(ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    def pick(cands):
        for want in ("en", "hi"):
            for k in cands:
                if k == want or k.startswith(want + "-") or k.startswith(want + "."):
                    return k
        for k in cands:
            return k
        return None

    lang = pick(subs)
    kind = "captions"
    if not lang:
        lang = pick(auto)
        kind = "auto-captions"
    if not lang:
        return {"error": "Is video me captions/transcript nahi mila. Kuch videos me captions hote hi nahi."}

    tmpdir = tempfile.mkdtemp(prefix="trans_")
    try:
        opts = ydl_opts({
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmpdir, "t.%(ext)s"),
        })
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        subfile = None
        for f in globmod.glob(os.path.join(tmpdir, "t.*")):
            if f.endswith((".vtt", ".srt")):
                subfile = f
                break
        if not subfile:
            return {"error": "Transcript download nahi ho paya"}
        text = parse_subs(subfile)
        if not text.strip():
            return {"error": "Transcript khaali mila"}
        return {"ok": True, "text": text, "lang": lang, "kind": kind,
                "title": info.get("title")}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "VD/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._serve_index()
        elif path == "/api/ping":
            self._json({"ok": True})
        elif path == "/api/info":
            url = (qs.get("url") or [""])[0].strip()
            if not url:
                return self._json({"error": "URL khaali hai"}, 400)
            try:
                self._json({"ok": True, "info": fetch_info(url)})
            except Exception as e:
                self._json({"error": str(e)[:300]}, 500)
        elif path == "/api/transcript":
            url = (qs.get("url") or [""])[0].strip()
            if not url:
                return self._json({"error": "URL khaali hai"}, 400)
            try:
                res = fetch_transcript(url)
                if res.get("ok"):
                    self._json({"ok": True, "transcript": res})
                else:
                    self._json({"error": res.get("error", "Transcript nahi mila")}, 404)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 500)
        elif path == "/api/job":
            jid = (qs.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(jid)
            if not job:
                return self._json({"error": "Job nahi mila"}, 404)
            self._json({"ok": True, "job": {k: v for k, v in job.items() if k != "filename"} |
                        ({"filename": job["filename"]} if job.get("status") == "done" else {})})
        elif path == "/api/file":
            jid = (qs.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(jid)
            if not job or job.get("status") != "done":
                return self._json({"error": "File taiyaar nahi"}, 404)
            fpath = os.path.join(DL_DIR, job["filename"])
            if not os.path.isfile(fpath):
                return self._json({"error": "File nahi mili"}, 404)
            fsize = os.path.getsize(fpath)
            self.send_response(200)
            self._cors()
            ctype = "audio/mpeg" if fpath.endswith(".mp3") else "video/mp4"
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(fsize))
            self.send_header("Content-Disposition",
                             f'attachment; filename="{job["filename"]}"')
            self.end_headers()
            with open(fpath, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile)
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/job":
            return self._json({"error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "Galat request"}, 400)
        url = (data.get("url") or "").strip()
        if not url:
            return self._json({"error": "URL khaali hai"}, 400)
        jid = uuid.uuid4().hex[:12]
        with jobs_lock:
            jobs[jid] = {"status": "running", "progress": None,
                         "url": url, "started": time.time()}
        t = threading.Thread(target=download_job,
                             args=(jid, url, data.get("format_id"),
                                   bool(data.get("mp3"))),
                             daemon=True)
        t.start()
        self._json({"ok": True, "job_id": jid})

    def _serve_index(self):
        try:
            with open(INDEX_HTML, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            body = b"<h1>index.html nahi mili</h1>"
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # quiet


def cleanup_old():
    now = time.time()
    for fn in os.listdir(DL_DIR):
        fp = os.path.join(DL_DIR, fn)
        try:
            if os.path.isfile(fp) and now - os.path.getmtime(fp) > 24 * 3600:
                os.remove(fp)
        except OSError:
            pass


if __name__ == "__main__":
    cleanup_old()
    try:
        import yt_dlp  # noqa
    except ImportError:
        print("Pehle install karo: pip install yt-dlp")
        raise SystemExit(1)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Video Downloader chal raha hai: http://{HOST}:{PORT}")
    print("Band karne ke liye Ctrl+C dabao")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBand ho gaya.")
