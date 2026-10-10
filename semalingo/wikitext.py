"""Small helpers for reading word lists out of MediaWiki wikitext (Wiktionary, Wikipedia).

Only what the word-list pages need: drop references, comments and templates, turn links into
their display text, and split a page into sections.
"""

from __future__ import annotations

import html
import re

REFERENCE = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
LINK = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]")
HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.M)


def strip_templates(text: str) -> str:
    """Remove {{...}} templates, including nested ones."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif depth and text.startswith("}}", i):
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def clean(text: str) -> str:
    """Wikitext without comments, references and templates.

    Comments go first: a comment can mention "<ref>", which would otherwise open a reference
    that swallows everything up to the next "</ref>".
    """
    return strip_templates(REFERENCE.sub("", COMMENT.sub("", text)))


def link_text(match: re.Match) -> str:
    target, display = match.group(1), match.group(2)
    if display is not None:
        return display
    return target.split(":")[-1] if ":" in target else target


WORD_PREFIXES = ("", "wikt")  # plain links and links to a Wiktionary entry ("[[wikt:a|a]]") name words


def links(text: str) -> list[str]:
    """Display texts of links to words: plain links and Wiktionary links.

    Links into other namespaces or wikis ("[[:simple:Wiktionary:...|Pictures of these words]]",
    "[[Category:...]]") are skipped.
    """
    found = []
    for match in LINK.finditer(text):
        target = match.group(1).lstrip(":")
        prefix = target.split(":", 1)[0].lower() if ":" in target else ""
        if prefix not in WORD_PREFIXES:
            continue
        found.append(link_text(match).strip())
    return [f for f in found if f]


def plain(text: str) -> str:
    """Text with links replaced by their display text, HTML tags removed, entities decoded."""
    text = LINK.sub(link_text, text)
    text = TAG.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    return " ".join(html.unescape(text).split())


def sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) for each section; the text before the first heading has heading ''."""
    parts = []
    last_heading, last_end = "", 0
    for match in HEADING.finditer(text):
        parts.append((last_heading, text[last_end:match.start()]))
        last_heading, last_end = plain(match.group(2)), match.end()
    parts.append((last_heading, text[last_end:]))
    return parts
