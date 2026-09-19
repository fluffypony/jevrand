import json
import os
import subprocess
import sys

import pytest

from jevrand.cli import main
from jevrand.errors import ProviderError
from jevrand.providers import Provider


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def approve(monkeypatch):
    monkeypatch.setattr(Provider, "decide", lambda *args: "approved")
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: width - 1)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], "10000"),
        (["100"], "100"),
        (["-10", "-2"], "-2"),
        (["1", "2", "--decimals", "3"], "2.000"),
        (["1", "2", "--decimals"], "2.00"),
        (["--json", "-1e2", "-1e1"], None),
    ],
)
def test_generate_forms(approve, capsys, args, expected):
    assert main(args) == 0
    output = capsys.readouterr()
    assert not output.err
    if expected is not None:
        assert output.out.strip() == expected
    else:
        assert json.loads(output.out)["number"] == -10


def test_check_rejected_json(monkeypatch, capsys):
    monkeypatch.setattr(Provider, "decide", lambda *args: "too_famous")
    assert main(["check", "42", "--json"]) == 1
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["reasons"] == ["too_famous"]


def test_verbose_preserves_json_stdout(monkeypatch, capsys):
    replies = iter(["meme", "approved"])
    monkeypatch.setattr(Provider, "decide", lambda *args: next(replies))
    assert main(["--verbose", "--json"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["attempts"] == 2
    assert "rejected" in output.err
    assert "approved" in output.err


@pytest.mark.parametrize(
    "args",
    [
        ["check"],
        ["check", "42", "43"],
        ["reasons", "1"],
        ["1", "2", "3"],
        ["10", "0"],
        ["--no-such-flag"],
        ["--decimals", "10"],
        ["--max-attempts", "0"],
        ["NaN"],
        ["check", "42", "--decimals"],
        ["check", "42", "--max-attempts", "5"],
    ],
)
def test_invalid_input_has_json_error(args, capsys):
    assert main([*args, "--json"]) == 2
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["error"]["code"] == "invalid_input"


def test_exhaustion_json(monkeypatch, capsys):
    monkeypatch.setattr(Provider, "decide", lambda *args: "meme")
    assert main(["--max-attempts", "2", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "attempts_exhausted"


def test_provider_error_json(monkeypatch, capsys):
    def fail(*args):
        raise ProviderError("offline")

    monkeypatch.setattr(Provider, "decide", fail)
    assert main(["--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "provider_error"


def test_interrupt_json(monkeypatch, capsys):
    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(Provider, "decide", interrupt)
    assert main(["--json"]) == 130
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "interrupted"


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["reasons", "--json"]])
def test_offline_commands_in_fresh_process(args):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "TYPESAFE_API_KEY",
            "OPENROUTER_API_KEY",
        )
    }
    completed = subprocess.run(
        [sys.executable, "-m", "jevrand", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout
    assert not completed.stderr


def test_missing_credentials(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert main(["--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "configuration_error"
