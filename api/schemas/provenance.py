"""
provenance.py — Modèle de provenance des données financières (D18, Tâche B.6).

Constat qui motive ce module : en B.5, `target_ebitda`/`enterprise_value`
étaient copiés depuis `SourcedTarget` vers `Deal` sans distinction entre une
donnée réelle (CA du registre) et une donnée dérivée d'une hypothèse
sectorielle (marge EBITDA %, moteur de valorisation LBO) — le mémo IC citait
ensuite les deux sans réserve, comme des faits établis.

Chaque point de donnée financière stocké doit pouvoir répondre à trois
questions : d'où vient ce chiffre (`provenance`), de quel exercice parle-t-il
(`as_of`), et par quelle référence peut-on la retracer (`reference` — URL,
nom de fichier, ou méthode d'estimation explicite) ?
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class DataProvenance(str, Enum):
    REGISTRY = "REGISTRY"   # comptes officiels déposés (registre, greffe, INPI)
    DOCUMENT = "DOCUMENT"   # extrait d'un document fourni (teaser, rapport annuel)
    MARKET = "MARKET"       # fournisseur de données de marché (FMP, Finnhub, ESEF)
    ESTIMATE = "ESTIMATE"   # dérivé d'une hypothèse ou d'une règle de calcul
    MANUAL = "MANUAL"       # saisi ou corrigé par l'utilisateur
    UNKNOWN = "UNKNOWN"     # origine indéterminable — jamais devinée (Étape 5)


class FieldProvenance(BaseModel):
    """Provenance d'un unique champ financier."""
    provenance: DataProvenance
    as_of: str | None = None    # exercice concerné, ex. "2022"
    reference: str | None = None  # URL, nom de fichier, ou méthode d'estimation


# Du plus faible au plus fort — sert à faire hériter un multiple calculé de
# la provenance la plus faible de ses composantes (ex. EV/EBITDA calculé sur
# un EBITDA ESTIMATE est lui-même ESTIMATE, même si l'EV était REGISTRY).
_PROVENANCE_STRENGTH_WEAKEST_FIRST: list[DataProvenance] = [
    DataProvenance.UNKNOWN,
    DataProvenance.ESTIMATE,
    DataProvenance.MANUAL,
    DataProvenance.DOCUMENT,
    DataProvenance.MARKET,
    DataProvenance.REGISTRY,
]


def weakest_provenance(*labels: DataProvenance | None) -> DataProvenance:
    """Retourne la provenance la plus faible parmi celles fournies (None ignorés).
    UNKNOWN si aucune n'est fournie."""
    present = [l for l in labels if l is not None]
    if not present:
        return DataProvenance.UNKNOWN
    return min(present, key=_PROVENANCE_STRENGTH_WEAKEST_FIRST.index)


def provenance_dict_to_json(prov: dict[str, FieldProvenance | None]) -> dict[str, Any]:
    """Sérialise un dict {champ: FieldProvenance} pour stockage JSON."""
    return {k: v.model_dump(mode="json") for k, v in prov.items() if v is not None}


def field_provenance_from_json(raw: dict[str, Any] | None, field: str) -> FieldProvenance | None:
    """Relit la provenance d'un champ depuis le JSON stocké, ou None si absente."""
    if not raw or field not in raw:
        return None
    try:
        return FieldProvenance.model_validate(raw[field])
    except Exception:
        return None
