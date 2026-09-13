"""Pruebas VideoProducer + cloud footage helpers (sin red real)."""

from agents.marketing_agents.cloud_footage import list_cloud_footage
from agents.marketing_agents.schemas import CloudFootageRef
from agents.marketing_agents.transcription_providers import ClipTranscript, Word
from agents.marketing_agents.video_producer import VideoProducerAgent, _select_stub_auto
from agents.marketing_agents.schemas import BriefInput, StrategyOutput


def test_select_stub_auto_prefers_price_keywords() -> None:
    words = []
    for i in range(40):
        start = float(i)
        text = "precio especial hoy" if i == 10 else f"blabla{i}"
        words.append(Word(text=text, start_s=start, end_s=start + 0.8))
    tr = ClipTranscript(clip_id="c1", words=words, text=" ".join(w.text for w in words))
    brief = BriefInput(tema="promo", publico_objetivo="clientes", red_social="instagram", objetivo="leads")
    segs = _select_stub_auto([tr], brief, "mostrar precios", 5)
    assert segs
    assert any("precio" in s.text for s in segs)


def test_list_cloud_footage_filters_videos(monkeypatch) -> None:
    import agents.marketing_agents.cloud_footage as cf

    monkeypatch.setattr(cf, "get_drive_access_token", lambda db, tenant_id: "tok")

    def _fake_list(token, folder_id):
        return [
            {"id": "1", "name": "a.mp4", "mimeType": "video/mp4"},
            {"id": "2", "name": "notes.txt", "mimeType": "text/plain"},
        ]

    import agents.marketing_agents.drive_source as ds

    monkeypatch.setattr(ds, "_list_folder_files", _fake_list)
    refs = list_cloud_footage(db=None, tenant_id="t", folder_id="f")
    assert len(refs) == 1
    assert isinstance(refs[0], CloudFootageRef)
    assert refs[0].file_id == "1"
