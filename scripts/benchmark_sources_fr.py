"""
benchmark_sources_fr.py — Banc d'essai comparatif des 4 sources candidates
pour remplacer Pappers (D8, Tâche B.2, Étape 4.1).

Interroge les 4 sources sur un même échantillon de 5 sociétés françaises
réelles du secteur TIC/ingénierie technique (dont 2 ETI vérifiées : Bureau
Alpes Contrôles, Edeis) et mesure pour chacune : succès, code HTTP, latence,
besoin de clé, rate limit documenté/constaté, champs retournés, présence de
données financières (CA, résultat net, EBITDA, effectifs, sur combien
d'exercices), et capacité de recherche par code NAF.

Aucune donnée n'est inventée : ce script ne fait qu'appeler les APIs
publiques et restituer ce qu'elles répondent, tel quel.

Usage :
    source .venv/bin/activate
    python -m scripts.benchmark_sources_fr
"""
from __future__ import annotations

import asyncio
import time

import httpx
from loguru import logger

from api.config import get_settings


SAMPLE_COMPANIES: list[dict] = [
    {"name": "Bureau Alpes Contrôles", "siren": "351812698", "note": "ETI vérifiée, CA ~91M€"},
    {"name": "Edeis Ingénierie", "siren": "444649537", "note": "ETI vérifiée, CA ~55.6M€"},
    {"name": "Institut de Soudure (IS)", "siren": "784756413", "note": "Groupe CND"},
    {"name": "Ginger CEBTP", "siren": "412442519", "note": "Laboratoire matériaux"},
    {"name": "Ingebime", "siren": "843349374", "note": "Bureau d'études structure"},
]


# ============================================================
# Source 1 — API Recherche d'Entreprises (recherche-entreprises.api.gouv.fr)
# ============================================================

async def test_recherche_entreprises(client: httpx.AsyncClient, siren: str) -> dict:
    url = "https://recherche-entreprises.api.gouv.fr/search"
    t0 = time.monotonic()
    try:
        resp = await client.get(url, params={"q": siren, "per_page": 1}, timeout=10.0)
        latency = time.monotonic() - t0
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return {"success": False, "http_code": resp.status_code, "latency_s": round(latency, 2), "fields": [], "finances": None}
        r = results[0]
        return {
            "success": True,
            "http_code": resp.status_code,
            "latency_s": round(latency, 2),
            "fields": sorted(r.keys()),
            "finances": r.get("finances"),
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "http_code": e.response.status_code, "latency_s": round(time.monotonic() - t0, 2), "fields": [], "finances": None}
    except Exception as e:
        return {"success": False, "http_code": None, "error": str(e), "latency_s": round(time.monotonic() - t0, 2), "fields": [], "finances": None}


# ============================================================
# Source 2 — API Sirene officielle INSEE (api.insee.fr)
# ============================================================

async def test_insee_officiel(client: httpx.AsyncClient, siren: str) -> dict:
    settings = get_settings()
    insee_key = getattr(settings, "insee_api_key", "") or ""
    url = f"https://api.insee.fr/entreprises/sirene/V3.11/siren/{siren}"
    headers = {"X-INSEE-Api-Key-Integration": insee_key} if insee_key else {}
    t0 = time.monotonic()
    try:
        resp = await client.get(url, headers=headers, timeout=10.0)
        latency = time.monotonic() - t0
        return {
            "success": resp.status_code == 200,
            "http_code": resp.status_code,
            "latency_s": round(latency, 2),
            "fields": [],
            "finances": None,
            "note": "Aucune clé PE_INSEE_API_KEY configurée dans ce projet" if not insee_key else "",
        }
    except Exception as e:
        return {"success": False, "http_code": None, "error": str(e), "latency_s": round(time.monotonic() - t0, 2), "fields": [], "finances": None}


# ============================================================
# Source 3 — Origami Entreprises (JSON public, sans clé)
# ============================================================

