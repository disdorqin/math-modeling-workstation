import json
from pathlib import Path

from mathworkstation.cli import main


def test_cli_case_and_workflow_round_trip(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "output"
    assert main(["--output-root", str(output_root), "create-case", "--competition", "SM", "--title", "CLI"]) == 0
    case = json.loads(capsys.readouterr().out)
    assert main(["--output-root", str(output_root), "show-workflow", "--case-id", case["case_id"]]) == 0
    workflow = json.loads(capsys.readouterr().out)
    assert workflow["nodes"]["input_validation"]["status"] == "PENDING"


def test_cli_blocks_generic_success_for_protected_nodes(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "output"
    assert main(["--output-root", str(output_root), "create-case", "--competition", "SM", "--title", "Guard"]) == 0
    case = json.loads(capsys.readouterr().out)
    result = main(
        [
            "--output-root",
            str(output_root),
            "succeed-node",
            "--case-id",
            case["case_id"],
            "--node-id",
            "model_plan",
        ]
    )
    assert result == 1
    assert "dedicated validated service" in capsys.readouterr().err
