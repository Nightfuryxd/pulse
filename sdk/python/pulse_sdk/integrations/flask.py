"""PULSE Flask integration — auto-captures slow requests and 5xx errors."""
import time
import uuid
import pulse_sdk


def init_app(app, slow_threshold_ms: int = 2000):
    """Attach PULSE to a Flask app. Call after pulse_sdk.init()."""

    @app.before_request
    def _before():
        from flask import g, request
        g.pulse_start    = time.time()
        g.pulse_trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())[:8]

    @app.after_request
    def _after(response):
        from flask import g, request
        duration_ms = (time.time() - g.get("pulse_start", time.time())) * 1000
        status      = response.status_code
        trace_id    = g.get("pulse_trace_id", "")

        if status >= 500 or duration_ms >= slow_threshold_ms:
            with pulse_sdk.trace(f"http.{request.method.lower()}", trace_id=trace_id) as span:
                span.set_tag("http.path",     request.path)
                span.set_tag("http.status",   str(status))
                span.set_tag("http.duration", f"{duration_ms:.1f}ms")
                if status >= 500:
                    span.error = f"HTTP {status}"

        return response

    @app.teardown_request
    def _error(exc):
        if exc:
            from flask import g
            pulse_sdk.capture_exception(exc, trace_id=g.get("pulse_trace_id",""))
