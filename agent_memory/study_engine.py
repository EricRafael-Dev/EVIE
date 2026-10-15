from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from google.genai import types

from .config import SECOND_BRAIN_DIR
from .tools import MemoryToolManager
from .indexer import MemorySearchEngine
from .router import aroute_generate, ROUTE_REASONING, ROUTE_BACKGROUND


class StudyAndTimelineEngine:
    """Motor cognitivo de linha do tempo e estudos para o Segundo Cérebro da Evie."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or SECOND_BRAIN_DIR).resolve()
        self.tools = MemoryToolManager(self.base_dir)
        self.indexer = MemorySearchEngine(base_dir=self.base_dir)

    async def recall_timeline(self, period: str = "hoje", session_log: list[str] | None = None) -> str:
        """Cruza notas modificadas recentemente no second_brain/ por timestamp,

        sessões recentes e o log atual para reconstruir onde o usuário parou e o que foi feito.
        """
        now = datetime.now()
        recent_files = []

        # Varre arquivos modificados recentemente
        for md_file in self.base_dir.rglob("*.md"):
            if ".cache" in md_file.parts or ".obsidian" in md_file.parts or md_file.name == "MEMORY_MAP.md":
                continue
            try:
                mtime = md_file.stat().st_mtime
                mod_dt = datetime.fromtimestamp(mtime)
                rel_path = md_file.relative_to(self.base_dir).as_posix()
                content = md_file.read_text(encoding="utf-8", errors="replace")
                
                # Pega a última linha com data ou últimas 3 linhas
                last_lines = [l.strip() for l in content.splitlines() if l.strip()][-3:]
                last_snippet = " | ".join(last_lines)

                recent_files.append({
                    "path": rel_path,
                    "mtime": mtime,
                    "mod_dt": mod_dt.strftime("%Y-%m-%d %H:%M"),
                    "snippet": last_snippet,
                })
            except Exception:
                continue

        # Ordena pelo mais recente
        recent_files.sort(key=lambda x: x["mtime"], reverse=True)
        top_files = recent_files[:6]

        session_turns = (session_log or [])[-8:]
        session_text = "\n".join(session_turns) if session_turns else "Nenhuma conversa gravada nesta sessão ainda."

        files_text = "\n".join(
            f"- `{f['path']}` (Modificado em {f['mod_dt']}): {f['snippet']}"
            for f in top_files
        ) if top_files else "Nenhuma nota recente."

        prompt = f"""Você é a Evie, assistente pessoal e parceira de produtividade.
O usuário perguntou sobre sua linha do tempo recente ou onde ele parou (período solicitado: '{period}').

DADOS RECENTES DO SISTEMA:
Notas modificadas recentemente no Segundo Cérebro:
{files_text}

Diálogo recente da sessão:
{session_text}

TAREFA:
Resuma de forma clara, natural e direta em Português do Brasil:
1. Em quais tópicos ou projetos o usuário esteve focado recentemente.
2. Onde exatamente ele parou (últimas tarefas, arquivos ou dúvidas).
3. Qual é o próximo passo lógico ou pendência imediata.
"""

        try:
            res = await aroute_generate(
                route=ROUTE_REASONING,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
                timeout_ms=25_000,
                allow_live_overflow=True,
            )
            return (getattr(res.response, "text", "") or "").strip()
        except Exception as e:
            return f"Linha do tempo baseada em arquivos recentes:\n{files_text}"

    async def generate_study_quiz(self, topic: str) -> str:
        """Lê notas relacionadas ao tópico no Segundo Cérebro, gera flashcards/perguntas de revisão

        e registra a realização do estudo na nota correspondente.
        """
        # Busca notas sobre o tópico
        results = self.indexer.search(topic, limit=2)
        context_notes = []
        target_path = None

        if results:
            target_path = results[0]["path"]
            for r in results:
                content = self.tools.read_memory_note(r["path"])
                context_notes.append(f"Nota `{r['path']}`:\n{content[:2000]}")
        else:
            # Tenta busca por nome direto
            candidates = list(self.base_dir.rglob(f"*{topic}*.md"))
            if candidates:
                target_path = candidates[0].relative_to(self.base_dir).as_posix()
                content = self.tools.read_memory_note(target_path)
                context_notes.append(f"Nota `{target_path}`:\n{content[:2000]}")

        if not context_notes:
            return f"Não encontrei notas de estudo ou referências sobre '{topic}' no Segundo Cérebro."

        notes_combined = "\n\n".join(context_notes)

        prompt = f"""Você é a Evie atuando como tutora e mentora de estudos.
Com base nas notas do Segundo Cérebro abaixo sobre o tema '{topic}', crie um mini-quiz de fixação rápida (3 perguntas práticas e instigantes).

NOTAS DE REFERÊNCIA:
\"\"\"
{notes_combined}
\"\"\"

FORMATO DA RESPOSTA:
Apresente 3 perguntas numeradas com respostas curtas explicativas em formato de flashcard.
Termine convidando o usuário a responder ou se aprofundar.
"""

        try:
            res = await aroute_generate(
                route=ROUTE_REASONING,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3),
                timeout_ms=30_000,
                allow_live_overflow=True,
            )
            quiz_text = (getattr(res.response, "text", "") or "").strip()

            # Registra a revisão na nota
            if target_path:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                log_entry = f"\n- [{now_str}] 🎯 Sessão de estudo/quiz realizada sobre '{topic}'."
                self.tools.update_or_create_note(target_path, log_entry, mode="append")

            return quiz_text
        except Exception as e:
            return f"Erro ao gerar quiz de estudo sobre '{topic}': {e}"
