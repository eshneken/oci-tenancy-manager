"""Verify a downloaded public release through standard GitHub attestations; never deploy."""

from otm.release_verification import main

if __name__ == "__main__":
    raise SystemExit(main())
