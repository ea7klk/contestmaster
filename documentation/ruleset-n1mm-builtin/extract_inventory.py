#!/usr/bin/env python3
"""Extract a non-code inventory from an ILSpy-decompiled N1MM assembly.

This deliberately records profile identifiers, source locations, and literal
setup metadata only. It does not execute N1MM or copy decompiled method bodies.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BUILD = "1.0.11466"
ARTIFACT_SCHEMA = "contestmaster.n1mm-profile-extraction.v1"
RELEVANT_METHODS = (
    "Initialize",
    "ComputePoints",
    "ComputeScore",
    "ScoreSqlString",
    "MultSqlString",
    "MultSqlString2",
    "MultSqlString3",
    "Nummults",
    "DupeSqlString",
    "IsWorkable",
    "QsoErrorString",
    "SentExch",
    "RcvdExch",
    "DefaultContestExchange",
    "CabrilloFormat",
    "SetSentExch",
    "SetRcvdExch",
)


def parse_dispatch(source: str) -> list[dict[str, str]]:
    """Map each factory switch key to the handler constructed after it."""
    pending: list[str] = []
    profiles: list[dict[str, str]] = []
    for line in source.splitlines():
        case = re.search(r'case\s+"([^"]+)"\s*:', line)
        if case:
            pending.append(case.group(1))
            continue
        assignment = re.search(r"contest\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", line)
        if assignment:
            profiles.extend(
                {"dispatch_key": key, "handler": assignment.group(1)} for key in pending
            )
            pending.clear()
    if pending:
        raise ValueError(f"Factory keys were not followed by handler construction: {pending}")
    keys = [profile["dispatch_key"] for profile in profiles]
    if len(keys) != len(set(keys)):
        raise ValueError("Factory contains duplicate dispatch keys")
    return profiles


def _method_lines(source: str, method_name: str) -> list[int]:
    pattern = re.compile(
        rf"\b(?:internal|public|private|protected)\s+override\s+[^;{{}}\n]+?\b{re.escape(method_name)}\s*\("
    )
    return [source.count("\n", 0, match.start()) + 1 for match in pattern.finditer(source)]


def _method_body(source: str, method_name: str) -> str | None:
    pattern = re.compile(
        rf"\b(?:internal|public|private|protected)\s+override\s+[^;{{}}\n]+?\b{re.escape(method_name)}\s*\([^)]*\)[^{{]*{{"
    )
    match = pattern.search(source)
    if match is None:
        return None
    start = match.end()
    depth = 1
    in_string = False
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise ValueError(f"Unclosed method body: {method_name}")


def extract_class_metadata(source_dir: Path, handler: str) -> dict[str, Any]:
    path = source_dir / "N1MMLogger.Net" / f"{handler}.cs"
    if not path.is_file():
        raise FileNotFoundError(f"Missing decompiled handler source: {path}")
    source = path.read_text(encoding="utf-8")
    initialize = _method_body(source, "Initialize") or ""
    declarations = re.findall(
        r"\b(string|short|int|bool)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\"(?:[^\"\\]|\\.)*\"|-?\d+|true|false)\s*;",
        initialize,
        flags=re.IGNORECASE,
    )
    setup_literals = [
        {"type": kind, "name": name, "literal": literal}
        for kind, name, literal in declarations
    ]
    method_locations = {
        method: _method_lines(source, method)
        for method in RELEVANT_METHODS
        if _method_lines(source, method)
    }
    default_exchange = _method_body(source, "DefaultContestExchange")
    default_exchange_literal = None
    if default_exchange is not None:
        found = re.search(r'return\s+"((?:[^"\\]|\\.)*)"\s*;', default_exchange)
        if found:
            default_exchange_literal = found.group(1)
    constant_returns: dict[str, list[str]] = {}
    for method in ("CabrilloFormat", "Nummults", "ComputeScore"):
        body = _method_body(source, method)
        if body is not None:
            returns = re.findall(r"return\s+([^;]+);", body)
            has_literal_returns = returns and all(
                re.fullmatch(r'\s*(?:-?\d+|"[^"\n]*")\s*', item) for item in returns
            )
            if has_literal_returns:
                constant_returns[method] = [item.strip() for item in returns]
    return {
        "source_file": f"N1MMLogger.Net/{path.name}",
        "source_class": handler,
        "source_methods": method_locations,
        "setup_literals": setup_literals,
        "default_exchange_literal": default_exchange_literal,
        "constant_method_returns": constant_returns,
    }


def build_inventory(source_dir: Path) -> dict[str, Any]:
    factory = source_dir / "N1MMLogger.Net" / "SetupContests.cs"
    profiles = parse_dispatch(factory.read_text(encoding="utf-8"))
    metadata_by_handler: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        handler = profile["handler"]
        if handler not in metadata_by_handler:
            metadata_by_handler[handler] = extract_class_metadata(source_dir, handler)
        profile["profile_id"] = profile["dispatch_key"]
        profile["extraction_status"] = "source-inventory-only"
        profile["conversion_status"] = "not-assessed"
        profile["importable_ruleset"] = False
        profile["handler_metadata"] = metadata_by_handler[handler]
    return {
        "artifact_schema": ARTIFACT_SCHEMA,
        "n1mm_build": BUILD,
        "dispatch_key_count": len(profiles),
        "handler_count": len(metadata_by_handler),
        "profiles": profiles,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decompiled-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = build_inventory(args.decompiled_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {inventory['dispatch_key_count']} dispatch profiles "
        f"from {inventory['handler_count']} handlers to {args.output}"
    )


if __name__ == "__main__":
    main()
