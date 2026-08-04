import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("jarvis_proxy", Path(__file__).resolve().parents[1] / "jarvis_proxy.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_extract_location_query_handles_place_requests():
    prompt = module.extract_location_query("Where is Tokyo")
    assert prompt == "Tokyo"


def test_extract_location_query_strips_map_phrases():
    prompt = module.extract_location_query("Show me Tokyo on the map")
    assert prompt == "Tokyo"


def test_show_me_research_prompt_does_not_probe_as_location():
    assert module.should_probe_show_me_location("Show me pictures of SpaceX") is False


def test_show_me_location_prompt_can_probe_as_location():
    assert module.should_probe_show_me_location("Show me Miami") is True


def test_legacy_chat_route_delegates_to_assistant(monkeypatch):
    monkeypatch.setattr(module, "assistant_internal", lambda payload: {
        "status": "success",
        "category": "LOCATION",
        "response": "Location acquired, sir.",
        "research": {
            "images": ["https://example.com/miami.jpg"],
            "news": "Nearby: Biscayne Bay",
            "location": {"title": "Miami, Florida, United States"},
        },
    })

    with module.app.test_client() as client:
        response = client.post("/api/chat", json={"prompt": "Where is Miami?"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["category"] == "LOCATION"
    assert payload["query_title"] == "MIAMI, FLORIDA, UNITED STATES"
    assert payload["images"] == ["https://example.com/miami.jpg"]


def test_location_info_endpoint_uses_query_and_returns_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.ok = True

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    def fake_get(url, timeout=6):
        captured["url"] = url
        if "nominatim.openstreetmap.org/search" in url:
            return FakeResponse([{"lat": "35.6764", "lon": "139.6503", "display_name": "Tokyo, Japan"}])
        if "api.open-meteo.com" in url:
            return FakeResponse({"current": {"temperature_2m": 78, "weather_code": 1}})
        if "wikipedia.org" in url and "/summary/" in url:
            return FakeResponse({"extract": "Tokyo is the capital of Japan."})
        if "wikipedia.org" in url and "/media-list/" in url:
            return FakeResponse({"items": []})
        return FakeResponse([])

    monkeypatch.setattr(module.requests, "get", fake_get)
    with module.app.test_client() as client:
        response = client.post("/api/location-info", json={"query": "Tokyo"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["title"] == "Tokyo, Japan"
    assert payload["coords"]["lat"] == 35.6764
