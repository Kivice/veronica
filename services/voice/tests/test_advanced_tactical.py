"""Hermetic tests for Advanced Tactical Features:
- Per-action approval gate (ApprovalManager & classify_risk)
- Multi-step task planner (task_plan)
- LAN IoT auto-discovery & RFC1918 camera snapshots
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from veronica_voice.approvals import ApprovalManager, classify_risk
from veronica_voice.iot import camera_snapshot, discover_devices
from veronica_voice.tools import execute_tool, task_plan


def test_classify_risk_high_risk_actions():
    # Commands
    risk = classify_risk("execute_command", {"command": "dir"})
    assert risk is not None
    assert risk[0] == "execute_command"

    # Force kill
    risk = classify_risk("close_application", {"app": "spotify", "force": True})
    assert risk is not None
    assert risk[0] == "close_application:force"

    # High-risk IoT
    risk = classify_risk("iot_control", {"action": "unlock", "device": "front_door"})
    assert risk is not None
    assert "iot_control:unlock" in risk[0]

    # Clipboard overwrite
    risk = classify_risk("clipboard_tool", {"action": "set", "text": "secret"})
    assert risk is not None
    assert risk[0] == "clipboard_tool:set"

    # Low risk actions return None
    assert classify_risk("search_web", {"query": "weather"}) is None
    assert classify_risk("media_control", {"action": "volume_up"}) is None
    assert classify_risk("system_status", {}) is None


@pytest.mark.asyncio
async def test_approval_manager_flow(tmp_path: Path):
    policy_file = tmp_path / "approvals.json"
    mgr = ApprovalManager(path=policy_file)

    # Initially no standing decisions
    assert mgr.standing_decision("cmd") is None

    # Test interactive approval resolution
    async def _send_ui(payload):
        # UI receives request and immediately resolves it
        req_id = payload["request_id"]
        loop = asyncio.get_running_loop()
        loop.call_soon(mgr.resolve, req_id, "allow_once")

    allowed = await mgr.request(
        key="execute_command",
        tool_name="run_command",
        reason="Run test cmd",
        args={"cmd": "whoami"},
        send=_send_ui,
        timeout=2.0,
    )
    assert allowed is True

    # Test "always" decision persistence
    async def _send_always(payload):
        req_id = payload["request_id"]
        mgr.resolve(req_id, "always")

    allowed = await mgr.request(
        key="test_always_key",
        tool_name="test_tool",
        reason="Test always",
        args={},
        send=_send_always,
        timeout=2.0,
    )
    assert allowed is True
    assert mgr.standing_decision("test_always_key") == "always"

    # Standing decision skips UI send
    allowed_standing = await mgr.request(
        key="test_always_key",
        tool_name="test_tool",
        reason="Test always",
        args={},
        send=None,
    )
    assert allowed_standing is True

    # Test reset
    mgr.reset()
    assert mgr.standing_decision("test_always_key") is None


def test_task_plan_lifecycle():
    # 1. Create plan
    res = task_plan(
        action="create",
        goal="Audit Network & Launch Dev Mode",
        steps=["Scan LAN IoT", "Launch VS Code", "Set Focus Mode"],
    )
    assert res["status"] == "success"
    assert res["goal"] == "Audit Network & Launch Dev Mode"
    assert len(res["plan"]) == 3
    assert res["plan"][0]["status"] == "running"
    assert res["plan"][1]["status"] == "pending"

    # 2. Advance step 1 to done -> step 2 automatically becomes running
    res = task_plan(action="update", index=1, status="done", note="Found 2 devices")
    assert res["status"] == "success"
    assert res["plan"][0]["status"] == "done"
    assert res["plan"][0]["note"] == "Found 2 devices"
    assert res["plan"][1]["status"] == "running"
    assert res["progress"] == "1/3"

    # 3. Mark step 2 done
    res = task_plan(action="update", index=2, status="done")
    assert res["plan"][1]["status"] == "done"
    assert res["plan"][2]["status"] == "running"

    # 4. Dispatch via universal execute_tool
    res = execute_tool("task_plan", {"action": "list"})
    assert res["status"] == "success"
    assert res["goal"] == "Audit Network & Launch Dev Mode"

    # 5. Clear plan
    res = task_plan(action="clear")
    assert res["status"] == "success"
    assert len(res["plan"]) == 0


def test_iot_discovery_and_camera_safety():
    # If no camera is registered, camera_snapshot returns a clean error message
    res = camera_snapshot(device="nonexistent_cam")
    assert res["status"] == "error"
    assert "No matching camera" in res["message"]

    # Register an external IP camera to verify RFC1918 enforcement
    from veronica_voice.iot import iot_control
    reg_res = iot_control(
        action="register",
        device="external_cam",
        device_type="camera",
        host="http://8.8.8.8/snapshot.jpg",
    )
    assert reg_res["status"] == "blocked"
    assert "RFC1918" in reg_res["message"]

    # Local discovery returns a valid dict schema even if no SSDP devices answer
    res = discover_devices(timeout_s=0.1)
    assert res["status"] == "success"
    assert "devices" in res or "discovered_count" in res
