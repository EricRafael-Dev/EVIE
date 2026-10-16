# actions/terminal_cmd.py
"""
actions/terminal_cmd.py — Native CMD / Terminal and Script Execution for Mark-LV / Evie.

Enables the assistant to:
1. Execute terminal commands (CMD, PowerShell, Git, Python, pip, etc.) directly.
2. Automate Git workflows (git init, git status, git add, git commit, git push, git pull).
3. Create and execute custom scripts on demand (e.g. generate a full GUI calculator and run it).
4. Enforce user approval via core.confirm for sensitive commands (git push, destructive operations).
"""

from __future__ import annotations

import os
import sys
import subprocess
import platform
import shlex
import time
from pathlib import Path
from typing import Optional, Callable

from core import confirm

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

def _get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_PROJECT_ROOT = _get_project_root()

def _resolve_working_dir(raw: str | None = None) -> Path:
    """Resolve shorthand or path to an absolute existing directory."""
    if not raw or raw.strip() in ("", ".", "here", "current", "project", "workspace", "mark-lv", "mark-lv-main"):
        return _PROJECT_ROOT

    s = raw.strip().strip('"').strip("'").lower()

    # Detect OneDrive and system user paths
    user_home = Path.home()
    onedrive = None
    for cand in [user_home / "OneDrive", user_home / "OneDrive - Personal"]:
        if cand.exists():
            onedrive = cand
            break

    shortcuts: dict[str, Path] = {
        "home": user_home,
        "desktop": user_home / "Desktop",
        "downloads": user_home / "Downloads",
        "documents": user_home / "Documents",
        "project": _PROJECT_ROOT,
        "workspace": _PROJECT_ROOT,
        "root": _PROJECT_ROOT,
    }

    if onedrive:
        shortcuts["onedrive"] = onedrive
        if (onedrive / "Desktop").exists() or (onedrive / "Área de Trabalho").exists():
            shortcuts["desktop"] = onedrive / "Desktop" if (onedrive / "Desktop").exists() else onedrive / "Área de Trabalho"
        if (onedrive / "Documents").exists() or (onedrive / "Documentos").exists():
            shortcuts["documents"] = onedrive / "Documents" if (onedrive / "Documents").exists() else onedrive / "Documentos"

    # Portuguese shortcuts
    shortcuts["área de trabalho"] = shortcuts["desktop"]
    shortcuts["area de trabalho"] = shortcuts["desktop"]
    shortcuts["documentos"] = shortcuts["documents"]
    shortcuts["transferencias"] = shortcuts["downloads"]
    shortcuts["transferências"] = shortcuts["downloads"]

    if s in shortcuts and shortcuts[s].exists():
        return shortcuts[s]

    # Try resolving path string
    try:
        p = Path(os.path.expandvars(os.path.expanduser(raw.strip().strip('"').strip("'"))))
        if p.is_dir() and p.exists():
            return p.resolve()
        # If relative to project
        proj_p = _PROJECT_ROOT / p
        if proj_p.is_dir() and proj_p.exists():
            return proj_p.resolve()
        # If relative to user home
        home_p = user_home / p
        if home_p.is_dir() and home_p.exists():
            return home_p.resolve()
    except Exception:
        pass

    return _PROJECT_ROOT


# Commands that should always ask confirmation unless explicitly allowed
_SENSITIVE_PATTERNS = [
    "git push",
    "git reset --hard",
    "git clean -f",
    "rmdir /s",
    "del /s",
    "rm -rf",
    "format ",
    "drop table",
    "taskkill /f",
    "shutdown",
]

def _is_sensitive_command(cmd: str) -> bool:
    c = cmd.lower()
    return any(p in c for p in _SENSITIVE_PATTERNS)


