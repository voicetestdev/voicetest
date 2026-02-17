"""Bundled Docker Compose files for voicetest infrastructure.

Provides access to the base compose file that defines infra services
(LiveKit, Whisper, Kokoro) needed for live voice calls.
"""

from collections.abc import Generator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path


@contextmanager
def get_compose_path() -> Generator[Path, None, None]:
    """Yield a filesystem path to the bundled docker-compose.yml.

    Uses importlib.resources.as_file() to handle zip-safe packages
    where the file may need to be extracted to a temporary location.

    Usage::

        with get_compose_path() as compose_path:
            subprocess.run(["docker", "compose", "-f", str(compose_path), "up", "-d"])
    """
    compose_ref = resources.files("voicetest.compose").joinpath("docker-compose.yml")
    with resources.as_file(compose_ref) as path:
        yield path
