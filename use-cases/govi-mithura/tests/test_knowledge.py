"""Tests for deterministic, source-preserving crop retrieval."""

from pathlib import Path

import pytest

import knowledge
from knowledge import load_documents, search_crop_documents


def test_knowledge_base_contains_three_topics_per_mvp_crop() -> None:
    documents = load_documents()

    assert sum(document.crop == "chili" for document in documents) >= 3
    assert sum(document.crop == "paddy" for document in documents) >= 3
    assert all(document.source_url.startswith("https://") for document in documents)


def test_chili_leaf_curl_retrieves_expected_document() -> None:
    result = search_crop_documents("chilli", "upward curling leaves with yellow veins and whiteflies")

    assert result["status"] == "ok"
    assert result["matches"][0]["document_id"] == "chili-leaf-curl"
    assert result["matches"][0]["source_publisher"] == "Department of Agriculture Sri Lanka"


def test_paddy_hopperburn_retrieves_expected_document() -> None:
    result = search_crop_documents("rice", "orange yellow hopperburn with insects at tiller base")

    assert result["matches"][0]["document_id"] == "paddy-planthopper"


def test_irrelevant_query_returns_no_match() -> None:
    result = search_crop_documents("paddy", "smartphone battery charging cable")

    assert result == {"status": "no_relevant_match", "crop": "paddy", "matches": []}


def test_retrieval_returns_structured_unsupported_crop() -> None:
    assert search_crop_documents("tea", "yellow leaves") == {
        "status": "unsupported_crop",
        "crop": "tea",
        "supported_crops": ["chili", "paddy"],
        "matches": [],
    }


def test_explicit_empty_document_corpus_does_not_fall_back_to_disk() -> None:
    assert search_crop_documents("chili", "leaf curl", documents=[]) == {
        "status": "no_relevant_match",
        "crop": "chili",
        "matches": [],
    }


def test_static_knowledge_documents_are_parsed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    load_documents.cache_clear()
    parse_count = 0
    original = knowledge._parse_document

    def counting_parse(path: Path) -> knowledge.CropDocument:
        nonlocal parse_count
        parse_count += 1
        return original(path)

    monkeypatch.setattr(knowledge, "_parse_document", counting_parse)
    first = load_documents()
    second = load_documents()

    assert first == second
    assert parse_count == len(first)
