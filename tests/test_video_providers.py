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


def test_publicize_edit_rewrites_localhost_srcs() -> None:
    from agents.marketing_agents.video_providers import _publicize_edit

    edit = {
        "timeline": {
            "soundtrack": {"src": "http://localhost:8000/static/audio/vo.wav", "effect": "fadeOut"},
            "tracks": [
                {
                    "clips": [
                        {"asset": {"type": "image", "src": "http://localhost:8000/static/images/a.png"}, "start": 0, "length": 4},
                        {"asset": {"type": "title", "text": "Hola"}, "start": 0, "length": 4},
                    ]
                }
            ],
        },
        "output": {"format": "mp4"},
    }
    public = _publicize_edit(edit, "https://example.ngrok-free.dev")
    assert public["timeline"]["soundtrack"]["src"] == "https://example.ngrok-free.dev/static/audio/vo.wav"
    assert public["timeline"]["tracks"][0]["clips"][0]["asset"]["src"] == (
        "https://example.ngrok-free.dev/static/images/a.png"
    )
    # title sin src no se toca; original intacto
    assert edit["timeline"]["soundtrack"]["src"].startswith("http://localhost:8000")
    assert public["timeline"]["tracks"][0]["clips"][1]["asset"]["text"] == "Hola"


def test_publicize_edit_leaves_fal_cdn_srcs_untouched() -> None:
    from agents.marketing_agents.video_providers import _publicize_edit

    fal_img = "https://v3b.fal.media/files/b/abc/scene.jpg"
    fal_audio = "https://v3b.fal.media/files/b/abc/vo.wav"
    edit = {
        "timeline": {
            "soundtrack": {"src": fal_audio, "effect": "fadeOut"},
            "tracks": [{"clips": [{"asset": {"type": "image", "src": fal_img}, "start": 0, "length": 4}]}],
        },
        "output": {"format": "mp4"},
    }
    public = _publicize_edit(edit, "https://example.ngrok-free.dev")
    assert public["timeline"]["soundtrack"]["src"] == fal_audio
    assert public["timeline"]["tracks"][0]["clips"][0]["asset"]["src"] == fal_img


def test_publicize_edit_rewrites_127_0_0_1() -> None:
    from agents.marketing_agents.video_providers import _publicize_edit

    edit = {
        "timeline": {
            "tracks": [
                {"clips": [{"asset": {"type": "video", "src": "http://127.0.0.1:8000/static/clips/a.mp4"}, "start": 0, "length": 4}]}
            ]
        },
        "output": {"format": "mp4"},
    }
    public = _publicize_edit(edit, "https://example.ngrok-free.dev")
    assert public["timeline"]["tracks"][0]["clips"][0]["asset"]["src"] == (
        "https://example.ngrok-free.dev/static/clips/a.mp4"
    )


def test_shotstack_submit_400_includes_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "shotstack")
    monkeypatch.setenv("SHOTSTACK_API_KEY", "fake-key")
    get_settings.cache_clear()

    import httpx

    class _BadResponse:
        text = '{"success":false,"message":"Invalid style"}'
        status_code = 400

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "Client error '400 Bad Request'",
                request=httpx.Request("POST", "https://api.shotstack.io/stage/render"),
                response=httpx.Response(400, text=self.text),
            )

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _BadResponse())

    from agents.marketing_agents.video_providers import render_video

    with pytest.raises(RuntimeError, match="Invalid style"):
        render_video(_sample_timeline())
