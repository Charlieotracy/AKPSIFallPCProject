"""Settings tests (INV-8, CUJ 4, Goal 10).

Every Settings() here passes _env_file=None so a developer's backend/.env can't change results.
The autouse fixture in conftest clears APP_ENV, DEV_IDENTITY_ENABLED and DATABASE_URL.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import LOCAL_SQLITE_URL, Settings


def test_missing_app_env_means_prod():
    assert Settings(_env_file=None).app_env == "prod"


def test_dev_identity_rejected_when_app_env_unset(monkeypatch):
    monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")
    with pytest.raises(ValidationError, match="only allowed when APP_ENV is local or test"):
        Settings(_env_file=None)


def test_validation_error_does_not_echo_database_url(monkeypatch):
    secret_url = "postgresql+asyncpg://jev:s3cret-password@db.example/jev"
    monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", secret_url)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "s3cret-password" not in str(excinfo.value)


def test_dev_identity_rejected_in_prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("env", ["local", "test"])
def test_dev_identity_allowed_in_local_and_test(monkeypatch, env):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")
    settings = Settings(_env_file=None)
    assert settings.app_env == env
    assert settings.dev_identity_enabled is True


def test_prod_without_database_url_refuses():
    settings = Settings(_env_file=None, app_env="prod")
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        _ = settings.resolved_database_url


def test_local_without_database_url_uses_sqlite_default():
    assert Settings(_env_file=None, app_env="local").resolved_database_url == LOCAL_SQLITE_URL


def test_empty_database_url_counts_as_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "")
    assert Settings(_env_file=None).resolved_database_url == LOCAL_SQLITE_URL


def test_explicit_database_url_wins():
    url = "postgresql+asyncpg://u:p@localhost/db"
    assert Settings(_env_file=None, app_env="prod", database_url=url).resolved_database_url == url


def test_env_file_is_ignored_when_disabled(tmp_path, monkeypatch):
    # Guards the Blocker from review: a developer's .env must not leak into tests.
    (tmp_path / ".env").write_text("APP_ENV=local\nDEV_IDENTITY_ENABLED=true\n")
    monkeypatch.chdir(tmp_path)
    assert Settings(_env_file=None).app_env == "prod"
    assert Settings().app_env == "local"  # without the override, .env is read


# --- Phase 5: these need create_app -----------------------------------------------------


def test_create_app_refuses_dev_identity_without_app_env(tmp_path, monkeypatch):
    from app.main import create_app

    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("DEV_IDENTITY_ENABLED", "true")
    with pytest.raises(ValidationError):
        create_app()


def test_create_app_refuses_prod_without_database_url():
    from app.main import create_app

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        create_app(Settings(_env_file=None, app_env="prod"))