def _detect_and_auto_heal(
    command: str,
    cwd: Path,
    returncode: int,
    stdout: str,
    stderr: str,
    shell_type: str = "powershell",
    timeout: int = 60,
    depth: int = 0
) -> tuple[bool, str]:
    """
    Diagnose command failures proactively and execute corrective alternatives.
    Returns (healed: bool, healing_log: str).
    """
    if returncode == 0 or depth >= 2:
        return False, ""

    combined_err = f"{stdout}\n{stderr}".lower()
    cmd_lower = command.strip().lower()
    healing_steps = []

    # 1. Git push: No upstream branch
    # "fatal: The current branch <branch> has no upstream branch."
    # "To push the current branch and set the remote as upstream, use: git push --set-upstream origin <branch>"
    if "no upstream branch" in combined_err or "set-upstream" in combined_err:
        # Determine current branch
        branch = "main"
        try:
            b_res = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            out_b = (b_res.stdout or "").strip()
            if out_b:
                branch = out_b
        except Exception:
            pass

        fix_cmd = f"git push --set-upstream origin {branch}"
        healing_steps.append(f"Detectado branch sem upstream no Git. Executando correcao automatica: '{fix_cmd}'")
        res_fix = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", fix_cmd] if _OS == "Windows" else ["/bin/bash", "-c", fix_cmd],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        if res_fix.returncode == 0:
            return True, f"-> Auto-recuperacao bem-sucedida: branch '{branch}' configurada no upstream e enviada para o remoto com sucesso!\n{res_fix.stdout or res_fix.stderr}"
        else:
            healing_steps.append(f"Tentativa de upstream retornou erro: {res_fix.stderr or res_fix.stdout}")

    # 2. Git push rejected (non-fast-forward / fetch first)
    if "fetch first" in combined_err or "[rejected]" in combined_err or "non-fast-forward" in combined_err:
        fix_cmd = "git pull --rebase"
        healing_steps.append(f"Detectadas alteracoes remotas pendentes. Executando 'git pull --rebase'...")
        p_res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", fix_cmd] if _OS == "Windows" else ["/bin/bash", "-c", fix_cmd],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        if p_res.returncode == 0:
            # Re-try the original push
            retry_res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command] if _OS == "Windows" else ["/bin/bash", "-c", command],
                cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
            )
            if retry_res.returncode == 0:
                return True, f"-> Auto-recuperacao bem-sucedida: git pull --rebase sincronizado e push concluido com sucesso!\n{retry_res.stdout or retry_res.stderr}"
            else:
                healing_steps.append(f"Push apos rebase falhou: {retry_res.stderr}")
        else:
            healing_steps.append(f"Rebase falhou: {p_res.stderr}")

    # 3. Git commit without staged files
    if ("nothing added to commit" in combined_err or "no changes added to commit" in combined_err) and "git commit" in cmd_lower:
        fix_cmd = "git add -A"
        healing_steps.append("Detectado commit sem arquivos staged. Executando 'git add -A' e reexecutando commit...")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", fix_cmd] if _OS == "Windows" else ["/bin/bash", "-c", fix_cmd],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        retry_res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command] if _OS == "Windows" else ["/bin/bash", "-c", command],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        if retry_res.returncode == 0:
            return True, f"-> Auto-recuperacao bem-sucedida: arquivos adicionados com 'git add -A' e commit realizado!\n{retry_res.stdout}"

    # 4. Git SSH: Host key verification failed
    if "host key verification failed" in combined_err or "permission denied (publickey)" in combined_err:
        # Check if the host key can be added automatically
        healing_steps.append("Detectada falha de chave de host SSH. Registrando chave de host do GitHub via StrictHostKeyChecking...")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "ssh -o StrictHostKeyChecking=accept-new -T git@github.com"],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        # Check if the remote is a dummy / placeholder URL
        try:
            r_res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            remote_url = (r_res.stdout or "").strip()
            if "username/repository.git" in remote_url or "usuario/repositorio" in remote_url:
                healing_steps.append(
                    f"Aviso crítico: A URL do seu repositório remoto está configurada como '{remote_url}' (placeholder de exemplo). "
                    "Para fazer o push no GitHub, configure seu repositório real com: git remote set-url origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git"
                )
        except Exception:
            pass

    # 5. Missing python module during script execution
    # "ModuleNotFoundError: No module named 'xyz'"
    import re
    mod_match = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", f"{stdout}\n{stderr}")
    if mod_match:
        missing_module = mod_match.group(1).strip()
        pip_cmd = f"{sys.executable} -m pip install {missing_module}"
        healing_steps.append(f"Detectado modulo Python ausente ('{missing_module}'). Instalando via '{pip_cmd}'...")
        pip_res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", pip_cmd] if _OS == "Windows" else ["/bin/bash", "-c", pip_cmd],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        if pip_res.returncode == 0:
            # Retry script
            retry_res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command] if _OS == "Windows" else ["/bin/bash", "-c", command],
                cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
            )
            if retry_res.returncode == 0:
                return True, f"-> Auto-recuperacao bem-sucedida: pacote '{missing_module}' instalado e comando finalizado com sucesso!\n{retry_res.stdout}"

    # If steps were attempted but couldn't completely resolve it
    if healing_steps:
        return False, "Diagnostico proativo tentado:\n" + "\n".join(healing_steps)

    return False, ""


