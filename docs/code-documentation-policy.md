# OCI Tenancy Manager code documentation

Inline documentation is part of every code change. Document the behavior a maintainer needs to preserve, without narrating ordinary syntax.

## Functions and types

- Give every class, named function, method, nested function, async function and test a concise `#` purpose comment block immediately above its declaration. For decorated classes or functions, put the comment immediately above the entire decorator block, at the same indentation as `class`, `def` or `async def`. Do not put blank lines between the comment block and declaration/decorators. Class and function docstrings inside their bodies are prohibited, including empty docstrings.
- Retain module docstrings. Document each class and each of its methods independently with an above-declaration purpose comment. For a simple helper or test, one sentence describing its purpose or protected behavior is sufficient.
- Explain meaningful inputs and return values when their interpretation is not obvious from names and types. State side effects, ownership of resources, relevant failure behavior and transaction boundaries.
- For contract models, explain what the type represents and which trust or lifecycle boundary it crosses. Add field comments where units, scope, order or provenance can be misread.
- Keep module docstrings focused on the module's responsibility and important limitations. Python anonymous validator expressions do not need artificial wrapper functions solely for documentation.

## Configuration fields

Document every field in application configuration files, including
`backend/config/application.toml`, with an adjacent purpose comment above the field. Explain
units, allowed values or bounds, and operational effects where relevant, including defaults,
reload/redeployment requirements and whether changes affect existing or only new records.
Keep comments aligned with executable validation and runtime behavior; never include secrets.
The persistent `inline_documentation` reviewer must check configuration-field comments on every
development slice that adds or changes configuration.

## Critical and difficult sections

Use short comments to explain why an invariant, ordering constraint or unusual algorithm is necessary. In particular, document:

- Source authority, identity normalization, retained organization evidence, graph validation and the gates for absence inference.
- Idempotency keys, ambiguous external outcomes, locking, optimistic revision checks, atomic audit/job writes and retry/recovery boundaries.
- Cross-tenancy credential scope, destructive-operation guards, secret lifetime and cleanup, without including secret values.
- Immutable evidence versus mutable processing/delivery state, and the limits of prototype safeguards.
- Non-obvious query/index choices, foreign-key scope, pagination stability and resource cleanup.

Keep comments adjacent to the code they justify. Describe known limitations accurately; do not claim an intent row sends a notification, a simulation qualifies OCI behavior, or database triggers prevent privileged DBA changes.

## Review and verification

Documentation must accompany the implementation rather than follow it in a separate cleanup. Review additions for missing or misplaced class/function purpose comments, forbidden class/function docstrings and comment coverage of changed safety-critical logic. The user has authorized the persistent inline-documentation reviewer for every development slice. Reuse that reviewer, or recreate the role with these instructions when unavailable, to assess documentation quality and placement; default its audit to read-only and coordinate any edits explicitly.

For documentation-only edits, check that the executable Python AST is unchanged after stripping docstrings, then run formatting and linting on the edited files. Run runtime tests when implementation changes or an unresolved behavioral concern warrants them. Existing test names do not replace their concise above-declaration purpose comments. Moving former class/function docstrings changes `__doc__` intentionally; check that no runtime behavior relies on it. If a class or Protocol method had only a docstring body, retain a valid body such as `pass` or `...` after moving its documentation. Pydantic class docstrings can contribute JSON Schema descriptions: regenerate affected artifacts and verify any resulting differences are limited to description metadata; do not add runtime documentation machinery to preserve those descriptions.

Do not add boilerplate parameter lists that repeat type hints, comments for every assignment, or docstrings to generated schemas/DDL that will be overwritten; document their generator and preserve useful generated artifact headers instead.


## Placement example and checker

```python
# Keep identity lookup constrained to the supplied source scope.
class Scope:
    # Resolve one scoped identity without changing the supplied source record.
    @classmethod
    def resolve(cls, record):
        return record.identity
```

Run `uv run --project backend python scripts/check_inline_docs.py` from the repository root. The checker requires a nonempty standalone comment block immediately above the first decorator or class/function declaration, with matching indentation; it rejects class and function docstrings even when an above-declaration comment exists. Module docstrings remain allowed. Ordinary critical-section comments inside a body remain unchanged. The checker validates placement/presence, while the persistent reviewer checks purpose and accuracy. Comment-shaped text inside strings and trailing comments on executable statements do not qualify.
