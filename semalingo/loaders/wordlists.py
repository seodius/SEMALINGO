"""Word lists published on Wiktionary and Wikipedia, each pinned to one page revision.

Every list word becomes an English form "<source>:<word>" with a "category" property (the
list's own grouping, e.g. "things (picturable)" in Basic English). The NSM page gives semantic
primes: concepts "nsm-primes:<prime>" (kind "prime") with their English exponents as forms
"nsm-primes:form/<word>" that "express" them.

The raw layer keeps the page's wikitext exactly as fetched (index.php?action=raw&oldid=...).
Link words to Concepticon afterwards with `semalingo match <source>`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import ClassVar, Iterator
from urllib.parse import quote

from ..fetch import download, write_source_info
from ..languages import ENGLISH
from ..wikitext import clean, links, plain, sections
from .base import Loader, register
from .frequencies import word_id

DASH = re.compile(r"\s+(?:–|—|&ndash;|-)\s+|\s+:\s+")
POS = re.compile(r"(?:^|;\s*)(n|v|ad|adj|adv|prep|pro|conj)\.\s")
PARENTHESES = re.compile(r"\s*\([^)]*\)")


class WikiListLoader(Loader):
    """A word list on a MediaWiki page, pinned to a revision id."""

    host: ClassVar[str]  # e.g. https://en.wiktionary.org
    title: ClassVar[str]
    revid: ClassVar[int]
    filename: ClassVar[str] = "page.wikitext"
    property_types: ClassVar[dict[str, dict]] = {
        "category": dict(construct="list category", description="The group the list puts the word in."),
    }

    @classmethod
    def url(cls) -> str:
        return f"{cls.host}/w/index.php?title={quote(cls.title)}&oldid={cls.revid}&action=raw"

    def download(self, folder: Path) -> None:
        download(self.url(), folder / self.filename)
        write_source_info(
            folder, source=self.source_id, url=self.url(), page=f"{self.host}/wiki/{self.title}",
            revid=self.revid, ref=self.ref, files=[self.filename],
        )

    def entries(self, text: str) -> Iterator[tuple[str, str, dict]]:
        """(word, category, other properties) for each list entry."""
        raise NotImplementedError

    def read(self, folder, writer):
        text = clean((folder / self.filename).read_text(encoding="utf-8"))
        for name, fields in self.property_types.items():
            writer.property_type(name, category="norms", method="concept lists", language=ENGLISH, **fields)
        categories: dict[str, list[str]] = defaultdict(list)
        extras: dict[str, dict] = {}
        spelling: dict[str, str] = {}
        for word, category, extra in self.entries(text):
            word = " ".join(word.split()).strip(" ,.;")
            if not word:
                continue
            node = self.node(word_id(word))
            spelling.setdefault(node, word)
            if category and category not in categories[node]:
                categories[node].append(category)
            extras.setdefault(node, extra)
        for node, word in spelling.items():
            writer.form(node, ENGLISH, word)
            writer.prop(node, "category", "; ".join(categories[node]))
            for name, value in extras[node].items():
                writer.prop(node, name, value)


@register
class BasicEnglishLoader(WikiListLoader):
    source_id = "basic-english"
    host = "https://en.wiktionary.org"
    title = "Appendix:Basic_English_word_list"
    revid = 87681413
    ref = f"rev-{revid}"
    CATEGORIES = {
        "operations": "operations",
        "400 general words": "things (general)",
        "things - 200 picturable words": "things (picturable)",
        "qualities - 100 descriptive words": "qualities (general)",
        "qualities - 50 opposites": "qualities (opposites)",
    }

    def entries(self, text):
        for heading, body in sections(text):
            key = heading.lower()
            category = next((v for k, v in self.CATEGORIES.items() if key.startswith(k)), None)
            if category is None:
                continue
            for word in links(body):
                yield word, category, {}


@register
class Basic1000Loader(WikiListLoader):
    source_id = "wiktionary-1000-basic"
    host = "https://en.wiktionary.org"
    title = "Appendix:1000_basic_English_words"
    revid = 78256317
    ref = f"rev-{revid}"

    def entries(self, text):
        body = sections(text)[0][1]  # the whole list sits before the first heading ("See also")
        for line in body.splitlines():
            if line.startswith(":"):
                for word in links(line):
                    yield word, None, {}


@register
class BasicCombinedLoader(WikiListLoader):
    source_id = "basic-english-combined"
    host = "https://simple.wikipedia.org"
    title = "Wikipedia:Basic_English_combined_wordlist"
    revid = 10726644
    ref = f"rev-{revid}"
    LABEL = re.compile(r"^'''(Basic|International|Addendum|Compound|Endings):'''(.*)$")

    def entries(self, text):
        for line in text.splitlines():
            match = self.LABEL.match(line.strip())
            if match:
                for word in links(match.group(2)):
                    yield word, match.group(1).lower(), {}


@register
class VoaSpecialEnglishLoader(WikiListLoader):
    source_id = "voa-special-english"
    host = "https://simple.wikipedia.org"
    title = "Wikipedia:VOA_Special_English_Word_Book"
    revid = 9852045
    ref = f"rev-{revid}"
    property_types = {
        **WikiListLoader.property_types,
        "pos": dict(construct="part of speech", description="Word classes VOA gives (n., v., ad., prep., pro., conj.)."),
        "definition": dict(construct="definition", description="VOA's definition in Special English."),
        "variant": dict(construct="variant", description="A form listed in brackets after the word, e.g. 'an' after 'a'."),
    }

    def entries(self, text):
        for heading, body in sections(text):
            if not heading:
                continue
            category = "core" if len(heading) == 1 else heading.lower()
            for line in body.splitlines():
                if not line.startswith("* "):
                    continue
                if category == "parts of speech":
                    for word in links(line):
                        yield word, category, {}
                    continue
                parts = DASH.split(plain(line[2:]), maxsplit=1)
                head = parts[0]
                definition = parts[1] if len(parts) > 1 else ""
                variants = re.findall(r"\(([^)]*)\)", head)
                word = PARENTHESES.sub("", head)
                pos = POS.findall(definition)
                yield word, category, {
                    "pos": ", ".join(dict.fromkeys(pos)) or None,
                    "definition": POS.sub(lambda m: "; " if m.group(0).startswith(";") else "", definition).strip("; ") or None,
                    "variant": "; ".join(variants) or None,
                }


@register
class MisspellingsLoader(WikiListLoader):
    source_id = "simple-misspellings"
    host = "https://simple.wikipedia.org"
    title = "Commonly_misspelled_words"
    revid = 10740719
    ref = f"rev-{revid}"
    property_types = {
        **WikiListLoader.property_types,
        "misspellings": dict(construct="misspelling", description="Common wrong spellings of the word, with the page's notes."),
    }

    def entries(self, text):
        for heading, body in sections(text):
            if not heading or heading.lower() in ("related pages", "references", "other websites", "notes"):
                continue
            for line in body.splitlines():
                if not line.startswith("* "):
                    continue
                parts = DASH.split(plain(line[2:]), maxsplit=1)
                wrong = parts[1].strip() if len(parts) > 1 else None
                for word in parts[0].split("/"):
                    yield word, None, {"misspellings": wrong}


@register
class NsmPrimesLoader(WikiListLoader):
    source_id = "nsm-primes"
    host = "https://en.wikipedia.org"
    title = "Natural_semantic_metalanguage"
    revid = 1359753587
    ref = f"rev-{revid}"
    ROW = re.compile(r"^\|\s*(.+?)\s*\|\|\s*(.+?)\s*$")

    def primes(self, text: str) -> Iterator[tuple[str, str]]:
        """(category, prime) from the table in the "Semantic primes" section."""
        for heading, body in sections(text):
            if heading.lower() != "semantic primes":
                continue
            for line in body.splitlines():
                match = self.ROW.match(line.strip())
                if match:
                    category = plain(match.group(1))
                    for prime in plain(match.group(2)).split(","):
                        if prime.strip():
                            yield category, prime.strip()

    def read(self, folder, writer):
        text = clean((folder / self.filename).read_text(encoding="utf-8"))
        writer.property_type("category", construct="prime category", language=ENGLISH, description="The group of the prime in the NSM table.")
        for category, prime in self.primes(text):
            # allolexes ("something/thing", "other~else~another") are written with "~" outside brackets
            gloss = re.sub(r"\([^)]*\)|\s*[/~]\s*", lambda m: m.group(0) if m.group(0).startswith("(") else "~", prime).upper()
            node = self.node(re.sub(r"[^a-z0-9]+", "-", prime.lower()).strip("-"))
            writer.concept(node, "prime", gloss)
            writer.prop(node, "category", category)
            for exponent in re.split(r"[/~]", PARENTHESES.sub("", prime)):
                word = " ".join(PARENTHESES.sub("", exponent).split())
                if word:
                    form = self.node(f"form/{word_id(word)}")
                    writer.form(form, ENGLISH, word)
                    writer.relation(form, node, "expresses")
