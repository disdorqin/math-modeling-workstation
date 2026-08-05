"""Validate the clean public sales package layout."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


SKILLS = [
    "math-modeling-orchestrator",
    "mm-problem-decomposer",
    "mm-model-selector",
    "mm-variable-assumption-builder",
    "mm-data-eda-cleaning",
    "mm-evaluation-models",
    "mm-prediction-models",
    "mm-optimization-models",
    "mm-classification-clustering",
    "mm-simulation-models",
    "mm-paper-structure-writer",
    "mm-abstract-polisher",
    "mm-paper-reviewer",
]

REQUIRED_SECTIONS = [
    "Purpose",
    "When to use",
    "When not to use",
    "Required inputs",
    "Workflow",
    "Output format",
    "Quality checks",
    "Academic integrity boundaries",
]


def public_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run(root: Path, command: list[str], errors: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        errors.append(
            "command failed: "
            + " ".join(command)
            + f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def validate_structure(root: Path, errors: list[str]) -> None:
    if not (root / "数学建模全流程AI-Skills包介绍.md").is_file():
        errors.append("missing root overview md")
    skills_root = root / "skills"
    if not skills_root.is_dir():
        errors.append("missing skills folder")
        return
    visible_root = sorted(p.name for p in root.iterdir())
    if visible_root != ["skills", "数学建模全流程AI-Skills包介绍.md"]:
        errors.append(f"public root should contain only overview md and skills/: {visible_root}")
    for skill_name in SKILLS:
        skill_dir = skills_root / skill_name
        skill_md = skill_dir / "SKILL.md"
        openai_yaml = skill_dir / "agents" / "openai.yaml"
        refs = skill_dir / "references"
        if not skill_md.is_file():
            errors.append(f"{skill_name}: missing SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        if f"name: {skill_name}" not in text:
            errors.append(f"{skill_name}: frontmatter name mismatch")
        if "description:" not in text:
            errors.append(f"{skill_name}: missing description")
        for section in REQUIRED_SECTIONS:
            if f"## {section}" not in text:
                errors.append(f"{skill_name}: missing section {section}")
        if not openai_yaml.is_file():
            errors.append(f"{skill_name}: missing agents/openai.yaml")
        elif f"${skill_name}" not in openai_yaml.read_text(encoding="utf-8"):
            errors.append(f"{skill_name}: openai.yaml missing explicit trigger")
        if not refs.is_dir() or not any(refs.iterdir()):
            errors.append(f"{skill_name}: missing non-empty references")
    counts = {
        "_shared/templates": 8,
        "_shared/model_cards": 15,
        "_shared/checklists": 5,
    }
    for folder, expected in counts.items():
        found = len(list((skills_root / folder).glob("*.md")))
        if found != expected:
            errors.append(f"{folder}: expected {expected}, found {found}")
    script_count = sum(len(list((skills_root / skill_name / "scripts").glob("*.py"))) for skill_name in SKILLS)
    if script_count != 15:
        errors.append(f"expected 15 skill scripts, found {script_count}")


def validate_scripts(root: Path, errors: list[str]) -> None:
    py = sys.executable
    skills_root = root / "skills"
    for skill_name in SKILLS:
        for script in sorted((skills_root / skill_name / "scripts").glob("*.py")):
            run(root, [py, str(script.relative_to(root)), "--help"], errors)


def validate_demo(root: Path, errors: list[str]) -> None:
    py = sys.executable
    commands = [
        [
            py,
            "skills/mm-data-eda-cleaning/scripts/eda_report.py",
            "--input",
            "skills/_examples/sample_data_prediction.csv",
            "--output",
            "/tmp/mm_public_eda",
        ],
        [
            py,
            "skills/mm-evaluation-models/scripts/entropy_weight.py",
            "--input",
            "skills/_examples/sample_data_evaluation.csv",
            "--output",
            "/tmp/mm_public_entropy",
            "--columns",
            "x1,x2,x3",
            "--directions",
            "positive,negative,positive",
        ],
        [
            py,
            "skills/mm-prediction-models/scripts/gm11.py",
            "--input",
            "skills/_examples/sample_data_prediction.csv",
            "--output",
            "/tmp/mm_public_gm11",
            "--column",
            "usage",
            "--periods",
            "2",
        ],
    ]
    for command in commands:
        run(root, command, errors)


def validate_clean(root: Path, errors: list[str]) -> None:
    blocked = {".pytest_cache", "__pycache__", ".DS_Store"}
    for path in root.rglob("*"):
        if path.name in blocked or path.suffix == ".pyc":
            errors.append(f"remove generated artifact: {path.relative_to(root)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate clean sales package structure.")
    parser.add_argument("--skip-demos", action="store_true", help="Skip sample script runs.")
    args = parser.parse_args()

    root = public_root()
    errors: list[str] = []
    validate_structure(root, errors)
    validate_scripts(root, errors)
    if not args.skip_demos:
        validate_demo(root, errors)
    validate_clean(root, errors)
    if errors:
        print("Public package validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Public package validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
