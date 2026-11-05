"""Require purpose comments above class and function declarations; retain module docstrings."""

import ast
import io
import tokenize
from pathlib import Path


# Validate each named definition at its own indentation and above its whole decorator block.
# Tokenization prevents comment-shaped data inside strings from satisfying the documentation rule.
def missing_documentation(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    comments = {
        token.start[0]: (lines[token.start[0] - 1][: token.start[1]], token.string[1:].strip())
        for token in tokens
        if token.type == tokenize.COMMENT
    }
    decorators = [token for token in tokens if token.type == tokenize.OP and token.string == "@"]
    failures = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        location = f"{path}:{node.lineno}: {getattr(node, 'name', '')}"
        if ast.get_docstring(node) is not None:
            failures.append(f"{location} must use an above-declaration comment, not a docstring")
        anchor = node.lineno
        if node.decorator_list:
            first_expression = min(decorator.lineno for decorator in node.decorator_list)
            # Parenthesized decorator expressions can start below the actual leading @ token.
            anchor = max(
                token.start[0]
                for token in decorators
                if token.start[1] == node.col_offset and token.start[0] <= first_expression
            )
        indent = lines[node.lineno - 1][: node.col_offset]
        previous = anchor - 1
        documented = False
        while previous in comments and comments[previous][0] == indent:
            documented = documented or bool(comments[previous][1])
            previous -= 1
        if not documented:
            failures.append(
                f"{location} needs a nonempty same-indent comment block immediately above "
                "its decorator block or declaration"
            )
    return failures


# Check authored application, experiment, test and tool code without scanning environments.
def main() -> None:
    root = Path(__file__).resolve().parents[1]
    # Include nested helpers and tests; generated contracts and virtual environments are excluded.
    paths = sorted(
        path
        for folder in (
            "prototype/experiments/runner/src",
            "prototype/experiments/runner/tests",
            "prototype/experiments/runner/scripts",
            "backend/migrations",
            "backend/src",
            "backend/tests",
            "prototype/backend",
            "prototype/scripts",
            "scripts",
        )
        for path in (root / folder).rglob("*.py")
    )
    failures = [failure for path in paths for failure in missing_documentation(path)]
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Above-declaration class and function comments present across {len(paths)} Python files."
    )


if __name__ == "__main__":
    main()
