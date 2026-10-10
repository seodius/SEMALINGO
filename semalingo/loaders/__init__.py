"""Loaders: one per source, each writing into the core tables.

Every loader follows the same contract (see `base.Loader`): fetch the raw files into the
pinned raw layer, then load them into the core tables. Importing this package registers
all loaders in LOADERS, keyed by source id.
"""

from .base import LOADERS, CLDFLoader, Loader, ManualLoader, ManualSourceMissing, register  # noqa: F401
from . import clics, concepticon, datsemshift, frequencies, glottolog, oewn, wold  # noqa: F401  (registers the loaders)

__all__ = ["LOADERS", "CLDFLoader", "Loader", "ManualLoader", "ManualSourceMissing", "register"]
