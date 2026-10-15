from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from google.genai import types

from .tools import MemoryToolManager
from .router import aroute_generate, ROUTE_BACKGROUND


async def reconcile_note_update(
    tool_manager: MemoryToolManager,
    relative_path: str,
    new_fact: str,
    related_entities: list[str] | None = None,
) -> str:
    """Verifica se uma nova informação atualiza ou contradiz um fato existente na nota.

    Se atualizar um estado (status de tarefa, horário, meta, telefone, preferência),
    atualiza a informação ativa no corpo da nota e move o valor superado para a seção
    <details><summary>Histórico de Alterações</summary>.
    Caso contrário, anexa o novo fato normalmente de forma idempotente.
    """
    existing_content = tool_manager.read_memory_note(relative_path)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    entities = related_entities or []
    links_str = " ".join(f"[[{e.strip()}]]" for e in entities if e.strip())

    fact_entry = new_fact.strip()
    if links_str and links_str not in fact_entry:
        fact_entry += f"\n- Conexões: {links_str}"

    if existing_content.startswith("Nota não encontrada") or existing_content.startswith("Nota") and "está vazia" in existing_content:
        # Nota nova
        header = f"# {Path(relative_path).stem.replace('_', ' ').title()}\n\n"
        full_content = f"{header}- [{now_str}] {fact_entry}\n"
        return tool_manager.update_or_create_note(relative_path, full_content, mode="overwrite")

    # Se a nota existente já tem conteúdo, verificamos se o fato é uma atualização de estado/conflito
    prompt = f"""Você é o Reconciliador de Estado da Evie (Segundo Cérebro).
Sua função é reconciliar uma nota Markdown existente com um NOVO FATO recém-aprendido.

OBJETIVO:
1. Se o NOVO FATO contradiz, atualiza ou substitui um dado existente (ex: mudança de horário, novo status de tarefa/projeto, nova preferência que substitui a anterior, novo número/endereço):
   - Atualize a linha ativa da nota com a nova informação.
   - Mova a informação antiga/superada para uma seção no final da nota formatada exatamente como:
     <details>
     <summary>Histórico de Alterações</summary>
     - [{now_str}] Substituído: <dado antigo> -> Motivo: Atualizado por novo fato.
     </details>
   (Se a seção de histórico já existir, anexe a linha dentro dela).
2. Se o NOVO FATO for apenas uma informação ADICIONAL ou novo tópico cumulativo:
   - Mantenha a nota intacta e anexe a nova linha na seção mais apropriada com data `[{now_str}]`.

CONTEÚDO ATUAL DA NOTA ({relative_path}):
\"\"\"
{existing_content}
\"\"\"

NOVO FATO A INTEGRAR:
\"\"\"
{fact_entry}
\"\"\"

Responda APENAS com o texto completo final da nota em Markdown puro, sem blocos ```markdown delimitadores.
"""

    try:
        res = await aroute_generate(
            route=ROUTE_BACKGROUND,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1),
            timeout_ms=25_000,
            allow_live_overflow=True,
        )
        updated_text = (getattr(res.response, "text", "") or "").strip()
        if updated_text and len(updated_text) > 20:
            # Remove cercas de código markdown se o modelo tiver incluído
            if updated_text.startswith("```"):
                updated_text = re.sub(r"^```[a-zA-Z]*\n", "", updated_text)
                updated_text = re.sub(r"\n```$", "", updated_text).strip()

            return tool_manager.update_or_create_note(
                relative_path=relative_path,
                content=updated_text,
                mode="overwrite",
            )
    except Exception as err:
        print(f"[Reconciler] Erro ao reconciliar semanticamente ({err}) — caindo para append seguro.")

    # Fallback seguro: append com timestamp
    append_block = f"\n- [{now_str}] {fact_entry}"
    return tool_manager.update_or_create_note(relative_path, append_block, mode="append")


async def trigger_autosleep_consolidation(tool_manager: MemoryToolManager | None = None) -> None:
    """Disparado quando a Evie entra em auto-sleep (após 2 minutos de inatividade).

    Consolida notas > 150 linhas e faz backup local no Git sem travar a thread de áudio.
    """
    try:
        from .consolidator import MemoryConsolidator
        consolidator = MemoryConsolidator()
        
        # Consolida notas extensas
        reports = await consolidator.consolidate_long_notes(threshold_lines=150)
        if reports:
            print(f"[Reconciler/AutoSleep] 🧹 {len(reports)} nota(s) consolidada(s).")

        # Commit de backup local silencioso
        ok, msg = consolidator.git_backup_and_commit(commit_message=f"Auto-sleep memory backup {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"[Reconciler/AutoSleep] 💾 Git status: {msg}")
    except Exception as e:
        print(f"[Reconciler/AutoSleep] Erro durante consolidação de auto-sleep: {e}")
