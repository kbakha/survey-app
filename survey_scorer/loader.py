import csv
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class NormConfig:
    scale_id: str
    level: str
    label: str
    min_val: float
    max_val: float
    interpretation: str


@dataclass
class ScaleConfig:
    id: str
    name: str
    direct_items: list
    reverse_items: list
    is_total: bool


@dataclass
class InstrumentConfig:
    id: str
    name: str
    n_items: int
    min_score: int
    max_score: int
    aggregation: str
    scales: list
    norms: list
    instruction: str = ""
    scale_labels: list = field(default_factory=list)
    items: list = field(default_factory=list)


def load_instruments(config_dir: Path) -> dict:
    instruments = {}
    yaml_files = sorted(config_dir.glob("*.yaml"))
    if not yaml_files:
        raise FileNotFoundError(f"No YAML configs found in {config_dir}")
    for yaml_file in yaml_files:
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        inst = data["instrument"]
        scales = [ScaleConfig(**s) for s in data["scales"]]
        norms = [NormConfig(**n) for n in data["norms"]]
        cfg = InstrumentConfig(
            id=inst["id"],
            name=inst["name"],
            n_items=inst["n_items"],
            min_score=inst["min_score"],
            max_score=inst["max_score"],
            aggregation=inst["aggregation"],
            scales=scales,
            norms=norms,
            instruction=inst.get("instruction", ""),
            scale_labels=data.get("scale_labels", []),
            items=data.get("items", []),
        )
        instruments[cfg.id] = cfg
    print(f"Loaded {len(instruments)} instrument(s): {', '.join(instruments)}")
    return instruments


def load_responses(csv_path: Path) -> list:
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for line_num, parts in enumerate(reader, start=2):
            parts = [p.strip() for p in parts]
            if not parts or not parts[0]:
                continue
            if len(parts) < 3:
                print(f"WARNING: Line {line_num} has fewer than 3 columns, skipping.")
                continue
            respondent_id = parts[0]
            instrument_id = parts[1]
            answers = {}
            for i, val in enumerate(parts[2:], start=1):
                if val == "":
                    continue
                try:
                    answers[i] = int(val)
                except ValueError:
                    print(f"WARNING: Line {line_num}, Q{i}: '{val}' is not an integer.")
            rows.append({
                "respondent_id": respondent_id,
                "instrument_id": instrument_id,
                "answers": answers,
            })
    print(f"Loaded {len(rows)} response row(s) from {csv_path}")
    return rows
