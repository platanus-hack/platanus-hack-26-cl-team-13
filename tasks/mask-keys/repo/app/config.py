import os
from pathlib import Path


def load_env(path: str = ".env") -> dict[str, str]:
    env = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return {**env, **{k: v for k, v in os.environ.items() if k in env}}
