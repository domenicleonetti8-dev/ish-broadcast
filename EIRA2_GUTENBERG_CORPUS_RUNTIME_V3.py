from __future__ import annotations

import json, os, shutil, sys, time, urllib.request, zipfile
from pathlib import Path, PurePosixPath

SCHEMA = "eira2_gutenberg_corpus_runtime_v3"
ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
LIB = ROOT / "eira_probe" / "universe_library"
BULK = LIB / "source_vault" / "project_gutenberg" / "bulk"
TEXTS = LIB / "source_vault" / "project_gutenberg" / "texts"
STATE = LIB / "gutenberg_corpus_runtime_v3_state.json"
URL = "https://www.gutenberg.org/cache/epub/feeds/txt-files.tar.zip"
ARCHIVE = BULK / "txt-files.tar.zip"
PART = BULK / "txt-files.tar.zip.part"
UA = "EIRA-Universe-Library/3.0 (+local lawful Project Gutenberg corpus mirror)"
CHUNK = 4 * 1024 * 1024


def atomic(obj):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, STATE)


def stage(status, **extra):
    out = {"schema": SCHEMA, "status": status, "updated_unix": time.time(), "source_is_not_fact": True, **extra}
    atomic(out)
    print(json.dumps(out, sort_keys=True), flush=True)


def safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and not name.startswith(("/", "\\"))


def download():
    BULK.mkdir(parents=True, exist_ok=True)
    start = PART.stat().st_size if PART.exists() else 0
    headers = {"User-Agent": UA, "Accept": "application/zip,application/octet-stream;q=0.9,*/*;q=0.1"}
    if start:
        headers["Range"] = f"bytes={start}-"
    req = urllib.request.Request(URL, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        code = getattr(r, "status", 200)
        if start and code != 206:
            start = 0
            PART.unlink(missing_ok=True)
        mode = "ab" if start and code == 206 else "wb"
        total_header = r.headers.get("Content-Range") or r.headers.get("Content-Length") or ""
        stage("DOWNLOADING", url=URL, resumed_from_bytes=start, response_status=code, remote_size_hint=total_header)
        written = start
        last = time.time()
        with PART.open(mode) as f:
            while True:
                b = r.read(CHUNK)
                if not b:
                    break
                f.write(b)
                written += len(b)
                if time.time() - last >= 10:
                    f.flush(); os.fsync(f.fileno())
                    stage("DOWNLOADING", bytes=written, url=URL)
                    last = time.time()
            f.flush(); os.fsync(f.fileno())
    if PART.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"download_too_small:{PART.stat().st_size}")
    if not zipfile.is_zipfile(PART):
        with PART.open("rb") as f:
            head = f.read(200)
        raise RuntimeError(f"download_not_zip:size={PART.stat().st_size}:head={head!r}")
    os.replace(PART, ARCHIVE)
    stage("DOWNLOAD_COMPLETE", archive=str(ARCHIVE), bytes=ARCHIVE.stat().st_size)


def extract():
    TEXTS.mkdir(parents=True, exist_ok=True)
    extracted = skipped = 0
    with zipfile.ZipFile(ARCHIVE) as z:
        members = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".txt")]
        stage("EXTRACTING", members=len(members), archive_bytes=ARCHIVE.stat().st_size)
        for i, info in enumerate(members, 1):
            if not safe_member(info.filename):
                skipped += 1
                continue
            dest = TEXTS / Path(PurePosixPath(info.filename)).name
            if dest.exists() and dest.stat().st_size == info.file_size:
                skipped += 1
                continue
            tmp = dest.with_name(dest.name + f".tmp.{os.getpid()}")
            with z.open(info) as src, tmp.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
                out.flush(); os.fsync(out.fileno())
            os.replace(tmp, dest)
            extracted += 1
            if i % 1000 == 0:
                stage("EXTRACTING", processed=i, members=len(members), extracted=extracted, skipped=skipped)
    stage("EXTRACT_COMPLETE", extracted=extracted, skipped=skipped, text_files=sum(1 for _ in TEXTS.glob("*.txt")))


def launch_indexer():
    import subprocess
    log = LIB / "gutenberg_index.log"
    cmd = [sys.executable, "-m", "eira2.evidence.gutenberg_document_indexer", "--index"]
    with log.open("ab") as out:
        p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    stage("INDEXER_LAUNCHED", pid=p.pid, log=str(log))
    return p.pid


def main():
    try:
        if not ARCHIVE.exists():
            download()
        elif not zipfile.is_zipfile(ARCHIVE):
            bad = ARCHIVE.with_name(ARCHIVE.name + f".bad_{int(time.time())}")
            os.replace(ARCHIVE, bad)
            stage("BAD_ARCHIVE_QUARANTINED", path=str(bad))
            download()
        else:
            stage("ARCHIVE_VALID", archive=str(ARCHIVE), bytes=ARCHIVE.stat().st_size)
        extract()
        pid = launch_indexer()
        stage("PIPELINE_READY", indexer_pid=pid, archive_bytes=ARCHIVE.stat().st_size, text_files=sum(1 for _ in TEXTS.glob("*.txt")))
        return 0
    except Exception as exc:
        stage("FAILED", error=f"{type(exc).__name__}:{exc}"[:2000])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
