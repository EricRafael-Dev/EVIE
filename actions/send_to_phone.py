"""
actions/send_to_phone.py — Envio e compartilhamento de arquivos para o celular

Permite que a Evie envie qualquer arquivo (pequeno ou grande, de qualquer tamanho/tipo)
diretamente para o celular (Poco X7 / Android / iOS) através da rede local e Tailscale.
Gera link direto de alta velocidade e exibe QR Code para download instantâneo.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

# Diretório padrão de compartilhamento
def _get_uploads_dir() -> Path:
    candidates = [
        Path.home() / "Downloads" / "JARVIS Uploads",
        Path.home() / "Documents" / "JARVIS Uploads",
        BASE_DIR / "uploads",
    ]
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            return c
        except Exception:
            pass
    return BASE_DIR / "uploads"


def _format_size(size_bytes: int) -> str:
    """Formata bytes em KB, MB ou GB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _get_host_ips() -> dict[str, str]:
    """Retorna os IPs do Host (Tailscale e Rede Local)."""
    ips = {"tailscale": "100.73.5.37", "local": "127.0.0.1"}

    # Tenta ler do devices.json
    try:
        dev_path = BASE_DIR / "config" / "devices.json"
        if dev_path.exists():
            data = json.loads(dev_path.read_text(encoding="utf-8"))
            for dev in data.get("devices", []):
                if dev.get("role") == "host_server":
                    ips["tailscale"] = dev.get("tailscale_ip", ips["tailscale"])
    except Exception:
        pass

    # Tenta descobrir o IP da rede local
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        if not local_ip.startswith("127."):
            ips["local"] = local_ip
    except Exception:
        pass

    return ips


def _find_file(query: str) -> Optional[Path]:
    """Procura o arquivo solicitado no sistema em locais comuns com suporte a busca exata, aproximada e por tokens."""
    query = (query or "").strip()
    if not query:
        return None

    raw_path = Path(query)
    if raw_path.exists() and raw_path.is_file():
        return raw_path.resolve()

    clean_query = raw_path.name.lower()

    search_dirs = [
        BASE_DIR,
        BASE_DIR / "uploads",
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Pictures",
        Path.home() / "Pictures" / "JARVIS Screenshots",
        Path.home() / "Downloads" / "JARVIS Uploads",
    ]

    # Caso especial: print ou captura de tela
    if any(k in clean_query for k in ("print", "screenshot", "captura")):
        candidates = []
        for s_dir in [
            Path.home() / "Pictures" / "JARVIS Screenshots",
            Path.home() / "Pictures",
            BASE_DIR,
            BASE_DIR / "uploads",
        ]:
            if s_dir.exists():
                for ext in ("*.png", "*.jpg", "*.jpeg"):
                    candidates.extend(s_dir.glob(ext))
        if candidates:
            latest = max(candidates, key=lambda f: f.stat().st_mtime)
            return latest.resolve()

    # 1. Busca exata por nome
    for s_dir in search_dirs:
        if s_dir.exists():
            candidate = s_dir / raw_path.name
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

    # 2. Busca por substring completa
    for s_dir in search_dirs:
        if s_dir.exists():
            for f in s_dir.glob("*"):
                if f.is_file() and clean_query in f.name.lower():
                    return f.resolve()

    # 3. Busca por palavras-chave (tokenizada e imune a números de versão/stop words)
    stopwords = {
        "do", "da", "de", "dos", "das", "o", "a", "os", "as",
        "que", "ta", "pasta", "downloads", "me", "manda", "arquivo",
        "instalador", "no", "na", "em", "para", "pro", "pra"
    }
    words = [w for w in re.split(r"[\s._\-]+", clean_query) if len(w) > 1 and w not in stopwords]

    if words:
        matches = []
        for s_dir in search_dirs:
            if s_dir.exists():
                for f in s_dir.glob("*"):
                    if f.is_file():
                        fname_lower = f.name.lower()
                        score = sum(1 for w in words if w in fname_lower)
                        if score > 0:
                            matches.append((score, f.stat().st_mtime, f))
        if matches:
            matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return matches[0][2].resolve()

    return None


