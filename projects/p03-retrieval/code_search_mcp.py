"""Minimal repo code-search MCP server for P03.

The server exposes one tool, search_code, over MCP stdio. It indexes text files
under CODE_SEARCH_ROOT and returns ranked snippets. The scorer is intentionally
small: BM25-style term matching plus a few synonym expansions that make the
"backend to talk to" prompt find proxy/backend-host code.

This file avoids external dependencies on purpose. It implements the tiny MCP
JSON-RPC surface needed by OpenHands: initialize, tools/list, and tools/call.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IGNORE_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".openhands-runs",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
IGNORE_SUFFIXES = {
    ".7z",
    ".avif",
    ".bin",
    ".bmp",
    ".class",
    ".db",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mov",
    ".mp4",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".sqlite",
    ".svg",
    ".webp",
    ".zip",
}
MAX_FILE_BYTES = 256_000
MAX_FILES = 2_500
CHUNK_LINES = 24
CHUNK_STRIDE = 12

QUERY_EXPANSIONS = {
    "backend": ("server", "agent-server", "proxy", "vite_backend_host"),
    "canvas": ("agent-canvas", "vite", "frontend"),
    "choose": ("pick", "select", "set", "config", "spawn"),
    "pick": ("choose", "select", "set", "config", "spawn"),
    "talk": ("connect", "proxy", "host", "url", "vite_backend_host"),
    "route": ("proxy", "host", "url", "ingress"),
}


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    terms: list[str]


@dataclass(frozen=True)
class Index:
    chunks: list[Chunk]
    document_frequency: dict[str, int]
    average_length: float


_INDEX: Index | None = None


def _root() -> Path:
    raw = os.environ.get("CODE_SEARCH_ROOT") or os.environ.get("WORKSPACE_DIR") or "."
    root = Path(raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"CODE_SEARCH_ROOT is not a directory: {root}")
    return root


def _tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9_.$/-]+", text.lower())
    terms: list[str] = []
    for token in raw_tokens:
        terms.append(token)
        terms.extend(part for part in re.split(r"[^a-z0-9]+|_", token) if part)
    return terms


def _query_terms(query: str) -> list[str]:
    terms = _tokenize(query)
    expanded = list(terms)
    for term in terms:
        expanded.extend(QUERY_EXPANSIONS.get(term, ()))
    return expanded


def _should_skip(path: Path) -> bool:
    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True
    return any(part in IGNORE_DIRS for part in path.parts)


def _iter_text_files(root: Path):
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= MAX_FILES:
            break
        if not path.is_file() or _should_skip(path.relative_to(root)):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        count += 1
        yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def _chunks_for_file(root: Path, path: Path) -> list[Chunk]:
    text = _read_text(path)
    if not text:
        return []

    lines = text.splitlines()
    if not lines:
        return []

    rel = path.relative_to(root).as_posix()
    chunks: list[Chunk] = []
    for start in range(0, len(lines), CHUNK_STRIDE):
        window = lines[start : start + CHUNK_LINES]
        if not window:
            continue
        chunk_text = "\n".join(window)
        terms = _tokenize(rel + "\n" + chunk_text)
        if terms:
            chunks.append(
                Chunk(
                    path=rel,
                    start_line=start + 1,
                    end_line=start + len(window),
                    text=chunk_text,
                    terms=terms,
                )
            )
        if start + CHUNK_LINES >= len(lines):
            break
    return chunks


def _build_index() -> Index:
    root = _root()
    chunks: list[Chunk] = []
    document_frequency: dict[str, int] = {}
    for path in _iter_text_files(root):
        for chunk in _chunks_for_file(root, path):
            chunks.append(chunk)
            for term in set(chunk.terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1

    average_length = sum(len(chunk.terms) for chunk in chunks) / max(len(chunks), 1)
    return Index(
        chunks=chunks,
        document_frequency=document_frequency,
        average_length=average_length,
    )


def _index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def _bm25_score(chunk: Chunk, terms: list[str], index: Index) -> float:
    if not terms or not chunk.terms:
        return 0.0

    term_counts: dict[str, int] = {}
    for term in chunk.terms:
        term_counts[term] = term_counts.get(term, 0) + 1

    total_docs = max(len(index.chunks), 1)
    chunk_len = len(chunk.terms)
    k1 = 1.5
    b = 0.75
    score = 0.0
    for term in set(terms):
        frequency = term_counts.get(term, 0)
        if frequency == 0:
            continue
        docs_with_term = index.document_frequency.get(term, 0)
        idf = math.log(1 + (total_docs - docs_with_term + 0.5) / (docs_with_term + 0.5))
        denominator = frequency + k1 * (
            1 - b + b * chunk_len / max(index.average_length, 1)
        )
        score += idf * (frequency * (k1 + 1) / denominator)
    return score


def _preview(text: str, terms: list[str], max_chars: int = 900) -> str:
    lowered_lines = [(line, set(_tokenize(line))) for line in text.splitlines()]
    query_set = set(terms)
    matching = [line for line, line_terms in lowered_lines if query_set & line_terms]
    chosen = matching[:8] if matching else [line for line, _ in lowered_lines[:8]]
    preview = "\n".join(chosen).strip()
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3].rstrip() + "..."
    return preview


def search_code(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Search the repository for code/docs related to a natural-language query.

    Returns ranked snippets with path, line range, score, and preview text.
    Use this when exact grep terms are unclear or a prompt uses synonyms.
    """
    limit = max(1, min(int(max_results), 20))
    index = _index()
    terms = _query_terms(query)
    scored = [
        (score, chunk)
        for chunk in index.chunks
        if (score := _bm25_score(chunk, terms, index)) > 0
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "path": chunk.path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "score": round(score, 3),
            "preview": _preview(chunk.text, terms),
        }
        for score, chunk in scored[:limit]
    ]


def _tool_schema() -> dict[str, Any]:
    return {
        "name": "search_code",
        "description": (
            "Search the repository for code/docs related to a natural-language "
            "query. Use when exact grep terms are unclear."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query or code terms to search for.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of snippets to return.",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    }


def _response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def _handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    message_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if message_id is None:
        return None

    if method == "initialize":
        protocol_version = params.get("protocolVersion", "2024-11-05")
        return _response(
            message_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "repo-code-search", "version": "0.1.0"},
            },
        )

    if method == "ping":
        return _response(message_id, {})

    if method == "tools/list":
        return _response(message_id, {"tools": [_tool_schema()]})

    if method == "tools/call":
        if params.get("name") != "search_code":
            return _error(message_id, -32602, f"Unknown tool: {params.get('name')}")
        arguments = params.get("arguments") or {}
        try:
            result = search_code(
                query=str(arguments["query"]),
                max_results=int(arguments.get("max_results", 8)),
            )
        except Exception as exc:  # noqa: BLE001 - report tool errors to MCP client
            return _response(
                message_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return _response(
            message_id,
            {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": False,
            },
        )

    return _error(message_id, -32601, f"Method not found: {method}")


def run_stdio_server() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = _handle_request(request)
        except Exception as exc:  # noqa: BLE001 - keep stdio server alive
            response = _error(None, -32603, str(exc))
        if response is not None:
            print(json.dumps(response), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the P03 code-search MCP server.")
    parser.add_argument("--query", help="Run one direct search and print JSON.")
    parser.add_argument("--max-results", type=int, default=8)
    args = parser.parse_args()

    if args.query:
        print(json.dumps(search_code(args.query, args.max_results), indent=2))
        return

    run_stdio_server()


if __name__ == "__main__":
    main()
