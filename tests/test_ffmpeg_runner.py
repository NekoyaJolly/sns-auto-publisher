from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.utils.ffmpeg_runner import FFmpegExecutionError, FFmpegNotFoundError, FFmpegRunner


def test_probe_video_parses_ffprobe_json(monkeypatch, tmp_path: Path):
    input_path = tmp_path / "movie.mp4"
    input_path.write_bytes(b"movie")

    def fake_which(binary_name: str) -> str:
        return f"/usr/bin/{binary_name}"

    def fake_run(command, capture_output, check, text):
        assert isinstance(command, list)
        assert command[0] == "ffprobe"
        return CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":[{"codec_type":"video","codec_name":"h264",'
                '"width":1280,"height":720,"duration":"5.5"}],'
                '"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"5.5"}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("app.utils.ffmpeg_runner.shutil.which", fake_which)
    monkeypatch.setattr("app.utils.ffmpeg_runner.subprocess.run", fake_run)

    info = FFmpegRunner().probe_video(input_path)

    assert info.duration_seconds == 5.5
    assert info.width == 1280
    assert info.height == 720
    assert info.codec_name == "h264"
    assert info.format_name == "mov,mp4,m4a,3gp,3g2,mj2"


def test_probe_video_raises_when_ffprobe_is_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.utils.ffmpeg_runner.shutil.which", lambda _binary_name: None)

    with pytest.raises(FFmpegNotFoundError, match="ffprobeが見つかりません"):
        FFmpegRunner().probe_video(tmp_path / "movie.mp4")


def test_convert_to_mp4_raises_on_ffmpeg_failure(monkeypatch, tmp_path: Path):
    input_path = tmp_path / "movie.mov"
    output_path = tmp_path / "movie.mp4"
    input_path.write_bytes(b"movie")

    monkeypatch.setattr("app.utils.ffmpeg_runner.shutil.which", lambda binary_name: f"/usr/bin/{binary_name}")
    monkeypatch.setattr(
        "app.utils.ffmpeg_runner.subprocess.run",
        lambda command, capture_output, check, text: CompletedProcess(command, 1, stdout="", stderr="failed"),
    )

    with pytest.raises(FFmpegExecutionError, match="動画変換に失敗"):
        FFmpegRunner().convert_to_mp4(input_path=input_path, output_path=output_path)
