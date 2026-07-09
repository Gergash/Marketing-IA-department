import pytest

from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    # get_settings usa lru_cache: sin esto, el .env ambiente cacheado por un
    # test contamina los monkeypatch.setenv de los siguientes
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
