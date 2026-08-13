"""API-key gateway in front of deployed models -- the data-plane auth layer.

Deliberately separate from the control plane's mTLS: mTLS gates who can
deploy/manage models (REQ-1.1-2.2); this gates who can actually *call* a
deployed model, and meters that usage for billing. Neither knows about the
other.

Routing: /{model}/openai/v1/{rest} -> http://{model}-predictor.{ns}.svc.cluster.local/openai/v1/{rest}
(same predictor-naming convention the control plane already uses in
cr_builder.py/server.py). Model is in the URL path, not just the request
body, so it works uniformly for GET (e.g. /v1/models) and POST alike.
"""
from __future__ import annotations
import json
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

import keystore

app = FastAPI()

NAMESPACE = os.environ.get("MODEL_NAMESPACE", "default")
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "120"))
# For local testing only, against a kubectl port-forward -- the cluster-
# internal DNS name doesn't resolve outside the cluster. Unset in production.
PREDICTOR_BASE_OVERRIDE = os.environ.get("PREDICTOR_BASE_OVERRIDE", "")


def _predictor_base(model: str) -> str:
    if PREDICTOR_BASE_OVERRIDE:
        return PREDICTOR_BASE_OVERRIDE
    return f"http://{model}-predictor.{NAMESPACE}.svc.cluster.local"


def _extract_usage(response_body: bytes) -> dict:
    try:
        return json.loads(response_body).get("usage", {}) or {}
    except (ValueError, AttributeError):
        return {}


@app.api_route("/{model}/openai/v1/{rest:path}", methods=["GET", "POST"])
async def proxy(model: str, rest: str, request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing API key")

    identity = keystore.validate_key(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid or revoked API key")

    body = await request.body()
    target = f"{_predictor_base(model)}/openai/v1/{rest}"
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }

    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        try:
            upstream = await client.request(
                request.method, target, content=body, headers=forward_headers,
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"upstream unreachable: {e}")

    usage = _extract_usage(upstream.content)
    keystore.log_usage(
        api_key_id=identity["api_key_id"],
        model=model,
        request_path=f"/openai/v1/{rest}",
        status_code=upstream.status_code,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
