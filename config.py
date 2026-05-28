import yaml
from pathlib import Path

_DEFAULT = Path(__file__).parent / "config.yaml"


def load(path: Path = _DEFAULT) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    cfg["notes_dir"] = Path(cfg["notes_dir"]).expanduser()
    return cfg
