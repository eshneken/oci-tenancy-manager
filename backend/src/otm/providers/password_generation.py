"""Default-compatible candidates; effective provider policy still needs verification."""

import secrets
import string

GROUPS = (string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#%+-_=")
ALPHABET = "".join(GROUPS)
PASSWORD_LENGTH = 32


# Length/classes are guaranteed locally; names/history/custom policy remain provider-owned checks.
def valid_generated_password(value, user_name):
    return (
        isinstance(value, str)
        and len(value) == PASSWORD_LENGTH
        and all(character in ALPHABET for character in value)
        and all(any(character in group for character in value) for group in GROUPS)
        and (not user_name or user_name.casefold() not in value.casefold())
    )


# Cryptographic choices and unbiased shuffle remove the old predictable class prefix.
def generate_recovery_password(user_name):
    for _ in range(16):
        characters = [secrets.choice(group) for group in GROUPS]
        characters.extend(secrets.choice(ALPHABET) for _ in range(PASSWORD_LENGTH - len(GROUPS)))
        for index in range(len(characters) - 1, 0, -1):
            other = secrets.randbelow(index + 1)
            characters[index], characters[other] = characters[other], characters[index]
        candidate = "".join(characters)
        if valid_generated_password(candidate, user_name):
            return candidate
    raise ValueError("RECOVERY_PASSWORD_GENERATION_UNAVAILABLE")
