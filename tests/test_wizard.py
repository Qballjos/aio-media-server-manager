"""
tests/test_wizard.py — Tests for Guided 12-Step Setup Wizard.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.wizard import WizardEngine, WIZARD_STEPS


def test_wizard_engine_lifecycle(tmp_path: Path):
    state_file = tmp_path / "wizard_state.json"
    engine = WizardEngine(state_file=state_file)

    assert engine.is_completed() is False
    status = engine.get_status()
    assert status["current_step"] == 1
    assert len(status["steps"]) == 12

    # Step 1: Welcome
    step1 = engine.get_step_data(1)
    assert step1["step"] == 1

    # Step 2: Platform
    step2 = engine.get_step_data(2)
    assert "platform" in step2
    assert "system" in step2["platform"]

    # Step 3: Storage update
    engine.update_step_selections(3, {"media_dir": "/custom/media", "config_dir": "/custom/config"})
    status = engine.get_status()
    assert status["selections"]["media_dir"] == "/custom/media"
    assert status["current_step"] >= 4

    # Step 5: Download clients
    engine.update_step_selections(5, {"download_clients": ["sabnzbd"]})
    assert engine.get_status()["selections"]["download_clients"] == ["sabnzbd"]

    # Step 6: VPN
    engine.update_step_selections(6, {"vpn_provider": "privadovpn"})
    assert engine.get_status()["selections"]["vpn_provider"] == "privadovpn"

    # Reload from disk to test persistence
    reloaded_engine = WizardEngine(state_file=state_file)
    assert reloaded_engine.get_status()["selections"]["vpn_provider"] == "privadovpn"


@pytest.mark.asyncio
async def test_wizard_api_endpoints(tmp_path: Path):
    app = create_app()
    client = TestClient(app)

    # Check status
    res = client.get("/api/wizard/status")
    assert res.status_code == 200
    assert "current_step" in res.json()

    # Get step 1
    res_step1 = client.get("/api/wizard/step/1")
    assert res_step1.status_code == 200
    assert res_step1.json()["step"] == 1

    # Submit step 4 (PUID/PGID)
    res_sub = client.post("/api/wizard/step/4", json={"puid": 1001, "pgid": 1001})
    assert res_sub.status_code == 200
    assert res_sub.json()["selections"]["puid"] == 1001

    # Execute wizard
    res_exec = client.post("/api/wizard/execute")
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert exec_data["completed"] is True
    assert "wiring" in exec_data
