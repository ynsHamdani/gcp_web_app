# Stage 1 — Local security hardening

This patch is intended for the current Windows, single-process development setup:

```text
(gcp-web) C:\my_dev\gcp_web_app> python app1.py
```

It does not replace the application architecture, change the GCP collection workflow, alter raster/coverage formats, or modify existing research records.

## What changed

1. **Environment-aware startup.** `app1.py` reads `APP_ENV`, `APP_HOST`, `APP_PORT`, and `APP_DEBUG`. Defaults preserve local development (`development`, `127.0.0.1`, `8050`, debug enabled). Production mode refuses debug mode.
2. **Session/security settings.** The session and raster signing keys must be distinct. `SESSION_COOKIE_SECURE` remains false by default in development and defaults to true in production; production startup refuses an insecure setting. Authenticated pages, Dash endpoints, login/password pages, admin routes, and signed raster responses receive `no-store` headers. Static assets remain cacheable.
3. **Login abuse protection.** Repeated failures are throttled by normalized account identifier and remote IP: five failures per identifier and thirty per IP within a 15-minute sliding window. The response uses HTTP 429 and `Retry-After` when the limit is reached.
4. **Raster upload preflight.** The encoded upload size is checked against the existing configured limit before the raster payload is decoded into another full-size bytes object. The existing upload limits are not reduced.
5. **Audit write resilience.** Audit inserts retry once on a transient database failure. Persistent failures are logged; the coverage-assignment callback no longer silently discards its audit exception.
6. **Least-privilege Neon runtime-role script.** `scripts/create_runtime_role.sql` creates `gcp_app_runtime` with no superuser, database-creation, role-creation, replication, or RLS-bypass attributes and grants application table access only. It is deliberately separate from application startup and is not run automatically.

## Important limits

- The login throttle is **process-local**. This is appropriate for the current single-process `python app1.py` workflow. It resets when the process restarts and is not shared by multiple workers. Before production or multi-worker deployment, replace it with a shared rate-limit backend.
- The runtime-role SQL is a reviewed starting point based on the SQL in this project. It has not been executed against your live Neon database. Keep using your current database login until you create the role, test the app with it, and confirm that the existing workflows work. Run schema migrations as `neondb_owner`, not as `gcp_app_runtime`.
- The SQL script intentionally does not grant schema creation or migration-table access. When a future migration adds a runtime table, grant only the required table and sequence privileges to the runtime role.
- This patch does not claim to make the app production-ready. HTTPS termination, a production WSGI server, centralized rate limiting, backup/restore drills, deployment secrets, and production upload capacity are Stage 3 work.

## Database role setup (optional, staged)

1. Open `scripts/create_runtime_role.sql` and replace `REPLACE_WITH_A_UNIQUE_RANDOM_PASSWORD` with a unique password of at least 32 characters. Do not reuse any existing application or Neon-owner secret.
2. Run the script once in the target Neon database while connected as `neondb_owner` (or another role with permission to create roles and grant these privileges).
3. Only after the script succeeds, change the `database.user` and `database.password` values in your local, git-ignored `config.yaml` to `gcp_app_runtime` and the new password.
4. Start the app and test login, student GCP add/edit/delete, raster upload/display, Admin GCP tools, coverage import, polygon assignment, task instructions, and exports.
5. To roll back the connection, restore the previous `database.user` and `database.password` values in `config.yaml`. Do not drop the role until you have confirmed no process still uses it.

The SQL script is additive and does not change existing tables, rows, or the `neondb_owner` role.

## Install

Extract this patch ZIP, then run PowerShell from the extracted patch folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_stage1.ps1 -ProjectPath "C:\my_dev\gcp_web_app"
```

The installer backs up each file it replaces to:

```text
C:\my_dev\gcp_web_app\.stage1_security_backups\<timestamp>\
```

It does not overwrite `.env`, `config.yaml`, `data`, or your database. The install can be rolled back with:

```powershell
.\rollback_stage1.ps1 -BackupPath "C:\my_dev\gcp_web_app\.stage1_security_backups\<timestamp>"
```

## Verify in your existing environment

From your `(gcp-web)` environment and project directory:

```powershell
python -m pytest -q
python app1.py
```

Check that the app still opens at `http://127.0.0.1:8050`, student and Admin workflows behave as before, and repeated invalid logins eventually return HTTP 429. `APP_DEBUG=true` and `SESSION_COOKIE_SECURE=false` are expected for this local HTTP setup.
