"""Unit tests for the dotenv parser."""

from __future__ import annotations

from pathlib import Path

from envdoctor.core.scan.dotenv import parse_dotenv

def test_parses_entries_with_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text(
        "# comment\nDATABASE_URL=postgres://localhost/db\n\nexport API_KEY=abc123\nDEBUG=true\n",
        encoding="utf-8",
    )
    parsed = parse_dotenv(path)
    names = [e.name for e in parsed.entries]
    assert names == ["DATABASE_URL", "API_KEY", "DEBUG"]
    by_name = {e.name: e.line for e in parsed.entries}
    assert by_name["DATABASE_URL"] == 2
    assert by_name["API_KEY"] == 4
    assert by_name["DEBUG"] == 5

def test_empty_example_value_warns(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text("SECRET_KEY=\n", encoding="utf-8")
    parsed = parse_dotenv(path)
    assert any("empty example value" in w for w in parsed.warnings)

def test_quoted_values_supported(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text('BASE_URL="https://example.com"\n', encoding="utf-8")
    parsed = parse_dotenv(path)
    assert parsed.entries[0].example_value == "https://example.com"
