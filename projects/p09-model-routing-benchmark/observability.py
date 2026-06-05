from __future__ import annotations

import os
from urllib.parse import quote


OTEL_TRACE_VARS = (
    "LMNR_PROJECT_API_KEY",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


def configure_p09_observability(default_mode: str = "auto") -> str:
    """Configure tracing before OpenHands imports its observability hooks."""
    os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "true")
    os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")

    mode = os.environ.get("P09_TRACE_MODE", default_mode).strip().lower().replace("_", "-")
    if mode in {"off", "none", "disabled"}:
        for name in OTEL_TRACE_VARS:
            os.environ.pop(name, None)
        return "off"

    if mode in {"grpc", "laminar-grpc"}:
        return "laminar-grpc" if os.environ.get("LMNR_PROJECT_API_KEY") else "auto"

    if mode not in {"auto", "http", "otlp-http", "laminar-http"}:
        raise RuntimeError(
            "P09_TRACE_MODE must be one of auto, laminar-http, laminar-grpc, or off"
        )

    key = os.environ.get("LMNR_PROJECT_API_KEY")
    if not key:
        return "auto"

    endpoint = os.environ.get("P09_LAMINAR_HTTP_ENDPOINT", "https://api.lmnr.ai/v1/traces")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        f"authorization={quote(f'Bearer {key}', safe='')}",
    )

    # OpenHands gives LMNR_PROJECT_API_KEY precedence and initializes the
    # Laminar SDK's gRPC exporter. For local terminal tools that fork tmux panes,
    # route through Laminar's OTLP/HTTP endpoint instead.
    os.environ.pop("LMNR_PROJECT_API_KEY", None)
    return "laminar-http"
