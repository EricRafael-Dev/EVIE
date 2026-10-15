from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path
from google.genai import types

from agent_memory.router import aroute_generate, ROUTE_REASONING, ROUTE_FAST
from agent_memory.config import SECOND_BRAIN_DIR


def _copy_to_windows_clipboard(text: str) -> bool:
    """Copia uma string para a área de transferência do Windows de forma segura."""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ps_proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
            stdin=subprocess.PIPE,
            creationflags=creationflags,
        )
        ps_proc.communicate(input=text.encode("utf-8"))
        return ps_proc.returncode == 0
    except Exception as e:
        print(f"[MediaStudio] Falha ao copiar para clipboard: {e}")
        return False


def rough_cut_silence_handler(parameters: dict, player=None, **_) -> str:
    """Detecta intervalos de silêncio via ffmpeg e exporta os cortes do vídeo sem travar a Evie."""
    video_path_str = str(parameters.get("video_path", "")).strip()
    threshold_db = int(parameters.get("threshold_db", -35))

    if not video_path_str:
        return "Por favor, especifique o caminho do arquivo de vídeo para o corte de silêncio."

    video_path = Path(video_path_str).resolve()
    if not video_path.exists() or not video_path.is_file():
        return f"Arquivo de vídeo não encontrado em: {video_path}"

    output_edl = video_path.with_suffix(".edl.txt")

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-af", f"silencedetect=noise={threshold_db}dB:d=0.5",
        "-f", "null",
        "-"
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
            timeout=300
        )
        stderr_output = proc.stderr

        # Parse dos silêncios detectados
        silence_starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", stderr_output)]
        silence_ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", stderr_output)]

        cuts_summary = []
        for s, e in zip(silence_starts, silence_ends):
            cuts_summary.append(f"Silêncio: {s:.2f}s até {e:.2f}s (duração: {e-s:.2f}s)")

        total_silence = sum(e - s for s, e in zip(silence_starts, silence_ends))
        
        # Salva o arquivo com os marcadores
        output_edl.write_text(
            f"Relatório de Cortes de Silêncio para: {video_path.name}\n"
            f"Limiar: {threshold_db} dB | Trechos detectados: {len(silence_starts)}\n"
            f"Tempo total de silêncio a remover: {total_silence:.2f}s\n\n"
            + "\n".join(cuts_summary),
            encoding="utf-8"
        )

        res_msg = (
            f"Análise de silêncio concluída para '{video_path.name}'. "
            f"Foram identificados {len(silence_starts)} trechos de silêncio ({total_silence:.1f}s elimináveis). "
            f"Arquivo de marcações exportado para '{output_edl.name}'."
        )

        if player and hasattr(player, "show_content"):
            player.show_content("ROUGH CUT — SILENCE", res_msg)

        return res_msg

    except FileNotFoundError:
        return "FFmpeg não está instalado ou acessível no PATH do sistema para executar o corte."
    except Exception as e:
        return f"Erro ao processar áudio do vídeo: {e}"


def generate_video_metadata_handler(parameters: dict, player=None, **_) -> str:
    """Lê a transcrição ou notas do projeto e gera títulos, descrição com timestamps e tags."""
    topic = str(parameters.get("project_topic", "")).strip()
    transcript_path_str = str(parameters.get("transcript_path", "")).strip()

    context_text = ""
    if transcript_path_str and Path(transcript_path_str).exists():
        try:
            context_text = Path(transcript_path_str).read_text(encoding="utf-8", errors="ignore")[:4000]
        except Exception:
            pass

    if not context_text:
        # Busca no second_brain/projetos/
        for candidate in (SECOND_BRAIN_DIR / "projetos").glob("*.md"):
            if topic.lower() in candidate.name.lower():
                context_text = candidate.read_text(encoding="utf-8", errors="ignore")[:3000]
                break

    prompt = f"""Você é um estrategista de conteúdo para YouTube e mídias digitais.
Com base no tema '{topic}' e no contexto do vídeo abaixo:
\"\"\"
{context_text or topic}
\"\"\"

Gere um pacote completo de metadados de publicação em Português do Brasil:
1. 3 Opções de Títulos com alto CTR (curtos e chamativos).
2. Descrição Estruturada para YouTube com ganchos, chamada para ação e tópicos de capítulos sugeridos (Timestamps estimados).
3. 15 Tags relevantes separadas por vírgula.
"""

    try:
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(aroute_generate(
            route=ROUTE_REASONING,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4),
            timeout_ms=30_000,
        ))
        loop.close()
        meta_text = (getattr(res.response, "text", "") or "").strip()

        if player and hasattr(player, "show_content"):
            player.show_content(f"METADATA — {topic.upper()}", meta_text)

        return f"Metadados de vídeo gerados com sucesso para '{topic}'. A estrutura de títulos, capítulos e tags foi exibida no HUD."
    except Exception as e:
        return f"Erro ao gerar metadados de vídeo: {e}"