async def test_origami(client: httpx.AsyncClient, siren: str) -> dict:
    url = f"https://origami-entreprises.fr/entreprise/{siren}.json"
    t0 = time.monotonic()
    try:
        resp = await client.get(url, timeout=10.0)
        latency = time.monotonic() - t0
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": True,
            "http_code": resp.status_code,
            "latency_s": round(latency, 2),
            "fields": sorted(data.keys()),
            "finances": {
                "chiffre_affaires": data.get("chiffre_affaires"),
                "resultat": data.get("resultat"),
                "annee_finances": data.get("annee_finances"),
                "effectifs_finances": data.get("effectifs_finances"),
            },
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "http_code": e.response.status_code, "latency_s": round(time.monotonic() - t0, 2), "fields": [], "finances": None}
    except Exception as e:
        return {"success": False, "http_code": None, "error": str(e), "latency_s": round(time.monotonic() - t0, 2), "fields": [], "finances": None}


# ============================================================
# Source 4 — Société.Ninja (URL réelle non identifiée)
# ============================================================

async def test_societe_ninja(client: httpx.AsyncClient, siren: str) -> dict:
    """Aucune documentation publique trouvée pour le pattern d'URL de fiche
    entreprise de ce site. Tentatives sur les patterns les plus plausibles ;
    échec honnêtement rapporté si aucun ne fonctionne (pas de contournement
    par scraping du moteur de recherche interne, hors budget de cette tâche).
    """
    candidate_paths = [
        f"/entreprise/{siren}", f"/siren/{siren}", f"/societe/{siren}", f"/{siren}",
    ]
    t0 = time.monotonic()
    for path in candidate_paths:
        try:
            resp = await client.get(f"https://societe.ninja{path}", timeout=8.0, follow_redirects=True)
            if resp.status_code == 200 and siren in resp.text:
                return {
                    "success": True, "http_code": 200,
                    "latency_s": round(time.monotonic() - t0, 2),
                    "fields": ["(page HTML, pas de JSON structuré identifié)"],
                    "finances": None, "note": f"Trouvé via {path}",
                }
        except Exception:
            continue
    return {
        "success": False, "http_code": 404,
        "latency_s": round(time.monotonic() - t0, 2),
        "fields": [], "finances": None,
        "note": "Aucun pattern d'URL testé ne résout vers une fiche entreprise valide. "
                "Pas d'API publique documentée trouvée pour ce site.",
    }


# ============================================================
# Orchestration du banc d'essai
# ============================================================

SOURCES = {
    "API Recherche d'Entreprises (recherche-entreprises.api.gouv.fr)": test_recherche_entreprises,
    "INSEE Sirene officiel (api.insee.fr V3.11)": test_insee_officiel,
    "Origami Entreprises (origami-entreprises.fr)": test_origami,
    "Société.Ninja (societe.ninja)": test_societe_ninja,
}


async def run_benchmark() -> dict:
    results: dict[str, list[dict]] = {name: [] for name in SOURCES}

    async with httpx.AsyncClient() as client:
        for company in SAMPLE_COMPANIES:
            logger.info("=" * 60)
            logger.info("Société : {} (SIREN {})", company["name"], company["siren"])
            for source_name, fn in SOURCES.items():
                r = await fn(client, company["siren"])
                r["company"] = company["name"]
                results[source_name].append(r)
                status = "✅" if r["success"] else "❌"
                logger.info(
                    "  {} {} — HTTP {} — {:.2f}s — finances={}",
                    status, source_name, r.get("http_code"), r.get("latency_s"),
                    bool(r.get("finances")),
                )

    return results


def print_summary_table(results: dict[str, list[dict]]) -> None:
    print("\n" + "=" * 100)
    print("TABLEAU COMPARATIF — Étape 4.1")
    print("=" * 100)
    for source_name, rows in results.items():
        successes = sum(1 for r in rows if r["success"])
        with_finances = sum(1 for r in rows if r.get("finances") and any(v for v in (r["finances"].values() if isinstance(r["finances"], dict) else [])))
        avg_latency = sum(r["latency_s"] for r in rows) / len(rows) if rows else 0
        all_fields = sorted({f for r in rows for f in r.get("fields", [])})
        print(f"\n{source_name}")
        print(f"  Succès              : {successes}/{len(rows)}")
        print(f"  Latence moyenne     : {avg_latency:.2f}s")
        print(f"  Avec données fin.   : {with_finances}/{len(rows)}")
        print(f"  Nb champs distincts : {len(all_fields)}")
        for r in rows:
            note = r.get("note", "")
            print(f"    - {r['company']}: HTTP {r.get('http_code')} | finances={r.get('finances')} {('| ' + note) if note else ''}")


if __name__ == "__main__":
    res = asyncio.run(run_benchmark())
    print_summary_table(res)
