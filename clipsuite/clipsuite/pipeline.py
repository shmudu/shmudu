"""End-to-end: source -> transcript -> picked clips -> rendered shorts -> hand-off exports."""

from __future__ import annotations

import re
import traceback
from pathlib import Path
from typing import Any, Callable

from . import chatcut, download, highlights, render, resolve, transcribe, wan2gp
from .util import read_json, write_json


def set_status(job: Path, status: str, **extra: Any) -> None:
    meta = read_json(job / "job.json", {})
    meta.update(status=status, **extra)
    write_json(job / "job.json", meta)


def ingest(source: str) -> Path:
    if re.match(r"https?://", source):
        return download.download(source)
    return download.import_file(Path(source))


def process(job: Path, opts: dict[str, Any] | None = None, log: Callable[[str], None] = print) -> Path:
    opts = opts or {}
    try:
        set_status(job, "transcribing")
        transcribe.transcribe(job, backend=opts.get("backend", "auto"), model=opts.get("model"),
                              language=opts.get("language"))
        set_status(job, "picking")
        clips = highlights.pick(job, picker=opts.get("picker", "auto"), count=int(opts.get("count", 5)),
                                min_len=float(opts.get("min_len", 20)), max_len=float(opts.get("max_len", 60)),
                                guidance=opts.get("guidance", ""))
        log(f"Picked {len(clips)} clips")
        set_status(job, "rendering")
        render.render_all(job, defaults=opts.get("style"))
        set_status(job, "exporting")
        resolve.export_fcpxml(job)
        chatcut.export(job, max_len=int(float(opts.get("max_len", 60))))
        wan2gp.write_prompts(job)
        set_status(job, "done", error=None)
    except Exception as e:  # keep the error visible in the UI
        set_status(job, "error", error=f"{e}\n{traceback.format_exc(limit=3)}")
        raise
    return job
