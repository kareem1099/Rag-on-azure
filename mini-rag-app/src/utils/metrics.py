from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from helpers.config import get_settings, Settings
import secrets
import time

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP Request Latency",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

RAG_ANSWERS = Counter("rag_answers_total", "RAG answers by model and outcome", ["model", "outcome"])
RAG_UNVERIFIED_QUOTES = Counter("rag_unverified_quotes_total", "Quotes not found in the retrieved documents")
RAG_UNVERIFIED_ATTRIBUTIONS = Counter("rag_unverified_attributions_total", "Attributions not matching the retrieved documents")

RAG_OUTCOMES = ("answered", "refused", "incomplete")
INITIAL_STATUSES = ("200", "400", "401", "422", "500")


class PrometheusMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or "unmatched"

        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=response.status_code).inc()

        return response


def setup_metrics(app: FastAPI):
    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request, settings: Settings = Depends(get_settings)):
        # When the app is exposed directly (no nginx in front), METRICS_TOKEN keeps /metrics private.
        if settings.METRICS_TOKEN:
            expected = f"Bearer {settings.METRICS_TOKEN}"
            provided = request.headers.get("authorization", "")
            if not secrets.compare_digest(provided.encode(), expected.encode()):
                raise HTTPException(status_code=404, detail="Not Found")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def initialize_metrics(app: FastAPI, model_ids: list):
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path == "/metrics":
            continue
        for method in route.methods:
            REQUEST_LATENCY.labels(method=method, endpoint=route.path)
            for status in INITIAL_STATUSES:
                REQUEST_COUNT.labels(method=method, endpoint=route.path, status=status)

    for model_id in model_ids:
        for outcome in RAG_OUTCOMES:
            RAG_ANSWERS.labels(model=model_id, outcome=outcome)
    RAG_ANSWERS.labels(model="none", outcome="error")


def record_rag_answer(model: str, outcome: str, unverified_quotes: int = 0, unverified_attributions: int = 0):
    RAG_ANSWERS.labels(model=model or "unknown", outcome=outcome).inc()
    if unverified_quotes:
        RAG_UNVERIFIED_QUOTES.inc(unverified_quotes)
    if unverified_attributions:
        RAG_UNVERIFIED_ATTRIBUTIONS.inc(unverified_attributions)
