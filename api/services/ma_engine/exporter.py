"""
exporter.py — Export des cibles M&A en CSV et HTML (io.BytesIO).

Génère des fichiers d'export en mémoire (pas d'écriture disque)
pour être streamés directement via FastAPI StreamingResponse.

Points d'entrée :
    export_targets_csv(targets)  -> io.BytesIO   (text/csv)
    export_targets_html(targets) -> io.BytesIO   (text/html)

Les targets sont des dicts ou des objets Pydantic / SQLAlchemy
avec les champs du modèle SourcedTarget.

Adapted from the original sync exporter for the pe_tracker FastAPI backend.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from loguru import logger

from api.services.ma_engine.financial_estimator import format_revenue


# ============================================================
# Colonnes exportées
# ============================================================

CSV_COLUMNS = [
    "id",
    "company_name",
    "url",
    "status",
    "score",
    "revenue_estimate",
    "ebitda_estimate",
    "enterprise_value",
    "lbo_irr",
    "lbo_moic",
    "entry_multiple",
    "business_summary",
    "keywords",
    "growth_signals",
    "red_flags",
    "competitors",
    "created_at",
    "updated_at",
]


# ============================================================
# Helpers
# ============================================================

def _target_to_dict(target: Any) -> dict:
    """Convertit un objet target (ORM, Pydantic, ou dict) en dict plat."""
    if isinstance(target, dict):
        return target
    # Pydantic model
    if hasattr(target, "model_dump"):
        return target.model_dump()
    # SQLAlchemy ORM
    if hasattr(target, "__dict__"):
        return {k: v for k, v in target.__dict__.items() if not k.startswith("_")}
    return dict(target)


def _format_list(val: Any) -> str:
    """Formate une liste en string pour CSV/HTML."""
    if val is None:
        return ""
    if isinstance(val, list):
        return " | ".join(str(v) for v in val)
    return str(val)


def _format_value(key: str, val: Any) -> str:
    """Formate une valeur selon son type pour l'export."""
    if val is None:
        return ""
    if key in ("revenue_estimate", "ebitda_estimate", "enterprise_value"):
        return format_revenue(val) if isinstance(val, (int, float)) else str(val)
    if key in ("lbo_irr",):
        return f"{val:.1f}%" if isinstance(val, (int, float)) else str(val)
    if key in ("lbo_moic", "entry_multiple"):
        return f"{val:.2f}x" if isinstance(val, (int, float)) else str(val)
    if key in ("score",):
        return f"{val:.1f}" if isinstance(val, (int, float)) else str(val)
    if key in ("keywords", "growth_signals", "red_flags", "competitors"):
        return _format_list(val)
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    return str(val)


# ============================================================
# CSV Export
# ============================================================

def export_targets_csv(
    targets: list[Any],
    columns: list[str] | None = None,
) -> io.BytesIO:
    """Génère un fichier CSV en mémoire depuis une liste de cibles.

    Args:
        targets:  Liste de targets (dicts, Pydantic models, ou ORM objects).
        columns:  Colonnes à exporter (défaut: CSV_COLUMNS complètes).

    Returns:
        io.BytesIO contenant le CSV (UTF-8 BOM pour Excel).
    """
    cols = columns or CSV_COLUMNS
    logger.info("📤 Export CSV — {} cibles, {} colonnes", len(targets), len(cols))

    buf = io.StringIO()
    # UTF-8 BOM pour compatibilité Excel
    buf.write("\ufeff")

    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()

    for target in targets:
        row = _target_to_dict(target)
        formatted_row = {col: _format_value(col, row.get(col)) for col in cols}
        writer.writerow(formatted_row)

    # Convertir en BytesIO
    content = buf.getvalue().encode("utf-8")
    bytes_buf = io.BytesIO(content)
    bytes_buf.seek(0)

    logger.info("  ✅ CSV généré ({:.0f} Ko)", len(content) / 1024)
    return bytes_buf


# ============================================================
# HTML Export
# ============================================================

_HTML_TEMPLATE_HEADER = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>PE Intelligence — Export Cibles M&A</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            padding: 2rem;
            margin: 0;
        }}
        h1 {{
            color: #007acc;
            border-bottom: 2px solid #007acc;
            padding-bottom: 0.5rem;
        }}
        .meta {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-bottom: 1.5rem;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            font-size: 0.85rem;
        }}
        th {{
            background: #1a1a2e;
            color: #007acc;
            padding: 0.6rem 0.8rem;
            text-align: left;
            border-bottom: 2px solid #333;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 0.5rem 0.8rem;
            border-bottom: 1px solid #222;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        tr:hover td {{
            background: #1a1a2e;
        }}
        .score-high {{ color: #28a745; font-weight: bold; }}
        .score-mid  {{ color: #ffc107; font-weight: bold; }}
        .score-low  {{ color: #dc3545; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🎯 PE Intelligence — Cibles M&A</h1>
    <div class="meta">Export généré le {date} — {count} cibles</div>
    <table>
        <thead>
            <tr>{headers}</tr>
        </thead>
        <tbody>
"""

_HTML_TEMPLATE_FOOTER = """
        </tbody>
    </table>
</body>
</html>
"""


def _score_class(score: Any) -> str:
    """Retourne la classe CSS d'un score."""
    if score is None:
        return ""
    try:
        s = float(score)
        if s >= 70:
            return "score-high"
        if s >= 40:
            return "score-mid"
        return "score-low"
    except (ValueError, TypeError):
        return ""


def export_targets_html(
    targets: list[Any],
    columns: list[str] | None = None,
) -> io.BytesIO:
    """Génère un fichier HTML en mémoire depuis une liste de cibles.

    Args:
        targets:  Liste de targets (dicts, Pydantic models, ou ORM objects).
        columns:  Colonnes à exporter (défaut: CSV_COLUMNS complètes).

    Returns:
        io.BytesIO contenant le HTML.
    """
    cols = columns or CSV_COLUMNS
    logger.info("📤 Export HTML — {} cibles, {} colonnes", len(targets), len(cols))

    headers = "".join(f"<th>{col}</th>" for col in cols)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = _HTML_TEMPLATE_HEADER.format(
        date=date_str, count=len(targets), headers=headers
    )

    for target in targets:
        row = _target_to_dict(target)
        cells = []
        for col in cols:
            val = _format_value(col, row.get(col))
            css_class = _score_class(row.get("score")) if col == "score" else ""
            cls_attr = f' class="{css_class}"' if css_class else ""
            cells.append(f"<td{cls_attr}>{val}</td>")
        html += f"            <tr>{''.join(cells)}</tr>\n"

    html += _HTML_TEMPLATE_FOOTER

    content = html.encode("utf-8")
    bytes_buf = io.BytesIO(content)
    bytes_buf.seek(0)

    logger.info("  ✅ HTML généré ({:.0f} Ko)", len(content) / 1024)
    return bytes_buf
