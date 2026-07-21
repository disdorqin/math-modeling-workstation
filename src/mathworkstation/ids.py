from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path


_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_COMPETITION_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")


def normalize_competition(value: str) -> str:
    normalized = value.strip().upper()
    if not _COMPETITION_RE.fullmatch(normalized):
        raise ValueError("competition must contain 2-8 uppercase letters or digits")
    return normalized


def random_code(length: int = 4) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def next_case_id(output_root: Path, competition: str, moment: datetime | None = None) -> str:
    current = moment or datetime.now().astimezone()
    day = current.strftime("%Y%m%d")
    competition = normalize_competition(competition)
    prefix = f"{day}-{competition}-"
    sequence = 0
    if output_root.exists():
        pattern = re.compile(rf"^{re.escape(prefix)}(\d{{4}})-[A-Z0-9]+$")
        for entry in output_root.iterdir():
            match = pattern.match(entry.name)
            if entry.is_dir() and match:
                sequence = max(sequence, int(match.group(1)))
    return f"{prefix}{sequence + 1:04d}-{random_code()}"


def next_session_id(case_id: str, sessions_root: Path, moment: datetime | None = None) -> str:
    current = moment or datetime.now().astimezone()
    parts = case_id.split("-")
    if len(parts) < 4:
        raise ValueError(f"invalid case id: {case_id}")
    short_case = f"{parts[1]}{parts[2]}"
    prefix = f"{current.strftime('%m%d')}-{short_case}-S"
    sequence = 0
    if sessions_root.exists():
        pattern = re.compile(rf"^{re.escape(prefix)}(\d{{2}})$")
        for entry in sessions_root.iterdir():
            match = pattern.match(entry.name)
            if entry.is_dir() and match:
                sequence = max(sequence, int(match.group(1)))
    return f"{prefix}{sequence + 1:02d}"


def new_run_id(moment: datetime | None = None) -> str:
    current = moment or datetime.now().astimezone()
    return f"run-{current.strftime('%Y%m%d-%H%M%S')}-{random_code(6).lower()}"

