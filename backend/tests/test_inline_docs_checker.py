"""Verify documentation placement without executing the authored-source fixtures."""

import runpy
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_inline_docs.py"
missing_documentation = runpy.run_path(str(CHECKER))["missing_documentation"]


# Parse isolated source through the real checker without importing or executing the fixture.
def check(tmp_path, source):
    path = tmp_path / "authored.py"
    path.write_text(source)
    return missing_documentation(path)


# Accept comments above entire decorator/definition blocks at every authored function scope.
@pytest.mark.parametrize(
    "source",
    [
        "# Return current status.\ndef status(): return True\n",
        "# Await the independent check.\nasync def check(): return True\n",
        (
            "# Own scope.\nclass Scope:\n"
            "    # Await the scoped lookup.\n    @classmethod\n"
            "    async def lookup(cls): return True\n"
        ),
        (
            "# Build a scoped adapter.\n"
            "# Preserve identity.\n"
            "def adapter(\n"
            "    identity,\n"
            "):\n"
            "    return identity\n"
        ),
        "# Reject stale work.\n@guard\n@trace(\n    'read',\n)\ndef read(): return True\n",
        "# Resolve the snapshot.\n@(\n    guard\n)\ndef read(): return True\n",
        (
            "# Construct scope.\n"
            "def outer():\n"
            "    # Read within scope.\n"
            "    async def inner():\n"
            "        return True\n"
            "    return inner\n"
        ),
        (
            "# Own the scope.\nclass Scope:\n"
            "    # Expose the key.\n"
            "    @property\n"
            "    def key(self):\n"
            '        return "current"\n'
        ),
        (
            "#\n"
            "# Preserve evidence.\n"
            "#\n"
            "def evidence():\n"
            "    # Critical body comments remain.\n"
            "    return True\n"
        ),
    ],
    ids=[
        "sync",
        "async",
        "decorated-async",
        "multiline",
        "decorators",
        "parenthesized",
        "nested",
        "method",
        "block",
    ],
)
def test_correct_function_comments_pass(tmp_path, source):
    assert check(tmp_path, source) == []


# Reject unrelated or misplaced comments rather than crediting text as function purpose.
@pytest.mark.parametrize(
    "source",
    [
        "def status(): return True\n",
        "#\ndef status(): return True\n",
        "# Describe status.\n\ndef status(): return True\n",
        "@guard\n# Describe status.\ndef status(): return True\n",
        "@first\n# Describe status.\n@second\ndef status(): return True\n",
        "def status():\n    # Describe status.\n    return True\n",
        "value = 1  # Describe status.\ndef status(): return True\n",
        ("# Own scope.\nclass Scope:\n# Describe method.\n    def method(self): return True\n"),
        (
            'text = """\n'
            '# This text is data, not an authored comment."""\n'
            "def status(): return True\n"
        ),
    ],
    ids=[
        "missing",
        "empty",
        "gap",
        "under-decorator",
        "between-decorators",
        "inside",
        "trailing",
        "indent",
        "string",
    ],
)
def test_missing_or_misplaced_comments_fail(tmp_path, source):
    failures = check(tmp_path, source)
    assert len(failures) == 1
    assert "nonempty same-indent comment block immediately above" in failures[0]


# Reject old function docstrings even when a valid above-definition comment is also supplied.
@pytest.mark.parametrize("body", ['"Old function documentation."', '""'])
def test_function_docstrings_are_rejected(tmp_path, body):
    source = f"# Return status.\ndef status():\n    {body}\n    return True\n"
    failures = check(tmp_path, source)
    assert len(failures) == 1
    assert "not a docstring" in failures[0]


# Preserve module docstrings while documenting classes above their declarations.
def test_module_docstrings_and_above_class_comments_remain_valid(tmp_path):
    source = '"""Module purpose."""\n# Own scope.\nclass Scope:\n    pass\n'
    assert check(tmp_path, source) == []


# A parent's purpose comment cannot substitute for documentation of its nested helper.
def test_nested_functions_require_their_own_comment(tmp_path):
    source = (
        "# Build scope.\ndef outer():\n    def inner():\n        return True\n    return inner\n"
    )
    failures = check(tmp_path, source)
    assert len(failures) == 1 and "inner needs" in failures[0]


# Accept whole-decorator, nested and multiline class declarations with independent purpose blocks.
@pytest.mark.parametrize(
    "source",
    [
        "# Freeze scope.\n@frozen\n@registered(\n    'scope',\n)\nclass Scope: pass\n",
        "# Own scope.\nclass Outer:\n    # Bind a local scope.\n    class Inner: pass\n",
        "# Compose scope traits.\nclass Scope(\n    Readable,\n    Scoped,\n):\n    pass\n",
        "# Register scope.\n@(\n    registered\n)\nclass Scope: pass\n",
    ],
    ids=["decorated-class", "nested-class", "multiline-class", "parenthesized-class"],
)
def test_correct_class_comments_pass(tmp_path, source):
    assert check(tmp_path, source) == []


# Do not credit body comments, unrelated indentation or comments below a class decorator.
@pytest.mark.parametrize(
    "source",
    [
        "class Scope: pass\n",
        "class Scope:\n    # Own scope.\n    pass\n",
        "# Own scope.\nclass Outer:\n# Bind local scope.\n    class Inner: pass\n",
        "@registered\n# Own scope.\nclass Scope: pass\n",
    ],
    ids=["missing-class", "below-class", "class-indent", "below-class-decorator"],
)
def test_missing_or_misplaced_class_comments_fail(tmp_path, source):
    failures = check(tmp_path, source)
    assert len(failures) == 1
    assert "nonempty same-indent comment block immediately above" in failures[0]


# Reject class docstrings, including empty ones, even with a valid above-class purpose comment.
@pytest.mark.parametrize("body", ['"Old class documentation."', '""'])
def test_class_docstrings_are_rejected(tmp_path, body):
    failures = check(tmp_path, f"# Own scope.\nclass Scope:\n    {body}\n    pass\n")
    assert len(failures) == 1 and "not a docstring" in failures[0]
