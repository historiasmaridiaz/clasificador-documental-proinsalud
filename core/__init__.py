"""Núcleo del clasificador documental TRD/CCD."""

from .catalog import build_catalog_from_files, load_catalog_json
from .ml_engine import DocumentClassifier

__all__ = ["build_catalog_from_files", "load_catalog_json", "DocumentClassifier"]

