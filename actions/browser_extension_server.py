"""
actions/browser_extension_server.py — Ponte WebSocket entre o JARVIS e a Extensão do Brave

Permite ao JARVIS controlar abas, extrair conteúdo, capturar telas e interagir
diretamente com as páginas no navegador Brave sem precisar de automação pesada
ou bloqueio de perfil (Playwright).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import websockets

logger = logging.getLogger("JARVIS.BraveBridge")

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"


class BraveController:
    """
    Controlador do Brave via WebSocket integrado com a extensão JARVIS.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server = None
        self._connected_clients: set[websockets.WebSocketServerProtocol] = set()
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._server_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Inicia o servidor WebSocket local para ouvir a extensão do Brave."""
        if self._running:
            return

        self._running = True
        self.server = await websockets.serve(self._handle_client, self.host, self.port)
        logger.info(f"[BraveController] Servidor iniciado em ws://{self.host}:{self.port}")
        print(f"[JARVIS Brave] Ponte WebSocket pronta em ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Encerra o servidor WebSocket."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        logger.info("[BraveController] Servidor finalizado.")

    @property
    def is_client_connected(self) -> bool:
        """Indica se a extensão do Brave está conectada no momento."""
        return len(self._connected_clients) > 0

    async def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Aguarda até que a extensão do Brave se conecte."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_client_connected:
                return True
            await asyncio.sleep(0.3)
        return False

    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Manipula conexão ativa com a extensão do Brave."""
        self._connected_clients.add(websocket)
        logger.info(f"[BraveController] Cliente conectado: {websocket.remote_address}")

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                    msg_id = data.get("id")

                    # Se for resposta para um comando enviado anteriormente
                    if msg_id and msg_id in self._pending_responses:
                        future = self._pending_responses.pop(msg_id)
                        if not future.done():
                            future.set_result(data)

                    # Se for handshake / identificação
                    elif data.get("type") == "client_hello":
                        logger.info(f"[BraveController] Extensão Brave identificada.")

                    # Resposta de Keep-Alive / Heartbeat
                    elif data.get("type") == "ping":
                        await websocket.send(json.dumps({"type": "pong", "timestamp": time.time()}))

                    elif data.get("type") == "pong":
                        pass

                except Exception as err:
                    logger.error(f"[BraveController] Erro ao processar mensagem do cliente: {err}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._connected_clients.discard(websocket)
            logger.info("[BraveController] Cliente desconectado.")

    async def send_command(self, action: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Envia um comando para a extensão e aguarda o resultado.
        """
        if not self._connected_clients:
            raise RuntimeError("Nenhuma extensão do Brave conectada. Verifique se o Brave está aberto com a extensão ativa.")

        client = next(iter(self._connected_clients))
        msg_id = f"cmd_{int(time.time() * 1000)}_{action}"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_responses[msg_id] = future

        message = {
            "id": msg_id,
            "action": action,
            "payload": payload or {}
        }

        await client.send(json.dumps(message))

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            self._pending_responses.pop(msg_id, None)
            raise TimeoutError(f"Tempo limite esgotado ({timeout}s) aguardando resposta para: {action}")

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS DE ALTO NÍVEL PARA O JARVIS
    # ─────────────────────────────────────────────────────────────────────────

    async def list_tabs(self) -> List[Dict[str, Any]]:
        """Retorna a lista de todas as guias abertas no Brave."""
        res = await self.send_command("list_tabs")
        return res.get("result", [])

    async def switch_tab(self, tab_id: Optional[int] = None, query: Optional[str] = None) -> bool:
        """Alterna para uma guia por ID ou por busca de título/URL."""
        res = await self.send_command("switch_tab", {"tabId": tab_id, "query": query})
        return res.get("ok", False)

    async def close_tabs(
        self,
        tab_ids: Optional[List[int]] = None,
        domain: Optional[str] = None,
        query: Optional[str] = None,
        duplicates_only: bool = False
    ) -> int:
        """
        Fecha guias com base em filtros ou lista de IDs. Retorna a contagem de fechadas.
        """
        payload = {
            "tabIds": tab_ids,
            "domain": domain,
            "query": query,
            "duplicatesOnly": duplicates_only
        }
        res = await self.send_command("close_tabs", payload)
        return res.get("closedCount", 0)

    async def create_tab(self, url: str = "about:blank", active: bool = True) -> Dict[str, Any]:
        """Abre uma nova guia no Brave."""
        res = await self.send_command("create_tab", {"url": url, "active": active})
        return res.get("tab", {})

    async def reload_tab(self, tab_id: Optional[int] = None) -> bool:
        """Recarrega uma guia (ou a ativa)."""
        res = await self.send_command("reload_tab", {"tabId": tab_id})
        return res.get("ok", False)

    async def extract_content(self, tab_id: Optional[int] = None, mode: str = "article") -> Dict[str, Any]:
        """
        Extrai dados da aba atual ou especificada.
        Modos: 'article' (Markdown limpo), 'metadata', 'links', 'tables', 'forms', 'selection'.
        """
        res = await self.send_command("extract_content", {"tabId": tab_id, "mode": mode})
        return res.get("data", {})

    async def capture_screenshot(self, tab_id: Optional[int] = None, save_path: Optional[str | Path] = None) -> bytes:
        """
        Captura a tela da aba ativa como imagem PNG.
        Se save_path for fornecido, grava o arquivo em disco.
        """
        res = await self.send_command("capture_screenshot", {"tabId": tab_id})
        data_url = res.get("screenshotBase64", "")
        if not data_url or "base64," not in data_url:
            raise ValueError("Falha ao capturar screenshot ou base64 inválido.")

        b64_data = data_url.split("base64,")[1]
        img_bytes = base64.b64decode(b64_data)

        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(img_bytes)

        return img_bytes

    async def click(self, selector: str, tab_id: Optional[int] = None) -> bool:
        """Clica em um elemento na página via seletor CSS."""
        res = await self.send_command("execute_action", {
            "tabId": tab_id,
            "domAction": "click",
            "selector": selector
        })
        return res.get("ok", False)

    async def fill(self, selector: str, value: str, tab_id: Optional[int] = None) -> bool:
        """Preenche um input/textarea na página."""
        res = await self.send_command("execute_action", {
            "tabId": tab_id,
            "domAction": "fill",
            "selector": selector,
            "value": value
        })
        return res.get("ok", False)

    async def scroll(self, value: str | int = "bottom", tab_id: Optional[int] = None) -> bool:
        """Rola a página ('top', 'bottom' ou número de pixels)."""
        res = await self.send_command("execute_action", {
            "tabId": tab_id,
            "domAction": "scroll",
            "value": value
        })
        return res.get("ok", False)

    async def control_media(self, media_action: str = "toggle") -> Dict[str, Any]:
        """
        Controla reprodução de mídia (YouTube, YouTube Music, etc.) em segundo plano.
        media_action: 'pause' | 'play' | 'toggle' | 'next' | 'mute'
        """
        return await self.send_command("control_media", {"mediaAction": media_action})


# Instância global reutilizável
brave_controller = BraveController()


# ─────────────────────────────────────────────────────────────────────────────
# MODO DE TESTE INTERATIVO / CLI
# ─────────────────────────────────────────────────────────────────────────────

async def _interactive_demo():
    print("=" * 60)
    print("  JARVIS BRAVE CONTROLLER — SERVIDOR WEBSOCKET")
    print("=" * 60)
    controller = BraveController()
    await controller.start()

    print("\nAguardando conexão da extensão do Brave...")
    print("Abra o Brave com a extensão instalada para testar.")

    connected = await controller.wait_for_connection(timeout=30.0)
    if not connected:
        print("⚠️ Nenhuma extensão conectada dentro do tempo limite.")
        await controller.stop()
        return

    print("✅ Extensão conectada com sucesso!")
    tabs = await controller.list_tabs()
    print(f"\nTotal de guias abertas no Brave: {len(tabs)}")
    for i, t in enumerate(tabs[:5], 1):
        print(f"  {i}. [{t.get('id')}] {t.get('title')} ({t.get('url')[:45]}...)")

    print("\nServidor permanecerá ouvindo. Pressione Ctrl+C para encerrar.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        await controller.stop()


if __name__ == "__main__":
    asyncio.run(_interactive_demo())
