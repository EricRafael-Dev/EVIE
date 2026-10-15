import asyncio
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.proactivity_engine import (
    ContextCollector, ProactivityEngine, AutonomyMode, CognitiveState,
    init_proactivity_engine, get_proactivity_engine
)
from dashboard.server import DashboardServer

async def test_proactivity_suite():
    print("[TEST] 1. Testando ContextCollector...")
    collector = ContextCollector()
    snapshot = collector.collect_snapshot()
    assert "active_window" in snapshot
    assert "user_idle_seconds" in snapshot
    assert snapshot["temporal"]["period"] in ("manhã", "tarde", "noite", "madrugada")
    print(f"  -> Contexto coletado: Janela='{snapshot['active_window']['title']}', Processo='{snapshot['active_window']['process']}', Idle={snapshot['user_idle_seconds']}s")

    print("[TEST] 2. Testando ProactivityEngine & Filtro de Silêncio...")
    received_events = []
    state_transitions = []

    def on_msg(evt):
        received_events.append(evt)

    def on_state(st):
        state_transitions.append(st)

    engine = ProactivityEngine(
        on_proactive_message=on_msg,
        on_state_change=on_state,
        base_dir=Path(__file__).resolve().parent.parent,
    )

    # Teste de modo SILENT
    engine.set_mode(AutonomyMode.SILENT)
    assert engine.mode == AutonomyMode.SILENT
    assert engine.level == 0

    # Teste de modo CURIOUS
    engine.set_mode(AutonomyMode.CURIOUS)
    assert engine.mode == AutonomyMode.CURIOUS
    assert engine.level == 100
    assert engine._get_heartbeat_interval() == 180.0
    assert engine._get_cooldown_seconds() == 900.0

    # Teste de modo BALANCED
    engine.set_mode(AutonomyMode.BALANCED)
    assert engine.mode == AutonomyMode.BALANCED
    assert engine.level == 50
    assert engine._get_heartbeat_interval() == 480.0
    assert engine._get_cooldown_seconds() == 2100.0

    # Teste de Filtro de Silêncio
    snapshot = collector.collect_snapshot()
    async def mock_llm_silent(prompt):
        return "[SILENCIO]"

    await engine._evaluate_and_pulse(snapshot, llm_evaluator=mock_llm_silent)
    assert len(received_events) == 0, "Deveria ter descartado [SILENCIO] silenciosamente"
    print("  -> Filtro [SILENCIO] funcionou com sucesso (nenhum evento disparado).")

    # Simula mock do LLM retornando uma ideia real
    async def mock_llm_idea(prompt):
        return "Rafael, notei que você está trabalhando no Mark LV. Gostaria de criar um teste unitário para o motor proativo?"

    await engine._evaluate_and_pulse(snapshot, llm_evaluator=mock_llm_idea)
    assert len(received_events) == 1, "Deveria ter disparado a ideia proativa"
    event = received_events[0]
    assert event["type"] in ("proactive_message", "evie_proactive_message")
    assert "Rafael, notei" in event["text"]
    assert event["target"] in ("pc", "mobile")
    assert len(engine._recent_topics) == 1
    print(f"  -> Disparo de evento proativo OK: target={event['target']}, texto='{event['text'][:40]}...'")

    # Anti-repeat check
    assert any("Rafael" in t or "Mark LV" in t for t in engine._recent_topics)

    # Teste de pausa temporária
    engine.pause_proactivity(minutes=60)
    assert engine._is_paused()
    print("  -> Pausa temporária OK.")
    engine.resume_proactivity()
    assert not engine._is_paused()

    print("[TEST] 3. Testando Endpoints REST no DashboardServer...")
    server = DashboardServer()
    server._tokens.add("token-secreto-evie-local-2026")
    # Inicializa engine global para o servidor
    init_proactivity_engine(base_dir=Path(__file__).resolve().parent.parent)

    from fastapi.testclient import TestClient
    client = TestClient(server.app)

    # 3.1 Status
    res = client.get("/api/proactivity/status", headers={"Authorization": "Bearer token-secreto-evie-local-2026"})
    assert res.status_code == 200
    st_data = res.json()
    assert "mode" in st_data
    assert "cognitive_state" in st_data

    # 3.2 Mode
    res = client.post("/api/proactivity/mode", json={"mode": "curious"}, headers={"Authorization": "Bearer token-secreto-evie-local-2026"})
    assert res.status_code == 200
    assert res.json()["mode"] == "curious"

    # 3.3 Pause
    res = client.post("/api/proactivity/pause", json={"minutes": 30}, headers={"Authorization": "Bearer token-secreto-evie-local-2026"})
    assert res.status_code == 200
    assert res.json()["paused"] is True

    # 3.4 Telemetria Mobile
    res = client.post("/api/mobile/telemetry", json={"battery": 88, "screen_on": True, "app_screen": "MainChatHUD", "device": "Poco X7"}, headers={"Authorization": "Bearer token-secreto-evie-local-2026"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    print("  -> Todos os endpoints REST de proatividade e telemetria responderam OK!")

    print("\n==========================================")
    print("SUÍTE DE TESTES DO MOTOR PROATIVO: 100% OK!")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(test_proactivity_suite())
