import io
import json
import sys
import threading
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

import jevrand.providers as providers
from jevrand.errors import ConfigurationError, InvalidResponseError, ProviderError, ValidationError
from jevrand.providers import Provider

FAKE_KEY = "fake-secret-only-for-tests"
QUESTION = {
    "type": "choice",
    "instructions": "Approve the number or reject it as too famous.",
    "criteria": {"approved": "Unremarkable", "too_famous": "Too recognisable"},
}


@pytest.fixture(autouse=True)
def clean_provider_environment(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def provider():
    return Provider.configure("typesafe", FAKE_KEY)


@pytest.fixture
def transport(monkeypatch):
    opener = Mock()
    monkeypatch.setattr(providers, "build_opener", Mock(return_value=opener))
    return opener


def reply(transport, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    transport.open.return_value = io.BytesIO(raw)


def decision(choice="approved", **extra):
    return {"answers": {"verdict": {"type": "choice", "choice": choice, **extra}}}


@pytest.mark.parametrize(
    ("name", "url", "model", "variable"),
    [
        (
            "typesafe",
            "https://api.typesafe.ai/v1/systemone",
            "jev-latest",
            "TYPESAFE_API_KEY",
        ),
        (
            "openrouter",
            "https://openrouter.ai/api/alpha/decisions",
            "~typesafe/jev-latest",
            "OPENROUTER_API_KEY",
        ),
    ],
)
def test_provider_wire_contract(monkeypatch, transport, name, url, model, variable):
    monkeypatch.setenv(variable, FAKE_KEY)
    client = Provider.configure(timeout=2.5)
    reply(transport, decision())

    assert client.decide({"number": 8317}, QUESTION) == "approved"

    request = transport.open.call_args.args[0]
    assert client.name == name
    assert request.full_url == url
    assert request.method == "POST"
    assert request.get_header("Authorization") == f"Bearer {FAKE_KEY}"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Accept") == "application/json"
    assert transport.open.call_args.kwargs == {"timeout": 2.5}
    assert json.loads(request.data) == {
        "model": model,
        "state": {"number": 8317},
        "questions": {"verdict": QUESTION},
    }


def test_typesafe_has_priority_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-typesafe")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter")
    client = Provider.configure()
    assert client.name == "typesafe"
    assert client.api_key == "fake-typesafe"


def test_empty_typesafe_key_does_not_hide_openrouter(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", " \t ")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter")
    assert Provider.configure().name == "openrouter"


def test_explicit_provider_overrides_environment_priority(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-typesafe")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter")
    client = Provider.configure("openrouter")
    assert client.name == "openrouter"
    assert client.api_key == "fake-openrouter"


def test_explicit_key_overrides_provider_environment(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-environment-key")
    client = Provider.configure("typesafe", f" {FAKE_KEY} ")
    assert client.api_key == FAKE_KEY
    assert FAKE_KEY not in repr(client)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "Set TYPESAFE_API_KEY or OPENROUTER_API_KEY"),
        ({"name": "typesafe"}, "Set TYPESAFE_API_KEY"),
        ({"name": "openrouter"}, "Set OPENROUTER_API_KEY"),
        ({"name": "unknown"}, "provider must be typesafe or openrouter"),
        ({"name": ["typesafe"]}, "provider must be typesafe or openrouter"),
        ({"api_key": FAKE_KEY}, "Specify a provider"),
    ],
)
def test_missing_or_invalid_configuration(kwargs, message):
    with pytest.raises(ConfigurationError, match=message):
        Provider.configure(**kwargs)


@pytest.mark.parametrize("key", ["", "   ", "fake\nkey", "fake key", "fake\x7fkey", "faké", 42])
def test_invalid_api_keys_do_not_reach_transport(key):
    with pytest.raises(ConfigurationError):
        Provider.configure("typesafe", key)


