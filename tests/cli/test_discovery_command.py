from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from app.cli.__main__ import cli


def test_discovery_plan_command_outputs_queries(tmp_path: Path) -> None:
    config = tmp_path / "matter.json"
    config.write_text(
        json.dumps(
            {
                "title": "Matter",
                "custodians": ["ceo@example.com"],
                "sources": [{"kind": "custom_csv", "label": "CSV export"}],
                "keyword_sets": [{"name": "terms", "terms": ["complaint"]}],
                "export_target": "local_csv",
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["--no-interactive", "discovery", "plan", str(config)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["title"] == "Matter"
    assert payload["queries"][0]["query_text"] == "(complaint) AND custodian:(ceo@example.com)"


def test_discovery_run_command_writes_artifacts(tmp_path: Path) -> None:
    config = tmp_path / "matter.json"
    config.write_text(
        json.dumps(
            {
                "title": "Matter",
                "custodians": [{"email": "ceo@example.com"}],
                "sources": [{"kind": "custom_csv", "label": "CSV export"}],
                "keyword_sets": [{"name": "terms", "terms": ["complaint"]}],
                "export_target": "local_csv",
            }
        ),
        encoding="utf-8",
    )
    source = tmp_path / "export.csv"
    source.write_text(
        "source,message_id,timestamp,sender,text\n"
        "slack,1,2026-01-01T00:00:00+00:00,ceo@example.com,complaint received\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    result = CliRunner().invoke(
        cli,
        [
            "--no-interactive",
            "discovery",
            "run",
            str(config),
            "--source",
            str(source),
            "--out",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "discovery_evidence.csv").exists()
    assert (output_dir / "discovery_hit_report.csv").exists()
    assert (output_dir / "discovery_manifest.json").exists()
    assert "Matched rows: 1" in result.output
