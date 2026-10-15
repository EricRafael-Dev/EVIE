import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from ui import PictureInPictureWindow, HudCanvas
from evie_eyes.face import Face
from evie_eyes.behaviors.dance import DanceLayer

def test_single_arc_dance():
    face = Face()
    dance = DanceLayer(face, bpm=120.0)
    dance.trigger(4.5)
    
    # 0.25s: indo para a direita máxima
    dance._time = 0.25
    from evie_eyes.model.params import EyeParams
    left, right = EyeParams(), EyeParams()
    dance.apply(left, right)
    
    # Olho esquerdo deve subir (y menor) e olho direito deve descer (y maior)
    assert left.y < right.y, f"Em direção à direita, olho esquerdo deve subir e direito descer: left={left.y}, right={right.y}"
    # Ambos devem estar inclinados para a direita
    assert left.lid_tilt < 0 and right.lid_tilt < 0, f"Ambos devem ter tilt negativo (para a direita): {left.lid_tilt}"
    
    # Ao parar a dança, deve disparar um piscar de olhos
    dance.stop()
    assert face.blink.blinking, "Ao encerrar a dança, deve piscar para transição"
    print("[OK] Teste: Dancinha em arco único com inclinação e piscar no encerramento validada!")

def test_independent_winks():
    face = Face()
    face.trigger_wink("left")
    assert face.expression == "wink_left"
    face.trigger_wink("right")
    assert face.expression == "wink_right"
    print("[OK] Teste: Piscar individual de cada olho (esquerdo e direito) validado!")

def test_green_listening_color():
    face = Face()
    face.set_custom_color((50.0, 235.0, 140.0))
    assert face._custom_color == (50.0, 235.0, 140.0)
    face.set_custom_color(None)
    assert face._custom_color is None
    print("[OK] Teste: Olhos verdes no modo escuta validados!")

