"""Print the API's OpenAPI schema as JSON. The web app generates its TypeScript types
from it:  uv run python -m clippers.openapi > web/openapi.json
"""

import json
from pathlib import Path

from clippers.api import create_app
from clippers.jobs import ServiceSettings


def schema() -> dict[str, object]:
    # Fixed settings, so the output doesn't depend on whoever runs it (or their .env).
    settings = ServiceSettings(redis_url="redis://unused", data_dir=Path("data"), api_key=None)
    return create_app(settings).openapi()


if __name__ == "__main__":
    print(json.dumps(schema(), indent=2, sort_keys=True))