def _generate_qr_code(url: str, output_path: Path) -> bool:
    """Gera um QR Code apontando para a URL de download."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#00f0ff", back_color="#0a0e17")
        img.save(str(output_path))
        return True
    except Exception as e:
        print(f"[send_to_phone] Falha ao gerar QR Code: {e}")
        return False


def send_to_phone(
    parameters: dict | None = None,
    file_path: str = "",
    target_device: str = "poco-x7",
    player=None,
    **kwargs
) -> str:
    """
    Localiza o arquivo, disponibiliza no servidor HTTP para o celular,
    gera link de download e QR Code.
    Aceita chamada via parameters dict ou kwargs diretos.
    """
    params = parameters or {}
    target_path = str(params.get("file_path") or file_path or "").strip()
    target_dev = str(params.get("target_device") or target_device or "poco-x7").strip()

    if not target_path:
        return "Por favor, especifique o nome ou caminho do arquivo que deseja enviar para o celular."

    found = _find_file(target_path)
    if not found:
        return f"Não consegui encontrar o arquivo '{target_path}' no seu computador. Verifique o nome e tente novamente."


    uploads_dir = _get_uploads_dir()
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', found.name).strip(". ")
    dest_path = uploads_dir / safe_name

    # Se o arquivo não estiver na pasta de uploads, copia
    if found != dest_path:
        try:
            shutil.copy2(found, dest_path)
        except Exception as e:
            return f"Erro ao preparar o arquivo '{found.name}' para envio: {e}"

    file_size = dest_path.stat().st_size
    size_str = _format_size(file_size)
    ips = _get_host_ips()

    # Detecta se o servidor está rodando com SSL/TLS
    certs = BASE_DIR / "config" / "certs"
    is_ssl = (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()
    proto = "https" if is_ssl else "http"

    # URLs de download: porta 8000 (padrão) e porta 8002 (HTTP sem SSL se TLS ativo)
    tailscale_url = f"{proto}://{ips['tailscale']}:8000/download/{safe_name}"
    local_url = f"{proto}://{ips['local']}:8000/download/{safe_name}"
    http_alias_url = f"http://{ips['tailscale']}:8002/download/{safe_name}" if is_ssl else tailscale_url

    # Gera imagem do QR Code
    qr_filename = f"qr_{dest_path.stem}.png"
    qr_dest = uploads_dir / qr_filename
    qr_ok = _generate_qr_code(tailscale_url, qr_dest)

    # Dispara evento para o aplicativo no celular exibir o popup e iniciar o download
    download_broadcasted = False
    try:
        from dashboard.server import broadcast_file_download
        download_broadcasted = broadcast_file_download(
            safe_name, tailscale_url, file_size, size_str=size_str, http_url=http_alias_url
        )
    except Exception as e:
        print(f"[send_to_phone] Falha ao enviar broadcast para o app: {e}")


    # Abre a imagem do QR Code na tela apenas se o celular não recebeu o broadcast automaticamente
    if not download_broadcasted and qr_ok and sys.platform == "win32":
        try:
            os.startfile(str(qr_dest))
        except Exception:
            pass


    # Notifica no log do Jarvis
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"JARVIS: Arquivo '{safe_name}' ({size_str}) enviado para o celular: {tailscale_url}")
        except Exception:
            pass

    if download_broadcasted:
        res = (
            f"Arquivo '{safe_name}' ({size_str}) enviado com sucesso! "
            f"O download já foi iniciado automaticamente no seu aplicativo celular."
        )
    else:
        res = (
            f"Arquivo '{safe_name}' ({size_str}) pronto para baixar no seu celular! "
            f"O download foi disponibilizado no link direto via Tailscale: {tailscale_url}"
        )
    return res


# ── Declaração de Ferramenta para a Evie (Action Loader) ─────────────────────
TOOL = {
    "name": "send_to_phone",
    "description": (
        "Sends/transfers any file (photo, video, document, PDF, ZIP, code, or any download, "
        "whether small or very large) from the computer to the user's mobile phone (Poco X7 / Android). "
        "Generates a direct ultra-fast download link via Tailscale/Wi-Fi and opens a QR code on screen."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "The name or path of the file to send to the phone (e.g. 'relatorio.pdf', 'video.mp4', 'foto.png').",
            },
            "target_device": {
                "type": "STRING",
                "description": "Target device name, e.g. 'poco-x7' or 'celular'. Defaults to poco-x7.",
            },
        },
        "required": ["file_path"],
    },
    "handler": send_to_phone,
}
