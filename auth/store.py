from __future__ import annotations

"""PostgreSQL-backed user lookup and password verification."""

from dataclasses import dataclass

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass(frozen=True)
class AuthUser(UserMixin):
    """Minimal Flask-Login identity backed by the existing users table."""

    user_id: int
    username: str
    email: str
    role: str
    active: bool

    def get_id(self) -> str:
        return str(self.user_id)

    @property
    def is_active(self) -> bool:
        return self.active


class AuthStore:
    """Access the existing users table through the application's DB adapter."""

    def __init__(self, pool) -> None:
        self.pool = pool

    @staticmethod
    def _to_user(row: dict | None) -> AuthUser | None:
        if row is None:
            return None

        role = str(row["user_role"]).strip().lower()
        if role not in {"student", "admin"}:
            return None

        return AuthUser(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            email=str(row["email"]),
            role=role,
            active=bool(row["is_active"]),
        )

    def get_by_id(self, user_id: str | int) -> AuthUser | None:
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None

        sql = """
            SELECT user_id, username, email, user_role, is_active
            FROM users
            WHERE user_id = %s
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (numeric_id,))
                row = cur.fetchone()

        user = self._to_user(row)
        if user is None or not user.is_active:
            return None
        return user

    def authenticate(self, identifier: str, password: str) -> AuthUser | None:
        """Authenticate against username or email without revealing which failed."""

        identifier = (identifier or "").strip()
        if not identifier or not password:
            return None

        sql = """
            SELECT user_id, username, email, password_hash, user_role, is_active
            FROM users
            WHERE LOWER(username) = LOWER(%s)
               OR LOWER(email) = LOWER(%s)
            LIMIT 1
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (identifier, identifier))
                row = cur.fetchone()

        if row is None or not bool(row["is_active"]):
            return None

        password_hash = row.get("password_hash")
        if not password_hash:
            return None

        try:
            password_valid = check_password_hash(str(password_hash), password)
        except (TypeError, ValueError):
            password_valid = False

        if not password_valid:
            return None

        return self._to_user(row)

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str,
    ) -> int:
        """Create a user with a Werkzeug-generated password hash."""

        username = (username or "").strip()
        email = (email or "").strip().lower()
        role = (role or "").strip().lower()

        if not username or len(username) > 100:
            raise ValueError("Username must contain 1–100 characters.")
        if not email or len(email) > 320 or "@" not in email:
            raise ValueError("Provide a valid email address.")
        if role not in {"student", "admin"}:
            raise ValueError("Role must be 'student' or 'admin'.")
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters.")

        password_hash = generate_password_hash(password)
        sql = """
            INSERT INTO users (username, email, password_hash, user_role)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (username, email, password_hash, role))
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("User creation did not return a user ID.")
                return int(row[0])
