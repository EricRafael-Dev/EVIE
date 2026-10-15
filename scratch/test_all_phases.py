import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def test_phase_1_quota_and_memory():
    print("[TEST] Fase 1: QuotaLedger & MemoryManager...")
    from agent_memory.router import QuotaLedger, LEDGER_PATH
    ledger = QuotaLedger(LEDGER_PATH)
    assert ledger._get_pacific_date() == datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

    # Cooldown on live
    ledger.mark_rate_limited_minute("live", retry_delay_seconds=5)
    assert not ledger.is_available("live")
    time.sleep(5.1)
    assert ledger.is_available("live")

    from memory.memory_manager import remember, load_memory
    remember("test_key", "unit_test_val", category="notes")
    mem = load_memory()
    assert "notes" in mem
    assert mem["notes"]["test_key"]["value"] == "unit_test_val"
    print("  -> QuotaLedger e MemoryManager OK!")

def test_phase_2_second_brain():
    print("[TEST] Fase 2: Second Brain FTS5 & WikiLinks...")
    from agent_memory.tools import rebuild_memory_map, search_second_brain, read_memory_note
    compact_map = rebuild_memory_map()
    assert len(compact_map) <= 650
    map_file = ROOT / "second_brain" / "MEMORY_MAP.md"
    assert map_file.exists()

    res = search_second_brain("projeto", limit=2)
    assert isinstance(res, str)
    print("  -> Second Brain FTS5 e WikiLinks OK!")

def test_phase_3_envelope_and_registry():
    print("[TEST] Fase 3: CommandEnvelope & DeviceRegistry...")
    from core.envelope import CommandEnvelope
    from core.device_registry import device_registry
    env = CommandEnvelope(
        source_device_id="mobile_test",
        input_modality="text",
        reply_audio_target="origin_ws",
        payload="teste"
    )
    assert env.source_device_id == "mobile_test"

    dev = device_registry.validate_token("invalid_token_xyz")
    assert dev is None
    print("  -> CommandEnvelope e DeviceRegistry OK!")

def test_phase_4_actions():
    print("[TEST] Fase 4: Actions de Força Bruta & Automação...")
    from actions.workspace_profiles import set_workspace_mode_handler
    from actions.media_studio import search_local_assets_handler
    from actions.dev_companion import hardware_telemetry_check_handler

    # Test hardware telemetry
    res_telem = hardware_telemetry_check_handler({})
    assert "Telemetria realizada" in res_telem

    # Test asset search
    res_assets = search_local_assets_handler({"query": "test"})
    assert isinstance(res_assets, str)
    print("  -> Actions FASE 4 OK!")

def test_phase_5_mobile_and_confirm():
    print("[TEST] Fase 5: Confirm Gate Mirroring & Mobile Endpoints...")
    from core import confirm
    broadcasts = []
    confirm.set_remote_broadcast_callback(lambda p: broadcasts.append(p))
    confirm.bind(lambda t, d: None, lambda: None, lambda m: None)

    msg = confirm.request("test_p5", "Ação Crítica", "Confirmação remota?", lambda: "Feito")
    assert len(broadcasts) == 1
    assert broadcasts[0]["type"] == "confirm_request"

    ok, _ = confirm.resolve_with_key("test_p5", True)
    assert ok
    time.sleep(0.1)
    assert len(broadcasts) == 2
    assert broadcasts[1]["type"] == "confirm_resolved"
    print("  -> Confirm Mirroring & Remote Gate OK!")

def test_phase_6_ecosystem_bridge():
    print("[TEST] Fase 6: Ecosystem Bridge & Digest...")
    from actions.ecosystem_bridge import compile_study_digest_handler, send_file_to_device_handler
    digest_res = compile_study_digest_handler({"days": 30})
    assert isinstance(digest_res, str)

    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ["config/quota_ledger.json", "config/devices.json", "second_brain/", "*.apk", "*.corrupted.*.json"]:
        assert pattern in gi, f"{pattern} faltando no .gitignore"
    print("  -> Ecosystem Bridge & .gitignore OK!")

if __name__ == "__main__":
    test_phase_1_quota_and_memory()
    test_phase_2_second_brain()
    test_phase_3_envelope_and_registry()
    test_phase_4_actions()
    test_phase_5_mobile_and_confirm()
    test_phase_6_ecosystem_bridge()
    print("\n==========================================")
    print("TODOS OS TESTES DAS FASES 1-6 PASSARAM COM SUCESSO!")
    print("==========================================")
