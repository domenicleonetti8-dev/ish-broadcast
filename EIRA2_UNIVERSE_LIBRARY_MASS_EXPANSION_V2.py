from __future__ import annotations

"""EIRA2 Universe Library mass lawful-source expansion.

This module extends the existing universe_public_library vault. It never grants
source material truth authority and never treats 'free to read' as permission to
redistribute/store full text.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

SCHEMA = "eira2_universe_library_mass_expansion_v2"
DEFAULT_ROOT = Path(os.environ.get("EIRA_LIVE_ROOT", "/media/domenicleonetti/easystore/EIRA/LIVE")).resolve()
STATE_PATH = DEFAULT_ROOT / "eira_probe" / "universe_library" / "mass_expansion_state.json"

SUBJECT_TAXONOMY = (
    "history", "world_history", "ancient_history", "modern_history", "military_history",
    "science", "technology", "engineering", "mechanical_engineering", "electrical_engineering",
    "civil_engineering", "aerospace_engineering", "chemical_engineering", "materials_science",
    "mathematics", "algebra", "geometry", "calculus", "statistics", "number_theory",
    "computer_science", "physics", "astronomy", "chemistry", "geology", "earth_science",
    "biology", "microbiology", "genetics", "evolution", "biochemistry", "neuroscience",
    "oceanography", "marine_biology", "marine_ecology", "fisheries", "hydrology",
    "zoology", "mammalogy", "ornithology", "herpetology", "ichthyology", "entomology",
    "botany", "mycology", "plant_science", "forestry", "agriculture", "ecology",
    "environment", "climate", "conservation", "biodiversity", "architecture",
    "construction", "urban_planning", "geography", "medicine", "public_health",
    "pharmacology", "psychology", "anthropology", "archaeology", "economics",
    "philosophy", "linguistics", "education", "law", "reference"
)

# full_text_policy values:
# public_domain_bulk = sanctioned bulk public-domain corpus
# open_license_only = retain full text only when item-level license permits
# oa_subset_only = only the provider's explicit open-access subset
# metadata_discovery = retain metadata/link unless rights are independently proven
SOURCES: dict[str, dict[str, Any]] = {
    "project_gutenberg": {
        "authority_class": "curated_public_domain_library",
        "full_text_policy": "public_domain_bulk",
        "catalog": "https://dev.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz",
        "bulk": "https://dev.gutenberg.org/cache/epub/feeds/txt-files.tar.zip",
        "refresh": "catalog_daily_bulk_weekly",
        "subjects": "all",
    },
    "doab": {
        "authority_class": "open_access_book_directory",
        "full_text_policy": "open_license_only",
        "homepage": "https://www.doabooks.org/",
        "metadata": "https://directory.doabooks.org/oai/request",
        "subjects": "all_academic",
    },
    "wikisource": {
        "authority_class": "community_curated_source_archive",
        "full_text_policy": "open_license_only",
        "homepage": "https://wikisource.org/",
        "subjects": "all",
    },
    "openstax": {
        "authority_class": "peer_reviewed_open_textbooks",
        "full_text_policy": "open_license_only",
        "homepage": "https://openstax.org/",
        "subjects": ["science", "mathematics", "technology", "biology", "chemistry", "physics", "economics"],
    },
    "ncbi_bookshelf_oa": {
        "authority_class": "government_biomedical_archive",
        "full_text_policy": "oa_subset_only",
        "homepage": "https://www.ncbi.nlm.nih.gov/books/",
        "subjects": ["biology", "medicine", "public_health", "genetics", "biochemistry", "neuroscience"],
    },
    "biodiversity_heritage_library": {
        "authority_class": "biodiversity_scientific_library",
        "full_text_policy": "open_license_only",
        "homepage": "https://www.biodiversitylibrary.org/",
        "subjects": ["biology", "zoology", "entomology", "botany", "marine_biology", "ecology", "biodiversity"],
    },
    "nasa_ntrs": {
        "authority_class": "us_government_technical_repository",
        "full_text_policy": "open_license_only",
        "homepage": "https://ntrs.nasa.gov/",
        "subjects": ["aerospace_engineering", "physics", "astronomy", "engineering", "materials_science", "technology"],
    },
    "noaa_repository": {
        "authority_class": "us_government_ocean_atmosphere_repository",
        "full_text_policy": "open_license_only",
        "homepage": "https://repository.library.noaa.gov/",
        "subjects": ["oceanography", "marine_biology", "fisheries", "climate", "environment", "hydrology"],
    },
    "usgs_publications": {
        "authority_class": "us_government_earth_science_repository",
        "full_text_policy": "open_license_only",
        "homepage": "https://pubs.usgs.gov/",
        "subjects": ["geology", "earth_science", "hydrology", "environment", "biology", "geography"],
    },
    "doe_osti": {
        "authority_class": "us_government_science_technology_repository",
        "full_text_policy": "open_license_only",
        "homepage": "https://www.osti.gov/",
        "subjects": ["physics", "chemistry", "engineering", "energy", "materials_science", "mathematics", "technology"],
    },
    "internet_archive_discovery": {
        "authority_class": "digital_archive",
        "full_text_policy": "metadata_discovery",
        "homepage": "https://archive.org/",
        "subjects": "all",
        "note": "Copy full text only when item-level rights are public-domain/open-license; borrowing/free-to-read is not storage permission.",
    },
    "open_library_discovery": {
        "authority_class": "book_metadata_catalog",
        "full_text_policy": "metadata_discovery",
        "homepage": "https://openlibrary.org/",
        "subjects": "all",
    },
}


def _atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def policy() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source_is_not_fact": True,
        "dedupe": "sha256_plus_source_work_id",
        "retain_full_text_when": ["public_domain", "recognized_open_license", "explicit_provider_open_access_subset"],
        "metadata_only_when": ["rights_unclear", "free_to_read_only", "borrow_only", "license_forbids_redistribution"],
        "preserve": ["source", "work_id", "title", "authors", "subjects", "language", "source_url", "license", "rights", "retrieved_at", "content_sha256"],
        "medical_currency_gate": True,
        "sources": SOURCES,
        "subject_taxonomy": list(SUBJECT_TAXONOMY),
    }


def run_gutenberg_stock(*, force_catalog: bool = True, force_bulk: bool = True) -> dict[str, Any]:
    """Run the already-qualified Gutenberg scheduler against the existing vault."""
    from eira2.evidence.gutenberg_refresh import GutenbergRefreshScheduler
    started = time.time()
    scheduler = GutenbergRefreshScheduler()
    result = scheduler.run_due(force_catalog=force_catalog, force_bulk=force_bulk)
    payload = {
        "schema": SCHEMA,
        "operation": "gutenberg_stock",
        "started_unix": started,
        "completed_unix": time.time(),
        "ok": result.get("ok") is True,
        "result": result,
        "source_is_not_fact": True,
    }
    _atomic(STATE_PATH, payload)
    return payload


def status() -> dict[str, Any]:
    state: dict[str, Any] = {}
    if STATE_PATH.is_file():
        try: state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception: state = {}
    try:
        from eira2.evidence.universe_public_library import PublicLibraryVault
        with PublicLibraryVault() as vault:
            vault_stats = vault.stats()
    except Exception as exc:
        vault_stats = {"error": f"{type(exc).__name__}:{exc}"}
    return {"schema": SCHEMA, "ok": True, "registered_sources": len(SOURCES), "subjects": len(SUBJECT_TAXONOMY), "vault": vault_stats, "state": state, "source_is_not_fact": True}


def self_test() -> dict[str, Any]:
    required = {"project_gutenberg", "doab", "wikisource", "openstax", "ncbi_bookshelf_oa", "biodiversity_heritage_library", "nasa_ntrs", "noaa_repository", "usgs_publications", "doe_osti"}
    checks = {
        "source_count": len(SOURCES) >= 12,
        "required_sources": required.issubset(SOURCES),
        "subject_depth": len(SUBJECT_TAXONOMY) >= 60,
        "gutenberg_bulk": SOURCES["project_gutenberg"]["full_text_policy"] == "public_domain_bulk",
        "unclear_rights_metadata_only": SOURCES["internet_archive_discovery"]["full_text_policy"] == "metadata_discovery",
        "source_not_fact": policy()["source_is_not_fact"] is True,
    }
    return {"schema": SCHEMA + "_self_test", "ok": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-gutenberg", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.stock_gutenberg:
        print(json.dumps(run_gutenberg_stock(), indent=2, sort_keys=True))
    elif args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
    else:
        out = self_test(); print(json.dumps(out, indent=2, sort_keys=True)); raise SystemExit(0 if out["ok"] else 1)
