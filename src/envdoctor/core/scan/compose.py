"""Minimal YAML subset parser + compose `environment:` / `env_file:` extraction.

We deliberately avoid a full YAML dependency: compose files that matter for
diagnosis use a small, regular subset (nested two-space maps, `- item`
sequences, inline `{}` maps, scalar values). Anything we cannot parse is
reported as `unparsed` so checks can degrade gracefully instead of crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MiniYaml:
    """Parsed subset of a YAML document."""

    root: dict[str, Any] = field(default_factory=dict)
    unparsed: list[str] = field(default_factory=list)  # lines we could not model


def _scalar(token: str) -> Any:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    lowered = token.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    if lowered in ("null", "~", ""):
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _inline_map(token: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    body = token.strip()[1:-1]  # strip { }
    for part in body.split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            out[k.strip().strip("'\"")] = _scalar(v)
    return out


def _inline_list(token: str) -> list[Any]:
    body = token.strip()[1:-1]  # strip [ ]
    if not body:
        return []
    return [_scalar(p) for p in body.split(",")]


def parse_yaml_subset(text: str) -> MiniYaml:
    """Parse the regular YAML subset used by compose files and CI workflows."""
    doc: dict[str, Any] = {}
    unparsed: list[str] = []
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, doc)]
    # (grandparent, key, key-indent) for a just-created empty child, so that a
    # following `- item` sequence can convert it into a list.
    last_empty: tuple[dict[str, Any], str, int] | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.strip() == "---":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack.append((-1, doc))
        parent: dict[str, Any] | list[Any] = stack[-1][1]

        if line.startswith("- "):
            # A sequence under a key we speculatively created as an empty dict.
            if (
                last_empty is not None
                and isinstance(parent, dict)
                and not parent
                and last_empty[0].get(last_empty[1]) is parent
                and indent > last_empty[2]
            ):
                gp, gkey, gindent = last_empty
                new_list: list[Any] = []
                gp[gkey] = new_list
                stack[-1] = (gindent, new_list)
                parent = new_list
                last_empty = None
            item_text = line[2:]
            if ":" in item_text and not item_text.startswith(("{", "[")):
                key, _, value = item_text.partition(":")
                if isinstance(parent, list):
                    parent.append({key.strip().strip("'\""): _scalar(value)})
                    continue
                if isinstance(parent, dict) and parent:
                    last_key = next(reversed(parent))
                    bucket = parent[last_key]
                    if isinstance(bucket, list):
                        bucket.append({key.strip().strip("'\""): _scalar(value)})
                        continue
            if isinstance(parent, list):
                parent.append(_scalar(item_text))
                continue
            unparsed.append(raw)
            continue

        if ":" not in line:
            unparsed.append(raw)
            continue

        key, _, value = line.partition(":")
        key = key.strip().strip("'\"")
        value = value.strip()

        if value == "":
            child: dict[str, Any] = {}
            if isinstance(parent, dict):
                parent[key] = child
                stack.append((indent, child))
                last_empty = (parent, key, indent)
            continue
        if value.startswith("{") and value.endswith("}"):
            if isinstance(parent, dict):
                parent[key] = _inline_map(value)
            last_empty = None
            continue
        if value.startswith("[") and value.endswith("]"):
            if isinstance(parent, dict):
                parent[key] = _inline_list(value)
            last_empty = None
            continue
        if isinstance(parent, dict):
            parent[key] = _scalar(value)
        last_empty = None

    return MiniYaml(root=doc, unparsed=unparsed)


@dataclass(frozen=True)
class ComposeEnvRef:
    """One required variable discovered in a compose file."""

    name: str
    line: int
    kind: str  # "compose-map" | "compose-list" | "compose-env_file"
    required: bool  # True when mapped to a literal value, False when ${VAR:-} passthrough


def _key_line_index(text: str) -> dict[str, int]:
    """First line number where a key appears as `name:` (with or without a value)."""
    index: dict[str, int] = {}
    key_re = re.compile(r"^\s*-?\s*([A-Za-z_][A-Za-z0-9_]*):(?:\s|$)")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        match = key_re.match(raw)
        if match and match.group(1) not in index:
            index[match.group(1)] = lineno
    return index


def extract_compose_env(path: Path) -> list[ComposeEnvRef]:
    """Pull required env vars out of `environment:` and `env_file:` sections."""
    text = path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_yaml_subset(text)
    refs: list[ComposeEnvRef] = []
    key_lines = _key_line_index(text)

    def find_env_blocks(node: Any) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("environment", "env_file"):
                    blocks.append({key: value})
                blocks.extend(find_env_blocks(value))
        elif isinstance(node, list):
            for item in node:
                blocks.extend(find_env_blocks(item))
        return blocks

    for block in find_env_blocks(parsed.root):
        for key, value in block.items():
            if key == "environment":
                if isinstance(value, dict):
                    for name in value:
                        refs.append(
                            ComposeEnvRef(
                                name=name,
                                line=key_lines.get(name, 0),
                                kind="compose-map",
                                required=True,
                            )
                        )
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            refs.extend(
                                ComposeEnvRef(name=name, line=0, kind="compose-list", required=True)
                                for name in item
                            )
                        elif isinstance(item, str):
                            name = item.split("=", 1)[0]
                            refs.append(
                                ComposeEnvRef(name=name, line=0, kind="compose-list", required=True)
                            )
            elif key == "env_file":
                # The referenced dotenv file is scanned separately by the
                # inventory; here we only note the reference exists.
                continue

    # Deduplicate by name keeping the strongest requirement.
    best: dict[str, ComposeEnvRef] = {}
    for ref in refs:
        existing = best.get(ref.name)
        if existing is None or (ref.required and not existing.required):
            best[ref.name] = ref
    return [best[name] for name in sorted(best)]
