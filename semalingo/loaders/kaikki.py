"""Wiktionary through Kaikki (wiktextract): English and Dutch words with their morphology.

Kaikki publishes the English Wiktionary as JSON lines, one file per language, rebuilt about
once a week; old files are not kept. So the raw layer holds one snapshot ("snapshot"), with
the extraction date, the Wiktionary dump date and a checksum in SOURCE.json, and the version
recorded on load is that date. `semalingo fetch kaikki-en --force` takes the newest snapshot.

Node ids: one form per written word, "kaikki-en:<word>" (or kaikki-nl), all parts of speech
together, with properties pos, gloss (first sense), sense_count (senses that are not just
inflected forms), ipa and etymology_source (e.g. "inh:enm", "bor:fr"). Entries that are only
inflected forms ("eyes") are skipped.

Morphology comes from the etymology templates (af/affix, prefix, suffix, confix, compound,
surf): "readable" -> "read" (has_base) and "-able" (has_suffix); "unhappy" -> "un-"
(has_prefix); "woordenboek" -> "woord", "-en-" (has_interfix), "boek"; "eyeball" -> "eye",
"ball" (has_part, a compound: two or more bases and no affix). Affixes are forms too, so
`-able` gets an in-degree that counts the words built with it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import urllib.request
from pathlib import Path
from typing import ClassVar, Iterator

from ..fetch import TIMEOUT, USER_AGENT, write_source_info
from ..languages import DUTCH, ENGLISH
from .base import Loader, register
from .frequencies import word_id

KAIKKI = "https://kaikki.org/dictionary"
AFFIX = {"af", "affix", "surf", "surface analysis"}
PREFIX = {"pre", "prefix"}
SUFFIX = {"suf", "suffix"}
CONFIX = {"con", "confix"}
COMPOUND = {"com", "compound"}
ORIGIN = {"inh", "inh+", "bor", "bor+", "lbor", "ubor", "slbor", "obor", "der", "der+", "cal", "sl"}
INLINE = re.compile(r"<[^<>]*>")
DATES = re.compile(r"extracted on (\d{4}-\d{2}-\d{2}) from the (\w+) dump dated (\d{4}-\d{2}-\d{2})")


def template_parts(template: dict, lang_code: str) -> list[tuple[str, str]]:
    """(part, role) for a morphology template, roles: prefix, suffix, interfix, base."""
    name = template.get("name")
    args = template.get("args") or {}
    if args.get("1") != lang_code:
        return []
    raw = [args[k] for k in sorted((k for k in args if k.isdigit() and k != "1"), key=int)]
    parts = [INLINE.sub("", p).strip() for p in raw]
    parts = [p for p in parts if p and ":" not in p]  # "la:dīcō" is a part from another language
    if not parts:
        return []
    if name in PREFIX:
        return [(p if p.endswith("-") else p + "-", "prefix") for p in parts[:-1]] + [(parts[-1], "base")]
    if name in SUFFIX:
        return [(parts[0], "base")] + [(p if p.startswith("-") else "-" + p, "suffix") for p in parts[1:]]
    if name in CONFIX:
        if len(parts) == 2:
            return [(parts[0].rstrip("-") + "-", "prefix"), ("-" + parts[1].lstrip("-"), "suffix")]
        return [(parts[0].rstrip("-") + "-", "prefix")] + [(p, "base") for p in parts[1:-1]] + [("-" + parts[-1].lstrip("-"), "suffix")]
    if name in AFFIX or name in COMPOUND:
        roles = []
        for p in parts:
            if p.startswith("-") and p.endswith("-") and len(p) > 2:
                roles.append((p, "interfix"))
            elif p.endswith("-") and len(p) > 1:
                roles.append((p, "prefix"))
            elif p.startswith("-") and len(p) > 1:
                roles.append((p, "suffix"))
            else:
                roles.append((p, "base"))
        return roles
    return []


def morphology(entry: dict) -> list[tuple[str, str]]:
    """(part, relation type) from the first morphology template of an entry."""
    lang_code = entry.get("lang_code")
    for template in entry.get("etymology_templates") or []:
        parts = template_parts(template, lang_code)
        if len(parts) < 2:
            continue
        bases = [p for p, role in parts if role == "base"]
        compound = len(bases) >= 2 and len(bases) == len(parts)
        return [(p, "has_part" if compound else f"has_{role}") for p, role in parts]
    return []


def origin(entry: dict) -> str | None:
    for template in entry.get("etymology_templates") or []:
        if template.get("name") in ORIGIN:
            source = (template.get("args") or {}).get("2")
            if source:
                return f"{template['name']}:{source}"
    return None


def lemma_senses(entry: dict) -> list[dict]:
    """Senses that are not just inflected forms of another word."""
    return [s for s in entry.get("senses") or [] if not s.get("form_of") and "form-of" not in (s.get("tags") or [])]


class KaikkiLoader(Loader):
    language_name: ClassVar[str]   # Kaikki's name for the language, e.g. "English"
    lang_code: ClassVar[str]       # Wiktionary code, e.g. "en"
    language: ClassVar[str]        # Glottocode
    ref = "snapshot"
    filename = "kaikki.jsonl.gz"

    @classmethod
    def url(cls) -> str:
        return f"{KAIKKI}/{cls.language_name}/kaikki.org-dictionary-{cls.language_name}.jsonl"

    def download(self, folder: Path) -> None:
        headers = {"User-Agent": USER_AGENT}
        index = urllib.request.urlopen(urllib.request.Request(f"{KAIKKI}/{self.language_name}/index.html", headers=headers),
                                       timeout=TIMEOUT).read().decode("utf-8", "replace")
        dates = DATES.search(index)
        target, partial = folder / self.filename, folder / (self.filename + ".part")
        request = urllib.request.Request(self.url(), headers={**headers, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
                with open(partial, "wb") as out:
                    shutil.copyfileobj(response, out, length=1 << 20)
            else:
                with gzip.open(partial, "wb") as out:
                    shutil.copyfileobj(response, out, length=1 << 20)
            last_modified = response.headers.get("Last-Modified")
        partial.replace(target)
        digest = hashlib.sha256()
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        write_source_info(
            folder, source=self.source_id, url=self.url(), files=[self.filename], sha256_gz=digest.hexdigest(),
            last_modified=last_modified, extracted=dates.group(1) if dates else None,
            dump=f"{dates.group(2)} {dates.group(3)}" if dates else None,
        )

    def version(self, folder: Path) -> str:
        try:
            info = json.loads((folder / "SOURCE.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.ref
        if info.get("extracted"):
            return f"snapshot of {info['extracted']} ({info.get('dump') or 'dump date unknown'})"
        return self.ref

    def entries(self, folder: Path) -> Iterator[dict]:
        with gzip.open(folder / self.filename, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def read(self, folder, writer):
        for name, fields in {
            "pos": dict(construct="part of speech", description="Parts of speech of the word's Wiktionary entries."),
            "gloss": dict(construct="definition", description="First gloss of the first sense."),
            "sense_count": dict(construct="polysemy", statistic="count", description="Number of senses, not counting inflected forms."),
            "ipa": dict(construct="pronunciation", description="First IPA transcription."),
            "etymology_source": dict(construct="etymology", description="First inherited/borrowed/derived template: relation and source language code."),
        }.items():
            writer.property_type(name, category="norms", method="dictionary", language=self.language, **fields)

        words: dict[str, dict] = {}
        for entry in self.entries(folder):
            if entry.get("lang_code") != self.lang_code:
                continue
            word = (entry.get("word") or "").strip()
            senses = lemma_senses(entry)
            if not word or not senses:
                continue  # an inflected form only
            info = words.setdefault(word, {"pos": [], "gloss": None, "senses": 0, "ipa": None, "origin": None, "parts": []})
            if entry.get("pos") and entry["pos"] not in info["pos"]:
                info["pos"].append(entry["pos"])
            info["senses"] += len(senses)
            if info["gloss"] is None:
                glosses = senses[0].get("glosses") or senses[0].get("raw_glosses") or []
                info["gloss"] = glosses[0][:300] if glosses else None
            if info["ipa"] is None:
                info["ipa"] = next((s["ipa"] for s in entry.get("sounds") or [] if s.get("ipa")), None)
            info["origin"] = info["origin"] or origin(entry)
            if not info["parts"]:
                info["parts"] = morphology(entry)

        nodes = {}
        for word, info in words.items():
            node = nodes[word] = self.node(word_id(word))
            writer.form(node, self.language, word)
            writer.prop(node, "pos", ", ".join(info["pos"]))
            writer.prop(node, "gloss", info["gloss"])
            writer.prop(node, "sense_count", info["senses"])
            writer.prop(node, "ipa", info["ipa"])
            writer.prop(node, "etymology_source", info["origin"])
        for word, info in words.items():
            for part, relation in info["parts"]:
                target = nodes.get(part)
                if target is None:  # a part without its own entry still becomes a form
                    target = nodes[part] = self.node(word_id(part))
                    writer.form(target, self.language, part)
                writer.relation(nodes[word], target, relation)


@register
class KaikkiEnglishLoader(KaikkiLoader):
    source_id = "kaikki-en"
    language_name = "English"
    lang_code = "en"
    language = ENGLISH


@register
class KaikkiDutchLoader(KaikkiLoader):
    source_id = "kaikki-nl"
    language_name = "Dutch"
    lang_code = "nl"
    language = DUTCH
