from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "eira2_live_public_observatory_v1"
ROOT = Path("/media/domenicleonetti/easystore/EIRA/LIVE")
STATE = ROOT / "eira_probe" / "observatory_v1"
CATALOG = STATE / "catalog"
PREVIEWS = STATE / "previews"
FITS = STATE / "fits"
SEEN = STATE / "seen.json"
MAST_INVOKE = "https://mast.stsci.edu/api/v0/invoke"
MAST_DOWNLOAD = "https://mast.stsci.edu/api/v0.1/Download/file"
USER_AGENT = "EIRA2-Observatory/1.0 (public-read-only; provenance-preserving)"
TIMEOUT = 30
MAX_QUERY_ROWS = 200
MAX_PREVIEWS_PER_WATCH = 4
MAX_PREVIEW_BYTES = 25 * 1024 * 1024
MAX_EXPLICIT_FITS_BYTES = 1024 * 1024 * 1024

for p in (STATE, CATALOG, PREVIEWS, FITS):
    p.mkdir(parents=True, exist_ok=True)


def _mast(service: str, params: dict[str, Any], pagesize: int = MAX_QUERY_ROWS) -> dict[str, Any]:
    req = {"service": service, "params": params, "format": "json", "pagesize": pagesize, "page": 1}
    data = urllib.parse.urlencode({"request": json.dumps(req, separators=(",", ":"))}).encode()
    r = urllib.request.Request(
        MAST_INVOKE,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(r, timeout=TIMEOUT) as f:
        return json.loads(f.read().decode("utf-8", "replace"))


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "product")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:240]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_seen() -> dict[str, Any]:
    try:
        x = json.loads(SEEN.read_text())
        return x if isinstance(x, dict) else {}
    except Exception:
        return {}


def _save_seen(x: dict[str, Any]) -> None:
    tmp = SEEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(x, indent=2, sort_keys=True))
    os.replace(tmp, SEEN)


def _public(row: dict[str, Any]) -> bool:
    rights = str(row.get("dataRights") or row.get("data_rights") or row.get("access") or "").upper()
    return rights in ("PUBLIC", "") and "EXCLUSIVE" not in rights and "PROPRIETARY" not in rights


def _sort_time(row: dict[str, Any]) -> float:
    for k in ("t_obs_release", "obs_release", "t_max", "t_min"):
        try:
            v = row.get(k)
            if v is not None:
                return float(v)
        except Exception:
            pass
    return 0.0


