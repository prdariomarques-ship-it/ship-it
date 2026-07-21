"""services/app_settings.py -- the settings catalog, the persisted-override
apply-at-boot hook, and the update path used by the admin PATCH endpoint."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from repositories.app_setting import AppSettingRepository
from services import app_settings as app_settings_service
from utils.config import get_settings


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _restore_auto_reply_enabled(monkeypatch):
    """`update_setting`/`apply_persisted_overrides` mutate the live,
    `@lru_cache`d `Settings` singleton in place -- priming monkeypatch with
    the current value (rather than calling it after the mutation) still
    guarantees teardown restores it, regardless of what changes it in
    between, so this test file can't leak `auto_reply_enabled` into any
    other test in the suite."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_reply_enabled", settings.auto_reply_enabled)


@pytest.mark.asyncio
async def test_apply_persisted_overrides_is_a_no_op_with_no_rows(session_factory):
    settings = get_settings()
    original = settings.auto_reply_enabled
    async with session_factory() as session:
        await app_settings_service.apply_persisted_overrides(session)
    assert settings.auto_reply_enabled == original


@pytest.mark.asyncio
async def test_apply_persisted_overrides_layers_a_stored_value_on_top_of_env_default(
    session_factory,
):
    settings = get_settings()
    settings.auto_reply_enabled = True
    async with session_factory() as session:
        await AppSettingRepository(session).upsert(
            key="auto_reply_enabled",
            value="false",
            description="x",
            category="behavior",
            editable=True,
            updated_by=None,
        )
        await app_settings_service.apply_persisted_overrides(session)
    assert settings.auto_reply_enabled is False


@pytest.mark.asyncio
async def test_apply_persisted_overrides_ignores_a_row_for_a_non_editable_key(
    session_factory,
):
    """Belt and suspenders: even if a row somehow existed for a read-only
    key (e.g. a stale row from before a key was demoted to non-editable),
    it must never be applied to the live Settings singleton."""
    settings = get_settings()
    original_jobs_enabled = settings.jobs_enabled
    async with session_factory() as session:
        await AppSettingRepository(session).upsert(
            key="jobs_enabled",
            value="false",
            description="x",
            category="behavior",
            editable=False,
            updated_by=None,
        )
        await app_settings_service.apply_persisted_overrides(session)
    assert settings.jobs_enabled == original_jobs_enabled


@pytest.mark.asyncio
async def test_list_settings_returns_every_catalog_entry(session_factory):
    async with session_factory() as session:
        entries = await app_settings_service.list_settings(session)
    keys = {entry["key"] for entry in entries}
    assert keys == {"auto_reply_enabled", "jobs_enabled", "environment"}
    by_key = {entry["key"]: entry for entry in entries}
    assert by_key["auto_reply_enabled"]["editable"] is True
    assert by_key["jobs_enabled"]["editable"] is False
    assert by_key["environment"]["editable"] is False
    # Never edited yet in this test -- no persisted row.
    assert by_key["auto_reply_enabled"]["updated_at"] is None
    assert by_key["auto_reply_enabled"]["updated_by"] is None


@pytest.mark.asyncio
async def test_update_setting_persists_and_applies_immediately(session_factory):
    async with session_factory() as session:
        updated = await app_settings_service.update_setting(
            session, "auto_reply_enabled", False, updated_by=42
        )
    assert updated["value"] is False
    assert updated["updated_by"] == 42
    assert get_settings().auto_reply_enabled is False

    async with session_factory() as session:
        entries = await app_settings_service.list_settings(session)
    by_key = {entry["key"]: entry for entry in entries}
    assert by_key["auto_reply_enabled"]["value"] is False
    assert by_key["auto_reply_enabled"]["updated_by"] == 42
    assert by_key["auto_reply_enabled"]["updated_at"] is not None


@pytest.mark.asyncio
async def test_update_setting_rejects_a_non_editable_key(session_factory):
    async with session_factory() as session:
        with pytest.raises(app_settings_service.SettingNotEditableError):
            await app_settings_service.update_setting(
                session, "jobs_enabled", False, updated_by=1
            )


@pytest.mark.asyncio
async def test_update_setting_rejects_an_unknown_key(session_factory):
    async with session_factory() as session:
        with pytest.raises(app_settings_service.UnknownSettingError):
            await app_settings_service.update_setting(
                session, "not_a_real_setting", True, updated_by=1
            )
