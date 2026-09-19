# jevrand

jevrand generates a number, asks TypeSafe's Jev whether it looks acceptably random, and keeps going until Jev approves. You can also submit a number for judgement. Jev can object to a number being "too famous" or "suspiciously round", which seems a little harsh on numbers that haven't done anything wrong.

This is a toy. You cannot establish randomness from a single number, and rejecting particular values biases the output. Candidates come from Python's `secrets` module. Use `secrets` directly for security-sensitive work, and an appropriate generator for simulations.

## Install and run

Requires Python 3.10 or newer. Install the CLI directly from GitHub with
[uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv tool install git+https://github.com/fluffypony/jevrand.git
export TYPESAFE_API_KEY='your-key'
jevrand
```

This installs `jevrand` on your command path in its own Python environment. You
can run it from any directory without activating a virtual environment. Nothing
needs to go on PyPI, and you do not need pipx.

If your shell cannot find `jevrand`, run `uv tool update-shell` and open a new
terminal. To update it, repeat the install command with `--reinstall`. Remove it
with `uv tool uninstall jevrand`.

For a local checkout, run `uv tool install .` from the repository directory.
After you pull changes, run `uv tool install --reinstall .` to update that copy.

The default range is 0 to 10 000, inclusive, using integers. The command prints the first approved number and stops. Rejected numbers trigger another attempt, with no attempt limit unless you set one.

For OpenRouter, set `OPENROUTER_API_KEY` instead:

```sh
export OPENROUTER_API_KEY='your-key'
jevrand --provider openrouter
```

jevrand selects TypeSafe when `TYPESAFE_API_KEY` is set, otherwise it uses `OPENROUTER_API_KEY`. If both exist, TypeSafe wins. `--provider typesafe` or `--provider openrouter` selects one explicitly and requires its key. Keys come from the process environment; jevrand does not load `.env` files.

There are no runtime dependencies beyond Python's standard library.

You can also run the CLI with `python3 -m jevrand`.

## Command line

| Command | Behaviour |
| --- | --- |
| `jevrand` | Generate an approved integer from 0 to 10 000. |
| `jevrand 100` | Generate from 0 to 100. |
| `jevrand -10 10` | Generate from -10 to 10. |
| `jevrand 1 2 --decimals 3` | Generate from 1.000 to 2.000, in steps of 0.001. |
| `jevrand 100 --decimals` | Use two decimal places. |
| `jevrand check 42` | Submit 42 for a single verdict. |
| `jevrand check 3.14159 --json` | Submit a decimal and return JSON. |
| `jevrand --verbose --max-attempts 50` | Show each verdict and stop after at most 50 attempts. |
| `jevrand reasons` | Print the rejection catalogue without an API call. |

All ranges include their endpoints when those endpoints fall on the selected decimal grid. With `--decimals 2`, for example, the range `1.001 1.029` contains `1.01` and `1.02`. The default is zero decimal places, and the supported range is 0 to 9. `--decimals` and `--max-attempts` apply only to generation.

`check` accepts a supported finite number without applying the generator's default range. You can submit `-42` or `65536` without changing any bounds.

| Option | Effect |
| --- | --- |
| `--json` | Write the result as JSON. Also works with `check` and `reasons`. |
| `--verbose` | Write each generation verdict to stderr. |
| `--decimals [N]` | Use `N` decimal places, or 2 when `N` is omitted. |
| `--provider typesafe\|openrouter` | Select the provider explicitly. |
| `--timeout SECONDS` | Set the socket timeout, greater than 0 and at most 86 400 seconds. Default: 30. |
| `--max-attempts N` | Stop generation after `N` rejected candidates. Default: unlimited. |
| `--help` | Show command help. |
| `--version` | Show the installed version. |

Each candidate requires an API request and may incur a charge. If Jev dislikes every number in your range, the default loop can run indefinitely. Set `--max-attempts` when you want a limit:

```sh
jevrand 100 --max-attempts 20 --json
```

An API error stops the command immediately, without retries. jevrand does not switch providers or count a failed request as a rejection.

Plain generation writes only the approved number to stdout, so you can use it in a shell pipeline. `--verbose` keeps the objections on stderr. Decimal output retains the requested number of places; JSON uses numbers and does not retain trailing zeros.

Exit codes:

- `0`: Approval, the reason catalogue, help, or version information.
- `1`: A rejected check or exhausted attempts.
- `2`: An input, configuration, provider, or response error.
- `130`: Ctrl-C.

With `--json`, errors use `{"error": {"code": "...", "message": "..."}}` on stdout.

## Python library

For library use, install the checkout into your project's Python environment:

```sh
python3 -m pip install /path/to/jevrand
```

```python
from jevrand import Jevrand

client = Jevrand()

result = client.generate(top=100, bottom=-10, decimals=2, max_attempts=50)
print(result.number)
print(result.to_json())

verdict = client.check(42)
print(verdict.approved, verdict.reasons, verdict.explanation)
```

The library uses the same environment variables and provider order as the CLI. Each call to `check` makes one request. `generate` returns the first approved result.

Set the provider and timeout with `Jevrand(provider="openrouter", timeout=10)`. You can also pass `api_key` to the constructor, provided you specify `provider`. Number inputs accept `int`, `float`, decimal strings, and `Decimal` values.

To see each verdict as it arrives, supply a callback:

```python
import sys

from jevrand import Jevrand


def report(verdict):
    print(verdict.number, verdict.explanation, file=sys.stderr)


result = Jevrand().generate(max_attempts=50, on_verdict=report)
```

Results expose these fields:

| Field | Value |
| --- | --- |
| `number` | The candidate, as an `int` or `float`. |
| `approved` | Jev's verdict as a boolean. |
| `reasons` | An empty tuple on approval, or a tuple with one rejection code. JSON uses an array. |
| `explanation` | Local text for the selected verdict. |
| `provider` | `typesafe` or `openrouter`. |
| `model` | The model identifier sent to the provider. |
| `attempts` | The number of candidates checked so far. A standalone check uses 1. |

`to_dict()` returns the same fields as a dictionary, and `to_json()` serialises them. CLI JSON uses this same result format.

For example, a `too_famous` verdict for 42 would look like this:

```json
{
  "number": 42,
  "approved": false,
  "reasons": ["too_famous"],
  "explanation": "Too famous",
  "provider": "typesafe",
  "model": "jev-latest",
  "attempts": 1
}
```

Catch `JevrandError` for any documented library error. Its subclasses are `ValidationError`, `ConfigurationError`, `ProviderError`, `InvalidResponseError`, and `AttemptsExhaustedError`. They are exported from `jevrand`. `AttemptsExhaustedError` carries `attempts` and `last_result`, so you can inspect Jev's final objection.

Numeric inputs must be finite, fit within `±(2**53 - 1)`, and use at most 100 characters. Nonzero values must have a magnitude of at least `1e-100`. For checks, a decimal must survive conversion to a float and back without a change to its decimal value.

Decimal generation uses a fixed grid. Each generated value multiplied by `10**decimals` must fit within `±10**15`; the bounds multiplied by that same factor must fit within `±(2**53 - 1)`. Invalid bounds, unsupported precision, and non-finite values raise `ValidationError` before an API request.

## Grounds for rejection

Jev picks one category from the catalogue, or approves the number. These examples describe the categories; a model can still make a different call.

| Code | Objection | Examples |
| --- | --- | --- |
| `too_famous` | Too famous | `42`, `1729` |
| `suspiciously_round` | Suspiciously round | `1000`, `5000` |
| `meme` | Meme | `69`, `420`, `1337` |
| `counting_practice` | Looks like counting practice | `1234`, `9876` |
| `stuck_key` | Looks like a stuck key (three or more repeated digits) | `111`, `777`, `888`, `1111` |
| `copy_paste` | Suspicious use of copy and paste | `1212`, `454545` |
| `palindrome` | Too pleased with its own reflection | `1221`, `45654` |
| `borrowed_constant` | Borrowed from a maths textbook | `3.14159`, `2.71828` |
| `computer_default` | Looks like a default buffer size | `1024`, `65536` |
| `retail_price` | Looks like it is on sale | `9.99`, `19.99` |
| `calendar_entry` | Looks like a calendar entry | `20240229`, `19991231` |
| `http_error` | Looks like an HTTP error | `404`, `418` |

The criteria ask for an obvious pattern or a known reference, and tell Jev to approve a number when no clear objection applies. There is no local blacklist that guarantees 42 will fail.

Use `jevrand reasons --json` to read the full catalogue, including the criteria and examples.

## How Jev fits in

TypeSafe's Jev is a decision model. jevrand sends the candidate and its context as `state`, then asks a typed choice question with approval and the rejection categories as options. Jev selects an option. The explanation comes from jevrand's catalogue; Jev does not write a free-form rationale.

| Provider | Endpoint | Model |
| --- | --- | --- |
| TypeSafe | `https://api.typesafe.ai/v1/systemone` | `jev-latest` |
| OpenRouter | `https://openrouter.ai/api/alpha/decisions` | `~typesafe/jev-latest` |

Both use bearer authentication and the typed Decisions API. The provider receives every candidate you generate or submit for checking.

Provider documentation:

- https://docs.typesafe.ai/introduction
- https://docs.typesafe.ai/api
- https://openrouter.ai/~typesafe/jev-latest

## Development

```sh
python3 -m pip install -e '.[dev]'
pytest
```

The default tests use mock responses and a local HTTP server. They run without
provider credentials or requests to either service. Live tests are skipped unless
you select a provider:

```sh
pytest tests/test_live.py --live-provider typesafe
pytest tests/test_live.py --live-provider openrouter
```

These tests need the selected provider's API key and make billable requests. They
check repeated digits such as `888`, ordinary numbers, and the rejection loop
against Jev itself. Model changes can change the results.
