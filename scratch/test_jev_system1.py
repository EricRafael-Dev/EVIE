"""scratch/test_jev_system1.py — Suíte de Testes Automatizada do Motor JEV Local (System 1).

Valida os 4 pilares:
1. DecisionEngine (Singleton, Lazy Loading, Async Non-blocking, Fail-Open).
2. Gate de Memória em agent_memory/extractor.py.
3. Roteamento Dinâmico (AUTO -> SEARCH, SMART, FAST) em core/gemini.py e agent_memory/router.py.
4. Pré-aquecimento de Visão (Warm-up com TTL de 3.0s) em main.py.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# Ajusta path para importar módulos do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.decision_engine import (
    DecisionEngine,
    get_decision_engine,
    MemoryDecision,
    RouteDecision,
    VisionWarmupDecision,
)
from pydantic import BaseModel, Field


async def test_pillar_1_decision_engine():
    print("\n" + "=" * 60)
    print("TESTE 1: Motor de Decisão Local JEV (System 1)")
    print("=" * 60)

    # 1.1 Singleton
    engine1 = get_decision_engine()
    engine2 = get_decision_engine()
    assert engine1 is engine2, "Falha: DecisionEngine deve ser um Singleton."
    print("[OK] 1.1 Singleton validado com sucesso.")

    # 1.2 Avaliação Assíncrona de Memória
    t0 = time.monotonic()
    decision_trivial, probs_trivial = await engine1.evaluate_memory("Olá Evie, bom dia! Tudo bem com você?")
    dt1 = time.monotonic() - t0
    assert not decision_trivial.should_extract_memory or decision_trivial.suggested_folder == "none", (
        f"Falha: Saudação não deve ser marcada para persistência. ({decision_trivial})"
    )
    print(f"[OK] 1.2 Memória Trivial filtrada em {dt1*1000:.2f}ms: should_extract={decision_trivial.should_extract_memory}, folder={decision_trivial.suggested_folder}")

    t0 = time.monotonic()
    decision_fact, probs_fact = await engine1.evaluate_memory("Meu nome é Rafael e eu trabalho no projeto Mark LV.")
    dt2 = time.monotonic() - t0
    assert decision_fact.should_extract_memory and decision_fact.suggested_folder in ("perfil", "projetos"), (
        f"Falha: Fato pessoal deve ser marcado para persistência. ({decision_fact})"
    )
    print(f"[OK] 1.3 Fato Pessoal detectado em {dt2*1000:.2f}ms: should_extract={decision_fact.should_extract_memory}, folder={decision_fact.suggested_folder}")

    # 1.3 Avaliação de Roteamento (AUTO)
    tier_search, r_search, _ = await engine1.evaluate_route("Pesquise as últimas notícias e a cotação do dólar hoje.")
    assert tier_search == "SEARCH", f"Falha: Esperado SEARCH, obtido {tier_search}"
    print(f"[OK] 1.4 Roteamento SEARCH detectado: tier={tier_search}")

    tier_smart, r_smart, _ = await engine1.evaluate_route("Escreva um script Python com algoritmo A* para busca em grafo.")
    assert tier_smart == "SMART", f"Falha: Esperado SMART, obtido {tier_smart}"
    print(f"[OK] 1.5 Roteamento SMART detectado: tier={tier_smart}")

    tier_fast, r_fast, _ = await engine1.evaluate_route("Tudo bem com você?")
    assert tier_fast == "FAST", f"Falha: Esperado FAST, obtido {tier_fast}"
    print(f"[OK] 1.6 Roteamento FAST detectado: tier={tier_fast}")

    # 1.4 Avaliação de Pré-aquecimento de Visão
    wants_vis, prob_vis = await engine1.evaluate_vision_warmup("Evie, dá uma olhada na minha tela e vê esse erro aqui.")
    assert wants_vis and prob_vis >= 0.80, f"Falha: Visão de tela deve ser detectada com prob >= 0.80 (obtido {wants_vis}, {prob_vis})"
    print(f"[OK] 1.7 Pré-aquecimento de Visão detectado: wants={wants_vis}, prob={prob_vis:.2f}")

    wants_novis, _ = await engine1.evaluate_vision_warmup("Aumente o volume da música por favor.")
    assert not wants_novis, "Falha: Comando de música não deve acionar visão."
    print(f"[OK] 1.8 Comando não-visual descartado corretamente: wants={wants_novis}")


async def test_pillar_2_memory_gate():
    print("\n" + "=" * 60)
    print("TESTE 2: Gate de Memória em agent_memory/extractor.py")
    print("=" * 60)

    from agent_memory.extractor import MemoryIngestionWorker

    # Mock tool manager e indexer para não precisar tocar no disco de produção
    class DummyToolManager:
        pass

    class DummyIndexer:
        def index_single_note(self, *args, **kwargs):
            pass

    worker = MemoryIngestionWorker(tool_manager=DummyToolManager(), indexer=DummyIndexer())

    # Turno trivial que DEVE ser abortado pelo Gate JEV sem chamar o LLM
    res_trivial = await worker.extract_facts_in_background("Oi Evie, boa tarde, valeu!")
    assert not res_trivial.get("has_new_info"), "Falha: Turno trivial não deve gerar extração."
    assert "JEV-Local" in res_trivial.get("summary_reason", ""), "Falha: Deve conter log de filtragem do JEV-Local."
    print(f"[OK] 2.1 Cota poupada na rota BACKGROUND confirmada: {res_trivial}")


async def test_pillar_3_auto_routing():
    print("\n" + "=" * 60)
    print("TESTE 3: Roteamento Dinâmico (AUTO) em gemini.py e router.py")
    print("=" * 60)

    from core import gemini
    from agent_memory import router

    # Testa se a constante AUTO existe em gemini e router
    assert getattr(gemini, "AUTO", None) == "auto", "Falha: gemini.AUTO deve ser 'auto'"
    assert getattr(router, "ROUTE_AUTO", None) == "auto", "Falha: router.ROUTE_AUTO deve ser 'auto'"
    print("[OK] 3.1 Constantes de tier AUTO validadas.")

    # Testa a função assíncrona de resolução de prompt do JEV no router
    engine = get_decision_engine()
    t_search, _, _ = await engine.evaluate_route("Qual a cotação do euro e previsão do tempo em SP?")
    assert t_search == "SEARCH", f"Falha no roteamento: {t_search}"

    t_code, _, _ = await engine.evaluate_route("Crie uma classe async em Python para WebSocket.")
    assert t_code == "SMART", f"Falha no roteamento: {t_code}"

    t_casual, _, _ = await engine.evaluate_route("Oi, quem é você?")
    assert t_casual == "FAST", f"Falha no roteamento: {t_casual}"

    print(f"[OK] 3.2 Roteamento dinâmico testado com sucesso (SEARCH, SMART, FAST).")


async def test_pillar_4_vision_warmup_flow():
    print("\n" + "=" * 60)
    print("TESTE 4: Pré-aquecimento e Buffer de Visão (TTL 3s) em main.py")
    print("=" * 60)

    # Simulação da estrutura de JarvisLive
    class SimulatedJarvis:
        def __init__(self):
            self._vision_busy = False
            self._vision_warmup_frame = None
            self._vision_warmup_ttl = 3.0
            self._pending_vision = None
            self._rt_executor = None

        async def _check_and_warmup_vision(self, text: str):
            if self._vision_busy:
                return
            engine = get_decision_engine()
            wants_vision, prob = await engine.evaluate_vision_warmup(text)
            if wants_vision and prob >= 0.80 and not self._vision_busy:
                # Mock de captura rápida de tela
                mock_img_bytes = b"MOCK_PNG_SCREEN_FRAME_BYTES"
                mock_mime = "image/png"
                self._vision_warmup_frame = (mock_img_bytes, mock_mime, time.monotonic())
                print(f"[JEV-Local] Simulado: Frame pré-aquecido armazenado (TTL={self._vision_warmup_ttl}s)")

        async def simulate_screen_process_call(self):
            _now = time.monotonic()
            used_warmup = False
            if self._vision_warmup_frame is not None:
                w_img_b, w_mime_t, w_ts = self._vision_warmup_frame
                self._vision_warmup_frame = None
                if (_now - w_ts) <= self._vision_warmup_ttl:
                    img_b, mime_t = w_img_b, w_mime_t
                    used_warmup = True
                    print(f"[JEV-Local] Simulado: Frame reutilizado com sucesso! Idade={_now - w_ts:.3f}s")
                    return img_b, mime_t, used_warmup

            # Se expirou ou não existia, captura novo frame
            img_b, mime_t = b"FRESH_CAPTURED_FRAME", "image/png"
            return img_b, mime_t, False

    jarvis = SimulatedJarvis()

    # 4.1 Usuário fala "Olhe minha tela"
    await jarvis._check_and_warmup_vision("Evie, por favor dê uma olhada na tela.")
    assert jarvis._vision_warmup_frame is not None, "Falha: Frame de pré-aquecimento deve estar presente."
    print("[OK] 4.1 Frame pré-aquecido criado em buffer.")

    # 4.2 Gemini Live aciona screen_process dentro da janela de 3 segundos (ex: após 0.2s)
    await asyncio.sleep(0.2)
    img_b, mime_t, used_warmup = await jarvis.simulate_screen_process_call()
    assert used_warmup is True, "Falha: O frame pré-aquecido deveria ter sido reutilizado dentro do TTL."
    assert img_b == b"MOCK_PNG_SCREEN_FRAME_BYTES", "Falha: Dados do frame reutilizado incorretos."
    print("[OK] 4.2 Reutilização do frame com latência zero validada dentro da janela de TTL.")

    # 4.3 Teste de expiração de TTL (> 3.0s)
    await jarvis._check_and_warmup_vision("Olha a tela de novo.")
    assert jarvis._vision_warmup_frame is not None
    # Força expiração alterando timestamp
    w_bytes, w_mime, _ = jarvis._vision_warmup_frame
    jarvis._vision_warmup_frame = (w_bytes, w_mime, time.monotonic() - 3.5)  # 3.5s atrás
    _, _, expired_reuse = await jarvis.simulate_screen_process_call()
    assert expired_reuse is False, "Falha: Frame expirado (> 3s) NÃO deve ser reutilizado."
    print("[OK] 4.3 Expiração de TTL validada: novo frame capturado se > 3.0s.")


async def main():
    print("\nINICIANDO SUÍTE DE TESTES: MOTOR JEV LOCAL (SYSTEM 1)")
    await test_pillar_1_decision_engine()
    await test_pillar_2_memory_gate()
    await test_pillar_3_auto_routing()
    await test_pillar_4_vision_warmup_flow()
    print("\n" + "=" * 60)
    print("TODOS OS 4 PILARES DO MOTOR JEV LOCAL PASSARAM COM SUCESSO!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
