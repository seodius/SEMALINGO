"""Glottolog: languages, dialects and families, into the languages reference table.

Other sources name languages by Glottocode, so this table gives every form a language
family and macroarea: the basis for "how many language families" counts and the gap map.
"""

from __future__ import annotations

from ..cldf import to_float
from .base import CLDFLoader, register


def joined(value):
    """Glottolog lists several macroareas for some languages; pycldf returns them as a list."""
    return "; ".join(value) if isinstance(value, list) else value


@register
class GlottologLoader(CLDFLoader):
    source_id = "glottolog"
    repo = "glottolog/glottolog-cldf"
    ref = "v5.3"
    tables = ("languages.csv",)

    def read(self, folder, writer):
        rows = list(self.dataset(folder).table("LanguageTable"))
        names = {row["ID"]: row.get("Name") for row in rows}
        for row in rows:
            family = row.get("Family_ID")
            writer.language(
                row["ID"],
                name=row.get("Name"),
                iso639_3=row.get("ISO639P3code"),
                level=row.get("Level"),
                family_id=family,
                family_name=names.get(family) if family else None,
                parent_language=row.get("Language_ID"),
                macroarea=joined(row.get("Macroarea")),
                latitude=to_float(row.get("Latitude")),
                longitude=to_float(row.get("Longitude")),
            )
