"""
sector_calibration.py — Service de calibrage sectoriel (D22, Tâche B.8).

Calcule, à partir du CompSet réel en base ("TIC & Ingénierie technique",
id=1 par défaut — PAS de constantes codées en dur type LBO_PROFILES), la
marge d'EBITDA médiane et le multiple EV/EBITDA médian des membres dotés
d'un EBITDA réel (provenance MARKET/DOCUMENT — jamais un membre sans
état financier réel), puis dérive un multiple d'entrée pour du non coté :

    multiple d'entrée = médiane comparables cotés × (1 − décote)

Ce n'est PAS une correction du multiple générique par substitution : les
deux multiples mesurent des objets différents (cotation vs transaction
mid-market non coté). La décote (« size & illiquidity discount, French
mid-market ») matérialise cet écart. Valeur par défaut 35 %, PARAMÈTRE
NOMMÉ et modifiable (jamais un facteur caché) — voir `DEFAULT_...DISCOUNT`.

⚠️ Prudence sur la marge d'EBITDA : les comparables cotés sont des leaders
mondiaux du secteur — leur marge est structurellement supérieure à celle
d'une PME/ETI française mid-market. La médiane est utilisée comme valeur
PAR DÉFAUT, mais reste modifiable et sa provenance signale explicitement
cette limite (voir `_MARGIN_CAVEAT`).

⚠️ Ne substitue JAMAIS silencieusement : si le CompSet est vide ou trop
petit (< MIN_SAMPLE_SIZE membres avec EBITDA réel), la calibration échoue
explicitement (`sufficient=False`, `fallback_reason=...`) et l'appelant
(valuation_engine / routers) DOIT retomber sur le profil générique en le
signalant à l'utilisateur — jamais en silence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.comps import CompSet, CompSetMember
from api.models.financial import Financial
from api.schemas.provenance import DataProvenance, FieldProvenance, weakest_provenance

TIC_COMP_SET_ID = 1
DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT = 0.35
MIN_SAMPLE_SIZE = 3
DISCOUNT_LABEL = "size & illiquidity discount, French mid-market"

# Le CompSet "TIC & Ingénierie technique" calibre le profil LBO_PROFILES
# "professional_svc" (Conseil, Juridique & Ingénierie) — c'est le profil que
# `resolve_profile_key` résout pour les NAF 69-75 (ingénierie, conseil…),
# le même auquel appartenaient les cibles comparées en B.7/B.8 (ex. BTP
# Consultants). Un seul secteur calibré pour l'instant — voir RAPPORT B.8.
# Constante partagée entre le routeur (calcul manuel) et le service de
# scénarios (base-case auto à la promotion, Tâche Review Produit D27).
CALIBRATED_SECTOR_PROFILE_KEY = "professional_svc"

_MARGIN_CAVEAT = (
    "Listed comparables in this CompSet are global TIC/engineering leaders "
    "(Bureau Veritas, Eurofins, Intertek, SGS…) — their EBITDA margin is "
    "structurally higher than a French mid-market SME/ETI. Used as a "
    "DEFAULT value only, always editable."
)


@dataclass
class ComparableDataPoint:
    ticker: str
    fiscal_year: int
    ebitda_margin: float
    ev_ebitda: float
    provenance: DataProvenance


@dataclass
class SectorCalibrationResult:
    sufficient: bool
    fallback_reason: str | None
    sample_size: int
    comp_set_id: int | None
    comp_set_name: str | None
    data_points: list[ComparableDataPoint] = field(default_factory=list)
    fiscal_years: list[int] = field(default_factory=list)
    median_ebitda_margin: float | None = None
    ebitda_margin_min: float | None = None
    ebitda_margin_max: float | None = None
    median_ev_ebitda: float | None = None
    ev_ebitda_min: float | None = None
    ev_ebitda_max: float | None = None
    size_illiquidity_discount: float = DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT
    derived_entry_multiple: float | None = None

    def to_dict(self) -> dict:
        return {
            "sufficient": self.sufficient,
            "fallback_reason": self.fallback_reason,
            "sample_size": self.sample_size,
            "comp_set_id": self.comp_set_id,
            "comp_set_name": self.comp_set_name,
            "tickers": [dp.ticker for dp in self.data_points],
            "fiscal_years": self.fiscal_years,
            "median_ebitda_margin": self.median_ebitda_margin,
            "ebitda_margin_min": self.ebitda_margin_min,
            "ebitda_margin_max": self.ebitda_margin_max,
            "median_ev_ebitda": self.median_ev_ebitda,
            "ev_ebitda_min": self.ev_ebitda_min,
            "ev_ebitda_max": self.ev_ebitda_max,
            "size_illiquidity_discount": self.size_illiquidity_discount,
            "discount_label": DISCOUNT_LABEL,
            "derived_entry_multiple": self.derived_entry_multiple,
            "entry_multiple_provenance": self.entry_multiple_provenance(),
            "ebitda_margin_provenance": self.ebitda_margin_provenance(),
        }

    def _sample_label(self) -> str:
        years = "-".join(str(y) for y in sorted(set(self.fiscal_years))) if self.fiscal_years else "N/A"
        return f"n={self.sample_size}, FY{years}"

    def _input_provenance_label(self) -> str:
        """Provenance des comparables sources (MARKET/DOCUMENT selon le
        connecteur) — décrit la qualité des DONNÉES D'ENTRÉE dans le texte
        de référence, mais n'est jamais la provenance finale retenue : voir
        entry_multiple_provenance/ebitda_margin_provenance ci-dessous."""
        weakest = weakest_provenance(*[dp.provenance for dp in self.data_points]) if self.data_points else DataProvenance.ESTIMATE
        return weakest.value

    def entry_multiple_provenance(self) -> dict | None:
        if self.derived_entry_multiple is None:
            return None
        # Correction (validée Architecte) : ce multiple est un DÉRIVÉ (médiane
        # + décote taille/illiquidité, une hypothèse de modèle), jamais un fait
        # documenté — même quand les comparables sources sont eux-mêmes MARKET.
        # La provenance finale est donc toujours ESTIMATE ; la qualité des
        # données d'entrée reste tracée dans `reference`, pas dans `provenance`.
        return FieldProvenance(
            provenance=DataProvenance.ESTIMATE,
            reference=(
                f"Calculated: {self.median_ev_ebitda:.2f}x listed comparables median "
                f"({self._input_provenance_label()}) (CompSet '{self.comp_set_name}', "
                f"{self._sample_label()}) "
                f"− {self.size_illiquidity_discount * 100:.0f}% {DISCOUNT_LABEL} "
                f"= {self.derived_entry_multiple:.2f}x"
            ),
        ).model_dump(mode="json")

    def ebitda_margin_provenance(self) -> dict | None:
        if self.median_ebitda_margin is None:
            return None
        # Même correction que ci-dessus : une médiane sur plusieurs comparables
        # est un agrégat statistique (ESTIMATE), pas une donnée MARKET directe.
        return FieldProvenance(
            provenance=DataProvenance.ESTIMATE,
            reference=(
                f"Median EBITDA margin of listed comparables ({self._input_provenance_label()}) "
                f"(CompSet '{self.comp_set_name}', {self._sample_label()}) "
                f"= {self.median_ebitda_margin * 100:.2f}%. {_MARGIN_CAVEAT}"
            ),
        ).model_dump(mode="json")


async def compute_sector_calibration(
    db: AsyncSession,
    *,
    comp_set_id: int = TIC_COMP_SET_ID,
    discount: float = DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
) -> SectorCalibrationResult:
    """Calcule la calibration sectorielle à partir du CompSet réel en base.

    N'utilise QUE les membres dotés d'un EBITDA réel ET d'une enterprise
    value réelle (provenance renseignée) — jamais une valeur mock ou
    absente. Échoue explicitement (`sufficient=False`) si l'échantillon
    est vide ou trop petit.
    """
    result = await db.execute(
        select(CompSet)
        .options(selectinload(CompSet.members).selectinload(CompSetMember.company))
        .where(CompSet.id == comp_set_id)
    )
    comp_set = result.scalar_one_or_none()

    if not comp_set:
        return SectorCalibrationResult(
            sufficient=False,
            fallback_reason=f"CompSet id={comp_set_id} not found in database.",
            sample_size=0, comp_set_id=comp_set_id, comp_set_name=None,
        )

    data_points: list[ComparableDataPoint] = []
    for member in comp_set.members:
        company = member.company
        if not company or company.enterprise_value is None:
            continue

        fin_q = await db.execute(
            select(Financial)
            .where(Financial.company_id == company.id, Financial.period_type == "annual")
            .order_by(Financial.period_end.desc())
            .limit(1)
        )
        fin = fin_q.scalar_one_or_none()
        if not fin or fin.ebitda is None or fin.revenue is None or fin.revenue <= 0:
            continue

        prov_raw = (fin.financial_provenance or {}).get("ebitda", {})
        try:
            ebitda_prov = DataProvenance(prov_raw.get("provenance", "UNKNOWN"))
        except ValueError:
            ebitda_prov = DataProvenance.UNKNOWN

        ev_prov_raw = (company.financial_provenance or {}).get("enterprise_value", {})
        try:
            ev_prov = DataProvenance(ev_prov_raw.get("provenance", "UNKNOWN"))
        except ValueError:
            ev_prov = DataProvenance.UNKNOWN

        data_points.append(
            ComparableDataPoint(
                ticker=company.ticker,
                fiscal_year=fin.fiscal_year,
                ebitda_margin=fin.ebitda / fin.revenue,
                ev_ebitda=company.enterprise_value / fin.ebitda,
                provenance=weakest_provenance(ebitda_prov, ev_prov),
            )
        )

    sample_size = len(data_points)
    if sample_size < MIN_SAMPLE_SIZE:
        # D34 (Tâche Review Produit — Partie D) : reformulé pour un
        # utilisateur non technique — le secteur EST le bon (contrairement au
        # cas "non applicable"), mais l'échantillon de comparables avec un
        # EBITDA réel est trop petit pour être fiable.
        return SectorCalibrationResult(
            sufficient=False,
            fallback_reason=(
                f"Calibrage non applicable : le secteur correspond bien au CompSet « {comp_set.name} », "
                f"mais seulement {sample_size} comparable(s) sur ce panel disposent d'un EBITDA réel "
                f"exploitable (minimum requis : {MIN_SAMPLE_SIZE}) — échantillon trop petit pour une "
                f"médiane fiable. Un profil générique documenté est utilisé à la place."
            ),
            sample_size=sample_size, comp_set_id=comp_set.id, comp_set_name=comp_set.name,
            data_points=data_points,
        )

    margins = [dp.ebitda_margin for dp in data_points]
    multiples = [dp.ev_ebitda for dp in data_points]
    median_margin = median(margins)
    median_multiple = median(multiples)
    derived_entry = round(median_multiple * (1 - discount), 2)

    return SectorCalibrationResult(
        sufficient=True,
        fallback_reason=None,
        sample_size=sample_size,
        comp_set_id=comp_set.id,
        comp_set_name=comp_set.name,
        data_points=data_points,
        fiscal_years=[dp.fiscal_year for dp in data_points],
        median_ebitda_margin=round(median_margin, 4),
        ebitda_margin_min=round(min(margins), 4),
        ebitda_margin_max=round(max(margins), 4),
        median_ev_ebitda=round(median_multiple, 2),
        ev_ebitda_min=round(min(multiples), 2),
        ev_ebitda_max=round(max(multiples), 2),
        size_illiquidity_discount=discount,
        derived_entry_multiple=derived_entry,
    )
