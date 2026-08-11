from upload_subtitles import current_manual_upload_surface


def test_current_manual_upload_surface_recognizes_video_language():
    text = "Languages Video language: English Edit subtitles Upload manual"

    assert current_manual_upload_surface(text, "English") is True


def test_current_manual_upload_surface_rejects_other_language():
    text = "Languages Video language: Russian Edit subtitles Upload manual"

    assert current_manual_upload_surface(text, "English") is False
