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
    assert caught.value.requested == 1
    assert caught.value.approved == 0
    assert len(calls) == 2


def test_generate_many_counts_approvals_and_reports_all_candidates(client, monkeypatch):
    calls = decisions(monkeypatch, ["meme", "approved", "too_famous", "approved"])
    ticks = iter([69, 731, 42, 853])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    progress = []

    results = list(client.generate_many(2, on_verdict=progress.append))

    assert [result.number for result in results] == [731, 853]
    assert all(result.approved for result in results)
    assert [result.attempts for result in results] == [2, 4]
    assert [result.number for result in progress] == [69, 731, 42, 853]
    assert [result.attempts for result in progress] == [1, 2, 3, 4]
    assert [result.approved for result in progress] == [False, True, False, True]
    assert len(calls) == 4


def test_generate_many_can_return_one_hundred_approved_numbers(client, monkeypatch):
    calls = decisions(monkeypatch, ["approved"] * 100)
    results = list(client.generate_many(100))

    assert len(results) == 100
    assert all(result.approved for result in results)
    assert [result.attempts for result in results] == list(range(1, 101))
    assert len(calls) == 100


def test_generate_many_allows_repeated_approved_numbers(client, monkeypatch):
    calls = decisions(monkeypatch, ["approved", "approved"])
    results = list(client.generate_many(2, 731, bottom=731))

    assert [result.number for result in results] == [731, 731]
    assert [result.attempts for result in results] == [1, 2]
    assert len(calls) == 2


def test_generate_many_is_lazy_and_does_not_prefetch(client, monkeypatch):
    calls = decisions(monkeypatch, ["meme", "approved", "approved"])
    ticks = iter([69, 731, 853])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    progress = []
    results = client.generate_many(2, on_verdict=progress.append)

    assert not calls
    assert not progress
    first = next(results)
    assert first.number == 731
    assert len(calls) == 2
    assert len(progress) == 2
    results.close()
    assert len(calls) == 2
    assert len(progress) == 2


def test_generate_many_applies_bounds_and_decimals_to_every_candidate(client, monkeypatch):
    calls = decisions(monkeypatch, ["meme", "approved", "approved"])
    ticks = iter([0, 75, 150])
    widths = []

    def draw(width):
        widths.append(width)
        return next(ticks)

    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", draw)
    results = list(client.generate_many(2, "0.5", bottom="-1", decimals=2))

    assert [result.number for result in results] == [-0.25, 0.5]
    assert widths == [151, 151, 151]
    assert [call[0]["number"] for call in calls] == [-1, -0.25, 0.5]
    assert all(call[0]["range"] == {"bottom": "-1", "top": "0.5", "decimals": 2} for call in calls)


@pytest.mark.parametrize("count", [0, -1, True, False, 1.5, "2", None])
def test_invalid_counts_do_not_call_provider(client, monkeypatch, count):
    calls = decisions(monkeypatch, [])
    results = client.generate_many(count)
    with pytest.raises(ValidationError):
        next(results)
    assert not calls


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2", 1])
def test_generate_many_invalid_attempt_limits_do_not_call_provider(client, monkeypatch, limit):
    calls = decisions(monkeypatch, [])
    with pytest.raises(ValidationError):
        list(client.generate_many(2, max_attempts=limit))
    assert not calls


@pytest.mark.parametrize("replies", [["approved", "meme"], ["meme", "approved"]])
def test_generate_many_exhaustion_preserves_partial_approvals(client, monkeypatch, replies):
    calls = decisions(monkeypatch, replies)
    progress = []
    results = client.generate_many(2, 731, bottom=731, max_attempts=2, on_verdict=progress.append)

    result = next(results)
    assert result.approved
    with pytest.raises(AttemptsExhaustedError) as caught:
        next(results)

    error = caught.value
    assert error.attempts == 2
    assert error.requested == 2
    assert error.approved == 1
    assert error.last_result is progress[-1]
    assert error.last_result.approved == (replies[-1] == "approved")
    assert "rejected 2" not in str(error).lower()
    assert "2 rejected" not in str(error).lower()
    assert len(calls) == 2
    assert len(progress) == 2


def test_generate_many_can_finish_on_final_allowed_attempt(client, monkeypatch):
    calls = decisions(monkeypatch, ["approved", "meme", "approved"])
    results = list(client.generate_many(2, max_attempts=3))

    assert [result.attempts for result in results] == [1, 3]
    assert len(calls) == 3


def test_generate_many_callback_error_stops_after_partial_success(client, monkeypatch):
    calls = decisions(monkeypatch, ["approved", "meme", "approved"])

    def stop_on_rejection(result):
        if not result.approved:
            raise RuntimeError("caller stopped")

    results = client.generate_many(2, on_verdict=stop_on_rejection)
    assert next(results).approved
    with pytest.raises(RuntimeError, match="caller stopped"):
        next(results)
    assert len(calls) == 2


def test_generate_many_provider_failure_stops_after_partial_success(client, monkeypatch):
    calls = decisions(monkeypatch, ["approved", ProviderError("offline"), "approved"])
    results = client.generate_many(2)
    assert next(results).approved
    with pytest.raises(ProviderError, match="offline"):
        next(results)
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
