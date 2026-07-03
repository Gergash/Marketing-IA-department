"""Pruebas de video_providers.py: mock, Shotstack (submit->poll->download monkeypatched), fallos distintos."""

import pytest

from agents.marketing_agents.video_timeline import OutputSpec, Scene, Timeline, VoiceoverTrack
from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_static_videos(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from agents.marketing_agents import video_providers

    monkeypatch.setattr(video_providers, "_STATIC_DIR", tmp_path / "videos")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch):
    from agents.marketing_agents import video_providers

    monkeypatch.setattr(video_providers.time, "sleep", lambda *_: None)


def _sample_timeline() -> Timeline:
    scene = Scene(
        background_url="http://localhost:8000/static/images/bg1.png",
        headline="Titulo",
        subline="Sub",
        duration_s=4.0,
    )
    return Timeline(
        scenes=[scene, scene, scene],
        voiceover=VoiceoverTrack(audio_url="http://localhost:8000/static/audio/vo1.mp3", duration_s=12.0),
        output=OutputSpec(),
    )


def test_mock_provider_returns_static_videos_url_and_dims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "mock")
    get_settings.cache_clear()

    from agents.marketing_agents.video_providers import render_video

    url, width, height = render_video(_sample_timeline())
    assert url.startswith("http://localhost:8000/static/videos/")
    assert width == 1080
    assert height == 1920


def test_shotstack_submit_poll_done_downloads_mp4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "shotstack")
    monkeypatch.setenv("SHOTSTACK_API_KEY", "fake-key")
    get_settings.cache_clear()

    import httpx

    poll_statuses = iter(["submitted", "rendering", "done"])

    class _SubmitResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"response": {"id": "render-123"}}

    class _PollResponse:
        def __init__(self, status: str) -> None:
            self._status = status

        def raise_for_status(self) -> None:
            return None

        def json(self):
            payload = {"status": self._status}
            if self._status == "done":
                payload["url"] = "https://cdn.shotstack.io/fake/render-123.mp4"
            return {"response": payload}

    class _DownloadResponse:
        content = b"fake-mp4-bytes"

        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, *, json, headers, timeout):
        assert "/render" in url
        assert headers["x-api-key"] == "fake-key"
        return _SubmitResponse()

    def _fake_get(url, *, headers=None, timeout=None, follow_redirects=False):
        if "cdn.shotstack.io" in url:
            return _DownloadResponse()
        return _PollResponse(next(poll_statuses))

    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get)

    from agents.marketing_agents.video_providers import render_video

    url, width, height = render_video(_sample_timeline())
    assert url.startswith("http://localhost:8000/static/videos/")
    assert width == 1080
    assert height == 1920


def test_shotstack_failed_status_raises_distinct_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "shotstack")
    monkeypatch.setenv("SHOTSTACK_API_KEY", "fake-key")
    get_settings.cache_clear()

    import httpx

    class _SubmitResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"response": {"id": "render-123"}}

    class _PollResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"response": {"status": "failed", "error": "codec unsupported"}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _SubmitResponse())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _PollResponse())

    from agents.marketing_agents.video_providers import render_video

    with pytest.raises(RuntimeError, match="video_render_failed"):
        render_video(_sample_timeline())


def test_shotstack_poll_timeout_raises_distinct_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "shotstack")
    monkeypatch.setenv("SHOTSTACK_API_KEY", "fake-key")
    monkeypatch.setenv("VIDEO_MAX_WAIT_SECONDS", "0")
    get_settings.cache_clear()

    import httpx

    class _SubmitResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"response": {"id": "render-123"}}

    class _PollResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"response": {"status": "rendering"}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _SubmitResponse())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _PollResponse())

    from agents.marketing_agents.video_providers import render_video

    with pytest.raises(TimeoutError, match="video_render_timeout"):
        render_video(_sample_timeline())


def test_shotstack_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "shotstack")
    monkeypatch.setenv("SHOTSTACK_API_KEY", "")
    get_settings.cache_clear()

    from agents.marketing_agents.video_providers import render_video

    with pytest.raises(RuntimeError, match="video_render_failed"):
        render_video(_sample_timeline())