def _run_command_sync(
    command: str,
    cwd: Path,
    shell_type: str = "powershell",
    timeout: int = 60
) -> str:
    """Execute command synchronously, capture output, and autonomously heal common failures."""
    try:
        if not cwd.exists():
            cwd.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        if _OS == "Windows":
            cmd_strip = command.strip()
            if shell_type.lower() == "cmd":
                args = ["cmd.exe", "/c", command]
            else:
                ps_cmd = command
                if ps_cmd.startswith('"') or ps_cmd.startswith("'"):
                    ps_cmd = f"& {ps_cmd}"
                args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        else:
            args = ["/bin/bash", "-c", command]

        res = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env
        )

        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()

        # Autonomous healing check on error
        if res.returncode != 0:
            healed, heal_details = _detect_and_auto_heal(
                command=command,
                cwd=cwd,
                returncode=res.returncode,
                stdout=stdout,
                stderr=stderr,
                shell_type=shell_type,
                timeout=timeout
            )
            if healed:
                return (
                    f"[Concluído com Auto-Recuperação Proativa]\n"
                    f"Comando original: {command}\n"
                    f"Ação corretiva executada:\n{heal_details}"
                )
            elif heal_details:
                stderr += f"\n\n[Diagnóstico Proativo]:\n{heal_details}"

        output_parts = []
        if stdout:
            output_parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            output_parts.append(f"STDERR:\n{stderr}")

        result_text = "\n\n".join(output_parts) if output_parts else "(Comando executado sem mensagens de saída)"
        status = f"Concluído (Exit code: {res.returncode})" if res.returncode == 0 else f"Aviso/Erro (Exit code: {res.returncode})"

        return f"[{status}] Diretório: {cwd}\n{result_text}"

    except subprocess.TimeoutExpired:
        return f"[Erro: Timeout] O comando excedeu o tempo limite de {timeout}s: {command}"
    except Exception as e:
        return f"[Erro ao executar comando]: {e}"


def _launch_gui_process(script_path: Path, cwd: Path) -> str:
    """Launch interactive GUI script (e.g. Tkinter calculator) without blocking."""
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        creationflags = 0
        if _OS == "Windows":
            creationflags = subprocess.CREATE_NEW_CONSOLE

        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(cwd),
            env=env,
            creationflags=creationflags
        )
        return (
            f"✅ Aplicativo iniciado com sucesso!\n"
            f"Arquivo: {script_path.name}\n"
            f"Local: {script_path.parent}\n"
            f"Status: A janela gráfica foi aberta e está em execução para o usuário."
        )
    except Exception as e:
        return f"Erro ao iniciar aplicativo gráfico: {e}"


