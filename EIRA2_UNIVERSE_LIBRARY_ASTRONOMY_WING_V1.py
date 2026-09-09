from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from typing import Any

SCHEMA = "eira2_universe_library_astronomy_wing_v1"
TIMEOUT = 20
MAX_RESULTS = 25
USER_AGENT = "EIRA2-Astronomy-Wing/1.0 (public-read-only; metadata-first; source-is-not-fact)"

SOURCES: dict[str, dict[str, Any]] = {
    "mast": {
        "name": "MAST / STScI",
        "covers": ["JWST", "Hubble", "Kepler", "TESS", "other MAST missions"],
        "mode": "public_read_only",
        "endpoint": "https://mast.stsci.edu/api/v0/invoke",
        "full_text_auto_download": False,
        "bulk_download": False,
    },
    "jwst_metadata": {
        "name": "JWST MAST metadata / engineering / wavefront",
        "mode": "public_read_only",
        "endpoint": "https://mast.stsci.edu/viz/api/v0.1/",
        "hardware_control": False,
    },
    "nasa_ads": {
        "name": "NASA ADS",
        "mode": "remote_live_keyed",
        "endpoint": "https://api.adsabs.harvard.edu/v1/search/query",
        "api_key_env": "ADS_API_TOKEN",
    },
    "heasarc": {
        "name": "NASA HEASARC",
        "mode": "virtual_observatory",
        "endpoint": "https://heasarc.gsfc.nasa.gov/",
    },
    "irsa": {
        "name": "NASA/IPAC IRSA",
        "mode": "tap",
        "endpoint": "https://irsa.ipac.caltech.edu/TAP/sync",
    },
    "exoplanet_archive": {
        "name": "NASA Exoplanet Archive",
        "mode": "tap",
        "endpoint": "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
    },
    "ned": {
        "name": "NASA/IPAC Extragalactic Database",
        "mode": "new_api_or_tap",
        "endpoint": "https://ned.ipac.caltech.edu/",
        "legacy_api_deprecated": True,
    },
    "jpl_horizons": {
        "name": "JPL Horizons",
        "mode": "json_api",
        "endpoint": "https://ssd.jpl.nasa.gov/api/horizons.api",
    },
}

def _json_request(url: str, *, params: dict[str, Any] | None = None,
                  data: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None) -> Any:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, headers=h, data=body)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _text_request(url: str, params: dict[str, Any] | None = None) -> str:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")

def _mast_invoke(service: str, params: dict[str, Any]) -> dict[str, Any]:
    request = {"service": service, "params": params, "format": "json", "pagesize": MAX_RESULTS, "page": 1}
    return _json_request(
        "https://mast.stsci.edu/api/v0/invoke",
        data={"request": json.dumps(request, separators=(",", ":"))},
    )

def _bounded(limit: int) -> int:
    return max(1, min(int(limit), MAX_RESULTS))

