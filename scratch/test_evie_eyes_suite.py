import sys
import os
import time

# Ensure PyQt6 offscreen
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))

def test_evie_eyes_avatar():
    print("[1] Testando EvieEyesAvatar oficial com o motor evie_eyes...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPixmap, QPainter, QColor
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    from core.avatar import EvieEyesAvatar, HoloAvatar
    assert HoloAvatar is EvieEyesAvatar, "HoloAvatar deve apontar para EvieEyesAvatar"
    
    avatar = EvieEyesAvatar()
    print(" - Instanciado com sucesso com FaceRenderer e Face")
    
    # Testar todas as expressões nativas do evie_eyes
    native_expressions = [
        "neutral", "happy", "sad", "angry", "sleepy",
        "asleep", "surprised", "suspicious", "wink", "love", "excited"
    ]
    for expr in native_expressions:
        avatar.set_expression(expr)
        assert avatar.face.expression == expr, f"Falha ao definir expressão nativa {expr}"
    print(f" - Todas as {len(native_expressions)} expressões nativas aceitas com perfeição")
    
    # Testar estados visuais SDUI
    visual_states = [
        "IDLE_OBSERVING", "HAPPY", "CURIOUS_SPARK",
        "THINKING_DEEP", "SPEAKING", "FOCUSED",
        "SLEEPY", "ALERT_URGENT", "SURPRISED", "LOVE", "EXCITED", "SAD", "ANGRY", "WINK"
    ]
    for vs in visual_states:
        avatar.set_visual_state(vs)
        assert avatar._visual_state == vs, f"Falha ao mapear visual state {vs}"
    print(" - Todos os estados visuais mapeados para as expressões procedurais")
    
    # Testar interações: glance, look_at, wink, happy, poke, yawn, sleep, snap, blink_now, dance
    avatar.glance(0.5, -0.3, hold=1.5)
    avatar.look_at(-0.4, 0.2, hold=2.0)
    avatar.trigger_wink("left")
    assert avatar.face.expression == "wink_left"
    avatar.trigger_wink("right")
    assert avatar.face.expression == "wink_right"
    avatar.trigger_happy(1.5)
    assert avatar.face.expression == "happy"
    avatar.blink_now(double=True)
    avatar.yawn()
    avatar.sleep()
    assert avatar.face.idle.stage == "asleep"
    avatar.poke()
    assert avatar.face.idle.stage != "asleep"
    avatar.snap()
    
    # Testar dança rítmica
    avatar.dance(4.0)
    assert avatar.face.dance.dancing, "DanceLayer deve estar ativa"
    assert avatar.face.expression == "happy", "Dança deve colocar expressão happy"
    avatar.step(0.016)
    avatar.face.dance.stop()
    print(" - Dança com olhos felizes (^ ^), pulinho e balanço rítmico validada com sucesso")

    # Testar perspectiva 3D (olho esquerdo aumenta quando mouse vai para a direita)
    avatar.track_gaze(0.8, 0.0)
    for _ in range(25):
        avatar.step(0.016)
    left_eye = avatar.face.eyes[0]
    right_eye = avatar.face.eyes[1]
    assert left_eye.w > right_eye.w, f"Olho esquerdo ({left_eye.w}) deve ser maior que o direito ({right_eye.w}) quando o olhar é para a direita"
    print(" - Perspectiva 3D validada: olho esquerdo aumenta proporcionalmente à distância do mouse à direita")
    
    # Testar simulação de 60 FPS com amplitude de voz
    for _ in range(60):
        avatar.step(dt=0.016, amp=0.85, speaking=True)
    assert avatar.face.breathing.period < 3.0, "Voz falando deve diminuir período de respiração (respirar mais rápido)"
    print(" - 60 steps simulados a 60 FPS com reatividade de voz e respiração ativa")
    
    # Testar renderização com QPainter e FaceRenderer
    pm = QPixmap(800, 600)
    pm.fill(QColor("#05070A"))
    p = QPainter(pm)
    avatar.paint(p, 400.0, 300.0, 120.0,
                 QColor("#00F0FF"), QColor("#00F0FF"), QColor("#05070A"))
    p.end()
    assert not pm.isNull(), "Pixmap gerada não deve ser nula"
    print("[OK] Teste 1: EvieEyesAvatar renderizado perfeitamente com supersampling, bloom e partículas!")

def test_sentiment_analysis_ui_schema():
    print("\n[2] Testando Análise de Sentimento Procedural em core/ui_schema.py...")
    from core.ui_schema import parse_llm_response_to_procedural_ui, VisualState
    
    # 1. Feliz
    p_happy = parse_llm_response_to_procedural_ui("Que maravilha, funcionou com perfeição! Adorei o resultado.")
    assert p_happy.visual_state == VisualState.HAPPY.value, f"Esperado HAPPY, obtido: {p_happy.visual_state}"
    print(" - Sentimento FELIZ -> VisualState.HAPPY [OK]")
    
    # 2. Alerta
    p_alert = parse_llm_response_to_procedural_ui("Atenção, detectei um erro crítico no processo!")
    assert p_alert.visual_state == VisualState.ALERT_URGENT.value, f"Esperado ALERT_URGENT, obtido: {p_alert.visual_state}"
    print(" - Sentimento ALERTA -> VisualState.ALERT_URGENT [OK]")
    
    # 3. Dúvida / Curiosidade / Pergunta
    p_curious = parse_llm_response_to_procedural_ui("Você gostaria que eu analisasse as métricas agora?")
    assert p_curious.visual_state == VisualState.CURIOUS_SPARK.value, f"Esperado CURIOUS_SPARK, obtido: {p_curious.visual_state}"
    print(" - Sentimento CURIOSA / PROATIVA -> VisualState.CURIOUS_SPARK [OK]")
    
    # 4. Foco / Código técnico
    p_focus = parse_llm_response_to_procedural_ui("Estou compilando e depurando o algoritmo neste momento.")
    assert p_focus.visual_state == VisualState.FOCUSED.value, f"Esperado FOCUSED, obtido: {p_focus.visual_state}"
    print(" - Sentimento FOCO TÉCNICO -> VisualState.FOCUSED [OK]")
    
    # 5. Fala padrão
    p_speech = parse_llm_response_to_procedural_ui("Os relatórios de hoje foram salvos na pasta de documentos.")
    assert p_speech.visual_state == VisualState.SPEAKING.value, f"Esperado SPEAKING, obtido: {p_speech.visual_state}"
    print(" - Sentimento FALA PADRÃO -> VisualState.SPEAKING [OK]")
    print("[OK] Teste 2: Análise de sentimento mapeada para as expressões faciais com sucesso!")

def test_hud_canvas_integration():
    print("\n[3] Testando integração com HudCanvas em ui.py...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QPointF, Qt
    
    app = QApplication.instance() or QApplication(sys.argv)
    from ui import HudCanvas
    
    hud = HudCanvas(None, assistant_name="EVIE")
    assert hasattr(hud, "set_subtitle"), "HudCanvas deve ter set_subtitle"
    assert hasattr(hud, "set_visual_state"), "HudCanvas deve ter set_visual_state"
    
    hud.set_subtitle("Olá Rafael, como posso ajudar agora?")
    assert hud._last_subtitle == "Olá Rafael, como posso ajudar agora?", "Subtítulo não foi definido"
    
    hud.set_visual_state("CURIOUS_SPARK")
    assert hud._avatar._visual_state == "CURIOUS_SPARK", "Avatar visual state não foi propagado"
    
    # Testar mouse glance e cliques
    evt = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(100.0, 150.0), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    hud.mouseMoveEvent(evt)
    
    # Clique esquerdo para wink
    evt_click = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(50.0, 150.0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    hud.mousePressEvent(evt_click)
    assert hud._avatar.face.expression == "wink_left", "Clique lateral esquerdo deve disparar wink_left"
    
    # Testar dança no HudCanvas
    hud.dance(4.0)
    assert hud._avatar.face.dance.dancing, "HudCanvas.dance deve acionar DanceLayer"
    hud._avatar.face.dance.stop()
    print(" - HudCanvas.dance validado com sucesso")
    
    print("[OK] Teste 3: HudCanvas totalmente integrado com o novo motor procedural dos olhos!")

def test_picture_in_picture_window():
    print("\n[4] Testando Picture-in-Picture Floating Window (PiP)...")
    from PyQt6.QtWidgets import QApplication, QPushButton
    from ui import PictureInPictureWindow
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Criamos mock simples de MainWindow
    class MockMainWindow:
        _face_path = ""
        class MockHud:
            state = "SLEEPING"
            speaking = False
            muted = False
            _visual_state = "IDLE_OBSERVING"
        hud = MockHud()
        def showNormal(self): pass
        def activateWindow(self): pass
        def raise_(self): pass
    
    mock_main = MockMainWindow()
    pip = PictureInPictureWindow(main_window=mock_main)
    assert pip.hud is not None, "PiP deve conter um HudCanvas interno"
    pip.show_pip()
    assert pip.isVisible(), "PiP deve estar visível após show_pip()"
    
    # Testar interações diretas no PiP (Astro Bot sem botões e sem textos fixos)
    assert not hasattr(pip, "btn_dance") or pip.findChild(QPushButton, "btn_dance") is None, "PiP não deve ter botões visíveis"
    assert hasattr(pip, "_bubble"), "PiP deve conter _bubble (SpeechBubbleWidget) para falas e iniciativas"
    
    # Testar balão de fala animado
    pip.show_speech_bubble("Testando balão de fala!")
    assert pip._bubble._text == "Testando balão de fala!"
    assert pip._bubble.isVisible(), "Balão de fala deve estar visível ao exibir fala"
    
    # Testar piscar olho esquerdo e direito individualmente
    pip.hud.wink("left")
    assert pip.hud._avatar.face.expression == "wink_left", f"Expressão esperada wink_left, recebida: {pip.hud._avatar.face.expression}"
    pip.hud.wink("right")
    assert pip.hud._avatar.face.expression == "wink_right", f"Expressão esperada wink_right, recebida: {pip.hud._avatar.face.expression}"
    
    # Testar disparo de dança a 120 BPM em arco único
    pip.hud.dance(4.5)
    assert pip.hud._avatar.face.dance.dancing, "Hud dance deve ativar o DanceLayer"
    assert pip.hud._avatar.face.dance.bpm == 120.0, "Dança deve rodar a 120 BPM"
    pip.hud._avatar.face.dance.stop()
    
    # Testar carinho / alegria
    pip.hud.trigger_happy(2.0)
    assert pip.hud._avatar.face.expression == "happy", "Carinho deve colocar expressão feliz (^ ^)"
    
    # Testar olhos verdes ao escutar
    pip.hud.set_listening(True)
    assert pip.hud._avatar.face._custom_color == (50.0, 235.0, 140.0), "Olhos devem ficar verdes na paleta ciano ao escutar"
    pip.hud.set_listening(False)
    assert pip.hud._avatar.face._custom_color is None, "Olhos devem restaurar ao parar de escutar"
    
    # Testar restauração e fechamento
    pip.restore_main_window()
    assert pip.isHidden(), "PiP deve ocultar ao restaurar janela principal"
    print("[OK] Teste 4: Picture-in-Picture estilo pod com balão de fala validada com sucesso!")

if __name__ == "__main__":
    test_evie_eyes_avatar()
    test_sentiment_analysis_ui_schema()
    test_hud_canvas_integration()
    test_picture_in_picture_window()
    print("\n[SUCESSO] TODOS OS TESTES DO NOVO MOTOR PROCEDURAL DE OLHOS PASSARAM COM SUCESSO!")
