import pytest

from clipforge.media.probe import MediaError, aspect_label, orientation, parse_probe


def test_aspect_labels():
    assert aspect_label(1920, 1080) == "16:9"
    assert aspect_label(1080, 1920) == "9:16"
    assert aspect_label(1080, 1080) == "1:1"
    assert aspect_label(1080, 1350) == "4:5"
    assert aspect_label(1000, 700) == "10:7"
    assert orientation(1920, 1080) == "landscape"
    assert orientation(720, 1280) == "portrait"


def _probe(**v):
    stream = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
              "avg_frame_rate": "30000/1001", **v}
    return {"streams": [stream], "format": {"duration": "12.5", "format_name": "mov,mp4"}}


def test_rotation_swaps_display_dimensions():
    info = parse_probe(_probe(side_data_list=[{"rotation": -90}]))
    assert (info.display_width, info.display_height) == (1080, 1920)
    assert info.rotation == 270
    assert info.aspect_ratio == "9:16"
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.has_audio is False


def test_no_video_stream_rejected():
    with pytest.raises(MediaError):
        parse_probe({"streams": [{"codec_type": "audio"}], "format": {"duration": "3"}})


def test_missing_duration_rejected():
    with pytest.raises(MediaError):
        parse_probe({"streams": [{"codec_type": "video", "width": 10, "height": 10}], "format": {}})
