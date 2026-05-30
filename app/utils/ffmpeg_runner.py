from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


class FFmpegNotFoundError(FFmpegError):
    pass


class FFmpegExecutionError(FFmpegError):
    pass


@dataclass(frozen=True)
class VideoProbeInfo:
    duration_seconds: float
    width: int
    height: int
    codec_name: str
    format_name: str


class FFmpegRunner:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def probe_video(self, input_path: Path | str) -> VideoProbeInfo:
        self._ensure_binary(self.ffprobe_path, "動画処理に必要なffprobeが見つかりません。")
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ]
        completed = self._run(command, "ffprobeによる動画メタデータ取得に失敗しました")
        try:
            payload = json.loads(completed.stdout)
            video_stream = next(
                stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"
            )
            duration = video_stream.get("duration") or payload.get("format", {}).get("duration")
            return VideoProbeInfo(
                duration_seconds=float(duration),
                width=int(video_stream["width"]),
                height=int(video_stream["height"]),
                codec_name=str(video_stream.get("codec_name") or ""),
                format_name=str(payload.get("format", {}).get("format_name") or ""),
            )
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.exception("ffprobe出力の解析に失敗しました")
            raise FFmpegExecutionError("ffprobeによる動画メタデータ取得に失敗しました") from exc

    def convert_to_mp4(
        self,
        *,
        input_path: Path | str,
        output_path: Path | str,
        max_width: int = 1920,
        max_height: int = 1920,
    ) -> None:
        self._ensure_binary(self.ffmpeg_path, "動画処理に必要なffmpegが見つかりません。")
        scale_filter = (
            f"scale='min({max_width},iw)':'min({max_height},ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
        )
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run(command, "ffmpegによる動画変換に失敗しました")

    def create_thumbnail(
        self,
        *,
        input_path: Path | str,
        output_path: Path | str,
        seek_seconds: float = 1.0,
    ) -> None:
        self._ensure_binary(self.ffmpeg_path, "動画処理に必要なffmpegが見つかりません。")
        command = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            str(seek_seconds),
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        self._run(command, "ffmpegによる動画サムネイル生成に失敗しました")

    @staticmethod
    def _ensure_binary(binary_name: str, message: str) -> None:
        if shutil.which(binary_name) is None:
            logger.error("%s がPATH上に見つかりません", binary_name)
            raise FFmpegNotFoundError(message)

    @staticmethod
    def _run(command: list[str], error_message: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            logger.error("%s: stderr=%s", error_message, completed.stderr)
            raise FFmpegExecutionError(error_message)
        return completed
