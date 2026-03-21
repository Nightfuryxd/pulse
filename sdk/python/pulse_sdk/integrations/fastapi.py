"""PULSE FastAPI middleware — auto-captures slow requests and 5xx errors."""
import time
import uuid
import pulse_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PulseMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, slow_threshold_ms: int = 2000):
        super().__init__(app)
        self.slow_threshold = slow_threshold_ms

    async def dispatch(self, request: Request, call_next):
        start    = time.time()
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())[:8]

        try:
            response = await call_next(request)
        except Exception as exc:
            pulse_sdk.capture_exception(exc, extra={
                "http.method": request.method,
                "http.path":   request.url.path,
            }, trace_id=trace_id)
            raise

        duration_ms = (time.time() - start) * 1000
        status      = response.status_code

        if status >= 500 or duration_ms >= self.slow_threshold:
            with pulse_sdk.trace(f"http.{request.method.lower()}", trace_id=trace_id) as span:
                span.set_tag("http.path",     request.url.path)
                span.set_tag("http.method",   request.method)
                span.set_tag("http.status",   str(status))
                span.set_tag("http.duration", f"{duration_ms:.1f}ms")
                if status >= 500:
                    span.error = f"HTTP {status}"

        return response
