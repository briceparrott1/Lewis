from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SeedEntry:
    company: str
    source: str
    board_token: str


_SEED_PATH = Path(__file__).with_name("seed_companies.yaml")


def load_seed() -> list[SeedEntry]:
    data = yaml.safe_load(_SEED_PATH.read_text()) or []
    return [SeedEntry(**row) for row in data]