def terminal_cmd(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = str(params.get("action", "execute")).lower().strip()
    command = str(params.get("command", "")).strip()
    script_name = str(params.get("script_name", "")).strip()
    code = str(params.get("code", "")).strip()
    raw_cwd = params.get("working_dir")
    shell_type = str(params.get("shell_type", "powershell")).lower().strip()
    timeout = int(params.get("timeout", 60))
    require_approval = bool(params.get("require_approval", False))
    is_gui = bool(params.get("is_gui", False))

    cwd = _resolve_working_dir(raw_cwd)

    if player:
        try:
            player.write_log(f"[CMD] {action}: {command or script_name} (in {cwd.name})")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # ACTION: CREATE AND RUN SCRIPT (e.g., calculator, automation)
    # ─────────────────────────────────────────────────────────────────────────
    if action in ("create_and_run", "run_script", "script"):
        if not code:
            # If code is inside command or instruction
            code = command or params.get("content", "")
        if not code:
            return "Nenhum código fornecido para criar e executar o script."

        if not script_name:
            # Infer name
            if "calc" in code.lower() or "calculator" in code.lower():
                script_name = "calculadora.py"
            else:
                script_name = f"script_{int(time.time())}.py"

        if not script_name.endswith((".py", ".ps1", ".bat", ".sh", ".js")):
            script_name += ".py"

        target_file = cwd / script_name

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            # Clean markdown code blocks if the model passed them
            clean_code = code.strip()
            if clean_code.startswith("```"):
                lines = clean_code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_code = "\n".join(lines).strip()

            target_file.write_text(clean_code, encoding="utf-8")
        except Exception as e:
            return f"Falha ao salvar script em {target_file}: {e}"

        # Detect if it's a GUI application
        lower_code = clean_code.lower()
        gui_keywords = ["tkinter", "pyqt", "pyside", "customtkinter", "pygame", "turtle", "mainloop()"]
        if is_gui or any(k in lower_code for k in gui_keywords):
            return _launch_gui_process(target_file, cwd)
        else:
            # Run via python interpreter directly and capture output
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                res = subprocess.run(
                    [sys.executable, str(target_file)],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    env=env
                )
                stdout = (res.stdout or "").strip()
                stderr = (res.stderr or "").strip()
                output_parts = []
                if stdout:
                    output_parts.append(f"STDOUT:\n{stdout}")
                if stderr:
                    output_parts.append(f"STDERR:\n{stderr}")
                result_text = "\n\n".join(output_parts) if output_parts else "(Script executado com sucesso sem mensagens no console)"
                status = f"Concluído (Exit code: {res.returncode})" if res.returncode == 0 else f"Aviso/Erro (Exit code: {res.returncode})"
                return f"[{status}] Script: {target_file.name}\n{result_text}"
            except subprocess.TimeoutExpired:
                return f"[Erro: Timeout] O script excedeu o tempo limite de {timeout}s: {script_name}"
            except Exception as e:
                return f"[Erro ao executar script]: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # ACTION: EXECUTE COMMAND (Git, PowerShell, CMD)
    # ─────────────────────────────────────────────────────────────────────────
    if not command:
        return "Nenhum comando especificado para o terminal."

    # Check if confirmation is required
    needs_confirm = require_approval or _is_sensitive_command(command)

    if needs_confirm:
        if confirm.pending_title():
            return "Já existe uma confirmação aguardando resposta na tela. Por favor, responda à anterior primeiro."

        def _do_execute() -> str:
            res = _run_command_sync(command, cwd, shell_type=shell_type, timeout=timeout)
            if player:
                try:
                    player.write_log(f"[CMD Confirmed]: {command}")
                except Exception:
                    pass
            return res

        return confirm.request(
            key=f"cmd_{int(time.time())}",
            title="⚠ Executar Comando Terminal",
            detail=f"Comando: {command}\nDiretório: {cwd}",
            run=_do_execute
        )

    # Execute directly
    return _run_command_sync(command, cwd, shell_type=shell_type, timeout=timeout)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "terminal_cmd",
    "description": (
        "Native terminal and command execution system. "
        "Run CMD, PowerShell, and Git commands (e.g. 'git init', 'git status', 'git push', 'git commit -m \"...\"', 'dir', 'python ...'), "
        "or create and immediately execute scripts like desktop calculators, utilities, or automation scripts. "
        "Sensitive commands like git push or destructive actions automatically prompt for user screen approval."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "execute | create_and_run"
            },
            "command": {
                "type": "STRING",
                "description": "The command line string to run (e.g. 'git status', 'git push origin main', 'python app.py')"
            },
            "code": {
                "type": "STRING",
                "description": "Full source code when creating and running a script (e.g. full Python code for a calculator)"
            },
            "script_name": {
                "type": "STRING",
                "description": "File name for the script (e.g. 'calculadora.py')"
            },
            "working_dir": {
                "type": "STRING",
                "description": "Directory to run in. Use shortcuts: 'project' (Mark-LV repo), 'desktop', 'documents', or an absolute path"
            },
            "shell_type": {
                "type": "STRING",
                "description": "powershell | cmd (default: powershell)"
            },
            "require_approval": {
                "type": "BOOLEAN",
                "description": "Set to true to ask user approval via screen banner before executing"
            },
            "is_gui": {
                "type": "BOOLEAN",
                "description": "Set to true if the script opens a window (e.g. Tkinter/PyQt calculator) so it launches without hanging"
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Max timeout in seconds (default: 60)"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": terminal_cmd,
}