class AstronomyWing:
    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "policy": {
                "public_read_only": True,
                "metadata_first": True,
                "bulk_download": False,
                "automatic_product_download": False,
                "hardware_control": False,
                "source_is_not_fact": True,
                "proprietary_data_bypass": False,
            },
            "sources": SOURCES,
        }

    def mast_observations(self, target: str = "", mission: str = "JWST", limit: int = 10) -> dict[str, Any]:
        n = _bounded(limit)
        filters = [{"paramName": "obs_collection", "values": [mission]}]
        if target:
            filters.append({"paramName": "target_name", "values": [target]})
        out = _mast_invoke("Mast.Caom.Filtered", {"columns": "*", "filters": filters})
        rows = (out.get("data") or [])[:n]
        return {
            "schema": SCHEMA,
            "source": "mast",
            "mission": mission,
            "target": target,
            "result_count": len(rows),
            "metadata_only": True,
            "source_is_not_fact": True,
            "results": rows,
        }

    def jwst_public_observations(self, target: str = "", limit: int = 10) -> dict[str, Any]:
        return self.mast_observations(target=target, mission="JWST", limit=limit)

    def hubble_public_observations(self, target: str = "", limit: int = 10) -> dict[str, Any]:
        return self.mast_observations(target=target, mission="HST", limit=limit)

    def probe_jwst_optics(self, keyword: str = "", limit: int = 10) -> dict[str, Any]:
        """
        Read-only optics/engineering reconnaissance.
        This never commands JWST. It reports public MAST metadata surfaces that expose
        JWST instrument keywords, engineering mnemonics, science products, and wavefront-related
        discovery paths. Optional keyword is used only for local filtering of returned descriptors.
        """
        n = _bounded(limit)
        descriptors = [
            {
                "surface": "jwst_metadata_parameters",
                "url": "https://mast.stsci.edu/viz/api/v0.1/parameters",
                "purpose": "JWST observation parameter metadata",
            },
            {
                "surface": "jwst_instrument_keywords",
                "url": "https://mast.stsci.edu/viz/api/v0.1/keywords/search",
                "purpose": "JWST instrument keyword discovery",
            },
            {
                "surface": "jwst_keyword_metadata",
                "url": "https://mast.stsci.edu/viz/api/v0.1/info/keywords",
                "purpose": "JWST keyword definitions and metadata",
            },
            {
                "surface": "jwst_engineering_mnemonics",
                "url": "https://mast.stsci.edu/viz/api/v0.1/info/mnemonics",
                "purpose": "public JWST engineering mnemonic metadata",
            },
            {
                "surface": "jwst_science_products",
                "url": "https://mast.stsci.edu/viz/api/v0.1/products",
                "purpose": "JWST related data product discovery",
            },
            {
                "surface": "jwst_level3_science_pixels",
                "url": "https://mast.stsci.edu/viz/api/v0.1/retrieve",
                "purpose": "public level-3 JWST science pixel retrieval by MAST data URI",
            },
            {
                "surface": "mast_jwst_wavefront",
                "url": "https://mast.stsci.edu/",
                "purpose": "MAST JWST wave-front products and engineering data discovery",
            },
        ]
        q = keyword.strip().casefold()
        if q:
            descriptors = [
                x for x in descriptors
                if q in (x["surface"] + " " + x["purpose"]).casefold()
            ]
        return {
            "schema": SCHEMA,
            "probe": "jwst_optics_public_read_only",
            "hardware_control": False,
            "can_command_telescope": False,
            "can_access_public_observation_products": True,
            "can_access_public_engineering_metadata": True,
            "can_access_public_wavefront_products": True,
            "source_is_not_fact": True,
            "result_count": min(len(descriptors), n),
            "results": descriptors[:n],
            "note": "JWST is a segmented reflecting telescope; this probes public optics/wavefront/instrument data, not a remotely controllable lens.",
        }

    def ads_search(self, query: str, limit: int = 10) -> dict[str, Any]:
        token = os.environ.get("ADS_API_TOKEN")
        if not token:
            return {"schema": SCHEMA, "source": "nasa_ads", "configured": False, "results": []}
        n = _bounded(limit)
        data = _json_request(
            "https://api.adsabs.harvard.edu/v1/search/query",
            params={"q": query, "rows": n, "fl": "bibcode,title,author,year,doi,citation_count,reference"},
            headers={"Authorization": "Bearer " + token},
        )
        docs = ((data.get("response") or {}).get("docs") or [])[:n]
        return {"schema": SCHEMA, "source": "nasa_ads", "configured": True, "result_count": len(docs),
                "metadata_only": True, "source_is_not_fact": True, "results": docs}

    def exoplanets(self, name_contains: str = "", limit: int = 10) -> dict[str, Any]:
        n = _bounded(limit)
        where = ""
        if name_contains:
            safe = name_contains.replace("'", "''")
            where = f" where pl_name like '%{safe}%'"
        query = (
            "select top {n} pl_name,hostname,disc_year,discoverymethod,pl_orbper,pl_rade,pl_bmasse,"
            "ra,dec from pscomppars{where}"
        ).format(n=n, where=where)
        text = _text_request(
            "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
            {"query": query, "format": "csv"},
        )
        rows = list(csv.DictReader(io.StringIO(text)))[:n]
        return {"schema": SCHEMA, "source": "nasa_exoplanet_archive", "result_count": len(rows),
                "source_is_not_fact": True, "results": rows}

    def irsa_query(self, adql: str, limit: int = 10) -> dict[str, Any]:
        if not adql.strip().lower().startswith("select"):
            raise ValueError("irsa_read_only_select_required")
        if ";" in adql:
            raise ValueError("multiple_statements_not_allowed")
        n = _bounded(limit)
        text = _text_request("https://irsa.ipac.caltech.edu/TAP/sync", {"QUERY": adql, "FORMAT": "csv"})
        rows = list(csv.DictReader(io.StringIO(text)))[:n]
        return {"schema": SCHEMA, "source": "irsa", "result_count": len(rows),
                "source_is_not_fact": True, "results": rows}

    def horizons(self, command: str, center: str = "500@0", start: str = "", stop: str = "",
                 step: str = "1 d") -> dict[str, Any]:
        params: dict[str, Any] = {
            "format": "json",
            "COMMAND": command,
            "EPHEM_TYPE": "OBSERVER",
            "CENTER": center,
            "CSV_FORMAT": "YES",
        }
        if start and stop:
            params.update({"START_TIME": start, "STOP_TIME": stop, "STEP_SIZE": step})
        data = _json_request("https://ssd.jpl.nasa.gov/api/horizons.api", params=params)
        return {"schema": SCHEMA, "source": "jpl_horizons", "source_is_not_fact": True, "result": data}

def describe() -> dict[str, Any]:
    return AstronomyWing().status()

if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, sort_keys=True))
