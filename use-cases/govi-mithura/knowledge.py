"""Small, deterministic retrieval layer for the curated crop knowledge base."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from farmer_profile import normalize_crop, normalized

DEFAULT_KB_PATH = Path(__file__).parent / "data" / "crop_kb"
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


@dataclass(frozen=True)
class CropDocument:
    """Validated retrieval document and its human-readable provenance."""

    document_id: str
    crop: str
    title: str
    keywords: tuple[str, ...]
    source_title: str
    source_publisher: str
    source_url: str
    source_date: str
    body: str
    keyword_tokens: frozenset[str]
    title_tokens: frozenset[str]
    body_tokens: frozenset[str]

    def as_match(self, score: float) -> dict[str, Any]:
        """Return a structured, prompt-safe representation of a retrieval match."""
        return {
            "document_id": self.document_id,
            "crop": self.crop,
            "title": self.title,
            "score": round(score, 3),
            "excerpt": self.body,
            "source_title": self.source_title,
            "source_publisher": self.source_publisher,
            "source_url": self.source_url,
            "source_date": self.source_date,
        }


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in TOKEN_PATTERN.findall(value))


def _parse_document(path: Path) -> CropDocument:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"Knowledge document must contain YAML front matter: {path}")
    raw_front_matter, body = text[4:].split("\n---\n", maxsplit=1)
    metadata = yaml.safe_load(raw_front_matter)
    required = {
        "document_id",
        "crop",
        "title",
        "keywords",
        "source_title",
        "source_publisher",
        "source_url",
        "source_date",
    }
    missing = required - set(metadata)
    if missing:
        raise ValueError(f"Knowledge document {path} is missing: {sorted(missing)}")
    keywords = tuple(str(value).casefold() for value in metadata["keywords"])
    title = str(metadata["title"])
    text = body.strip()
    return CropDocument(
        document_id=str(metadata["document_id"]),
        crop=normalize_crop(str(metadata["crop"])),
        title=title,
        keywords=keywords,
        source_title=str(metadata["source_title"]),
        source_publisher=str(metadata["source_publisher"]),
        source_url=str(metadata["source_url"]),
        source_date=str(metadata["source_date"]),
        body=text,
        keyword_tokens=_tokens(" ".join(keywords)),
        title_tokens=_tokens(title),
        body_tokens=_tokens(text),
    )


@lru_cache(maxsize=None)
def load_documents(kb_path: Path = DEFAULT_KB_PATH) -> tuple[CropDocument, ...]:
    """Load all curated Markdown documents in stable filename order."""
    return tuple(_parse_document(path) for path in sorted(kb_path.glob("*.md")))


def search_crop_documents(
    crop: str,
    query: str,
    top_k: int = 3,
    *,
    documents: Sequence[CropDocument] | None = None,
) -> dict[str, Any]:
    """Rank supported-crop documents using transparent lexical scoring."""
    try:
        canonical_crop = normalize_crop(crop)
    except ValueError:
        return {
            "status": "unsupported_crop",
            "crop": crop.strip(),
            "supported_crops": ["chili", "paddy"],
            "matches": [],
        }
    if not 1 <= top_k <= 5:
        raise ValueError("top_k must be between 1 and 5.")

    query_tokens = _tokens(query)
    if not query_tokens:
        return {"status": "no_relevant_match", "crop": canonical_crop, "matches": []}

    ranked: list[tuple[float, CropDocument]] = []
    corpus = documents if documents is not None else load_documents()
    query_text = normalized(query)
    for document in corpus:
        if document.crop != canonical_crop:
            continue
        score = (
            4.0 * len(query_tokens & document.keyword_tokens)
            + 2.0 * len(query_tokens & document.title_tokens)
            + 0.25 * len(query_tokens & document.body_tokens)
        )
        score += 5.0 * sum(1 for keyword in document.keywords if " " in keyword and keyword in query_text)
        if score > 0:
            ranked.append((score, document))

    ranked.sort(key=lambda item: (-item[0], item[1].document_id))
    matches = [document.as_match(score) for score, document in ranked[:top_k]]
    return {
        "status": "ok" if matches else "no_relevant_match",
        "crop": canonical_crop,
        "matches": matches,
    }


def crop_kb_search(crop: str, query: str, top_k: int = 3) -> str:
    """Search trusted chili or paddy guidance using concise English symptom keywords.

    Translate a Sinhala symptom description into English search terms before calling.
    The returned JSON contains evidence and source metadata; do not claim a diagnosis from it.
    """
    return json.dumps(search_crop_documents(crop, query, top_k), ensure_ascii=False)
