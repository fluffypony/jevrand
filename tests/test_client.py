import json

import pytest

from jevrand import AttemptsExhaustedError, Jevrand, ProviderError, ValidationError
from jevrand.client import _question
from jevrand.providers import Provider
from jevrand.reasons import REJECTION_REASONS


@pytest.fixture
def client():
    return Jevrand(provider="typesafe", api_key="fake-key")


def decisions(monkeypatch, choices):
    calls = []
    replies = iter(choices)

    def decide(self, state, question):
        calls.append((state, question))
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(Provider, "decide", decide)
    return calls


def test_repeats_until_approved_with_progress_and_attempt_count(client, monkeypatch):
    calls = decisions(monkeypatch, ["too_famous", "meme", "approved"])
    ticks = iter([42, 69, 731])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    progress = []
    result = client.generate(on_verdict=progress.append)
    assert result.number == 731
    assert result.approved is True
    assert result.attempts == 3
    assert [r.number for r in progress] == [42, 69, 731]
    assert [r.attempts for r in progress] == [1, 2, 3]
    assert calls[0][0]["range"] == {"bottom": "0", "top": "10000", "decimals": 0}


def test_exhaustion_exposes_last_verdict(client, monkeypatch):
    calls = decisions(monkeypatch, ["too_famous"] * 2)
    with pytest.raises(AttemptsExhaustedError) as caught:
        client.generate(42, bottom=42, max_attempts=2)
    assert caught.value.attempts == 2
    assert caught.value.last_result.number == 42
    assert caught.value.last_result.reasons == ("too_famous",)
    assert len(calls) == 2


def test_provider_failure_does_not_retry(client, monkeypatch):
    calls = decisions(monkeypatch, [ProviderError("offline")])
    with pytest.raises(ProviderError, match="offline"):
        client.generate()
    assert len(calls) == 1


def test_check_has_no_generator_range_and_does_not_repeat(client, monkeypatch):
    calls = decisions(monkeypatch, ["meme"])
    result = client.check(-10001.25)
    assert result.number == -10001.25
    assert not result.approved
    assert result.reasons == ("meme",)
    assert result.explanation == "Meme"
    assert calls[0][0] == {"number": -10001.25}
    assert len(calls) == 1


def test_json_result_has_native_number_and_reason_array(client, monkeypatch):
    decisions(monkeypatch, ["approved"])
    result = client.check("0.125")
    data = json.loads(result.to_json())
    assert data == {
        "number": 0.125,
        "approved": True,
        "reasons": [],
        "explanation": "Jev has no objection.",
        "provider": "typesafe",
        "model": "jev-latest",
        "attempts": 1,
    }
    assert result.to_dict() == data


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2"])
def test_invalid_attempt_limits_do_not_call_provider(client, monkeypatch, limit):
    calls = decisions(monkeypatch, [])
    with pytest.raises(ValidationError):
        client.generate(max_attempts=limit)
    assert not calls


def test_callback_errors_stop_generation(client, monkeypatch):
    calls = decisions(monkeypatch, ["meme"])

    def stop(result):
        raise RuntimeError("caller stopped")

    with pytest.raises(RuntimeError, match="caller stopped"):
        client.generate(on_verdict=stop)
    assert len(calls) == 1


def test_all_catalogue_options_reach_jev():
    question = _question()
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"approved", *(r.code for r in REJECTION_REASONS)}
