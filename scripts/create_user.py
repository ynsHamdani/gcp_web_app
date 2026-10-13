from __future__ import annotations

"""Create a student or administrator account interactively."""

import argparse
import getpass
import sys
from pathlib import Path

# Make the project root importable when this script is run as `python scripts/create_user.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from auth.store import AuthStore
from database.db import close_db_pool, get_db_pool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role",
        choices=("student", "admin"),
        help="Account role. If omitted, it is requested interactively.",
    )
    args = parser.parse_args()

    username = input("Username: ").strip()
    email = input("Email: ").strip()
    role = args.role or input("Role [student/admin]: ").strip().lower()
    if role not in {"student", "admin"}:
        parser.error("Role must be 'student' or 'admin'.")

    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match.")
    if len(password) < 12:
        parser.error("Password must contain at least 12 characters.")

    try:
        pool = get_db_pool()
        user_id = AuthStore(pool).create_user(
            username=username,
            email=email,
            password=password,
            role=role,
        )
        print(f"Created {role} account {username!r} with user_id={user_id}.")
        return 0
    except Exception as exc:
        print(f"Could not create account: {exc}", file=sys.stderr)
        return 1
    finally:
        close_db_pool()


if __name__ == "__main__":
    raise SystemExit(main())
