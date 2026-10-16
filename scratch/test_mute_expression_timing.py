# scratch/test_mute_expression_timing.py
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.avatar import HoloAvatar

def test_mute_timing():
    print("Iniciando teste de timing da expressão ao mutar...")
    avatar = HoloAvatar()

    # Estado inicial: neutro
    avatar.set_expression("neutral")
    assert avatar.face.expression == "neutral", "Deveria iniciar em neutral"

    # Muta o microfone
    avatar.set_muted(True)

    # Imediatamente após mutar: deve ter a micro-reação rápida de sleepy com duração de 1.0s
    print(f"Expressão logo após mutar: {avatar.face.expression} (revert_in: {avatar.face._revert_in})")
    assert avatar.face.expression == "sleepy", "Logo após mutar deve acionar brevemente sleepy"
    assert avatar.face._revert_in is not None and avatar.face._revert_in <= 1.0, (
        f"A duração não deve ultrapassar 1.0s! Obtido: {avatar.face._revert_in}"
    )

    # Avança a simulação em 1.1s (passou 1 segundo)
    avatar.step(0.6, amp=0.0, muted=True, state="MUTED")
    avatar.step(0.6, amp=0.0, muted=True, state="MUTED")

    # Agora a expressão DEVE ter retornado para "neutral", mesmo continuando com muted=True e state="MUTED"
    print(f"Expressão após 1.2s com microfone ainda mutado: {avatar.face.expression}")
    assert avatar.face.expression == "neutral", (
        f"A Evie não deve ficar presa em 'sleepy' enquanto mutada! Obtido: {avatar.face.expression}"
    )

    # Roda mais 5 segundos de simulação mutada para garantir que NÃO volta para sleepy em loop
    for _ in range(50):
        avatar.step(0.1, amp=0.0, muted=True, state="MUTED")

    print(f"Expressão após 5s com microfone mutado: {avatar.face.expression}")
    assert avatar.face.expression == "neutral", (
        f"Expressão não deveria ter virado sleepy/tediosa em loop! Obtido: {avatar.face.expression}"
    )

    # Desmuta
    avatar.set_muted(False)
    avatar.step(0.1, amp=0.0, muted=False, state="LISTENING")
    assert avatar.face.expression == "neutral"

    print("[OK] TESTE DE TIMING DE MUTE APROVADO COM SUCESSO!")

if __name__ == "__main__":
    test_mute_timing()