@pytest.mark.parametrize(
    "timeout", [0, -1, True, "30", None, float("inf"), float("nan"), 10**400, 1e100, 86401]
)
def test_invalid_timeouts(timeout):
    with pytest.raises(ValidationError, match="timeout"):
        Provider.configure("typesafe", FAKE_KEY, timeout)


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        (401, "Check the API key"),
        (402, "Check the account balance"),
        (403, "Check the account's access"),
        (422, "rejected the request format"),
        (429, "rate limit"),
        (529, "overloaded"),
        (500, "provider's status"),
    ],
)
def test_http_errors_are_actionable_and_do_not_echo_secrets(provider, transport, status, hint):
    response = io.BytesIO(f"Authorization: Bearer {FAKE_KEY}".encode())
    transport.open.side_effect = HTTPError(provider.url, status, FAKE_KEY, {}, response)

    with pytest.raises(ProviderError) as error:
        provider.decide({"number": 42}, QUESTION)

    assert f"HTTP {status}" in str(error.value)
    assert hint in str(error.value)
    assert FAKE_KEY not in str(error.value)
    assert error.value.__suppress_context__
    assert response.closed


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(FAKE_KEY),
        URLError(FAKE_KEY),
        ConnectionResetError(FAKE_KEY),
        HTTPException(FAKE_KEY),
    ],
)
def test_transport_errors_do_not_echo_secrets(provider, transport, failure):
    transport.open.side_effect = failure
    with pytest.raises(ProviderError, match="failed or timed out") as error:
        provider.decide({"number": 42}, QUESTION)
    assert FAKE_KEY not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b"\xff",
        [],
        None,
        {"error": {"message": FAKE_KEY}},
        {},
        {"answers": []},
        {"answers": {"verdict": None}},
        {"answers": {"verdict": {"type": "noul", "noul": 1}}},
        {"answers": {"verdict": {"type": "choice"}}},
        decision("invented_reason"),
        decision(None),
        decision(["approved"]),
        decision(True),
    ],
)
def test_malformed_or_unknown_decisions_fail_closed(provider, transport, body):
    reply(transport, body)
    with pytest.raises(InvalidResponseError) as error:
        provider.decide({"number": 42}, QUESTION)
    assert FAKE_KEY not in str(error.value)


@pytest.mark.parametrize("choice", ["approved", "too_famous"])
@pytest.mark.parametrize(
    "extra",
    [{}, {"confidence": 0.96, "probabilities": {"approved": 0.96, "too_famous": 0.04}}],
)
def test_confidence_and_probabilities_are_optional(provider, transport, choice, extra):
    reply(transport, decision(choice, **extra))
    assert provider.decide({"number": 42}, QUESTION) == choice


def test_oversized_response_is_rejected(provider, transport):
    reply(transport, b" " * (providers.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(InvalidResponseError, match="exceeded 1 MiB"):
        provider.decide({"number": 42}, QUESTION)


def test_deeply_nested_json_is_rejected(provider, transport):
    depth = max(sys.getrecursionlimit() * 10, 100000)
    reply(transport, b"[" * depth + b"]" * depth)
    with pytest.raises(InvalidResponseError):
        provider.decide({"number": 42}, QUESTION)


def test_json_recursion_error_is_reported_as_invalid_response(provider, transport, monkeypatch):
    reply(transport, decision())
    monkeypatch.setattr(providers.json, "loads", Mock(side_effect=RecursionError))
    with pytest.raises(InvalidResponseError, match="valid JSON"):
        provider.decide({"number": 42}, QUESTION)


@pytest.fixture
def local_provider_server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(
                (self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length)))
            )
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/credential-sink")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps(decision("too_famous")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization"), None))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_actual_http_request_and_response(local_provider_server):
    base_url, requests = local_provider_server
    client = Provider("typesafe", f"{base_url}/decision", "jev-latest", FAKE_KEY, 2)

    assert client.decide({"number": 42}, QUESTION) == "too_famous"
    assert requests == [
        (
            "/decision",
            f"Bearer {FAKE_KEY}",
            {"model": "jev-latest", "state": {"number": 42}, "questions": {"verdict": QUESTION}},
        )
    ]


def test_http_redirect_does_not_forward_credentials(local_provider_server):
    base_url, requests = local_provider_server
    client = Provider("typesafe", f"{base_url}/redirect", "jev-latest", FAKE_KEY, 2)

    with pytest.raises(ProviderError, match="HTTP 302"):
        client.decide({"number": 42}, QUESTION)

    assert len(requests) == 1
    assert requests[0][0] == "/redirect"
