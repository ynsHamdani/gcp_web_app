from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_development_server_defaults_to_loopback_and_environment_debug_flag():
    config = read("config.py")
    app = read("app1.py")
    assert 'os.getenv("APP_HOST", "127.0.0.1")' in config
    assert 'APP_DEBUG = _env_bool("APP_DEBUG", APP_ENV == "development")' in config
    assert 'if APP_ENV == "production" and APP_DEBUG' in config
    assert "host=APP_HOST" in app
    assert "debug=APP_DEBUG" in app


def test_private_responses_are_marked_no_store():
    source = read("auth/__init__.py")
    assert "(current_user.is_authenticated and not is_static_asset)" in source
    assert "or is_signed_raster or is_auth_page or is_admin_page or is_dash_endpoint" in source
    assert 'response.headers["Cache-Control"] = "private, no-store' in source
    assert 'response.headers["Pragma"] = "no-cache"' in source


def test_raster_base64_payload_is_size_checked_before_decode():
    source = read("maps/raster.py")
    decoder = source.split("def _decode_upload", 1)[1].split("def _hash_bytes", 1)[0]
    assert decoder.index("validate_dash_upload_size(contents") < decoder.index("base64.b64decode(encoded")


def test_neon_runtime_role_is_not_a_superuser_and_does_not_receive_schema_ddl():
    source = read("scripts/create_runtime_role.sql")
    assert "NOSUPERUSER" in source
    assert "NOCREATEDB" in source
    assert "NOCREATEROLE" in source
    assert "NOBYPASSRLS" in source
    assert "GRANT CREATE ON SCHEMA" not in source.upper()
    assert "gcp_app_runtime" in source
