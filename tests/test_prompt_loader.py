from pathlib import Path

import pytest

from app.services.prompt_loader import CaptionPromptLoader


def test_caption_prompt_loader_reads_markdown_templates(tmp_path: Path):
    prompt_dir = tmp_path / "caption"
    prompt_dir.mkdir()
    (prompt_dir / "system.ja.md").write_text("system", encoding="utf-8")
    (prompt_dir / "user.ja.md").write_text(
        "mode={posting_mode}\nmedia={media_summary}",
        encoding="utf-8",
    )

    template = CaptionPromptLoader(prompt_dir).load()
    system, user = template.render(posting_mode="dry_run", media_summary="- image")

    assert system == "system"
    assert user == "mode=dry_run\nmedia=- image"


def test_caption_prompt_loader_reports_missing_template(tmp_path: Path):
    prompt_dir = tmp_path / "caption"
    prompt_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="caption生成プロンプト"):
        CaptionPromptLoader(prompt_dir).load()
