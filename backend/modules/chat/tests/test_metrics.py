from backend.modules.chat import metrics


def test_chat_metrics_use_only_bounded_dimensions():
    assert metrics.chat_requests_total._labelnames == ("requested_mode", "route", "outcome")
    assert metrics.chat_route_total._labelnames == ("requested_mode", "route", "reason")
    assert metrics.chat_response_latency_ms._labelnames == ("route",)
    assert metrics.chat_sources_total._labelnames == ("kind",)
    assert metrics.chat_errors_total._labelnames == ("code", "route")
    assert metrics.chat_stream_events_total._labelnames == ("event",)
