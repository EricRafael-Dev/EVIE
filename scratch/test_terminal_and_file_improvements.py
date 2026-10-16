# scratch/test_terminal_and_file_improvements.py
import sys
import io
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_improvements():
    print("=" * 60)
    print("Iniciando testes de Terminal e File Controller...")
    print("=" * 60)

    # 1. Action Loader discovery
    from core.action_loader import discover_actions
    registry = discover_actions(PROJECT_ROOT / "actions")
    assert registry.has("terminal_cmd"), "terminal_cmd não foi descoberto pelo action_loader!"
    assert registry.has("file_controller"), "file_controller não foi descoberto pelo action_loader!"
    print("✅ 1. Descoberta de ações: terminal_cmd e file_controller carregados com sucesso!")

    # 2. File controller - Path resolution & finding folders/files
    from actions.file_controller import file_controller, _resolve_path

    doc_path = _resolve_path("documentos")
    print(f"   [Path Resolution] 'documentos' -> {doc_path} (Existe: {doc_path.exists()})")
    assert doc_path.exists(), "Resolução de 'documentos' falhou!"

    # Search for project folder
    res_folder = file_controller({
        "action": "find_folders",
        "name": "Mark-LV",
        "path": "workspace",
        "max_results": 5
    })
    print("   [Find Folders Result]:")
    print("  ", res_folder.replace("\n", "\n   "))
    assert "Encontrado" in res_folder or "Mark-LV" in res_folder, "Busca de pastas falhou!"
    print("✅ 2. Busca e navegação de pastas validada!")

    # Search for files
    res_file = file_controller({
        "action": "find",
        "name": "terminal_cmd",
        "path": "workspace",
        "target_type": "file"
    })
    print("   [Find Files Result]:")
    print("  ", res_file.replace("\n", "\n   "))
    assert "terminal_cmd.py" in res_file, "Busca de arquivos falhou!"
    print("✅ 3. Busca de arquivos validada com sucesso!")

    # 3. Terminal CMD - Safe command execution (e.g. git status, python --version)
    from actions.terminal_cmd import terminal_cmd
    res_cmd = terminal_cmd({
        "action": "execute",
        "command": "git status",
        "working_dir": "workspace"
    })
    print("   [Git Status Result]:")
    first_lines = "\n   ".join(res_cmd.splitlines()[:5])
    print(f"   {first_lines}")
    assert "On branch" in res_cmd or "branch" in res_cmd.lower(), "Execução de git status falhou!"
    print("✅ 4. Execução de comandos Git (git status) validada!")

    # 4. Terminal CMD - Confirmation Gate on sensitive command (git push)
    from core import confirm
    # Bind dummy callbacks if not already bound
    confirm.bind(
        show=lambda title, detail: print(f"   [HUD BANNER SIMULADO] {title} - {detail[:40]}..."),
        hide=lambda: print("   [HUD BANNER SIMULADO] Esconder banner"),
        log=lambda m: None
    )

    res_push = terminal_cmd({
        "action": "execute",
        "command": "git push origin main",
        "working_dir": "workspace"
    })
    print(f"   [Git Push Result]: {res_push}")
    assert "[CONFIRMATION_PENDING]" in res_push or "confirm" in res_push.lower(), "Gate de confirmação para git push falhou!"
    print("✅ 5. Gate de aprovação/confirmação para git push validado!")

    # 5. Terminal CMD - Create and Run script
    test_code = """
import sys
print(f"CALCULADORA_OK:{2 + 2}")
"""
    res_script = terminal_cmd({
        "action": "create_and_run",
        "script_name": "teste_calc.py",
        "code": test_code,
        "working_dir": "workspace",
        "is_gui": False
    })
    print(f"   [Create and Run Result]: {res_script}")
    assert "CALCULADORA_OK:4" in res_script, "Criação e execução de script falhou!"
    print("✅ 6. Criação e execução de scripts sob demanda validada com sucesso!")

    # Limpar arquivo temporário de teste
    temp_file = PROJECT_ROOT / "teste_calc.py"
    if temp_file.exists():
        temp_file.unlink()

    print("=" * 60)
    print("TODOS OS TESTES FORAM APROVADOS COM SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    test_improvements()
