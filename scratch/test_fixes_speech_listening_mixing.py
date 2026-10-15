import os
import sys
import time
from pathlib import Path

# Add project root
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint
import pygame

# Initialize QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ui import PictureInPictureWindow, SpeechBubbleWidget
from evie_eyes.face import Face
from evie_eyes.render.shapes import draw_eyes, Layout
from core.avatar import HoloAvatar

class FakeMainWindow:
    def __init__(self):
        self.hud = type("HUD", (), {"state": "IDLE", "speaking": False, "muted": False, "_visual_state": "IDLE_OBSERVING"})()

def test_floating_speech_bubble_outside():
    print("[1] Testando Balão de Fala Flutuante ACIMA e FORA do Layout do PiP...")
    main_win = FakeMainWindow()
    pip = PictureInPictureWindow(main_win)
    pip.resize(160, 160)
    pip.move(500, 400)
    pip.show()
    app.processEvents()

    bubble = pip._bubble
    assert isinstance(bubble, SpeechBubbleWidget), "O balão deve ser uma instância de SpeechBubbleWidget"
    assert bubble.isWidgetType(), "O balão deve ser um QWidget independente para flutuar fora do layout do PiP"
    
    # Exibir texto de fala
    pip.show_speech_bubble("Olá! Eu sou a Evie!", duration_sec=5.0)
    app.processEvents()

    # Verificar posicionamento: deve estar ACIMA da janela do PiP (y menor)
    pip_geo = pip.geometry()
    bubble_geo = bubble.geometry()
    print(f" - Geometria PiP: {pip_geo.x()}, {pip_geo.y()}, {pip_geo.width()}x{pip_geo.height()}")
    print(f" - Geometria Balão: {bubble_geo.x()}, {bubble_geo.y()}, {bubble_geo.width()}x{bubble_geo.height()}")
    
    assert bubble_geo.y() < pip_geo.y(), "O balão de fala DEVE estar acima da borda superior do PiP"
    assert bubble_geo.bottom() <= pip_geo.top() + 2, "O balão deve estar flutuando fora do layout do PiP"
    assert bubble._tail_direction == "down", "A cauda do balão deve apontar para baixo em direção à cabeça da Evie"

    # Ao mover o PiP, o balão deve acompanhar sincronizado
    pip.move(600, 350)
    app.processEvents()
    bubble._sync_geometry()
    new_bubble_geo = bubble.geometry()
    assert new_bubble_geo.y() < 350, "Ao mover o PiP, o balão deve continuar acima do pod"

    pip.hide()
    bubble.hide()
    print("[OK] Balão de fala flutuante testado com sucesso fora do layout do PiP!")

def test_listening_mode_timeout_and_cyan_recovery():
    print("\n[2] Testando Timeout do Modo Listening (Não travar verde)...")
    main_win = FakeMainWindow()
    pip = PictureInPictureWindow(main_win)
    pip.resize(160, 160)
    pip.state = "LISTENING"
    pip.set_listening(True)

    # Cor deve estar verde
    assert pip._avatar.face._custom_color == (50.0, 235.0, 140.0), "Modo listening deve ativar verde"
    assert pip._listening_timeout_t > time.time(), "Timeout do listening deve ser agendado no futuro (+6s)"

    # Se usuário falar (amp > 0.08), o timeout deve ser renovado
    pip._step()  # amp normal
    prev_timeout = pip._listening_timeout_t
    pip._live_amp = 0.50
    pip._step()
    assert pip._listening_timeout_t >= prev_timeout, "Fala do usuário deve manter/estender o modo escuta"

    # Simular passagem do tempo sem fala (> 6 segundos)
    pip._live_amp = 0.0
    pip._amp_disp = 0.0
    pip._listening_timeout_t = time.time() - 0.1
    pip.speaking = False
    pip._step()

    # Deve ter voltado automaticamente para IDLE e cor ciano (None no custom_color)
    assert pip.state == "IDLE", f"Após silêncio, estado deve ser IDLE e não {pip.state}"
    assert pip._avatar.face._custom_color is None, "Após timeout, cor personalizada verde deve ser limpa (ciano ativo)"
    assert pip._listening_timeout_t == 0.0, "Timeout deve estar zerado após reset"
    print("[OK] Modo listening recupera automaticamente o estado IDLE ciano após silêncio!")

def test_animations_not_mixing_or_slicing_happy_eyes():
    print("\n[3] Testando Prevenção de Mistura de Animações e Corte de Chevrons (^ ^)...")
    face = Face()
    
    # 1. Colocar pálpebras caídas de tédio / sono
    face.set_expression("sleepy")
    face.update(0.3)
    assert face._targets[0].lid_top > 0.4, "Sleepy deve ter lid_top > 0.4"
    assert face._pose[0].lid_top > 0.4, "Após update, sleepy deve ter lid_top > 0.4 na pose"

    # 2. Usuário ou interação dispara "happy" (olhos felizes ^ ^)
    face.set_expression("happy")
    # Pálpebras DEVEM ter sido zeradas e snapadas imediatamente para 0
    assert face._targets[0].lid_top == 0.0, "Happy não pode ter pálpebras ativas no alvo"
    assert face._pose[0].lid_top == 0.0, "Happy deve ter zerado o lid_top na pose"
    assert face._springs[0]["lid_top"].value == 0.0, "Happy deve ter snapado o spring lid_top para 0.0"
    assert face._targets[0].arc >= 0.95, "Happy deve ter arco configurado"

    # 3. Renderizar com Pygame e garantir que as pálpebras não cortam o chevron
    pygame.init()
    surf = pygame.Surface((200, 200))
    surf.fill((0, 0, 0))
    layout = Layout(width=200, height=200)
    
    # Simular step de 0.1s
    face.update(0.1)
    
    # Checar se no Face e nos parâmetros dos olhos arc está ativo e lid_top está zerado
    eye_left, eye_right = face.eyes
    assert eye_left.arc > 0.5, "Olhos devem estar em formato de arco ^ ^"
    assert eye_left.lid_top == 0.0, f"lid_top não deve existir em happy eye: {eye_left.lid_top}"

    # Renderizar na superfície sem exceções ou cortes
    draw_eyes(surf, face.eyes, layout, (0, 0, 0), face.particles)
    
    # 4. Testar interrupção limpa: chamar dance enquanto happy está ativo
    face.trigger_dance(4.5)
    assert face.dance.dancing, "Dance deve iniciar"
    
    # Interromper dança com surpresa ou carinho
    face.set_expression("surprised", duration=2.0)
    assert not face.dance.dancing, "Nova expressão deve interromper a dança limpando seu estado"
    assert face.expression == "surprised", "Expressão deve ser surprised"

    # 5. Testar que THINKING no HoloAvatar não injeta 'sleepy'
    avatar = HoloAvatar()
    avatar.set_expression("happy")
    avatar.set_visual_state("THINKING")
    assert avatar.face.expression != "sleepy", "THINKING não deve aplicar sleepy e estragar os olhos!"
    
    print("[OK] Animações se interrompem limpamente sem misturar e sem cortar chevrons ^^!")

if __name__ == "__main__":
    test_floating_speech_bubble_outside()
    test_listening_mode_timeout_and_cyan_recovery()
    test_animations_not_mixing_or_slicing_happy_eyes()
    print("\nTODAS AS 3 CORREÇÕES VALIDADAS COM SUCESSO ABSOLUTO!")
