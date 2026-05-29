from __future__ import annotations

import json
import subprocess
import sys

from tbdy_engine.archx import (
    archx_run_result_to_dict,
    build_demo_snapshot,
    render_archx_markdown_report,
    run_archx_checks,
    write_archx_markdown_report,
)


TURKISH_REPORT_TEXT = [
    "Kiriş geometri minimum şartları sağlanıyor.",
    "Kolon geometri minimum şartları sağlanmıyor.",
    "Göreli kat ötelemesi sınırı aşılmış.",
]


def _demo_payload() -> dict:
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")
    return archx_run_result_to_dict(result)


def test_rendered_markdown_preserves_turkish_characters():
    markdown = render_archx_markdown_report(_demo_payload())

    for text in TURKISH_REPORT_TEXT:
        assert text in markdown


def test_written_markdown_preserves_turkish_characters_utf8(tmp_path):
    output_path = write_archx_markdown_report(_demo_payload(), tmp_path / "report.md")
    content = output_path.read_text(encoding="utf-8")

    for text in TURKISH_REPORT_TEXT:
        assert text in content


def test_report_cli_written_markdown_preserves_turkish_characters_utf8(tmp_path):
    input_path = tmp_path / "run.json"
    output_path = tmp_path / "report.md"
    input_path.write_text(json.dumps(_demo_payload(), ensure_ascii=False), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.archx.report_cli", "--input", str(input_path), "--out", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    content = output_path.read_text(encoding="utf-8")
    for text in TURKISH_REPORT_TEXT:
        assert text in content
