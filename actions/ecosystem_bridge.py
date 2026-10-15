from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agent_memory.config import SECOND_BRAIN_DIR
from dashboard.server import get_dashboard_server

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def send_file_to_device_handler(parameters: dict, player=None, **_) -> str:
    """Envia arquivo para celular ou tablet gerando link temporário e push notification."""
    file_path_str = str(parameters.get("file_path", "")).strip()
    target_device = str(parameters.get("target_device", "mobile")).strip()

    target_path: Path | None = None

    if file_path_str:
        p = Path(file_path_str).resolve()
        if p.exists() and p.is_file():
            target_path = p
        else:
            return f"Arquivo especificado não foi encontrado: {file_path_str}"
    else:
        # Fallback 1: arquivo carregado no HUD
        if player:
            candidate = getattr(player, "_current_file", None) or getattr(player, "loaded_file", None)
            if candidate and Path(candidate).exists() and Path(candidate).is_file():
                target_path = Path(candidate).resolve()

        # Fallback 2: arquivo mais recente em uploads/ ou downloads/
        if target_path is None:
            recent_files: list[Path] = []
            for check_dir in [UPLOADS_DIR, Path.home() / "Downloads"]:
                if check_dir.exists():
                    try:
                        for item in check_dir.iterdir():
                            if item.is_file() and not item.name.startswith("."):
                                recent_files.append(item)
                    except Exception:
                        pass
            if recent_files:
                target_path = max(recent_files, key=lambda f: f.stat().st_mtime)

    if target_path is None or not target_path.exists():
        return "Nenhum arquivo ativo para enviar. Por favor informe o caminho do arquivo."

    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', target_path.name).strip(". ")
    dest_path = UPLOADS_DIR / safe_name

    try:
        if dest_path.resolve() != target_path.resolve():
            shutil.copy2(target_path, dest_path)
    except Exception as e:
        return f"Erro ao preparar arquivo para envio: {e}"

    file_size = dest_path.stat().st_size
    formatted_size = _format_size(file_size)

    from dashboard.server import broadcast_file_download
    from actions.send_to_phone import _get_host_ips
    ips = _get_host_ips()
    certs = BASE_DIR / "config" / "certs"
    is_ssl = (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()
    proto = "https" if is_ssl else "http"
    download_url = f"{proto}://{ips['tailscale']}:8000/download/{safe_name}"
    http_alias_url = f"http://{ips['tailscale']}:8002/download/{safe_name}" if is_ssl else download_url

    broadcast_file_download(safe_name, download_url, file_size, formatted_size, http_url=http_alias_url)

    if player and hasattr(player, "write_log"):
        player.write_log(f"SYS: Arquivo '{safe_name}' disponibilizado para {target_device}.")
    if player and hasattr(player, "show_content"):
        player.show_content(
            f"AIRDROP — {target_device.upper()}",
            f"Arquivo: **{safe_name}** ({formatted_size})\nLink: [{download_url}]({download_url})"
        )

    return (
        f"Arquivo '{safe_name}' ({formatted_size}) disponibilizado para {target_device}. "
        f"Link de transferência enviado via WebSocket."
    )


def compile_study_digest_handler(parameters: dict, player=None, **_) -> str:
    """Compila notas e leituras salvas nos últimos 7 dias em um resumo de leitura formatado para Kindle/Tablet."""
    days = int(parameters.get("days", 7))
    cutoff = datetime.now() - timedelta(days=days)

    collected_notes: list[tuple[str, str, datetime]] = []

    for sub_dir in ["leituras", "notas", "estudos"]:
        folder = SECOND_BRAIN_DIR / sub_dir
        if folder.exists() and folder.is_dir():
            for note_path in folder.glob("*.md"):
                try:
                    mtime = datetime.fromtimestamp(note_path.stat().st_mtime)
                    if mtime >= cutoff:
                        content = note_path.read_text(encoding="utf-8", errors="ignore")
                        title = note_path.stem.replace("_", " ").title()
                        collected_notes.append((title, content, mtime))
                except Exception:
                    pass

    if not collected_notes:
        return f"Nenhuma nota encontrada nos últimos {days} dias no Second Brain."

    collected_notes.sort(key=lambda x: x[2], reverse=True)

    digest_date = datetime.now().strftime("%Y-%m-%d")
    digest_md_lines = [
        f"# Compilado de Leituras e Estudos — {digest_date}",
        f"> Resumo das notas e artigos salvos no Second Brain nos últimos {days} dias.",
        f"> Total de itens compilados: {len(collected_notes)}",
        "",
        "## Índice de Tópicos",
    ]

    for title, _, mtime in collected_notes:
        anchor = re.sub(r'[^\w\-]', '', title.lower().replace(" ", "-"))
        digest_md_lines.append(f"- [{title}](#{anchor}) — *{mtime.strftime('%d/%m/%Y')}*")

    digest_md_lines.append("\n---\n")

    html_articles = []
    for title, content, mtime in collected_notes:
        clean_content = re.sub(r'^---[\s\S]*?---\n*', '', content)  # remove frontmatter
        digest_md_lines.append(f"## {title}")
        digest_md_lines.append(f"*Data: {mtime.strftime('%d/%m/%Y %H:%M')}*\n")
        digest_md_lines.append(clean_content.strip())
        digest_md_lines.append("\n---\n")

        html_articles.append(
            f"<article style='margin-bottom: 40px; page-break-after: always;'>"
            f"<h2 style='color:#1a202c;'>{title}</h2>"
            f"<p style='color:#718096; font-size:12px;'>Data: {mtime.strftime('%d/%m/%Y %H:%M')}</p>"
            f"<div style='line-height: 1.7; font-size: 16px;'>{clean_content.replace(chr(10), '<br>')}</div>"
            f"</article>"
        )

    digests_dir = SECOND_BRAIN_DIR / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)

    md_file = digests_dir / f"digest_{digest_date}.md"
    md_file.write_text("\n".join(digest_md_lines), encoding="utf-8")

    # Generate styled HTML suitable for Kindle, tablet and e-readers
    html_content = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Digest {digest_date}</title>"
        f"<style>"
        f"body {{ font-family: 'Georgia', serif; max-width: 800px; margin: 40px auto; padding: 20px; color: #2d3748; background: #fff; }}"
        f"h1 {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}"
        f"a {{ color: #3182ce; text-decoration: none; }}"
        f"@media print {{ body {{ max-width: 100%; }} }}"
        f"</style></head><body>"
        f"<h1>Compilado Semanal — {digest_date}</h1>"
        f"<p><em>{len(collected_notes)} notas copiladas para leitura calma.</em></p><hr>"
        f"{''.join(html_articles)}"
        f"</body></html>"
    )

    html_file = digests_dir / f"digest_{digest_date}.html"
    html_file.write_text(html_content, encoding="utf-8")

    # Make copy in uploads for instant mobile/Kindle download
    dest_html = UPLOADS_DIR / f"digest_{digest_date}.html"
    shutil.copy2(html_file, dest_html)

    from dashboard.server import broadcast_file_download
    from actions.send_to_phone import _get_host_ips
    ips = _get_host_ips()
    certs = BASE_DIR / "config" / "certs"
    is_ssl = (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()
    proto = "https" if is_ssl else "http"
    digest_url = f"{proto}://{ips['tailscale']}:8000/download/{dest_html.name}"
    http_alias_url = f"http://{ips['tailscale']}:8002/download/{dest_html.name}" if is_ssl else digest_url

    broadcast_file_download(dest_html.name, digest_url, dest_html.stat().st_size, http_url=http_alias_url)

    if player and hasattr(player, "show_content"):
        player.show_content(f"DIGEST — {digest_date}", f"Compilado salvo em `{md_file.name}`.\nLink para tablet: [{digest_url}]({digest_url})")

    return f"Compilado com {len(collected_notes)} notas gerado com sucesso em '{md_file.name}' e disponibilizado para leitura em '{dest_html.name}'."


TOOLS = [
    {
        "name": "send_file_to_device",
        "description": "Envia um arquivo local ou o documento atualmente aberto para o celular ou tablet via WebSocket / download temporário no ecossistema Evie.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Caminho absoluto ou relativo do arquivo a enviar. Se omitido, usa o arquivo atualmente aberto no HUD.",
                },
                "target_device": {
                    "type": "STRING",
                    "description": "Dispositivo de destino: 'mobile', 'tablet' ou 'kindle'.",
                },
            },
        },
        "handler": send_file_to_device_handler,
        "behavior": "BLOCKING",
        "scheduling": "WHEN_IDLE",
    },
    {
        "name": "compile_study_digest",
        "description": "Reúne notas e artigos salvos na semana no Second Brain, compila em um arquivo Markdown e HTML diagramado para leitura calma e envia link para Tablet/Kindle.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "days": {
                    "type": "INTEGER",
                    "description": "Quantidade de dias retroativos a compilar (padrão 7 dias).",
                },
            },
        },
        "handler": compile_study_digest_handler,
        "behavior": "BLOCKING",
        "scheduling": "WHEN_IDLE",
    },
]

TOOL = TOOLS[0]
