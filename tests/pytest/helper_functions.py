from pathlib import Path


def base_dir() -> Path:
    return Path(__file__).parent.parent.absolute()
