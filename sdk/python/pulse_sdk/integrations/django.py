"""PULSE Django middleware — auto-captures slow requests and 5xx errors."""
import time
import pulse_sdk


class PulseMiddleware:
    def __init__(self, get_response):
        self.get_response  = get_response
        self.slow_threshold = 2000  # ms

    def __call__(self, request):
        start    = time.time()
        trace_id = request.headers.get("x-trace-id") or pulse_sdk.str(pulse_sdk.uuid.uuid4())[:8]

        try:
            response = self.get_response(request)
        except Exception as exc:
            pulse_sdk.capture_exception(exc, extra={
                "http.method": request.method,
                "http.path":   request.path,
                "http.host":   request.get_host(),
            }, trace_id=trace_id)
            raise

        duration_ms = (time.time() - start) * 1000
        status      = response.status_code

        if status >= 500 or duration_ms >= self.slow_threshold:
            with pulse_sdk.trace(f"http.{request.method.lower()}", trace_id=trace_id) as span:
                span.set_tag("http.path",     request.path)
                span.set_tag("http.method",   request.method)
                span.set_tag("http.status",   str(status))
                span.set_tag("http.duration", f"{duration_ms:.1f}ms")
                if status >= 500:
                    span.error = f"HTTP {status}"

        return response
