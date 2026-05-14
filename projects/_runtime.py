"""Shared runtime helpers for the tutorial project scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path, PurePosixPath


DEFAULT_SERVER_ROOT = "/projects"


def resolve_api_key() -> str | None:
    key = os.environ.get("AGENT_SERVER_API_KEY")
    if key:
        return key
    path = Path.home() / ".openhands" / "agent-canvas" / "session-api-key.txt"
    return path.read_text().strip() if path.exists() else None


def _host_root() -> Path | None:
    raw = os.environ.get("AGENT_WORKSPACE_HOST_ROOT") or os.environ.get("PROJECT_PATH")
    return Path(raw).expanduser().resolve() if raw else None


def _server_root() -> str:
    if os.environ.get("AGENT_WORKSPACE_HOST_ROOT") or os.environ.get("PROJECT_PATH"):
        return os.environ.get("AGENT_WORKSPACE_SERVER_ROOT", DEFAULT_SERVER_ROOT)
    return os.environ.get("AGENT_WORKSPACE_SERVER_ROOT", DEFAULT_SERVER_ROOT)


def _relative_to_server_root(path_text: str) -> PurePosixPath | None:
    try:
        return PurePosixPath(path_text).relative_to(PurePosixPath(_server_root()))
    except ValueError:
        return None


def _workspace_error(raw: str) -> None:
    print(
        "\n".join(
            [
                f"WORKSPACE_DIR is not visible on this host: {raw}",
                "",
                "If your Agent Canvas server runs in Docker, remember that the",
                "server usually sees your project root at /projects. Either:",
                "  1. set WORKSPACE_DIR to a host path and set PROJECT_PATH or",
                "     AGENT_WORKSPACE_HOST_ROOT so the script can map it, or",
                "  2. set WORKSPACE_DIR to the server path, for example",
                "     /projects/agent-canvas, for scripts that use remote Workspace.",
            ]
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)


def resolve_host_working_dir(value: str | None = None) -> Path:
    """Return a host-visible workspace path for local copy or DockerWorkspace."""
    raw = value or os.environ.get("WORKSPACE_DIR") or str(Path.cwd())
    expanded = os.path.expanduser(raw)
    host_root = _host_root()
    server_relative = _relative_to_server_root(expanded)
    if host_root is not None and server_relative is not None:
        candidate = (host_root / Path(server_relative.as_posix())).resolve()
    else:
        candidate = Path(expanded).resolve()

    if not candidate.exists() or not candidate.is_dir():
        _workspace_error(raw)
    return candidate


def server_visible_path(path: str | Path) -> str:
    """Map a host path into the path namespace seen by a Dockerized agent server."""
    resolved = Path(path).expanduser().resolve()
    host_root = _host_root()
    if host_root is None:
        return str(resolved)

    try:
        relative = resolved.relative_to(host_root)
    except ValueError:
        return str(resolved)
    return str(PurePosixPath(_server_root()) / PurePosixPath(relative.as_posix()))


def resolve_server_working_dir(value: str | None = None) -> str:
    """Return the working_dir string to pass to remote Workspace."""
    raw = value or os.environ.get("WORKSPACE_DIR")
    if raw:
        expanded = os.path.expanduser(raw)
        if _relative_to_server_root(expanded) is not None:
            return expanded
    return server_visible_path(resolve_host_working_dir(value))


def token_counts(metrics) -> tuple[int, int]:
    """Read token counts across OpenHands SDK metric shape changes."""
    usage = getattr(metrics, "accumulated_token_usage", None)
    prompt = getattr(usage, "prompt_tokens", None) if usage is not None else None
    completion = getattr(usage, "completion_tokens", None) if usage is not None else None
    if prompt is None:
        prompt = getattr(metrics, "accumulated_prompt_tokens", 0)
    if completion is None:
        completion = getattr(metrics, "accumulated_completion_tokens", 0)
    return int(prompt or 0), int(completion or 0)
