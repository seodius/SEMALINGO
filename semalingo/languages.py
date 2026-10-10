"""Language codes. Forms carry a Glottocode, so words from different sources can be compared.

The table below maps the ISO 639-1 codes that Concepticon uses for its gloss lookup tables
(mappings/map-<code>.tsv) to Glottocodes. The Glottocodes are the ones Concepticon itself
assigns to these languages (concepticon-cldf v3.4.2, cldf/languages.csv).
"""

from __future__ import annotations

ENGLISH = "stan1293"
DUTCH = "dutc1256"
GERMAN = "stan1295"

ISO1_GLOTTOCODE = {
    "af": "afri1274",  # Afrikaans
    "ar": "stan1318",  # Standard Arabic
    "az": "nort2697",  # North Azerbaijani
    "ca": "stan1289",  # Catalan
    "cy": "wels1247",  # Welsh
    "da": "dani1285",  # Danish
    "de": GERMAN,
    "el": "mode1248",  # Modern Greek
    "en": ENGLISH,
    "es": "stan1288",  # Spanish
    "et": "esto1258",  # Estonian
    "fa": "west2369",  # Western Farsi
    "fi": "finn1318",  # Finnish
    "fr": "stan1290",  # French
    "ga": "iris1253",  # Irish
    "ha": "haus1257",  # Hausa
    "he": "hebr1245",  # Modern Hebrew
    "hu": "hung1274",  # Hungarian
    "is": "icel1247",  # Icelandic
    "it": "ital1282",  # Italian
    "ja": "nucl1643",  # Japanese
    "ka": "nucl1302",  # Georgian
    "la": "lati1261",  # Latin
    "lb": "luxe1241",  # Luxembourgish
    "lt": "lith1251",  # Lithuanian
    "mr": "mara1378",  # Marathi
    "mt": "malt1254",  # Maltese
    "nl": DUTCH,
    "no": "norw1258",  # Norwegian
    "pl": "poli1260",  # Polish
    "pt": "port1283",  # Portuguese
    "ru": "russ1263",  # Russian
    "sk": "slov1269",  # Slovak
    "sr": "serb1264",  # Serbian
    "sv": "swed1254",  # Swedish
    "tr": "nucl1301",  # Turkish
    "uk": "ukra1253",  # Ukrainian
    "vi": "viet1252",  # Vietnamese
    "wo": "nucl1347",  # Wolof
    "xh": "xhos1239",  # Xhosa
    "zh": "mand1415",  # Mandarin Chinese
}
