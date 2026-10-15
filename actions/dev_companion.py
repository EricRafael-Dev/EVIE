from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import psutil
from google.genai import types

from agent_memory.router import aroute_generate, ROUTE_REASONING
from agent_memory.config import SECOND_BRAIN_DIR
from agent_memory.tools import MemoryToolManager
from core.confirm import request as confirm_request


# Padrões regex para detecção preventiva de credenciais expostas
SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z-_]{35}", "Chave Google API/Gemini"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub Personal Access Token"),
    (r"gho_[0-9A-Za-z]{36}", "GitHub OAuth Access Token"),
    (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "Chave Privada SSL/SSH"),
    (r"AKIA[0-9A-Z]{16}", "Chave AWS Access Key"),
    (r"sk-[a-zA-Z0-9]{32,}", "Chave de API OpenAI"),
]


def git_review_and_log_handler(parameters: dict, player=None, **_) -> str:
    """Revisa o diff e status do repositório Git, audita segredos e registra o avanço no Obsidian."""
    repo_path_str = str(parameters.get("repo_path", "")).strip()
    repo_dir = Path(repo_path_str).resolve() if repo_path_str else Path(__file__).resolve().parent.parent

    if not (repo_dir / ".git").exists():
        return f"O diretório '{repo_dir}' não é a raiz de um repositório Git."

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=10
        )
        status_out = status_proc.stdout.strip()
        if not status_out:
            return f"Repositório '{repo_dir.name}' está limpo, sem alterações pendentes."

        diff_proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=15
        )
        diff_out = diff_proc.stdout[:8000]  # Limita para não estourar

        # 1. Auditoria de Segredos e Chaves
        exposed_secrets = []
        for pat, label in SECRET_PATTERNS:
            if re.search(pat, diff_out):
                exposed_secrets.append(label)

        security_warning = ""
        if exposed_secrets:
            security_warning = (
                f"🚨 ALERTA CRÍTICO DE SEGURANÇA: Foi detectada a exposição de "
                f"{', '.join(set(exposed_secrets))} no git diff! "
                f"NÃO FAÇA COMMIT antes de remover esses segredos!\n\n"
            )

        # 2. Resumo Técnico via IA
        prompt = f"""Você é o Engenheiro Revisor de Código da Evie.
Analise o status e o diff das alterações abaixo:

STATUS DOS ARQUIVOS:
{status_out}

GIT DIFF:
\"\"\"
{diff_out}
\"\"\"

TAREFA:
1. Resuma as alterações em 2 ou 3 tópicos técnicos objetivos.
2. Sugira uma mensagem de commit semântico padronizada (ex: 'feat: ...', 'fix: ...', 'refactor: ...').
"""

        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(aroute_generate(
            route=ROUTE_REASONING,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
            timeout_ms=25_000,
        ))
        loop.close()
        review_summary = (getattr(res.response, "text", "") or "").strip()

        # 3. Registra na nota do projeto no Obsidian
        proj_note_path = f"projetos/{repo_dir.name}.md"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_block = (
            f"\n\n### 🚀 Avanço Git [{now_str}]\n"
            f"{review_summary}\n"
        )
        mgr = MemoryToolManager()
        mgr.update_or_create_note(proj_note_path, log_block, mode="append")

        full_display = f"{security_warning}RESUMO DO REPOSITÓRIO ({repo_dir.name}):\n\n{review_summary}"
        if player and hasattr(player, "show_content"):
            player.show_content(f"GIT REVIEW — {repo_dir.name}", full_display)

        return f"{security_warning}Revisão Git concluída para '{repo_dir.name}'. O resumo técnico e sugestão de commit foram registrados na nota do projeto."

    except Exception as e:
        return f"Erro ao revisar repositório Git: {e}"


