"""
plugins/brave_controller.py — Plugin do Brave para a Evie (Mark-LV / JARVIS)

Permite à Evie controlar o navegador Brave diretamente pela extensão:
- Alternar e listar guias abertas
- Fechar guias específicas ou fechar duplicadas
- Abrir novas guias
- Extrair texto limpo de artigos e páginas
- Tirar capturas de tela (screenshots)
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from actions.browser_extension_server import BraveController

# Configuração e metadados do Plugin para o Gerenciador de Plugins da Evie
PLUGIN = {
    "name": "brave_controller",
    "description": (
        "Controle total do navegador Brave e de mídias em segundo plano. "
        "Use SEMPRE que o usuário pedir para PAUSAR o YouTube ou vídeos ('pausa o youtube', 'pausar', 'pausa o vídeo'), "
        "DAR PLAY / DESPAUSAR ('despausa o youtube', 'continua o vídeo', 'dar play'), "
        "avançar ('próximo vídeo', 'pular vídeo'), alternar abas, fechar abas, fechar duplicadas, "
        "listar guias ou extrair dados."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Ação no Brave: "
                    "pause | play | toggle_media | next_video | mute | "
                    "list_tabs | switch_tab | close_tab | close_duplicates | open_tab | extract_content | screenshot | reload"
                ),
            },
            "query": {
                "type": "STRING",
                "description": "Termo de busca, título, site ou comando (ex: 'youtube', 'github', 'pausar').",
            },
            "url": {
                "type": "STRING",
                "description": "URL completa para abrir ou filtrar.",
            },
            "domain": {
                "type": "STRING",
                "description": "Domínio específico para fechar (ex: 'youtube.com').",
            },
            "tab_id": {
                "type": "INTEGER",
                "description": "ID numérico opcional de uma aba específica.",
            },
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "title": "Brave Browser Controller",
    "namespace": "brave_controller",
    "fields": [
        {
            "key": "ws_port",
            "type": "INT",
            "default": 8765,
            "label": "Porta WebSocket",
            "description": "Porta de comunicação local com a extensão do Brave.",
        }
    ],
}

# ── Servidor WebSocket em Segundo Plano ───────────────────────────────────────
_controller = BraveController()
_server_thread: Optional[threading.Thread] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def _start_background_server():
    """Garante que a ponte com a extensão do Brave esteja rodando."""
    global _server_thread, _loop
    if _server_thread and _server_thread.is_alive():
        return

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(_controller.start())
            _loop.run_forever()
        except OSError as e:
            if "10048" in str(e) or "already in use" in str(e).lower():
                pass
            else:
                raise

    _server_thread = threading.Thread(target=_run, daemon=True, name="BraveControllerServer")
    _server_thread.start()
    time.sleep(0.3)


# Inicia a ponte assim que o plugin for carregado
_start_background_server()


def _run_async(coro, timeout: float = 12.0) -> Any:
    _start_background_server()
    if not _loop or not _loop.is_running():
        raise RuntimeError("A ponte com a extensão do Brave não está em execução.")

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


# ── Função Principal de Execução do Plugin ────────────────────────────────────
def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Executado pela Evie ao receber comando de voz ou texto.
    """
    action = (parameters.get("action") or "").strip().lower()
    query = parameters.get("query")
    url = parameters.get("url")
    domain = parameters.get("domain")
    tab_id = parameters.get("tab_id")

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"JARVIS: [Brave] Executando '{action}' (query='{query}')")
        except Exception:
            pass

    if not _controller.is_client_connected:
        return (
            "A extensão do Brave não está conectada no momento. "
            "Abra o navegador Brave para que a conexão seja ativada."
        )

    try:
        # 0. CONTROLE DE MÍDIA / YOUTUBE (PAUSE / PLAY / NEXT / MUTE)
        if (
            action in ("pause", "pausar", "pause_youtube", "pausar_youtube", "stop")
            or (query and ("paus" in query.lower() or "para o video" in query.lower()))
        ):
            res = _run_async(_controller.control_media("pause"))
            if res.get("ok"):
                title = res.get("title", "YouTube")
                return f"Pausei o vídeo no Brave: {title}."
            return f"Não consegui pausar o vídeo: {res.get('error', 'Nenhum vídeo em reprodução encontrado')}."

        elif (
            action in ("play", "despausar", "dar_play", "play_youtube", "resume", "continuar")
            or (query and ("despaus" in query.lower() or "da play" in query.lower() or "dar play" in query.lower() or "continuar" in query.lower()))
        ):
            res = _run_async(_controller.control_media("play"))
            if res.get("ok"):
                title = res.get("title", "YouTube")
                return f"Dei play no vídeo no Brave: {title}."
            return f"Não consegui reproduzir o vídeo: {res.get('error', 'Nenhum vídeo encontrado')}."

        elif action in ("toggle_media", "toggle", "alternar_midia"):
            res = _run_async(_controller.control_media("toggle"))
            if res.get("ok"):
                state_str = "pausado" if res.get("state") == "paused" else "reproduzindo"
                return f"Vídeo no Brave alternado para: {state_str}."
            return f"Não foi possível alternar o vídeo: {res.get('error')}."

        elif action in ("next_video", "next", "proximo", "pular_video"):
            res = _run_async(_controller.control_media("next"))
            if res.get("ok"):
                return "Pulei para o próximo vídeo no YouTube."
            return f"Não consegui avançar o vídeo: {res.get('error')}."

        # 1. LISTAR GUIAS
        elif action in ("list_tabs", "listar_guias", "tabs", "abas"):
            tabs = _run_async(_controller.list_tabs())
            if not tabs:
                return "Não há guias abertas no Brave no momento."
            titulos = [f"• {t.get('title', 'Sem título')}" for t in tabs[:10]]
            res = f"Você tem {len(tabs)} guia(s) aberta(s) no Brave:\n" + "\n".join(titulos)
            if len(tabs) > 10:
                res += f"\n...e mais {len(tabs) - 10} outras."
            return res

        # 2. ALTERNAR GUIA
        elif action in ("switch_tab", "alternar_guia", "ir_para_guia", "switch"):
            target_query = query or url or ""
            if not target_query and not tab_id:
                return "Diga o nome ou link da guia que deseja alternar."

            ok = _run_async(_controller.switch_tab(tab_id=tab_id, query=target_query))
            if ok:
                return f"Alternei para a guia correspondente a '{target_query}' no Brave."
            return f"Não encontrei nenhuma guia aberta correspondente a '{target_query}'."

        # 3. FECHAR DUPLICADAS
        elif action in ("close_duplicates", "fechar_duplicadas", "limpar_duplicadas"):
            count = _run_async(_controller.close_tabs(duplicates_only=True))
            if count > 0:
                return f"Fechei {count} guia(s) duplicada(s) no Brave com sucesso."
            return "Nenhuma guia duplicada foi encontrada no Brave."

        # 4. FECHAR GUIAS ESPECÍFICAS OU POR DOMÍNIO
        elif action in ("close_tab", "close_tabs", "fechar_guia", "fechar_abas", "close"):
            target_query = query or domain or ""
            if not target_query and not tab_id:
                return "Por favor, diga qual guia ou site deseja fechar."

            count = _run_async(_controller.close_tabs(tab_ids=[tab_id] if tab_id else None, query=target_query, domain=domain))
            if count > 0:
                return f"Fechei {count} guia(s) correspondente(s) a '{target_query}' no Brave."
            return f"Não encontrei nenhuma guia aberta com '{target_query}' para fechar."

        # 5. ABRIR NOVA GUIA
        elif action in ("open_tab", "new_tab", "nova_guia", "abrir_guia"):
            target_url = url or query or "https://google.com"
            if not target_url.startswith("http://") and not target_url.startswith("https://"):
                target_url = "https://" + target_url

            tab = _run_async(_controller.create_tab(url=target_url))
            return f"Abri uma nova guia com o site {target_url} no Brave."

        # 6. EXTRAIR CONTEÚDO DA PÁGINA
        elif action in ("extract_content", "extrair_conteudo", "ler_pagina", "resumir_pagina"):
            mode = "article"
            if query and "tabela" in query.lower():
                mode = "tables"
            elif query and "link" in query.lower():
                mode = "links"

            data = _run_async(_controller.extract_content(mode=mode))
            if mode == "article":
                md = data.get("markdown", "")
                title = data.get("metadata", {}).get("title", "Página")
                if not md:
                    return f"Não consegui extrair o texto principal de '{title}'."
                return f"Conteúdo de '{title}':\n\n{md[:1500]}"
            else:
                return f"Dados extraídos ({mode}):\n{str(data)[:1000]}"

        # 7. SCREENSHOT
        elif action in ("screenshot", "captura_de_tela", "print", "tirar_print"):
            screenshots_dir = Path.home() / "Pictures" / "JARVIS Screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            filename = screenshots_dir / f"brave_screenshot_{int(time.time())}.png"
            _run_async(_controller.capture_screenshot(save_path=filename))
            return f"Tirei um print da tela do Brave e salvei em: {filename}"

        # 8. RECARREGAR
        elif action in ("reload", "recarregar_guia", "atualizar"):
            _run_async(_controller.reload_tab(tab_id=tab_id))
            return "A guia ativa no Brave foi recarregada com sucesso."

        else:
            return f"Ação '{action}' não reconhecida. Suportadas: list_tabs, switch_tab, close_tab, close_duplicates, open_tab, extract_content, screenshot."

    except Exception as exc:
        return f"Erro ao executar comando no Brave: {exc}"
