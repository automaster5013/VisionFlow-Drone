from __future__ import annotations

from fastapi.testclient import TestClient

from app.sources.browser_upload import BrowserUploadSource
from app.streaming import AnnotatedFrameHub, create_stream_app


INTERNAL_KEY = "stage2-test-ai-internal-key-0123456789abcdef"
PROTECTED_OPERATIONS = (
    ("get", "/api/streams/status"),
    ("get", "/api/metrics/status"),
    ("post", "/api/metrics/reset"),
    ("get", "/api/models/status"),
    ("get", "/api/streams/latest.jpg"),
    ("get", "/api/streams/annotated.mjpeg"),
    ("get", "/api/ingest/status"),
    ("post", "/api/ingest/frame"),
)


def create_client() -> TestClient:
    source = BrowserUploadSource(fps=5.0, queue_capacity=3)
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        model_status_provider=lambda: {"profile": "test"},
        internal_security_enabled=True,
        internal_api_key=INTERNAL_KEY,
    )
    return TestClient(app)


def test_health_stays_public() -> None:
    with create_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_sensitive_operations_declare_internal_api_key_security() -> None:
    with create_client() as client:
        document = client.get("/openapi.json").json()
    for method, path in PROTECTED_OPERATIONS:
        security = document["paths"][path][method].get("security", [])
        assert security, f"missing OpenAPI security declaration: {method} {path}"


def test_missing_and_invalid_keys_are_rejected() -> None:
    with create_client() as client:
        for method, path in PROTECTED_OPERATIONS:
            without_key = client.request(method, path)
            assert without_key.status_code == 401, (method, path, without_key.text)

            invalid_key = client.request(
                method,
                path,
                headers={"X-VisionFlow-AI-Key": "wrong-key"},
            )
            assert invalid_key.status_code == 401, (method, path, invalid_key.text)


def test_valid_key_reaches_protected_handlers() -> None:
    headers = {"X-VisionFlow-AI-Key": INTERNAL_KEY}
    with create_client() as client:
        stream = client.get("/api/streams/status", headers=headers)
        ingest = client.get("/api/ingest/status", headers=headers)
        model = client.get("/api/models/status", headers=headers)

    assert stream.status_code == 200
    assert ingest.status_code == 200
    assert model.status_code == 200
    assert model.json()["profile"] == "test"
