"""Full English norm lists: Kuperman age of acquisition and Brysbaert concreteness.

NoRaRe already carries both, but only for the words it links to Concepticon (about 2,600
each). These loaders read the complete lists from Hugging Face mirrors, pinned to a commit
and checked against a SHA-256 checksum.

Node ids: "kuperman-aoa:<word>" and "brysbaert-concreteness:<word>" (forms, English);
every column becomes a property, described in property_types.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import ClassVar

from ..cldf import to_float
from ..fetch import download, write_source_info
from ..languages import ENGLISH
from .base import Loader, register
from .frequencies import word_id

HUGGING_FACE = "https://huggingface.co/datasets"


class HuggingFaceCsvLoader(Loader):
    """A CSV file in a Hugging Face dataset repository, pinned to a commit and a checksum."""

    repo: ClassVar[str]
    commit: ClassVar[str]
    filename: ClassVar[str]
    sha256: ClassVar[str]
    word_column: ClassVar[str] = "Word"
    # column -> (property, value kind "num" or "text", property_types fields)
    columns: ClassVar[dict[str, tuple[str, str, dict]]]

    @classmethod
    def url(cls) -> str:
        return f"{HUGGING_FACE}/{cls.repo}/resolve/{cls.commit}/{cls.filename}"

    def download(self, folder: Path) -> None:
        path = download(self.url(), folder / self.filename)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != self.sha256:
            path.unlink()
            raise RuntimeError(f"{self.source_id}: sha256 {digest} does not match the pinned {self.sha256}")
        write_source_info(folder, source=self.source_id, url=self.url(), ref=self.ref, commit=self.commit,
                          sha256=self.sha256, files=[self.filename])

    def read(self, folder, writer):
        for name, kind, fields in self.columns.values():
            writer.property_type(name, language=ENGLISH, **fields)
        with open(folder / self.filename, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                word = (row.get(self.word_column) or "").strip()
                if not word:
                    continue
                node = self.node(word_id(word))
                writer.form(node, ENGLISH, word)
                for column, (name, kind, _) in self.columns.items():
                    value = row.get(column)
                    if kind == "num":
                        writer.prop(node, name, to_float(value))
                    elif value not in (None, "", "0", "NA") and value.strip() != word:
                        writer.prop(node, name, value.strip())


RATINGS = dict(category="ratings", method="users")
CORPUS = dict(category="norms", method="corpus")


@register
class KupermanAoaLoader(HuggingFaceCsvLoader):
    source_id = "kuperman-aoa"
    repo = "StephanAkkerman/English-Age-of-Acquisition"
    commit = "e3a18bb843650b0441de107a6c17373481c1b365"
    ref = "hf-e3a18bb"
    filename = "en.aoa.csv"
    sha256 = "0f9e3ed9d3763a9b493dcdb33ab0988764e7b56c04661b6e5975362ad1f8e744"
    columns = {
        "AoA_Kup": ("aoa_mean", "num", dict(construct="aoa", statistic="mean", **RATINGS,
                    description="Mean rated age of acquisition in years (Kuperman et al. 2012).")),
        "Perc_known": ("known_share", "num", dict(construct="familiarity", statistic="percentage", **RATINGS,
                       description="Share of raters who knew the word (0-1).")),
        "AoA_Kup_lem": ("aoa_mean_lemma", "num", dict(construct="aoa", aspect="lemma", statistic="mean", **RATINGS,
                        description="Kuperman AoA of the word's lemma; fills in inflected forms that were not rated.")),
        "Perc_known_lem": ("known_share_lemma", "num", dict(construct="familiarity", aspect="lemma", statistic="percentage", **RATINGS,
                           description="Share of raters who knew the lemma (0-1).")),
        "AoA_Bird_lem": ("aoa_bird_lemma", "num", dict(construct="aoa", aspect="lemma", statistic="mean", **RATINGS,
                         description="Lemma AoA from the Bird et al. norms, as included in the list.")),
        "AoA_Bristol_lem": ("aoa_bristol_lemma", "num", dict(construct="aoa", aspect="lemma", statistic="mean", **RATINGS,
                            description="Lemma AoA from the Bristol norms, as included in the list.")),
        "AoA_Cort_lem": ("aoa_cortese_lemma", "num", dict(construct="aoa", aspect="lemma", statistic="mean", **RATINGS,
                         description="Lemma AoA from the Cortese norms, as included in the list.")),
        "AoA_Schock": ("aoa_schock", "num", dict(construct="aoa", statistic="mean", **RATINGS,
                       description="AoA from the Schock norms, as included in the list.")),
        "Freq_pm": ("freq_pm", "num", dict(construct="frequency", statistic="per million", **CORPUS,
                    description="SUBTLEX-US frequency per million words.")),
        "Dom_PoS_SUBTLEX": ("dominant_pos", "text", dict(construct="part of speech", statistic="dominant", **CORPUS,
                            description="Most frequent part of speech in SUBTLEX-US.")),
        "Lemma_highest_PoS": ("lemma", "text", dict(construct="lemma", statistic="dominant", **CORPUS,
                              description="Lemma of the word in its most frequent part of speech.")),
        "Alternative.spelling": ("alternative_spelling", "text", dict(construct="spelling", description="Alternative spelling.")),
        "Nletters": ("letters", "num", dict(construct="length", aspect="letters", statistic="count", description="Number of letters.")),
        "Nphon": ("phonemes", "num", dict(construct="length", aspect="phonemes", statistic="count", description="Number of phonemes.")),
        "Nsyll": ("syllables", "num", dict(construct="length", aspect="syllables", statistic="count", description="Number of syllables.")),
    }


@register
class BrysbaertConcretenessLoader(HuggingFaceCsvLoader):
    source_id = "brysbaert-concreteness"
    repo = "StephanAkkerman/concreteness-ratings"
    commit = "10f460a4d535800d89c579db7cd2664dbaf6b1d6"
    ref = "hf-10f460a"
    filename = "concreteness_ratings.csv"
    sha256 = "dd0cbb72b2fb0867c0de66a26cfa8624cfbbeb514b90116c969840f01109e453"
    columns = {
        "Conc.M": ("concreteness_mean", "num", dict(construct="concreteness", statistic="mean", **RATINGS,
                   description="Mean concreteness rating, 1 (abstract) to 5 (concrete) (Brysbaert et al. 2014).")),
        "Conc.SD": ("concreteness_sd", "num", dict(construct="concreteness", statistic="standard deviation", **RATINGS,
                    description="Standard deviation of the concreteness ratings.")),
        "Percent_known": ("known_share", "num", dict(construct="familiarity", statistic="percentage", **RATINGS,
                          description="Share of raters who knew the word (0-1).")),
        "Total": ("raters", "num", dict(construct="raters", statistic="count", **RATINGS, description="Number of ratings.")),
        "Unknown": ("unknown_count", "num", dict(construct="familiarity", aspect="unknown", statistic="count", **RATINGS,
                    description="Number of raters who did not know the word.")),
        "Bigram": ("bigram", "num", dict(construct="multiword", statistic="indicator", description="1 for a two-word expression.")),
        "SUBTLEX": ("subtlex_count", "num", dict(construct="frequency", statistic="count", **CORPUS,
                    description="SUBTLEX-US frequency count.")),
        "Dom_Pos": ("dominant_pos", "text", dict(construct="part of speech", statistic="dominant", **CORPUS,
                    description="Most frequent part of speech in SUBTLEX-US (missing for some words).")),
    }
