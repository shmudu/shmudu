"""A small web editor (stdlib only) so you can drive ClipSuite from your phone.

Run `clipsuite serve` on the Mac, then open the printed URL on your phone
(same Wi-Fi). Paste a link or upload a video, watch clips render, adjust
in/out points, titles and caption style, and download finished shorts.
"""

from __future__ import annotations

import json
import mimetypes
import re
import secrets
import socket
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import captions, chatcut, download, pipeline, render, resolve, wan2gp
from .util import WORKSPACE, job_dir, list_jobs, read_json, slugify, write_json

WEB = Path(__file__).resolve().parent.parent / "web"
TOKEN = ""
_locks: dict[str, threading.Lock] = {}


def _lock(job_id: str) -> threading.Lock:
    return _locks.setdefault(job_id, threading.Lock())


def _bg(job_id: str, fn, *args) -> None:
    def work():
        with _lock(job_id):
            try:
                fn(*args)
            except Exception as e:
                traceback.print_exc()
                pipeline.set_status(job_dir(job_id), "error", error=str(e))
    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipSuite/0.1"

    # ------------------------------------------------------------------ helpers
    def _authed(self) -> bool:
        if not TOKEN:
            return True
        q = parse_qs(urlparse(self.path).query)
        return self.headers.get("X-Token") == TOKEN or q.get("t", [""])[0] == TOKEN

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, path: Path) -> None:
        if not path.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m and (m.group(1) or m.group(2)):  # iOS Safari needs byte ranges to play video
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if "dl" in parse_qs(urlparse(self.path).query):
            self.send_header("Content-Disposition", f'attachment; filename="{path.parent.name}-{path.name}"')
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
        if not self.path.startswith("/files/"):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------------ routes
    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._file(WEB / "index.html")
        if not self._authed():
            return self._json({"error": "bad token"}, 401)
        if path == "/api/jobs":
            return self._json(list_jobs())
        if m := re.fullmatch(r"/api/jobs/([\w.-]+)", path):
            d = job_dir(m.group(1))
            return self._json({"job": read_json(d / "job.json"), "clips": read_json(d / "clips.json", []),
                               "presets": list(captions.PRESETS)})
        if m := re.fullmatch(r"/files/([\w.-]+)/(.+)", path):
            base = job_dir(m.group(1)).resolve()
            target = (base / m.group(2)).resolve()
            if base not in target.parents:
                return self.send_error(HTTPStatus.FORBIDDEN)
            return self._file(target)
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if not self._authed():
            return self._json({"error": "bad token"}, 401)
        try:
            if path == "/api/jobs":  # {url, ...options}
                body = self._body()
                url = body.get("url", "").strip()
                if not re.match(r"https?://", url):
                    return self._json({"error": "Paste a full http(s) link"}, 400)
                def go():
                    job = download.download(url)
                    pipeline.process(job, body)
                threading.Thread(target=_safe(go), daemon=True).start()
                return self._json({"ok": True, "note": "Downloading; the job appears in the list shortly."})

            if path == "/api/create":  # {script, voice}
                from . import create
                body = self._body()
                try:
                    plan = create.parse_script(str(body.get("script", ""))[:20000])
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                voice = str(body.get("voice", ""))[:40]
                threading.Thread(target=_safe(lambda: create.build(plan, voice=voice)), daemon=True).start()
                return self._json({"ok": True, "note": f"Building \"{plan['title']}\" "
                                   f"({len(plan['scenes'])} scenes). It appears in Jobs in a moment."})

            if path == "/api/upload":  # raw file body, ?name=
                q = parse_qs(urlparse(self.path).query)
                name = slugify(q.get("name", ["upload"])[0].rsplit(".", 1)[0]) + ".mp4"
                n = int(self.headers.get("Content-Length", 0))
                tmp_dir = WORKSPACE / "_uploads"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp = tmp_dir / name
                with tmp.open("wb") as f:
                    while n > 0:
                        chunk = self.rfile.read(min(1 << 20, n))
                        if not chunk:
                            break
                        f.write(chunk)
                        n -= len(chunk)
                job = download.import_file(tmp)
                tmp.unlink(missing_ok=True)
                opts = {k: v[0] for k, v in q.items() if k not in ("name", "t")}
                _bg(job.name, pipeline.process, job, opts)
                return self._json({"ok": True, "job": job.name})

            if m := re.fullmatch(r"/api/jobs/([\w.-]+)/clips/([\w.-]+)", path):  # edit + re-render
                job_id, clip_id = m.groups()
                d = job_dir(job_id)
                body = self._body()
                clips = read_json(d / "clips.json", [])
                clip = next(c for c in clips if c["id"] == clip_id)
                for k in ("start", "end"):
                    if k in body:
                        clip[k] = round(float(body[k]), 3)
                for k in ("title", "hook"):
                    if k in body:
                        clip[k] = str(body[k])[:200]
                if isinstance(body.get("style"), dict):
                    clip["style"] = {**clip.get("style", {}), **body["style"]}
                if clip["end"] <= clip["start"] + 1:
                    return self._json({"error": "Clip must be at least 1 second"}, 400)
                write_json(d / "clips.json", clips)

                def rerender():
                    pipeline.set_status(d, "rendering")
                    render.render_all(d, only=[clip_id])
                    pipeline.set_status(d, "done")
                _bg(job_id, rerender)
                return self._json({"ok": True})

            if m := re.fullmatch(r"/api/jobs/([\w.-]+)/clips", path):  # add a manual clip
                job_id = m.group(1)
                d = job_dir(job_id)
                body = self._body()
                clips = read_json(d / "clips.json", [])
                title = body.get("title") or "Custom clip"
                clip = {"id": f"{len(clips) + 1:02d}-{slugify(title, 32)}", "start": float(body["start"]),
                        "end": float(body["end"]), "title": title, "hook": "", "score": 0, "reason": "manual",
                        "style": {}, "broll_prompts": [], "picker": "manual"}
                clips.append(clip)
                write_json(d / "clips.json", clips)
                _bg(job_id, render.render_all, d, [clip["id"]])
                return self._json({"ok": True, "clip": clip})

            if m := re.fullmatch(r"/api/jobs/([\w.-]+)/export/(resolve|chatcut|wan2gp)", path):
                d = job_dir(m.group(1))
                out = {"resolve": resolve.export_fcpxml, "chatcut": chatcut.export,
                       "wan2gp": wan2gp.write_prompts}[m.group(2)](d)
                return self._json({"ok": True, "file": str(out.relative_to(d))})
        except StopIteration:
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        path = unquote(urlparse(self.path).path)
        if not self._authed():
            return self._json({"error": "bad token"}, 401)
        if m := re.fullmatch(r"/api/jobs/([\w.-]+)/clips/([\w.-]+)", path):
            d = job_dir(m.group(1))
            clips = [c for c in read_json(d / "clips.json", []) if c["id"] != m.group(2)]
            write_json(d / "clips.json", clips)
            return self._json({"ok": True})
        self.send_error(HTTPStatus.NOT_FOUND)


def _safe(fn):
    def inner():
        try:
            fn()
        except Exception:
            traceback.print_exc()
    return inner


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def serve(host: str = "0.0.0.0", port: int = 8765, open_access: bool = False) -> None:
    global TOKEN
    TOKEN = "" if open_access else secrets.token_urlsafe(8)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    suffix = f"/?t={TOKEN}" if TOKEN else "/"
    print(f"ClipSuite editor running.\n  On this Mac:  http://localhost:{port}{suffix}\n"
          f"  On your phone (same Wi-Fi): http://{_lan_ip()}:{port}{suffix}\nCtrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
