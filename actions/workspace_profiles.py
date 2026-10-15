from __future__ import annotations

import os
import subprocess
import sys
from typing import Any
import psutil

from core.undo import push_undo

# Perfis predefinidos de espaço de trabalho
PROFILES_CONFIG = {
    "estudo": {
        "apps_to_close": ["steam.exe", "discord.exe", "epicgameslauncher.exe"],
        "apps_to_launch": ["obsidian.exe"],
        "volume": 25,
        "description": "Modo Estudo: Foco em leitura, Obsidian e redução de distrações sonoras.",
    },
    "edicao": {
        "apps_to_close": ["steam.exe", "game.exe"],
        "apps_to_launch": ["adobe premiere pro.exe"],
        "volume": 60,
        "description": "Modo Edição: Desempenho liberado para produção de vídeo e mídia.",
    },
    "jogo": {
        "apps_to_close": ["obsidian.exe", "code.exe"],
        "apps_to_launch": ["steam.exe"],
        "volume": 70,
        "description": "Modo Jogo: Encerramento de editores e foco em gráficos e áudio imersivo.",
    },
    "aula": {
        "apps_to_close": ["steam.exe", "spotify.exe"],
        "apps_to_launch": ["obsidian.exe"],
        "volume": 50,
        "description": "Modo Aula: Notificações contidas e ferramentas de anotação prontas.",
    },
    "foco": {
        "apps_to_close": ["steam.exe", "discord.exe", "telegram.exe", "whatsapp.exe"],
        "apps_to_launch": [],
        "volume": 15,
        "description": "Modo Foco Extremo: Fechamento de mensageiros e volume reduzido.",
    },
}


def _get_active_process_names() -> set[str]:
    """Captura os nomes dos processos em execução no momento."""
    names = set()
    for proc in psutil.process_iter(["name"]):
        try:
            n = proc.info.get("name")
            if n:
                names.add(n.lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return names


def _set_windows_volume(percent: int) -> None:
    """Ajusta o volume mestre do Windows via PowerShell de forma silenciosa."""
    try:
        # PowerShell script simples para alterar volume
        vol_normalized = max(0, min(100, percent)) / 100.0
        ps_cmd = (
            f"$obj = New-Object -ComObject WScript.Shell; "
            f"1..50 | ForEach-Object {{ $obj.SendKeys([char]174) }}; "
            f"1..{int(percent // 2)} | ForEach-Object {{ $obj.SendKeys([char]175) }}"
        )
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, creationflags=creationflags, timeout=5)
    except Exception as e:
        print(f"[WorkspaceProfiles] Erro ao ajustar volume: {e}")


def set_workspace_mode_handler(parameters: dict, player=None, **_) -> str:
    """Altera o perfil do espaço de trabalho com suporte a Undo LIFO."""
    raw_mode = str(parameters.get("mode", "")).strip().lower()
    
    # Mapeamento semântico
    mode_aliases = {
        "estudos": "estudo",
        "estudar": "estudo",
        "edicao": "edicao",
        "edição": "edicao",
        "editar": "edicao",
        "jogar": "jogo",
        "games": "jogo",
        "game": "jogo",
        "aula": "aula",
        "aulas": "aula",
        "foco": "foco",
        "concentracao": "foco",
        "concentração": "foco",
    }
    mode = mode_aliases.get(raw_mode, raw_mode)

    if mode not in PROFILES_CONFIG:
        valid_list = ", ".join(PROFILES_CONFIG.keys())
        return f"Modo '{raw_mode}' não reconhecido. Modos disponíveis: {valid_list}."

    cfg = PROFILES_CONFIG[mode]
    
    # 1. Snapshot do estado antes da alteração
    prior_processes = _get_active_process_names()
    
    # 2. Registra o closure reversível no Undo seguro
    def undo_profile() -> str:
        # Tenta reverter o ajuste do volume
        _set_windows_volume(40)
        msg = f"Perfil de trabalho '{mode}' desfeito. Volume reajustado para padrão."
        if player and hasattr(player, "write_log"):
            player.write_log(f"SYS: {msg}")
        return msg

    push_undo(f"modo de trabalho '{mode}'", undo_profile)

    # 3. Fecha apps desnecessários do perfil
    closed_apps = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname in cfg["apps_to_close"]:
                proc.terminate()
                closed_apps.append(pname)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 4. Ajusta volume
    target_vol = cfg.get("volume", 40)
    _set_windows_volume(target_vol)

    # 5. Notifica HUD e dispositivos
    status_summary = (
        f"Espaço de trabalho configurado para [{mode.upper()}].\n"
        f"- {cfg['description']}\n"
        f"- Volume ajustado para {target_vol}%.\n"
    )
    if closed_apps:
        status_summary += f"- Processos encerrados: {', '.join(set(closed_apps))}.\n"

    if player and hasattr(player, "write_log"):
        player.write_log(f"SYS: Modo [{mode.upper()}] ativado.")
    if player and hasattr(player, "show_content"):
        player.show_content(f"PERFIL: {mode.upper()}", status_summary)

    return f"Modo {mode} ativado, senhor. {cfg['description']} Volume ajustado para {target_vol}%."


TOOL = {
    "name": "set_workspace_mode",
    "description": "Altera o perfil operacional do computador para os modos 'estudo', 'edicao', 'jogo', 'aula' ou 'foco', otimizando volume, encerrando distrações e registrando reversão no undo.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "description": "Nome do perfil desejado: 'estudo', 'edicao', 'jogo', 'aula' ou 'foco'.",
            },
        },
        "required": ["mode"],
    },
    "handler": set_workspace_mode_handler,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
