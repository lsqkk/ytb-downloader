"""Tests for the config module."""

import os
import tempfile

from ytb_downloader.config import get_search_queries, load_config, validate_config

SAMPLE_YAML = """
proxy: "http://127.0.0.1:7890"
cookies: "cookies.txt"
workers: 4
output_dir: "downloads"
max_duration: 300
categories:
  - name: test_category
    target: 10
    queries:
      - "test query 1"
      - "test query 2"
  - name: another_cat
    target: 5
    queries:
      - "another query"
"""


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_YAML)
        tmp_path = f.name

    try:
        config = load_config(tmp_path)
        assert config["proxy"] == "http://127.0.0.1:7890"
        assert config["workers"] == 4
        assert config["max_duration"] == 300
        assert len(config["categories"]) == 2
        assert config["categories"][0]["name"] == "test_category"
        assert config["categories"][0]["target"] == 10
        assert config["categories"][0]["queries"] == ["test query 1", "test query 2"]
    finally:
        os.unlink(tmp_path)


def test_load_config_defaults():
    """Non-existent file should return defaults."""
    config = load_config("/nonexistent/path/config.yaml")
    assert config["workers"] == 3
    assert config["categories"] == []


def test_load_config_merge():
    """File values should override defaults."""
    minimal = """
workers: 1
categories:
  - name: single
    target: 5
    queries: ["query"]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(minimal)
        tmp_path = f.name

    try:
        config = load_config(tmp_path)
        assert config["workers"] == 1  # overridden
        assert config["proxy"] == ""  # default
        assert len(config["categories"]) == 1
    finally:
        os.unlink(tmp_path)


def test_validate_config_valid():
    config = {
        "workers": 3,
        "categories": [
            {"name": "cat1", "target": 10, "queries": ["query1"]},
        ],
    }
    assert validate_config(config) == []


def test_validate_config_empty_categories():
    config = {"workers": 3, "categories": []}
    errors = validate_config(config)
    assert len(errors) > 0


def test_validate_config_missing_name():
    config = {
        "workers": 1,
        "categories": [
            {"target": 10, "queries": ["q"]},
        ],
    }
    errors = validate_config(config)
    assert any("name" in e for e in errors)


def test_validate_config_missing_queries():
    config = {
        "workers": 1,
        "categories": [
            {"name": "cat1", "target": 10},
        ],
    }
    errors = validate_config(config)
    assert any("queries" in e for e in errors)


def test_validate_config_bad_target():
    config = {
        "workers": 1,
        "categories": [
            {"name": "cat1", "target": 0, "queries": ["q"]},
        ],
    }
    errors = validate_config(config)
    assert any("target" in e for e in errors)


def test_validate_config_bad_workers():
    config = {
        "workers": 0,
        "categories": [
            {"name": "cat1", "target": 5, "queries": ["q"]},
        ],
    }
    errors = validate_config(config)
    assert any("workers" in e for e in errors)


def test_get_search_queries():
    cat = {"name": "test", "target": 10, "queries": ["q1", "q2", "q3"]}
    queries = get_search_queries(cat)
    assert queries == ["q1", "q2", "q3"]


def test_get_search_queries_fallback():
    cat = {"name": "fallback_cat", "target": 10}
    queries = get_search_queries(cat)
    # Falls back to name if no queries
    assert len(queries) == 1
    assert queries[0] == "fallback_cat"
