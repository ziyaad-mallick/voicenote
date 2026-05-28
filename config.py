import yaml
from pathlib import Path

CONFIG_PATH = Path.home() / ".voicenote" / "config.yaml"


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


def get_default() -> dict:
    return {
        "user": {
            "name": "",
            "email": ""
        },
        "notes_dir": "~/Documents/VoiceNotes",
        "categories": ["Projects", "Ideas", "Uni", "Personal"],
        "ollama": {
            "host": "http://localhost:11434",
            "model": "goekdenizguelmez/JOSIEFIED-Qwen3:latest"
        },
        "whisper": {
            "model": "small",
            "language": "en",
            "device": "cpu",
            "compute_type": "int8",
            "backend": "whisper"
        },
        "output": {
            "markdown": True,
            "docx": False
        },
        "audio": {
            "sample_rate": 16000,
            "channels": 1
        }
    }


def load() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
    else:
        cfg = get_default()

    defaults = get_default()
    for key in defaults:
        if key not in cfg:
            cfg[key] = defaults[key]

    cfg["notes_dir"] = Path(cfg["notes_dir"]).expanduser()
    return cfg


def save(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    cfg_to_save = cfg.copy()
    if isinstance(cfg_to_save["notes_dir"], Path):
        cfg_to_save["notes_dir"] = str(cfg_to_save["notes_dir"])

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg_to_save, f, default_flow_style=False)
