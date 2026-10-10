"""Word-frequency sources: SUBTLEX-US, SUBTLEX-NL, SUBTLEX-UK and childLex.

Each word becomes a form "<source>:<word>" with properties freq_count, zipf and, where the
source has them, cd_count (number of films or programmes) and dominant_pos. Zipf values are
computed the same way for every source (see frequency.zipf_values), so they can be compared.
SUBTLEX-NL, SUBTLEX-UK and childLex are manual downloads; SUBTLEX-US is fetched.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from collections import defaultdict
from pathlib import Path

from ..cldf import to_float
from ..fetch import download, write_source_info
from ..frequency import is_word, xlsx_rows, zipf_values
from .base import Loader, ManualLoader, register


def word_id(word: str) -> str:
    """A node-id-safe local id for a word (whitespace becomes '_')."""
    return "_".join(str(word).split())


class FrequencyTable:
    """Collects words with counts and extra properties, then writes forms and properties."""

    def __init__(self, loader: Loader, language: str):
        self.loader = loader
        self.language = language
        self.counts: dict[str, float] = {}
        self.extra: dict[str, dict] = defaultdict(dict)

    def add(self, word, count, **extra) -> None:
        if not is_word(word) or count is None:
            return
        word = str(word).strip()
        if word in self.counts:  # keep the first (most frequent) spelling variant
            return
        self.counts[word] = float(count)
        self.extra[word] = extra

    def write(self, writer, prefix: str = "") -> None:
        zipf = zipf_values(self.counts)
        for word, count in self.counts.items():
            node = self.loader.node(prefix + word_id(word))
            writer.form(node, self.language, word)
            writer.prop(node, "freq_count", count)
            writer.prop(node, "zipf", round(zipf[word], 4))
            for name, value in self.extra[word].items():
                writer.prop(node, name, value)


@register
class SubtlexUsLoader(Loader):
    source_id = "subtlex-us"
    ref = "openlexicon-ee7be8db"
    url = "http://www.lexique.org/databases/SUBTLEX-US/SUBTLEXus74286wordstextversion.tsv"
    md5 = "ee7be8db21f26e1925ac0ea3ab598f32"
    filename = "SUBTLEXus74286wordstextversion.tsv"

    def download(self, folder: Path) -> None:
        path = download(self.url, folder / self.filename)
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        if digest != self.md5:
            path.unlink()
            raise RuntimeError(f"subtlex-us: md5 {digest} does not match the pinned {self.md5}")
        write_source_info(folder, source=self.source_id, url=self.url, ref=self.ref, md5=self.md5, files=[self.filename])

    def read(self, folder, writer):
        table = FrequencyTable(self, "eng")
        with open(folder / self.filename, encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                table.add(row.get("Word"), to_float(row.get("FREQcount")), cd_count=to_float(row.get("CDcount")))
        table.write(writer)


@register
class SubtlexNlLoader(ManualLoader):
    source_id = "subtlex-nl"
    ref = "pos-zipf"
    files = ("SUBTLEX-NL with pos and Zipf.xlsx",)
    instructions = "the SUBTLEX-NL Excel file with part of speech and Zipf values, from osf.io/3d8cx"

    def read(self, folder, writer):
        table = FrequencyTable(self, "nld")
        for row in xlsx_rows(folder / self.files[0]):
            table.add(
                row.get("Word"), to_float(row.get("FREQcount")),
                cd_count=to_float(row.get("CDcount")),
                dominant_pos=row.get("dominant.pos"),
                dominant_lemma=row.get("dominant.pos.lemma"),
            )
        table.write(writer)


@register
class SubtlexUkLoader(ManualLoader):
    source_id = "subtlex-uk"
    ref = "all"
    files = ("SUBTLEX-UK_all.xlsx",)
    instructions = "SUBTLEX-UK_all.xlsx from the SUBTLEX-UK download"

    def read(self, folder, writer):
        table = FrequencyTable(self, "eng")
        for row in xlsx_rows(folder / self.files[0]):
            table.add(
                row.get("Spelling"), to_float(row.get("Freq")),
                cd_count=to_float(row.get("CDCount")),
                dominant_pos=row.get("DomPoS"),
            )
        table.write(writer)


@register
class ChildlexLoader(ManualLoader):
    source_id = "childlex"
    ref = "sqlite"
    files = ("childlex",)
    instructions = "the childLex SQLite database (a file named childlex)"

    def read(self, folder, writer):
        conn = sqlite3.connect(f"file:{folder / self.files[0]}?mode=ro", uri=True)
        try:
            words = FrequencyTable(self, "deu")
            for word, count in conn.execute("SELECT w, f FROM w ORDER BY f DESC"):
                words.add(word, count)
            words.write(writer)

            lemmas = FrequencyTable(self, "deu")
            for lemma, count in conn.execute("SELECT l, f FROM l ORDER BY f DESC"):
                lemmas.add(lemma, count)
            lemmas.write(writer, prefix="lemma/")

            pairs: dict[tuple[str, str], float] = defaultdict(float)
            for word, lemma, count in conn.execute("SELECT w, l, f FROM lex"):
                if word in words.counts and lemma in lemmas.counts:
                    pairs[(word, lemma)] += count
            for (word, lemma), count in pairs.items():
                writer.relation(self.node(word_id(word)), self.node("lemma/" + word_id(lemma)), "has_lemma", count)
        finally:
            conn.close()
