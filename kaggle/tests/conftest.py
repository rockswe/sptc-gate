"""Shared fixtures for the bench tests: the bench module and a fake server subprocess.

Run: python -m pytest -q kaggle/tests   (no GPU, no vLLM, no openai package needed)
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

KAGGLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KAGGLE))

FAKE = KAGGLE / "fake_openai_server.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_fake(*flags: str) -> tuple[subprocess.Popen, str]:
    port = free_port()
    p = subprocess.Popen([sys.executable, str(FAKE), "fake-model", "--port", str(port), *flags],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/v1"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/models", timeout=1)
            return p, url
        except OSError:
            time.sleep(0.05)
    p.kill()
    raise RuntimeError("fake server did not start")


@pytest.fixture
def fake():
    """Factory: fake(*flags) -> base_url; every server started is killed at the end."""
    procs = []

    def make(*flags: str) -> str:
        p, url = start_fake(*flags)
        procs.append(p)
        return url

    yield make
    for p in procs:
        p.kill()
        p.wait()
