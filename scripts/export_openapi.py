#!/usr/bin/env python3
"""Export OpenAPI spec from the FastAPI app."""

import json
from pathlib import Path
import sys

from voicetest.rest import app


def main() -> None:
    """Export OpenAPI JSON to stdout or file."""
    spec = app.openapi()

    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(spec, indent=2))
        print(f"Wrote OpenAPI spec to {output_path}")
    else:
        print(json.dumps(spec, indent=2))


if __name__ == "__main__":
    main()
