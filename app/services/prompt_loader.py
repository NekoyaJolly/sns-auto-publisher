from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaptionPromptTemplate:
    system_template: str
    user_template: str

    def render(self, *, posting_mode: str, media_summary: str) -> tuple[str, str]:
        return (
            self.system_template.strip(),
            self.user_template.format(
                posting_mode=posting_mode,
                media_summary=media_summary,
            ).strip(),
        )


class CaptionPromptLoader:
    def __init__(self, prompt_dir: Path | None = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parents[1] / "prompts" / "caption"

    def load(self) -> CaptionPromptTemplate:
        system_path = self.prompt_dir / "system.ja.md"
        user_path = self.prompt_dir / "user.ja.md"
        missing_paths = [path for path in [system_path, user_path] if not path.exists()]
        if missing_paths:
            missing = ", ".join(path.as_posix() for path in missing_paths)
            raise FileNotFoundError(f"caption生成プロンプトが見つかりません: {missing}")
        return CaptionPromptTemplate(
            system_template=system_path.read_text(encoding="utf-8"),
            user_template=user_path.read_text(encoding="utf-8"),
        )
