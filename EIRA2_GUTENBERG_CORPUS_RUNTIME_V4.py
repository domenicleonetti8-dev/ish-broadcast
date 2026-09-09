from __future__ import annotations

import json, os, shutil, subprocess, sys, tarfile, time, urllib.request, zipfile
from pathlib import Path, PurePosixPath

SCHEMA = "eira2_gutenberg_corpus_runtime_v4"
ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
LIB = ROOT / "eira_probe" / "universe_library"
BULK = LIB / "source_vault" / "project_gutenberg" / "bulk"
TEXTS = LIB / "source_vault" / "project_gutenberg" / "texts"
STATE = LIB / "gutenberg_corpus_runtime_v4_state.json"
URL = "https://www.gutenberg.org/cache/epub/feeds/txt-files.tar.zip"
ARCHIVE = BULK / "txt-files.tar.zip"
PART = BULK / "txt-files.tar.zip.part"
UA = "EIRA-Universe-Library/4.0 (+local lawful Project Gutenberg corpus mirror)"
CHUNK = 4 * 1024 * 1024


def atomic(obj):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, STATE)


def stage(status, **extra):
    out = {"schema": SCHEMA, "status": status, "updated_unix": time.time(), "source_is_not_fact": True, **extra}
    atomic(out)
    print(json.dumps(out, sort_keys=True), flush=True)


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and not name.startswith(("/", "\\"))


def target_for(name: str) -> Path:
    base = Path(PurePosixPath(name)).name
    if not base.lower().endswith(".txt"):
        raise ValueError("not_text")
    return TEXTS / base


def write_stream(src, dest: Path, expected_size: int | None = None):
    if dest.exists() and expected_size is not None and dest.stat().st_size == expected_size:
        return False
    tmp = dest.with_name(dest.name + f".tmp.{os.getpid()}")
    with tmp.open("wb") as out:
        shutil.copyfileobj(src, out, length=1024 * 1024)
        out.flush(); os.fsync(out.fileno())
    os.replace(tmp, dest)
    return True


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
        stage("DOWNLOADING", url=URL, resumed_from_bytes=start, response_status=code,
              remote_size_hint=r.headers.get("Content-Range") or r.headers.get("Content-Length") or "")
        written = start; last = time.time()
        with PART.open(mode) as f:
            while True:
                b = r.read(CHUNK)
                if not b:
                    break
                f.write(b); written += len(b)
                if time.time() - last >= 10:
                    f.flush(); os.fsync(f.fileno())
                    stage("DOWNLOADING", bytes=written, url=URL)
                    last = time.time()
            f.flush(); os.fsync(f.fileno())
    if PART.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"download_too_small:{PART.stat().st_size}")
    if not zipfile.is_zipfile(PART):
        with PART.open("rb") as f: head = f.read(200)
        raise RuntimeError(f"download_not_zip:size={PART.stat().st_size}:head={head!r}")
    os.replace(PART, ARCHIVE)
    stage("DOWNLOAD_COMPLETE", archive=str(ARCHIVE), bytes=ARCHIVE.stat().st_size)


def extract_direct_zip(z: zipfile.ZipFile, members):
    extracted = skipped = processed = 0
    for info in members:
        processed += 1
        if not safe_name(info.filename):
            skipped += 1; continue
        dest = target_for(info.filename)
        with z.open(info) as src:
            if write_stream(src, dest, info.file_size): extracted += 1
            else: skipped += 1
        if processed % 1000 == 0:
            stage("EXTRACTING_ZIP_TEXT", processed=processed, members=len(members), extracted=extracted, skipped=skipped)
    return extracted, skipped


def extract_inner_tar(z: zipfile.ZipFile, info: zipfile.ZipInfo):
    extracted = skipped = processed = 0
    stage("INNER_TAR_STREAM_OPEN", member=info.filename, compressed_bytes=info.compress_size, uncompressed_bytes=info.file_size)
    with z.open(info) as inner:
        with tarfile.open(fileobj=inner, mode="r|") as tf:
            for member in tf:
                if not member.isfile() or not member.name.lower().endswith(".txt"):
                    continue
                processed += 1
                if not safe_name(member.name):
                    skipped += 1; continue
                src = tf.extractfile(member)
                if src is None:
                    skipped += 1; continue
                dest = target_for(member.name)
                with src:
                    if write_stream(src, dest, member.size): extracted += 1
                    else: skipped += 1
                if processed % 1000 == 0:
                    stage("EXTRACTING_TAR_TEXT", processed=processed, extracted=extracted, skipped=skipped)
    return extracted, skipped, processed


def extract():
    TEXTS.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as z:
        txt_members = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".txt")]
        tar_members = [i for i in z.infolist() if not i.is_dir() and (i.filename.lower().endswith(".tar") or i.filename.lower().endswith(".tar.gz"))]
        stage("ARCHIVE_LAYOUT", zip_members=len(z.infolist()), direct_txt_members=len(txt_members), tar_members=[i.filename for i in tar_members[:10]])
        if txt_members:
            extracted, skipped = extract_direct_zip(z, txt_members)
            processed = len(txt_members)
        elif tar_members:
            extracted, skipped, processed = extract_inner_tar(z, tar_members[0])
        else:
            raise RuntimeError("archive_contains_no_txt_or_tar_members")
    total = sum(1 for _ in TEXTS.glob("*.txt"))
    if total == 0:
        raise RuntimeError("extraction_completed_but_zero_text_files")
    stage("EXTRACT_COMPLETE", extracted=extracted, skipped=skipped, processed=processed, text_files=total)
    return total


def existing_indexer_pid():
    proc = Path("/proc")
    for p in proc.iterdir():
        if not p.name.isdigit(): continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except Exception:
            continue
        if "eira2.evidence.gutenberg_document_indexer" in cmd:
            return int(p.name)
    return None


def launch_indexer():
    pid = existing_indexer_pid()
    if pid:
        stage("INDEXER_REUSED", pid=pid)
        return pid
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
        text_files = extract()
        pid = launch_indexer()
        stage("PIPELINE_READY", indexer_pid=pid, archive_bytes=ARCHIVE.stat().st_size, text_files=text_files)
        return 0
    except Exception as exc:
        stage("FAILED", error=f"{type(exc).__name__}:{exc}"[:2000])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
