from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"
STATIC_DIR = ROOT / "french_learning" / "static"
DEMO_FILES = ("index.html", "demo.css", "demo-api.js", "demo-runtime.js", "demo-data.json")
STATIC_FILES = ("app.js", "styles.css", "favicon.svg")


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in DEMO_FILES:
        shutil.copy2(DEMO_DIR / name, output / name)
    for name in STATIC_FILES:
        shutil.copy2(STATIC_DIR / name, output / name)
    (output / ".nojekyll").touch()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "demo"
    build(target.resolve())
    print(f"Demo built at {target.resolve()}")
