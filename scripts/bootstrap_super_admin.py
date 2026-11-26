from __future__ import annotations

"""One-time, password-verified bootstrap of the first Super Admin."""

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from auth.store import AuthStore
from database.db import close_db_pool, get_db_pool


def main() -> int:
    print("One-time Super Admin bootstrap")
    print("This promotes an existing active Admin account. No account is created.")
    identifier = input("Existing Admin username or email: ").strip()
    password = getpass.getpass("Password for that Admin account: ")
    if not identifier or not password:
        print("An account identifier and password are required.", file=sys.stderr)
        return 2

    pool = None
    try:
        pool = get_db_pool()
        store = AuthStore(pool)
        user = store.authenticate(identifier, password)
        if user is None or not user.is_active or user.role != "admin" or user.must_change_password:
            print(
                "Verification failed. Provide the credentials of an existing active Admin account "
                "that has completed any required temporary-password change.",
                file=sys.stderr,
            )
            return 3

        print(f"Verified account: {user.username} <{user.email}> (ID {user.user_id})")
        confirmation = input("Type BOOTSTRAP SUPER ADMIN to confirm this one-time promotion: ").strip()
        if confirmation != "BOOTSTRAP SUPER ADMIN":
            print("Confirmation did not match. No changes were made.")
            return 4

        promoted = store.bootstrap_super_admin(user.user_id, password)
        print(
            f"Bootstrap completed. {promoted['username']} is now Super Admin. "
            "All existing sessions for this account were revoked; sign in again."
        )
        return 0
    except Exception as exc:
        print(f"Super Admin bootstrap failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if pool is not None:
            close_db_pool()


if __name__ == "__main__":
    raise SystemExit(main())
