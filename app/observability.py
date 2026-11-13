from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request


def configure_observability(app: FastAPI, level: str = 'INFO') -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    logger = logging.getLogger('athleteops.request')

    @app.middleware('http')
    async def request_context(request: Request, call_next):
        request_id = request.headers.get('x-request-id') or str(uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('request_failed request_id=%s path=%s', request_id, request.url.path)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers['X-Request-ID'] = request_id
        logger.info(
            'request_complete request_id=%s method=%s path=%s status=%s duration_ms=%.2f',
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    # Optional OpenTelemetry wiring. Core application behavior does not depend on it.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
    except Exception:
        return
    FastAPIInstrumentor.instrument_app(app)