class Observatory:
    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "root": str(STATE),
            "missions": ["JWST", "HST"],
            "policy": {
                "public_only": True,
                "read_only_remote": True,
                "fits_is_scientific_source": True,
                "preview_is_derivative": True,
                "automatic_preview_download": True,
                "automatic_fits_download": False,
                "explicit_fits_required": True,
                "bulk_download": False,
                "hardware_control": False,
                "source_is_not_fact": True,
            },
        }

    def recent_public(self, mission: str = "JWST", limit: int = 20) -> list[dict[str, Any]]:
        mission = mission.upper()
        if mission not in ("JWST", "HST"):
            raise ValueError("mission_must_be_JWST_or_HST")
        filters = [{"paramName": "obs_collection", "values": [mission]}]
        out = _mast("Mast.Caom.Filtered", {"columns": "*", "filters": filters})
        rows = [r for r in (out.get("data") or []) if isinstance(r, dict) and _public(r)]
        rows.sort(key=_sort_time, reverse=True)
        return rows[: max(1, min(int(limit), 50))]

    def products(self, obsid: str) -> list[dict[str, Any]]:
        out = _mast("Mast.Caom.Products", {"obsid": str(obsid)}, pagesize=500)
        return [r for r in (out.get("data") or []) if isinstance(r, dict) and _public(r)]

    def classify_products(self, obsid: str) -> dict[str, Any]:
        rows = self.products(obsid)
        previews, fits = [], []
        for r in rows:
            fn = str(r.get("productFilename") or "")
            ext = Path(fn.lower()).suffix
            if ext in (".png", ".jpg", ".jpeg"):
                previews.append(r)
            elif ext in (".fits", ".fit", ".fts"):
                fits.append(r)
        return {
            "schema": SCHEMA,
            "obsid": str(obsid),
            "public_only": True,
            "preview_products": previews,
            "fits_products": fits,
            "preview_count": len(previews),
            "fits_count": len(fits),
        }

    def _download(self, row: dict[str, Any], dest_dir: Path, max_bytes: int) -> dict[str, Any]:
        uri = str(row.get("dataURI") or row.get("dataUri") or "")
        if not uri.startswith("mast:"):
            raise ValueError("mast_data_uri_required")
        name = _safe_name(str(row.get("productFilename") or uri.rsplit("/", 1)[-1]))
        dest = dest_dir / name
        url = MAST_DOWNLOAD + "?" + urllib.parse.urlencode({"uri": uri})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        fd, tmpname = tempfile.mkstemp(prefix=name + ".", suffix=".part", dir=str(dest_dir))
        total = 0
        try:
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=TIMEOUT) as src:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("download_size_limit_exceeded")
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmpname, dest)
        except Exception:
            try:
                os.unlink(tmpname)
            except FileNotFoundError:
                pass
            raise
        receipt = {
            "schema": SCHEMA,
            "mast_uri": uri,
            "path": str(dest.relative_to(ROOT)),
            "bytes": total,
            "sha256": _sha256(dest),
            "downloaded_unix": time.time(),
            "source_is_not_fact": True,
        }
        receipt_path = dest.with_suffix(dest.suffix + ".receipt.json")
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
        return receipt

    def download_preview(self, product: dict[str, Any]) -> dict[str, Any]:
        fn = str(product.get("productFilename") or "").lower()
        if not fn.endswith((".png", ".jpg", ".jpeg")):
            raise ValueError("preview_product_required")
        return self._download(product, PREVIEWS, MAX_PREVIEW_BYTES)

    def download_fits(self, product: dict[str, Any], *, explicit: bool = False) -> dict[str, Any]:
        if not explicit:
            raise PermissionError("explicit_fits_download_required")
        fn = str(product.get("productFilename") or "").lower()
        if not fn.endswith((".fits", ".fit", ".fts")):
            raise ValueError("fits_product_required")
        return self._download(product, FITS, MAX_EXPLICIT_FITS_BYTES)

    def watch_once(self, per_mission: int = 10, download_previews: bool = True) -> dict[str, Any]:
        seen = _load_seen()
        discovered, preview_receipts, failures = [], [], {}
        preview_budget = MAX_PREVIEWS_PER_WATCH

        for mission in ("JWST", "HST"):
            try:
                rows = self.recent_public(mission, per_mission)
            except Exception as e:
                failures[mission] = f"{type(e).__name__}:{e}"[:500]
                continue

            for row in rows:
                obsid = str(row.get("obsid") or row.get("obs_id") or row.get("obsID") or "")
                if not obsid:
                    continue
                key = mission + ":" + obsid
                if key in seen:
                    continue
                item = {
                    "mission": mission,
                    "obsid": obsid,
                    "target_name": row.get("target_name"),
                    "instrument_name": row.get("instrument_name"),
                    "t_obs_release": row.get("t_obs_release"),
                    "dataRights": row.get("dataRights"),
                    "source_is_not_fact": True,
                }
                discovered.append(item)
                seen[key] = {"first_seen_unix": time.time(), "observation": item}

                if download_previews and preview_budget > 0:
                    try:
                        products = self.classify_products(obsid)
                        for product in products["preview_products"]:
                            if preview_budget <= 0:
                                break
                            preview_receipts.append(self.download_preview(product))
                            preview_budget -= 1
                            break
                    except Exception as e:
                        failures[key] = f"{type(e).__name__}:{e}"[:500]

        _save_seen(seen)
        snapshot = {
            "schema": SCHEMA,
            "watch_unix": time.time(),
            "mode": "newly_seen_public_archive_products",
            "not_spacecraft_live_feed": True,
            "fits_is_scientific_source": True,
            "automatic_fits_download": False,
            "discovered_count": len(discovered),
            "preview_download_count": len(preview_receipts),
            "discovered": discovered,
            "preview_receipts": preview_receipts,
            "failures": failures,
        }
        stamp = str(int(snapshot["watch_unix"]))
        (CATALOG / f"watch_{stamp}.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        return snapshot


def describe() -> dict[str, Any]:
    return Observatory().status()


if __name__ == "__main__":
    print(json.dumps(Observatory().watch_once(), indent=2, sort_keys=True))
