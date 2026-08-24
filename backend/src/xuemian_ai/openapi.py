import json
import sys
from pathlib import Path

from xuemian_ai.main import app


def export_openapi(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m xuemian_ai.openapi <output-path>")
    export_openapi(Path(sys.argv[1]))
