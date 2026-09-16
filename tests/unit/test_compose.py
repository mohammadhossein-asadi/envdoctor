"""Unit tests for the compose mini-YAML parser and env extraction."""

from __future__ import annotations

from pathlib import Path

from envdoctor.core.scan.compose import extract_compose_env, parse_yaml_subset


def test_yaml_subset_services_map() -> None:
    text = """services:
  web:
    image: nginx:1.25
    ports:
      - "8080:80"
    environment:
      - DEBUG=1
"""
    doc = parse_yaml_subset(text)
    services = doc.root["services"]
    assert services["web"]["image"] == "nginx:1.25"


def test_extract_env_map_and_list(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        """services:
  api:
    image: api:1.0
    environment:
      DATABASE_URL: postgres://db
      REDIS_URL: redis://cache
  worker:
    image: worker:1.0
    environment:
      - QUEUE_NAME
      - LOG_LEVEL=info
""",
        encoding="utf-8",
    )
    refs = {ref.name: ref for ref in extract_compose_env(compose)}
    assert set(refs) == {"DATABASE_URL", "REDIS_URL", "QUEUE_NAME", "LOG_LEVEL"}
    assert refs["DATABASE_URL"].line == 5  # services: / api: / image: / environment: / DATABASE_URL
    assert refs["QUEUE_NAME"].kind == "compose-list"


def test_unparsed_lines_are_reported(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  api:\n    build: .\n", encoding="utf-8")
    doc = parse_yaml_subset(compose.read_text(encoding="utf-8"))
    assert doc.root["services"]["api"]["build"] == "."