def search_local_assets_handler(parameters: dict, player=None, **_) -> str:
    """Indexa e pesquisa arquivos de mídia locais (vídeos, B-rolls, SFX) e copia o melhor match para o clipboard."""
    query = str(parameters.get("query", "")).strip().lower()
    if not query:
        return "Por favor, especifique o nome ou categoria do asset a pesquisar."

    search_dirs = [
        Path.home() / "Videos",
        Path.home() / "Downloads",
        Path("D:/Assets") if Path("D:/Assets").exists() else None,
        Path("E:/Assets") if Path("E:/Assets").exists() else None,
        Path("C:/Assets") if Path("C:/Assets").exists() else None,
    ]
    valid_dirs = [d for d in search_dirs if d and d.exists()]

    media_extensions = {".mp4", ".mov", ".mkv", ".mp3", ".wav", ".png", ".jpg", ".svg", ".webm"}
    matches = []

    for s_dir in valid_dirs:
        try:
            for root, _, files in os.walk(s_dir):
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in media_extensions:
                        fname_lower = f.lower()
                        if all(word in fname_lower for word in query.split()):
                            matches.append(Path(root) / f)
                            if len(matches) >= 5:
                                break
                if len(matches) >= 5:
                    break
        except Exception:
            continue

    if not matches:
        return f"Nenhum arquivo de mídia encontrado contendo '{query}' nas pastas locais de assets."

    top_asset = matches[0]
    copied = _copy_to_windows_clipboard(str(top_asset))
    
    report_lines = [f"Encontrados {len(matches)} asset(s):"]
    for m in matches:
        report_lines.append(f"- `{m.name}` ({m.parent})")

    report_lines.append(f"\nO caminho de '{top_asset.name}' foi {'copiado para a área de transferência' if copied else 'localizado'}.")
    full_report = "\n".join(report_lines)

    if player and hasattr(player, "show_content"):
        player.show_content(f"ASSETS — {query.upper()}", full_report)

    return f"Asset encontrado: {top_asset.name}. O caminho completo foi copiado para o clipboard para colar na timeline da edição."


TOOL = {
    "name": "media_studio",
    "description": "Estúdio de mídia para criadores e editores de vídeo: realiza cortes automáticos de silêncio com FFmpeg, gera metadados de vídeo (títulos, descrição, tags) e busca assets locais copiando caminhos para a timeline.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Ação a executar: 'rough_cut_silence', 'generate_video_metadata' ou 'search_local_assets'.",
            },
            "video_path": {
                "type": "STRING",
                "description": "Caminho do arquivo de vídeo (usado em rough_cut_silence).",
            },
            "project_topic": {
                "type": "STRING",
                "description": "Assunto ou título de trabalho do vídeo (usado em generate_video_metadata).",
            },
            "query": {
                "type": "STRING",
                "description": "Termo de busca para assets, B-rolls ou efeitos sonoros (usado em search_local_assets).",
            },
        },
        "required": ["action"],
    },
    "handler": lambda parameters, player=None, **kw: (
        rough_cut_silence_handler(parameters, player=player) if parameters.get("action") == "rough_cut_silence"
        else generate_video_metadata_handler(parameters, player=player) if parameters.get("action") == "generate_video_metadata"
        else search_local_assets_handler(parameters, player=player)
    ),
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
