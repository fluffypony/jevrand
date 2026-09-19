def pytest_addoption(parser):
    parser.addoption(
        "--live-provider",
        choices=("typesafe", "openrouter"),
        default=None,
        help="Run billable Jev regression tests against this provider (requires its API key).",
    )
