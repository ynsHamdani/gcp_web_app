from __future__ import annotations

"""PostgreSQL-backed users and revocable server-side authentication sessions."""

from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime
from typing import Any

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass(frozen=True)
class AuthUser(UserMixin):
    user_id: int
    username: str
    email: str
    role: str
    active: bool
    must_change_password: bool = False

    def get_id(self) -> str:
        return str(self.user_id)

    @property
    def is_active(self) -> bool:
        return self.active


class AuthStore:
    """User, password, audit and session operations using the existing DB adapter."""

    def __init__(self, pool) -> None:
        self.pool = pool

    @staticmethod
    def _session_hash(session_id: str) -> str:
        if not session_id:
            raise ValueError("A session identifier is required.")
        return sha256(session_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_user(row: dict | None) -> AuthUser | None:
        if row is None:
            return None
        role = str(row["user_role"]).strip().lower()
        if role not in {"student", "admin", "super_admin"}:
            return None
        return AuthUser(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            email=str(row["email"]),
            role=role,
            active=bool(row["is_active"]),
            must_change_password=bool(row.get("must_change_password", False)),
        )

    def get_by_id(self, user_id: str | int) -> AuthUser | None:
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None
        sql = """
            SELECT user_id, username, email, user_role, is_active,
                   must_change_password
            FROM users WHERE user_id = %s
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (numeric_id,))
                row = cur.fetchone()
        user = self._to_user(row)
        return user if user and user.is_active else None

    def authenticate(self, identifier: str, password: str) -> AuthUser | None:
        identifier = (identifier or "").strip()
        if not identifier or not password:
            return None
        sql = """
            SELECT user_id, username, email, password_hash, user_role,
                   is_active, must_change_password
            FROM users
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
            LIMIT 1
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (identifier, identifier))
                row = cur.fetchone()
        if row is None or not bool(row["is_active"]):
            return None
        try:
            valid = check_password_hash(str(row.get("password_hash") or ""), password)
        except (TypeError, ValueError):
            valid = False
        return self._to_user(row) if valid else None

    def verify_password(self, user_id: int, password: str) -> bool:
        sql = "SELECT password_hash FROM users WHERE user_id = %s AND is_active = TRUE"
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (int(user_id),))
                row = cur.fetchone()
        if not row or not row.get("password_hash"):
            return False
        try:
            return check_password_hash(str(row["password_hash"]), password or "")
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _validate_profile(username: str, email: str) -> tuple[str, str]:
        import re
        username = (username or "").strip()
        email = (email or "").strip().lower()
        if not username or len(username) > 100:
            raise ValueError("Username must contain 1–100 characters.")
        if "@" in username or any(character.isspace() for character in username):
            raise ValueError("Username cannot contain an @ sign or whitespace; use the email field for email addresses.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 320:
            raise ValueError("Provide a valid email address.")
        return username, email

    @staticmethod
    def _validate_password(password: str) -> str:
        if not password or len(password) < 12:
            raise ValueError("Password must contain at least 12 characters.")
        if len(password) > 1024:
            raise ValueError("Password is too long.")
        return password

    def create_user(
        self, *, username: str, email: str, password: str,
        role: str = "student", must_change_password: bool = False,
    ) -> int:
        username, email = self._validate_profile(username, email)
        password = self._validate_password(password)
        role = (role or "student").strip().lower()
        if role != "student":
            raise ValueError("This method only creates student accounts. Privileged roles require the Super Admin workflow.")
        password_hash = generate_password_hash(password)
        sql = """
            INSERT INTO users
                (username, email, password_hash, must_change_password)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (username, email, password_hash, bool(must_change_password)))
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("User creation did not return a user ID.")
        return int(row[0])

    def list_users(
        self,
        role: str | None = None,
        *,
        include_gcp_count: bool = True,
    ) -> list[dict]:
        """List users; optionally include GCP contribution counts.

        The workspace contributor dropdown does not need GCP counts, so it can
        use the narrow query and avoid aggregating the partitioned GCP table on
        every GCP workspace page load. User Management retains the counts.
        """
        role = (role or "").strip().lower() or None
        if role is not None and role not in {"student", "admin", "super_admin"}:
            raise ValueError("role must be student, admin, or super_admin.")

        if include_gcp_count:
            sql = """
                SELECT u.user_id, u.username, u.email, u.user_role, u.is_active,
                       u.must_change_password, u.created_at,
                       COUNT(g.gcp_id)::BIGINT AS gcp_count
                FROM users u
                LEFT JOIN gcps g ON g.student_id = u.user_id
            """
        else:
            sql = """
                SELECT u.user_id, u.username, u.email, u.user_role, u.is_active,
                       u.must_change_password, u.created_at,
                       0::BIGINT AS gcp_count
                FROM users u
            """
        params: tuple[Any, ...] = ()
        if role:
            sql += " WHERE u.user_role = %s"
            params = (role,)
        if include_gcp_count:
            sql += " GROUP BY u.user_id"
        sql += " ORDER BY u.user_role, LOWER(u.username)"

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        result = []
        for row in rows:
            created = row.get("created_at")
            result.append({
                "user_id": int(row["user_id"]),
                "username": str(row["username"]),
                "email": str(row["email"]),
                "user_role": str(row["user_role"]),
                "is_active": bool(row["is_active"]),
                "must_change_password": bool(row["must_change_password"]),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
                "gcp_count": int(row.get("gcp_count") or 0),
            })
        return result

    def update_student_profile(self, user_id: int, *, username: str, email: str) -> None:
        username, email = self._validate_profile(username, email)
        sql = """
            UPDATE users SET username = %s, email = %s
            WHERE user_id = %s AND user_role = 'student'
            RETURNING user_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (username, email, int(user_id)))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Student account not found: {user_id}")

    def reset_student_password(self, user_id: int, password: str) -> None:
        password = self._validate_password(password)
        password_hash = generate_password_hash(password)
        # One statement keeps password replacement and session revocation atomic
        # even though the compatibility DB adapter runs in AUTOCOMMIT mode.
        sql = """
            WITH changed AS (
                UPDATE users
                SET password_hash = %s, must_change_password = TRUE
                WHERE user_id = %s AND user_role = 'student'
                RETURNING user_id
            ), revoked AS (
                UPDATE auth_sessions s
                SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'password_reset'
                FROM changed c
                WHERE s.user_id = c.user_id AND s.revoked_at IS NULL
                RETURNING s.session_id_hash
            )
            SELECT user_id FROM changed
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (password_hash, int(user_id)))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Student account not found: {user_id}")

    def change_own_password(self, user_id: int, password: str, current_session_id: str) -> None:
        password = self._validate_password(password)
        password_hash = generate_password_hash(password)
        current_hash = self._session_hash(current_session_id) if current_session_id else None
        sql = """
            WITH changed AS (
                UPDATE users
                SET password_hash = %s, must_change_password = FALSE
                WHERE user_id = %s AND is_active = TRUE
                RETURNING user_id
            ), revoked AS (
                UPDATE auth_sessions s
                SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'password_changed'
                FROM changed c
                WHERE s.user_id = c.user_id AND s.revoked_at IS NULL
                  AND (%s = TRUE OR s.session_id_hash <> %s)
                RETURNING s.session_id_hash
            )
            SELECT user_id FROM changed
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (password_hash, int(user_id), current_hash is None, current_hash or ""))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Active account not found: {user_id}")

    def set_student_active(self, user_id: int, is_active: bool) -> None:
        sql = """
            WITH changed AS (
                UPDATE users SET is_active = %s
                WHERE user_id = %s AND user_role = 'student'
                RETURNING user_id
            ), revoked AS (
                UPDATE auth_sessions s
                SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'account_deactivated'
                FROM changed c
                WHERE NOT %s AND s.user_id = c.user_id AND s.revoked_at IS NULL
                RETURNING s.session_id_hash
            )
            SELECT user_id FROM changed
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (bool(is_active), int(user_id), bool(is_active)))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Student account not found: {user_id}")

    def _transactional_connection(self):
        """Return a SQLAlchemy transaction context for security-critical changes.

        The compatibility pool deliberately uses AUTOCOMMIT for legacy storage
        calls. Privileged account writes must instead use a real transaction so
        the account mutation, session revocation, bootstrap marker and audit
        record either all commit or all roll back.
        """
        engine = getattr(self.pool, "engine", None)
        if engine is None or not callable(getattr(engine, "begin", None)):
            raise RuntimeError(
                "A transaction-capable SQLAlchemy engine is required for privileged account changes."
            )
        return engine.begin()

    @staticmethod
    def _require_super_admin_actor(connection, actor_id: int) -> dict:
        result = connection.exec_driver_sql(
            "SELECT user_id, username, user_role, is_active FROM users WHERE user_id = %s FOR UPDATE",
            (int(actor_id),),
        )
        row = AuthStore._row_mapping(result.fetchone())
        if row is None or str(row["user_role"]).lower() != "super_admin" or not bool(row["is_active"]):
            raise PermissionError("An active Super Admin account is required for this operation.")
        return row

    @staticmethod
    def _row_mapping(row) -> dict | None:
        if row is None:
            return None
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    @staticmethod
    def _lock_bootstrap_guard(connection) -> dict:
        result = connection.exec_driver_sql(
            "SELECT guard_id, bootstrap_completed_at FROM super_admin_bootstrap_guard WHERE guard_id = 1 FOR UPDATE"
        )
        row = result.fetchone()
        if row is None:
            raise RuntimeError("Super Admin bootstrap guard is missing. Apply migration 009 first.")
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    @staticmethod
    def _insert_privileged_audit(connection, actor_id: int, action: str, target_id: int, details: dict) -> None:
        import json
        connection.exec_driver_sql(
            """
            INSERT INTO admin_audit_log (actor_user_id, action, target_type, target_id, details)
            VALUES (%s, %s, 'privileged_account', %s, %s::jsonb)
            """,
            (int(actor_id), action, str(int(target_id)), json.dumps(details, ensure_ascii=False)),
        )

    def bootstrap_super_admin(self, target_user_id: int, password: str) -> dict:
        """One-time promotion of a verified active Admin to the first Super Admin."""
        from werkzeug.security import check_password_hash

        target_user_id = int(target_user_id)
        with self._transactional_connection() as connection:
            guard = self._lock_bootstrap_guard(connection)
            if guard.get("bootstrap_completed_at") is not None:
                raise ValueError("Super Admin bootstrap has already been completed.")

            existing = connection.exec_driver_sql(
                "SELECT user_id FROM users WHERE user_role = 'super_admin' LIMIT 1"
            ).fetchone()
            if existing is not None:
                raise ValueError("A Super Admin already exists; bootstrap is not available.")

            result = connection.exec_driver_sql(
                "SELECT user_id, username, email, user_role, is_active, password_hash, must_change_password "
                "FROM users WHERE user_id = %s FOR UPDATE",
                (target_user_id,),
            )
            target = self._row_mapping(result.fetchone())
            if (
                target is None
                or str(target["user_role"]).lower() != "admin"
                or not bool(target["is_active"])
                or bool(target.get("must_change_password", False))
            ):
                raise ValueError(
                    "Bootstrap requires an existing active Admin account whose temporary-password change is complete."
                )
            stored_hash = str(target["password_hash"] or "")
            try:
                verified = bool(stored_hash) and check_password_hash(stored_hash, password or "")
            except (TypeError, ValueError):
                verified = False
            if not verified:
                raise PermissionError("The Admin account password could not be verified.")

            changed = self._row_mapping(connection.exec_driver_sql(
                "UPDATE users SET user_role = 'super_admin' "
                "WHERE user_id = %s AND user_role = 'admin' AND is_active = TRUE AND password_hash = %s "
                "RETURNING user_id, username, email, user_role, is_active",
                (target_user_id, stored_hash),
            ).fetchone())
            if changed is None:
                raise RuntimeError("The target account changed during bootstrap; no changes were committed.")

            guard_update = connection.exec_driver_sql(
                "UPDATE super_admin_bootstrap_guard "
                "SET bootstrap_completed_at = CURRENT_TIMESTAMP, bootstrapped_by = %s, promoted_user_id = %s "
                "WHERE guard_id = 1 AND bootstrap_completed_at IS NULL",
                (target_user_id, target_user_id),
            )
            if guard_update.rowcount != 1:
                raise RuntimeError("Bootstrap was already completed; no changes were committed.")
            connection.exec_driver_sql(
                "UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'super_admin_bootstrap' "
                "WHERE user_id = %s AND revoked_at IS NULL",
                (target_user_id,),
            )
            self._insert_privileged_audit(
                connection, target_user_id, "super_admin_bootstrapped", target_user_id,
                {"username": str(target["username"]), "from_role": "admin", "to_role": "super_admin", "bootstrap": True},
            )
            return {
                "user_id": int(changed["user_id"]), "username": str(changed["username"]),
                "email": str(changed["email"]), "user_role": str(changed["user_role"]),
                "is_active": bool(changed["is_active"]),
            }

    def create_privileged_user(
        self, actor_id: int, *, username: str, email: str, password: str, role: str,
    ) -> int:
        """Create an Admin/Super Admin and its audit record in one transaction."""
        username, email = self._validate_profile(username, email)
        password = self._validate_password(password)
        role = str(role or "").strip().lower()
        if role not in {"admin", "super_admin"}:
            raise ValueError("Privileged account role must be admin or super_admin.")
        password_hash = generate_password_hash(password)
        with self._transactional_connection() as connection:
            guard = self._lock_bootstrap_guard(connection)
            if guard.get("bootstrap_completed_at") is None:
                raise PermissionError("The one-time Super Admin bootstrap must be completed before privileged management is enabled.")
            self._require_super_admin_actor(connection, int(actor_id))
            created = self._row_mapping(connection.exec_driver_sql(
                """
                INSERT INTO users (username, email, password_hash, must_change_password)
                VALUES (%s, %s, %s, TRUE)
                RETURNING user_id
                """,
                (username, email, password_hash),
            ).fetchone())
            if created is None:
                raise RuntimeError("Privileged account creation did not return a user ID.")
            user_id = int(created["user_id"])
            promoted = connection.exec_driver_sql(
                "UPDATE users SET user_role = %s WHERE user_id = %s AND user_role = 'student' RETURNING user_id",
                (role, user_id),
            ).fetchone()
            if promoted is None:
                raise RuntimeError("Privileged role could not be assigned; account creation was rolled back.")
            self._insert_privileged_audit(
                connection, int(actor_id), "privileged_account_created", user_id,
                {"username": username, "email": email, "to_role": role, "is_active": True},
            )
            return user_id

    def update_privileged_account(
        self, actor_id: int, target_user_id: int, *, new_role: str, is_active: bool,
    ) -> dict:
        """Change a privileged role/status with last-Super-Admin protection and atomic audit."""
        actor_id, target_user_id = int(actor_id), int(target_user_id)
        new_role = str(new_role or "").strip().lower()
        if new_role not in {"student", "admin", "super_admin"}:
            raise ValueError("Role must be student, admin, or super_admin.")
        is_active = bool(is_active)
        if actor_id == target_user_id:
            raise ValueError("You cannot change your own privileged role or account status.")

        with self._transactional_connection() as connection:
            guard = self._lock_bootstrap_guard(connection)
            if guard.get("bootstrap_completed_at") is None:
                raise PermissionError("The one-time Super Admin bootstrap must be completed before privileged management is enabled.")
            self._require_super_admin_actor(connection, actor_id)
            target_result = connection.exec_driver_sql(
                "SELECT user_id, username, email, user_role, is_active FROM users WHERE user_id = %s FOR UPDATE",
                (target_user_id,),
            )
            target = self._row_mapping(target_result.fetchone())
            if target is None or str(target["user_role"]).lower() not in {"student", "admin", "super_admin"}:
                raise KeyError("User account not found.")

            old_role = str(target["user_role"]).lower()
            old_active = bool(target["is_active"])
            removes_active_super_admin = old_role == "super_admin" and old_active and (new_role != "super_admin" or not is_active)
            if removes_active_super_admin:
                count_result = connection.exec_driver_sql(
                    "SELECT COUNT(*) AS active_count FROM users WHERE user_role = 'super_admin' AND is_active = TRUE"
                )
                active_count_row = self._row_mapping(count_result.fetchone()) or {}
                active_count = int(active_count_row.get("active_count", 0))
                if active_count <= 1:
                    raise ValueError("This action is blocked because it would remove the last active Super Admin.")

            if old_role == new_role and old_active == is_active:
                return {
                    "user_id": target_user_id, "username": str(target["username"]),
                    "email": str(target["email"]), "user_role": old_role, "is_active": old_active,
                    "changed": False,
                }

            updated = self._row_mapping(connection.exec_driver_sql(
                "UPDATE users SET user_role = %s, is_active = %s "
                "WHERE user_id = %s AND user_role IN ('student', 'admin', 'super_admin') "
                "RETURNING user_id, username, email, user_role, is_active",
                (new_role, is_active, target_user_id),
            ).fetchone())
            if updated is None:
                raise RuntimeError("Privileged account update failed; no changes were committed.")

            if old_role != new_role or old_active != is_active:
                connection.exec_driver_sql(
                    "UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'privileged_account_changed' "
                    "WHERE user_id = %s AND revoked_at IS NULL",
                    (target_user_id,),
                )
            self._insert_privileged_audit(
                connection, actor_id, "privileged_account_updated", target_user_id,
                {
                    "username": str(target["username"]), "from_role": old_role, "to_role": new_role,
                    "from_active": old_active, "to_active": is_active,
                },
            )
            return {
                "user_id": int(updated["user_id"]), "username": str(updated["username"]),
                "email": str(updated["email"]), "user_role": str(updated["user_role"]),
                "is_active": bool(updated["is_active"]), "changed": True,
            }

    def list_privileged_audit(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        sql = """
            SELECT a.audit_id, a.action, a.target_type, a.target_id, a.details, a.created_at,
                   actor.username AS actor_username, target.username AS target_username
            FROM admin_audit_log a
            LEFT JOIN users actor ON actor.user_id = a.actor_user_id
            LEFT JOIN users target ON target.user_id = CASE
                WHEN a.target_id ~ '^[0-9]+$' THEN a.target_id::BIGINT ELSE NULL END
            WHERE a.target_type = 'privileged_account'
               OR a.action = 'super_admin_bootstrapped'
            ORDER BY a.created_at DESC, a.audit_id DESC
            LIMIT %s
        """
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=True) as cursor:
                cursor.execute(sql, (limit,))
                rows = cursor.fetchall()
        result = []
        for row in rows:
            created = row.get("created_at")
            details = row.get("details") or {}
            result.append({
                "audit_id": int(row["audit_id"]), "action": str(row["action"]),
                "target_type": str(row["target_type"]), "target_id": str(row.get("target_id") or ""),
                "details": details if isinstance(details, (dict, list)) else str(details),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
                "actor_username": str(row.get("actor_username") or "(deleted user)"),
                "target_username": str(row.get("target_username") or "(unknown account)"),
            })
        return result

    def create_session(
        self, session_id: str, user_id: int, expires_at: datetime,
        user_agent: str | None = None,
    ) -> None:
        digest = self._session_hash(session_id)
        ua = (user_agent or "")[:300]
        # Opportunistic cleanup keeps the session table bounded.
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM auth_sessions WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days'")
                cur.execute("""
                    INSERT INTO auth_sessions
                        (session_id_hash, user_id, expires_at, user_agent)
                    VALUES (%s, %s, %s, %s)
                """, (digest, int(user_id), expires_at, ua))

    def touch_session(self, session_id: str, user_id: int) -> bool:
        digest = self._session_hash(session_id)
        sql = """
            UPDATE auth_sessions
            SET last_seen_at = CASE
                WHEN last_seen_at < CURRENT_TIMESTAMP - INTERVAL '60 seconds'
                THEN CURRENT_TIMESTAMP ELSE last_seen_at END
            WHERE session_id_hash = %s AND user_id = %s
              AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
              AND last_seen_at > CURRENT_TIMESTAMP - INTERVAL '12 hours'
              AND EXISTS (SELECT 1 FROM users u WHERE u.user_id = %s AND u.is_active = TRUE)
            RETURNING session_id_hash
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (digest, int(user_id), int(user_id)))
                return cur.fetchone() is not None

    def revoke_session(self, session_id: str, user_id: int, reason: str = "logout") -> None:
        digest = self._session_hash(session_id)
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = %s
                    WHERE session_id_hash = %s AND user_id = %s AND revoked_at IS NULL
                """, (reason[:100], digest, int(user_id)))

    def revoke_user_sessions(
        self, user_id: int, *, reason: str,
        except_session_id: str | None = None,
    ) -> None:
        params: list[Any] = [reason[:100], int(user_id)]
        extra = ""
        if except_session_id:
            extra = " AND session_id_hash <> %s"
            params.append(self._session_hash(except_session_id))
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = %s "
                    "WHERE user_id = %s AND revoked_at IS NULL" + extra,
                    tuple(params),
                )

    def list_active_sessions(self, user_id: int | None = None) -> list[dict]:
        sql = """
            SELECT s.session_id_hash, s.user_id, u.username, u.email, u.user_role,
                   s.created_at, s.last_seen_at, s.expires_at, s.user_agent
            FROM auth_sessions s JOIN users u ON u.user_id = s.user_id
            WHERE s.revoked_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP
              AND s.last_seen_at > CURRENT_TIMESTAMP - INTERVAL '12 hours'
        """
        params: tuple[Any, ...] = ()
        if user_id is not None:
            sql += " AND s.user_id = %s"
            params = (int(user_id),)
        sql += " ORDER BY s.last_seen_at DESC"
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def revoke_session_hash(self, session_id_hash: str, reason: str = "admin_revoked") -> bool:
        """Revoke one session using its persisted hash (never the raw cookie token)."""
        import re
        digest = str(session_id_hash or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid session reference.")
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = %s "
                    "WHERE session_id_hash = %s AND revoked_at IS NULL RETURNING session_id_hash",
                    (str(reason)[:100], digest),
                )
                return cur.fetchone() is not None

    def log_admin_action(
        self, actor_id: int, action: str, target_type: str,
        target_id: str | int | None = None, details: dict | None = None,
    ) -> None:
        import json
        import logging
        import time

        statement = """
            INSERT INTO admin_audit_log
                (actor_user_id, action, target_type, target_id, details)
            VALUES (%s, %s, %s, %s, %s::jsonb)
        """
        parameters = (
            int(actor_id), str(action)[:100], str(target_type)[:80],
            str(target_id) if target_id is not None else None,
            json.dumps(details or {}, ensure_ascii=False),
        )
        # Transient pool/network failures are retried once. The method still
        # raises after the retry so callback-level logging can surface a
        # persistent audit outage rather than silently masking it.
        for attempt in range(2):
            try:
                with self.pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(statement, parameters)
                return
            except Exception:
                if attempt == 1:
                    logging.getLogger(__name__).exception(
                        "Admin audit insert failed after retry (action=%s, target_type=%s)",
                        str(action)[:100], str(target_type)[:80],
                    )
                    raise
                time.sleep(0.1)
