"""Build a Home Assistant manual-install ZIP for UNED Study."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "uned_study"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"uned-study-{args.version}.zip"

    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(COMPONENT.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, path.relative_to(ROOT).as_posix())

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
