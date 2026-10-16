"""
scratch/verify_all_customizations.py
Validação automatizada de todas as 3 solicitações de áudio:
1. Física de mola com bounce / overshoot nos olhos + Correção de congelamento no duplo clique / clique
2. Coreografia de despertar procurando o mouse pela tela com pulinho e piscar
3. Área de Trabalho Remota (SpaceView) com multi-monitor, streaming JPEG e injeção de inputs
"""

import time
import math
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_eye_physics_and_double_click():
    print("\n--- TESTE 1: Física Elástica & Descongelamento do Duplo Clique ---")
    from evie_eyes.face import Face
    from evie_eyes.behaviors.saccade import SaccadeLayer
    from evie_eyes.behaviors.dance import DanceLayer

    face = Face(seed=42)
    assert face.expression == "neutral", "Face deve iniciar como neutral"

    # Teste de overshoot elástico no SaccadeLayer
    saccade = face.saccade
    saccade.look_at(0.8, -0.4, hold=1.5)
    
    positions = []
    for _ in range(30):
        saccade.update(0.016)
        positions.append(saccade._left[0].value)

    max_x = max(positions)
    final_x = positions[-1]
    overshoot = (max_x - final_x) / (final_x if final_x != 0 else 1.0)
    print(f"Alvo X: 0.8 | Pico do salto elástico: {max_x:.4f} | Estabilizado: {final_x:.4f} | Overshoot: {overshoot*100:.1f}%")
    assert max_x > 0.8, "A mola sob-amortecida deve gerar overshoot elástico (bounce)"

    # Teste de duplo clique (clique 1 = happy, clique 2 = dance)
    # Simula o clique 1 definindo happy
    face.set_expression("happy", duration=1.8, source="user")
    assert face.expression == "happy"
    
    # Simula o clique 2 disparando dança
    face.dance.trigger(duration=0.5)
    assert face.dance.dancing, "Dança deve estar ativa"
    
    # Avança a simulação no tempo até a dança terminar
    for _ in range(40):
        face.update(0.02)

    assert not face.dance.dancing, "Dança deve ter finalizado"
    print(f"Expressão após dança finalizar: '{face.expression}'")
    assert face.expression == "neutral", f"Esperado 'neutral', obteve '{face.expression}' (NÃO PODE CONGELAR EM HAPPY)"
    print("✅ Teste 1 APROVADO: Física elástica ativa e duplo clique retorna perfeitamente para neutral!")


def test_wake_mouse_search():
    print("\n--- TESTE 2: Rotina de Despertar Procurando o Mouse ---")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QPoint
    from ui import HudCanvas

    app = QApplication.instance() or QApplication([])
    canvas = HudCanvas(face_path="", assistant_name="Evie")
    canvas._on_screen = lambda: True

    assert canvas._wake_search_active == True, "_wake_search_active deve iniciar como True no boot"
    print("Evie iniciou com busca ativa pelo cursor.")

    # Simula passos de busca com cursor estático
    from PyQt6.QtGui import QCursor
    actual_pos = QCursor.pos()
    canvas._wake_search_start_cursor = actual_pos
    canvas._wake_search_t = 0.3
    canvas._step()
    assert canvas._wake_search_active == True, "Deve continuar buscando nos primeiros instantes"
    
    # Caso 1: Cursor se moveu mais de 40px desde o início da busca
    canvas._wake_search_t = 0.8
    canvas._wake_search_start_cursor = QPoint(actual_pos.x() - 120, actual_pos.y() - 80)
    canvas._step()
    assert canvas._wake_search_active == False, "Ao detectar movimento do cursor, deve travar no mouse e desativar wake search"
    
    # Caso 2: Timeout da busca coreografada
    canvas.trigger_wake_search()
    assert canvas._wake_search_active == True
    canvas._wake_search_t = 3.5
    canvas._step()
    assert canvas._wake_search_active == False, "Ao atingir timeout, deve finalizar busca e travar no mouse"
    print("✅ Teste 2 APROVADO: Coreografia de busca e travamento no mouse funcionando perfeitamente!")


def test_remote_desktop_and_monitors():
    print("\n--- TESTE 3: Área de Trabalho Remota & Multi-Monitores ---")
    from dashboard.server import DashboardServer

    monitors = DashboardServer._get_system_monitors()
    print(f"Monitores detectados: {len(monitors)}")
    for m in monitors:
        print(f" - {m['name']}: {m['width']}x{m['height']} pos=({m['x']}, {m['y']})")

    assert len(monitors) >= 1, "Pelo menos 1 monitor deve ser detectado"

    # Captura frame do Monitor 0
    t0 = time.perf_counter()
    jpeg0 = DashboardServer._capture_monitor_jpeg(0, quality=60, max_w=1280)
    dt0 = (time.perf_counter() - t0) * 1000
    print(f"Monitor 0 frame capturado em {dt0:.1f}ms | Tamanho: {len(jpeg0)/1024:.1f} KB")
    assert len(jpeg0) > 1000, "Frame do Monitor 0 deve ter dados válidos"

    if len(monitors) > 1:
        # Captura frame do Monitor 1 (secundário)
        t1 = time.perf_counter()
        jpeg1 = DashboardServer._capture_monitor_jpeg(1, quality=60, max_w=1280)
        dt1 = (time.perf_counter() - t1) * 1000
        print(f"Monitor 1 frame capturado em {dt1:.1f}ms | Tamanho: {len(jpeg1)/1024:.1f} KB")
        assert len(jpeg1) > 1000, "Frame do Monitor 1 deve ter dados válidos"

    # Teste de execução de inputs remotos (sem throw de exceção)
    DashboardServer._execute_remote_input({"action": "move", "monitor": 0, "x": 0.5, "y": 0.5})
    DashboardServer._execute_remote_input({"action": "scroll", "monitor": 0, "x": 0.5, "y": 0.5, "dy": 0})
    print("Injeção de inputs remotos executada sem erros.")

    # Teste da intenção em computer_settings
    from actions.computer_settings import _detect_action, _IRREVERSIBLE
    assert "remote_desktop" in _IRREVERSIBLE, "remote_desktop deve estar protegido pelo portão de confirmação"
    
    act = _detect_action("conectar ao computador")
    print(f"Detecção de voz 'conectar ao computador': {act}")
    assert act.get("action") == "remote_desktop", f"Esperado 'remote_desktop', obteve {act}"

    print("✅ Teste 3 APROVADO: Multi-monitores, captura ultra rápida, injeção de inputs e gate de confirmação validados!")


if __name__ == "__main__":
    test_eye_physics_and_double_click()
    test_wake_mouse_search()
    test_remote_desktop_and_monitors()
    print("\n🎉 TODOS OS TESTES PASSARAM COM SUCESSO!")