def test_pip_interactions_and_bubble():
    app = QApplication.instance() or QApplication(sys.argv)
    
    class MockMainWindow:
        _face_path = ""
        class MockHud:
            state = "IDLE"
            speaking = False
            muted = False
        hud = MockHud()
        def showNormal(self): pass
        def activateWindow(self): pass
        def raise_(self): pass
    
    mock_main = MockMainWindow()
    pip = PictureInPictureWindow(main_window=mock_main)
    pip.show_pip()
    
    # 1. Testar balão de fala animado
    pip.show_speech_bubble("Ideia espontânea da Evie!")
    assert pip._bubble._text == "Ideia espontânea da Evie!"
    assert pip._bubble.isVisible()
    
    # 2. Testar clique no olho esquerdo (rel_x = 0.30)
    pip._handle_release(pip.mapToGlobal(pip.rect().center()), QPointF(pip.width() * 0.30, pip.height() * 0.50).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "wink_left", f"Clique à esquerda deve piscar olho esquerdo, obtido: {pip.hud._avatar.face.expression}"
    
    # 3. Testar clique no olho direito (rel_x = 0.70)
    pip._handle_release(pip.mapToGlobal(pip.rect().center()), QPointF(pip.width() * 0.70, pip.height() * 0.50).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "wink_right", f"Clique à direita deve piscar olho direito, obtido: {pip.hud._avatar.face.expression}"
    
    # 4. Testar clique no centro (carinho/alegria)
    pip._handle_release(pip.mapToGlobal(pip.rect().center()), QPointF(pip.width() * 0.50, pip.height() * 0.50).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "happy", f"Clique no centro deve gerar alegria, obtido: {pip.hud._avatar.face.expression}"
    
    # 5. Testar movimento: fica desconfiada na direção do sentido e feliz ao soltar
    pip._handle_press(QPointF(100, 100).toPoint(), QPointF(50, 50).toPoint(), Qt.MouseButton.LeftButton)
    # Arraste para a direita -> suspicious_right
    pip._handle_move(QPointF(120, 100).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "suspicious_right", f"Ao mover para a direita, deve olhar desconfiada para a direita, obtido: {pip.hud._avatar.face.expression}"
    
    # Arraste para a esquerda -> suspicious_left
    pip._handle_move(QPointF(80, 100).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "suspicious_left", f"Ao mover para a esquerda, deve olhar desconfiada para a esquerda, obtido: {pip.hud._avatar.face.expression}"
    
    pip._handle_release(QPointF(80, 100).toPoint(), QPointF(30, 50).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "happy", "Ao soltar o PiP após mover, deve ficar feliz"
    
    print("[OK] Teste: Interações táteis, desconfiada/feliz e balão de fala validados com 100% de sucesso!")

def test_square_and_border_resizing():
    app = QApplication.instance() or QApplication(sys.argv)
    class MockMainWindow:
        _face_path = ""
        class MockHud:
            state = "IDLE"
            speaking = False
            muted = False
        hud = MockHud()
        def showNormal(self): pass
        def activateWindow(self): pass
        def raise_(self): pass

    pip = PictureInPictureWindow(main_window=MockMainWindow())
    
    # 1. Verificar design quadrado
    assert pip.width() == pip.height(), f"Design deve ser quadrado: {pip.width()}x{pip.height()}"
    assert pip.width() == 160, f"Largura inicial deve ser 160px, obtido: {pip.width()}"
    
    # 2. Verificar zonas de hit-testing nas bordas metálicas
    # Centro (visor) -> 1 (HTCLIENT)
    assert pip._get_resize_zone(QPointF(80, 80).toPoint()) == 1, "Centro deve ser HTCLIENT (1)"
    # Borda esquerda -> 10 (HTLEFT)
    assert pip._get_resize_zone(QPointF(4, 80).toPoint()) == 10, "Borda esquerda deve ser HTLEFT (10)"
    # Borda direita -> 11 (HTRIGHT)
    assert pip._get_resize_zone(QPointF(156, 80).toPoint()) == 11, "Borda direita deve ser HTRIGHT (11)"
    # Borda superior -> 12 (HTTOP)
    assert pip._get_resize_zone(QPointF(80, 4).toPoint()) == 12, "Borda superior deve ser HTTOP (12)"
    # Borda inferior -> 15 (HTBOTTOM)
    assert pip._get_resize_zone(QPointF(80, 156).toPoint()) == 15, "Borda inferior deve ser HTBOTTOM (15)"
    # Fora do pod (canto transparente) -> -1 (HTTRANSPARENT)
    assert pip._get_resize_zone(QPointF(0, 0).toPoint()) == -1, "Canto externo deve ser HTTRANSPARENT (-1)"
    
    # 3. Testar redimensionamento via arraste na borda direita
    # Clica na borda direita (x=158, y=80)
    pip._handle_press(QPointF(300, 300).toPoint(), QPointF(158, 80).toPoint(), Qt.MouseButton.LeftButton)
    assert pip._resize_edge == 11, f"Deve iniciar redimensionamento na borda direita, obtido: {pip._resize_edge}"
    
    # Arraste para a direita por 30px
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    move_ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(188, 80), QPointF(330, 300), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    pip.mouseMoveEvent(move_ev)
    assert pip.width() == 190, f"Após arrastar borda direita em +30px, largura deve ser 190, obtido: {pip.width()}"
    
    # Solta o clique
    pip._handle_release(QPointF(330, 300).toPoint(), QPointF(188, 80).toPoint(), Qt.MouseButton.LeftButton)
    assert pip._resize_edge is None, "Ao soltar o mouse, o redimensionamento deve ser finalizado"
    
    print("[OK] Teste: Design quadrado (160x160) e redimensionamento pelas bordas metálicas validados!")

def test_instantaneous_drag_sensitivity():
    app = QApplication.instance() or QApplication(sys.argv)
    class MockMainWindow:
        _face_path = ""
        class MockHud:
            state = "IDLE"
            speaking = False
            muted = False
        hud = MockHud()
        def showNormal(self): pass
        def activateWindow(self): pass
        def raise_(self): pass

    pip = PictureInPictureWindow(main_window=MockMainWindow())
    
    # Inicia arraste na posição global (200, 200)
    pip._handle_press(QPointF(200, 200).toPoint(), QPointF(80, 80).toPoint(), Qt.MouseButton.LeftButton)
    time.sleep(0.04)
    
    # Arrasta para a direita (de 200 para 220)
    pip._handle_move(QPointF(220, 200).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "suspicious_right", f"Ao mover para a direita, deve olhar suspicious_right, obtido: {pip.hud._avatar.face.expression}"
    time.sleep(0.04)
    
    # Agora inverte o movimento para a esquerda em apenas 4px (de 220 para 216, ainda à direita do ponto inicial 200!)
    # O sistema anterior continuava olhando suspicious_right porque 216 - 200 = +16 > 0!
    # O novo sistema ultra-sensível detecta velocidade instantânea negativa e vira para a esquerda!
    pip._handle_move(QPointF(216, 200).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "suspicious_left", f"Ao inverter o sentido para a esquerda, deve olhar suspicious_left imediatamente! Obtido: {pip.hud._avatar.face.expression}"
    time.sleep(0.04)
    
    # Inverte novamente para a direita em apenas 5px (de 216 para 221)
    pip._handle_move(QPointF(221, 200).toPoint(), Qt.MouseButton.LeftButton)
    assert pip.hud._avatar.face.expression == "suspicious_right", f"Ao inverter novamente para a direita, deve olhar suspicious_right imediatamente! Obtido: {pip.hud._avatar.face.expression}"
    
    print("[OK] Teste: Alternância instantânea e ultra-sensível da direção da desconfiança validada!")

def test_sleep_breathing_combination():
    face = Face()
    face.set_expression("asleep")
    assert face.expression == "asleep"
    assert not face.saccade.enabled, "Ao dormir, sacadas devem estar desabilitadas"
    assert not face.blink.enabled, "Ao dormir, piscar involuntário deve estar desabilitado"
    
    # Testa ciclo de respiração profunda e viva durante o sono
    face.breathing.period = 4.8
    face.breathing.amplitude = 0.08
    face.breathing.bob = 0.045
    
    # Executa múltiplos steps para verificar a respiração rítmica
    y_values = []
    h_values = []
    glow_values = []
    for _ in range(50):
        face.update(0.1)
        y_values.append(face.eyes[0].y)
        h_values.append(face.eyes[0].h)
        glow_values.append(face.eyes[0].glow)
    
    # A respiração viva deve produzir variação visível no heave vertical (y) e brilho/espessura
    y_range = max(y_values) - min(y_values)
    glow_range = max(glow_values) - min(glow_values)
    assert y_range > 0.06, f"Heave vertical da respiração ao dormir deve ser vivo (> 0.06), obtido: {y_range:.4f}"
    assert glow_range > 0.15, f"Pulso de brilho da respiração ao dormir deve ser perceptível (> 0.15), obtido: {glow_range:.4f}"
    
    print("[OK] Teste: Animação de sono combinada com respiração profunda e viva validada!")

if __name__ == "__main__":
    test_single_arc_dance()
    test_independent_winks()
    test_green_listening_color()
    test_pip_interactions_and_bubble()
    test_square_and_border_resizing()
    test_instantaneous_drag_sensitivity()
    test_sleep_breathing_combination()
    print("\nTODOS OS TESTES (INCLUINDO DESIGN QUADRADO, REDIMENSIONAMENTO, SENSIBILIDADE E SONO VIVO) FORAM CONCLUÍDOS COM 100% DE SUCESSO!")
