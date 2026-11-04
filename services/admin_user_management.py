from __future__ import annotations

"""Pure helpers for safe student roster imports and one-time credentials."""

import base64
import csv
import io
import re
import secrets
import string


def generate_temporary_password(length: int = 22) -> str:
    if length < 16:
        raise ValueError("Temporary passwords must be at least 16 characters.")
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%*-_"]
    alphabet = "".join(groups)
    # Guarantee a character from every class, then cryptographically shuffle.
    chars = [secrets.choice(group) for group in groups]
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def parse_student_roster(
    contents: str, *, max_rows: int = 1000, max_bytes: int = 2 * 1024 * 1024
) -> list[dict]:
    if not contents or "," not in contents:
        raise ValueError("Upload a CSV file containing username and email columns.")
    encoded = contents.split(",", 1)[1].strip()
    estimated_bytes = max(0, (len(encoded) * 3 // 4) - (len(encoded) - len(encoded.rstrip("="))))
    if estimated_bytes > max_bytes:
        raise ValueError(f"The CSV roster exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    try:
        raw = base64.b64decode(encoded, validate=True).decode("utf-8-sig")
    except Exception as exc:
        raise ValueError("The roster must be a UTF-8 CSV file.") from exc
    reader = csv.DictReader(io.StringIO(raw))
    header_map = {str(x or "").strip().lower(): x for x in (reader.fieldnames or [])}
    if not {"username", "email"}.issubset(header_map):
        raise ValueError("CSV headers must include username,email. All imported accounts are students.")

    rows: list[dict] = []
    seen_usernames: set[str] = set()
    seen_emails: set[str] = set()
    for line_no, item in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            raise ValueError(f"A maximum of {max_rows} student rows can be imported at once.")
        username = str(item.get(header_map["username"]) or "").strip()
        email = str(item.get(header_map["email"]) or "").strip().lower()
        if not username and not email:
            continue
        errors = []
        if not username or len(username) > 100:
            errors.append("username must contain 1–100 characters")
        elif "@" in username or any(character.isspace() for character in username):
            errors.append("username cannot contain @ or whitespace")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 320:
            errors.append("email is invalid")
        if username.casefold() in seen_usernames:
            errors.append("duplicate username in this CSV")
        if email.casefold() in seen_emails:
            errors.append("duplicate email in this CSV")
        seen_usernames.add(username.casefold())
        seen_emails.add(email.casefold())
        rows.append({"line": line_no, "username": username, "email": email, "error": "; ".join(errors)})
    if not rows:
        raise ValueError("The CSV contains no student rows.")
    return rows


def credentials_csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["username", "email", "temporary_password", "must_change_password"])
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")
