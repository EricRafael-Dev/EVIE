import asyncio
import sys
from pathlib import Path

# Ensure root in path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def test_confirm_gate():
    print("Testing confirm gate...")
    from core import confirm

    received_broadcasts = []
    confirm.set_remote_broadcast_callback(lambda p: received_broadcasts.append(p))

    executed = []
    # bind dummy ui callbacks
    confirm.bind(
        show=lambda title, detail: None,
        hide=lambda: None,
        log=lambda msg: None
    )

    msg = confirm.request("test_key_123", "Desligar PC", "Desligar computador agora?", lambda: executed.append("RUN") or "Desligado")
    assert "[CONFIRMATION_PENDING]" in msg
    assert len(received_broadcasts) == 1
    assert received_broadcasts[0]["type"] == "confirm_request"
    assert received_broadcasts[0]["key"] == "test_key_123"

    # Test rejection with invalid key
    ok, err = confirm.resolve_with_key("wrong_key", True)
    assert not ok
    assert len(executed) == 0

    # Test resolution with valid key
    ok, success = confirm.resolve_with_key("test_key_123", True)
    assert ok
    import time
    time.sleep(0.1) # wait for worker thread
    assert "RUN" in executed
    assert len(received_broadcasts) == 2
    assert received_broadcasts[1]["type"] == "confirm_resolved"
    print("Confirm gate tests PASSED!")

def test_action_loader():
    print("Testing action loader discovery...")
    from core.action_loader import discover_actions
    registry = discover_actions(ROOT / "actions", logger=lambda m: None)
    names = registry.names()
    print(f"Total discovered actions: {len(names)}")
    
    # Check Phase 4 actions
    assert "set_workspace_mode" in names, "set_workspace_mode missing"
    assert "media_studio" in names, "media_studio missing"
    assert "dev_companion" in names, "dev_companion missing"

    # Check Phase 6 actions
    assert "send_file_to_device" in names, "send_file_to_device missing"
    assert "compile_study_digest" in names, "compile_study_digest missing"
    print("Action loader tests PASSED!")

def test_dashboard_routes():
    print("Testing dashboard server routes...")
    from dashboard.server import DashboardServer
    server = DashboardServer()
    routes = [route.path for route in server.app.routes]
    
    expected_routes = [
        "/api/mobile/vision",
        "/api/confirm/resolve",
        "/api/mobile/offline_sync",
        "/api/session/handoff",
        "/ws/whiteboard",
        "/api/clipboard",
        "/api/airdrop",
        "/api/clipper/ingest"
    ]
    for r in expected_routes:
        assert r in routes, f"Route {r} not registered in DashboardServer!"
    print(f"All {len(expected_routes)} new routes verified in DashboardServer!")

def test_gitignore():
    print("Testing .gitignore rules...")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "config/quota_ledger.json" in gi
    assert "config/devices.json" in gi
    assert "second_brain/" in gi
    assert "*.apk" in gi
    assert "*.corrupted.*.json" in gi
    print(".gitignore rules PASSED!")

if __name__ == "__main__":
    test_confirm_gate()
    test_action_loader()
    test_dashboard_routes()
    test_gitignore()
    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
