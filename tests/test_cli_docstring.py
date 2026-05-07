from ntask._cli_docstring import parse_docstring


def test_first_line_as_summary():
    parsed = parse_docstring("Run tests.\n\nLong description here.")
    assert parsed.summary == "Run tests."


def test_no_docstring_yields_empty_summary():
    parsed = parse_docstring(None)
    assert parsed.summary == ""
    assert parsed.args == {}


def test_google_args_block_parsed():
    doc = """Run tests.

    Args:
        pattern: only run tests matching this glob
        verbose: verbose output
    """
    parsed = parse_docstring(doc)
    assert parsed.args["pattern"] == "only run tests matching this glob"
    assert parsed.args["verbose"] == "verbose output"


def test_google_args_multiline_description():
    doc = """Build.

    Args:
        target: the build target
            which may include a suffix like ``-debug``
        env: environment name
    """
    parsed = parse_docstring(doc)
    assert "may include a suffix" in parsed.args["target"]
    assert parsed.args["env"] == "environment name"