def hardware_telemetry_check_handler(parameters: dict, player=None, **_) -> str:
    """Verifica CPU, RAM, Disco e GPU, listando processos ofensores com opção de encerramento via confirmação humana."""
    target_process = str(parameters.get("kill_process", "")).strip()

    # 1. Telemetria Geral
    cpu_percent = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Telemetria de GPU via nvidia-smi se disponível
    gpu_info = "N/A"
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        smi_proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=3
        )
        if smi_proc.returncode == 0 and smi_proc.stdout.strip():
            parts = [p.strip() for p in smi_proc.stdout.strip().split(",")]
            if len(parts) >= 5:
                gpu_info = f"{parts[0]} — GPU: {parts[1]}% | VRAM: {parts[3]}MB/{parts[4]}MB ({parts[2]}%)"
    except Exception:
        pass

    # 2. Processos Ofensores (Top 3 CPU e Top 3 RAM)
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top_cpu = sorted(procs, key=lambda x: x.get("cpu_percent") or 0.0, reverse=True)[:3]
    top_mem = sorted(procs, key=lambda x: x.get("memory_percent") or 0.0, reverse=True)[:3]

    cpu_lines = [f"- {p['name']} (PID: {p['pid']}): {p['cpu_percent']}% CPU" for p in top_cpu]
    mem_lines = [f"- {p['name']} (PID: {p['pid']}): {p['memory_percent']:.1f}% RAM" for p in top_mem]

    telemetry_report = (
        f"📊 Telemetria de Hardware:\n"
        f"• CPU: {cpu_percent}%\n"
        f"• RAM: {mem.percent}% ({mem.used // (1024**2):,} MB / {mem.total // (1024**2):,} MB)\n"
        f"• Disco: {disk.percent}% livre: {disk.free // (1024**3):,} GB\n"
        f"• GPU: {gpu_info}\n\n"
        f"🔥 Maiores Consumidores de CPU:\n" + "\n".join(cpu_lines) + "\n\n"
        f"💾 Maiores Consumidores de Memória:\n" + "\n".join(mem_lines)
    )

    if player and hasattr(player, "show_content"):
        player.show_content("TELEMETRIA DE HARDWARE", telemetry_report)

    # 3. Se o usuário solicitou encerrar um processo ofensor, dispara o gate humano seguro
    if target_process:
        def do_kill() -> str:
            killed = 0
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if target_process.lower() in (proc.info.get("name") or "").lower():
                        proc.terminate()
                        killed += 1
                except Exception:
                    pass
            return f"Encerrado(s) {killed} processo(s) correspondente(s) a '{target_process}'."

        confirm_msg = confirm_request(
            title=f"Encerrar processo '{target_process}'",
            detail=f"Deseja encerrar os processos correspondentes a '{target_process}' identificados na telemetria?",
            action=do_kill
        )
        return f"{telemetry_report}\n\n{confirm_msg}"

    return f"Telemetria realizada: CPU em {cpu_percent}%, RAM em {mem.percent}%, GPU: {gpu_info}. Relatório de consumidores exibido no HUD."


TOOL = {
    "name": "dev_companion",
    "description": "Ferramenta de engenharia e telemetria: audita repositórios Git contra vazamento de chaves/segredos, gera commits semânticos, monitora saúde de hardware (CPU/RAM/GPU) e permite encerrar processos ofensores com confirmação segura.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Ação a executar: 'git_review_and_log' ou 'hardware_telemetry_check'.",
            },
            "repo_path": {
                "type": "STRING",
                "description": "Caminho do repositório Git (opcional, usado em git_review_and_log).",
            },
            "kill_process": {
                "type": "STRING",
                "description": "Nome do processo ofensor a encerrar mediante confirmação do usuário (usado em hardware_telemetry_check).",
            },
        },
        "required": ["action"],
    },
    "handler": lambda parameters, player=None, **kw: (
        git_review_and_log_handler(parameters, player=player) if parameters.get("action") == "git_review_and_log"
        else hardware_telemetry_check_handler(parameters, player=player)
    ),
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
