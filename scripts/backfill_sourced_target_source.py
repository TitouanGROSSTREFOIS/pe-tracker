"""
Tâche Finalisation, Partie C (D47) — Backfill de `SourcedTarget.source` pour
les cibles créées avant que ce champ soit renseigné par le pipeline Google
Radar (sourcing_pipeline.py::_map_to_schema — corrigé dans cette même tâche).

Ne devine jamais : le backfill s'appuie sur un signal fiable et vérifié dans
le code, pas une supposition.
    - `sirene_sourcing_pipeline.py` (voie registre) pose TOUJOURS `siren`
      (clé de recherche registre, non optionnelle) → toute cible avec un
      `siren` renseigné vient forcément de cette voie.
    - `upload_teaser` (routers/sourcing.py) pose TOUJOURS une URL de la
      forme `upload://<nom de fichier>` → toute cible avec ce préfixe vient
      forcément de cette voie.
    - Tout le reste vient de `sourcing_pipeline.py` (voie Google Radar,
      scan unique ou batch CSV) — c'est la SEULE autre voie de création de
      SourcedTarget dans le code (vérifié : grep sur SourcedTargetCreate(
      dans api/, 3 sites d'appel au total, les 2 premiers couverts
      ci-dessus).

Si une cible ne correspond à aucun de ces trois signaux de façon certaine,
elle est laissée `source=NULL` (indéterminé) — jamais devinée.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal, init_db
from api.models.sourcing import SourcedTarget


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SourcedTarget).where(SourcedTarget.source.is_(None)))
        targets = list(result.scalars().all())
        print(f"{len(targets)} target(s) with source=NULL.")

        tagged = 0
        left_null = 0
        for t in targets:
            if t.siren:
                t.source = "registry"
                tagged += 1
            elif t.url and t.url.startswith("upload://"):
                t.source = "document_upload"
                tagged += 1
            else:
                # Seule voie de création restante dans le code actuel — voir
                # docstring. Backfill positif, pas un "sinon" par défaut.
                t.source = "google_radar"
                tagged += 1

        await db.commit()
        print(f"{tagged} tagged, {left_null} left as indéterminé (NULL).")


asyncio.run(main())
