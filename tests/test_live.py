import json

import pytest

from jevrand import Jevrand
from jevrand.cli import main
from jevrand.numbers import NumberRange


@pytest.fixture
def live_client(request):
    provider = request.config.getoption("--live-provider")
    if provider is None:
        pytest.skip("Select --live-provider to run billable Jev regression tests.")
    return Jevrand(provider=provider)


@pytest.mark.parametrize(
    ("number", "approved"),
    [
        (111, False),
        (222, False),
        (777, False),
        (888, False),
        (999, False),
        (-888, False),
        (8888, False),
        ("888.00", False),
        (738, True),
        (1882, True),
        (883, True),
    ],
)
def test_jev_distinguishes_repeated_digits_from_ordinary_numbers(live_client, number, approved):
    result = live_client.check(number)
    assert result.approved is approved, result.to_json()


def test_generation_rejects_888_and_continues_with_a_new_candidate(live_client, monkeypatch):
    candidates = iter([888, 738])
    monkeypatch.setattr(NumberRange, "draw", lambda self: next(candidates))
    verdicts = []

    result = live_client.generate(max_attempts=2, on_verdict=verdicts.append)

    assert result.number == 738, result.to_json()
    assert result.attempts == 2
    assert verdicts[0].number == 888
    assert verdicts[0].approved is False


def test_cli_checks_8008_without_a_replacement(live_client, monkeypatch, capsys):
    def forbid_generation(self):
        pytest.fail("A supplied number must not trigger generation.")

    monkeypatch.setattr(NumberRange, "draw", forbid_generation)
    assert main(["8008", "--provider", live_client.provider]) == 1
    output = capsys.readouterr()
    assert not output.err
    assert len(output.out.splitlines()) == 1
    assert output.out.startswith("8008: rejected."), output.out


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_shows_rejection_before_final_approval(live_client, monkeypatch, capsys, json_output):
    candidates = iter([888, 738])
    monkeypatch.setattr(NumberRange, "draw", lambda self: next(candidates))
    arguments = ["--range", "0", "10000", "--provider", live_client.provider, "--max-attempts", "2"]
    if json_output:
        arguments.append("--json")

    assert main(arguments) == 0
    output = capsys.readouterr()
    assert not output.err
    lines = output.out.splitlines()
    assert len(lines) == 2, output.out
    if json_output:
        rejected, approved = map(json.loads, lines)
        assert rejected["number"] == 888 and rejected["approved"] is False
        assert rejected["reasons"] and rejected["explanation"]
        assert approved["number"] == 738 and approved["approved"] is True
        assert approved["attempts"] == 2
    else:
        assert lines[0].startswith("[1] 888: rejected."), output.out
        assert lines[1].startswith("[2] 738: approved."), output.out


def test_cli_count_includes_only_approved_values(live_client, monkeypatch, capsys):
    candidates = iter([888, 738, 8008, 1882])
    monkeypatch.setattr(NumberRange, "draw", lambda self: next(candidates))

    assert (
        main(["--count", "2", "--max-attempts", "4", "--json", "--provider", live_client.provider])
        == 0
    )
    output = capsys.readouterr()
    assert not output.err
    verdicts = [json.loads(line) for line in output.out.splitlines()]
    assert [verdict["number"] for verdict in verdicts] == [888, 738, 8008, 1882]
    assert [verdict["approved"] for verdict in verdicts] == [False, True, False, True]
    assert [verdict["attempts"] for verdict in verdicts] == [1, 2, 3, 4]
