"""Live Mem0 export. Runs only with SKIPWATCH_LIVE=1 and MEM0_API_KEY.

Not run by builders; the orchestrator runs it only when Robert provides a key:
    SKIPWATCH_LIVE=1 MEM0_API_KEY=... uv run pytest tests/live/test_live_mem0.py -m live -v -s
SKIPWATCH_MEM0_TEST_USER_ID sets the user id; unset, the memory is stored under agent_id.
"""

import os
import time

import pytest
import requests

from skipwatch.models import Config, Manifest
from skipwatch.providers import export_mem0
from skipwatch.workdir import read_model
from tests.unit._skills import installed_skill

pytestmark = pytest.mark.live

EVENT_URL = "https://api.mem0.ai/v1/event/{}/"
MEMORY_URL = "https://api.mem0.ai/v1/memories/{}/"
POLL_S = 60.0


def _memory_ids(event: dict) -> list[str]:
    """Memory ids the event response names, wherever it keeps them."""
    found = []
    for value in event.get("results") or event.get("data") or []:
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            found.append(value["id"])
    if isinstance(event.get("memory_id"), str):
        found.append(event["memory_id"])
    return found


def test_live_mem0_export_round_trip(tmp_path, monkeypatch):
    key = os.environ.get("MEM0_API_KEY", "").strip()
    if not key:
        pytest.skip("needs MEM0_API_KEY")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    skill = installed_skill(tmp_path / "home" / ".claude")
    manifest = read_model(skill / "skipwatch.json", Manifest)
    user_id = os.environ.get("SKIPWATCH_MEM0_TEST_USER_ID", "")
    cfg = Config.model_validate({"exports": {"mem0": {"enabled": True, "user_id": user_id}}})

    item = export_mem0.PROVIDER.export(skill, manifest, cfg)
    assert item.ok and item.location and item.location.startswith("mem0 event ")
    event_id = item.location.removeprefix("mem0 event ")

    headers = {"Authorization": f"Token {key}", "Accept": "application/json"}
    deadline = time.monotonic() + POLL_S
    event: dict = {}
    while time.monotonic() < deadline:
        response = requests.get(EVENT_URL.format(event_id), headers=headers, timeout=20)
        assert response.status_code == 200, response.status_code
        event = response.json()
        if event.get("status") in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(2)
    print("event keys:", sorted(event))  # recorded by the orchestrator: the event shape
    assert event.get("status") == "SUCCEEDED", event.get("status")

    ids = _memory_ids(event)
    if not ids:
        print(f"no memory id in event {event_id}; delete the test memory by hand")
    for memory_id in ids:
        gone = requests.delete(MEMORY_URL.format(memory_id), headers=headers, timeout=20)
        print(f"deleted memory {memory_id}: HTTP {gone.status_code}")
