import io

from PIL import Image


def _png_bytes(size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_vision_offline_uses_the_filename_hint(client):
    res = client.post("/api/vision", files={"file": ("tiger.png", _png_bytes(), "image/png")}, data={"user_id": "u1"})
    assert res.status_code == 200
    body = res.json()
    assert body["animal"] == "tiger"
    assert body["mode"] == "offline"
    assert body["animal_info"]["name"] == "孟加拉虎"


def test_vision_offline_without_a_hint_returns_unknown(client):
    res = client.post("/api/vision", files={"file": ("IMG_0001.png", _png_bytes(), "image/png")})
    assert res.status_code == 200
    assert res.json()["animal"] is None
    assert res.json()["animal_info"] is None


def test_vision_rejects_non_images_and_empty_files(client):
    bad = client.post("/api/vision", files={"file": ("tiger.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    empty = client.post("/api/vision", files={"file": ("tiger.png", b"", "image/png")})
    assert empty.status_code == 400


def test_prepare_image_downsizes_large_images():
    from backend import config
    from backend.services import vision

    big = _png_bytes((config.MAX_IMAGE_SIDE * 2, config.MAX_IMAGE_SIDE))
    out = Image.open(io.BytesIO(vision.prepare_image(big)))
    assert max(out.size) <= config.MAX_IMAGE_SIDE
    assert out.format == "JPEG"


def test_parse_vision_result_validates_model_output():
    from backend.services.vision import _parse_result

    animals = {"tiger": {}}
    assert _parse_result('{"animal": "tiger", "confidence": 0.93}', animals) == {"animal": "tiger", "confidence": 0.93}
    assert _parse_result('```json\n{"animal": "tiger", "confidence": 2}\n```', animals)["confidence"] == 1.0
    assert _parse_result('{"animal": "dragon", "confidence": 0.9}', animals)["animal"] is None
    assert _parse_result("not json", animals)["animal"] is None


def test_tts_strips_markdown_and_limits_length(client):
    res = client.post("/api/voice/tts", json={"text": "**老虎**是`大型`貓科動物。\n- 很會游泳"})
    body = res.json()
    assert body["status"] == "success" and body["engine"] == "browser"
    assert "*" not in body["text"] and "`" not in body["text"]

    long = client.post("/api/voice/tts", json={"text": "好" * 1000}).json()["text"]
    assert len(long) <= 410
    assert client.post("/api/voice/tts", json={"text": ""}).status_code == 422


def test_stt_requires_audio_and_an_api_key(client):
    not_audio = client.post("/api/voice/stt", files={"file": ("a.txt", b"hello", "text/plain")})
    assert not_audio.status_code == 400
    no_key = client.post("/api/voice/stt", files={"file": ("a.webm", b"\x00\x01", "audio/webm;codecs=opus")})
    assert no_key.status_code == 503
