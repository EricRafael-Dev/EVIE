from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field
from google.genai import types

from .config import MODEL_LIGHTWEIGHT
from .tools import MemoryToolManager
from .indexer import MemorySearchEngine


class MemoryExtractionResult(BaseModel):
    """Esquema Pydantic para validação estrita da extração de memórias pelo modelo leve."""
    has_new_info: bool = Field(
        description="Verdadeiro se o turno contiver novos fatos, preferências, projetos ou dados relevantes a serem lembrados."
    )
    target_file: str | None = Field(
        default=None,
        description="Caminho relativo do arquivo de destino em second_brain/ (ex: 'perfil/usuario.md', 'projetos/novo_app.md', 'entidades/pessoas/carlos.md')."
    )
    content_to_append: str | None = Field(
        default=None,
        description="Conteúdo Markdown conciso e formatado em tópicos/título a ser anexado à nota, usando links [[pasta/nota]] quando citar entidades."
    )
    related_entities: list[str] = Field(
        default_factory=list,
        description="Lista de referências a projetos ou entidades cruzadas vinculadas ao fato, ex: ['entidades/pessoas/carlos', 'projetos/mark_lv_evie']."
    )
    summary_reason: str | None = Field(
        default=None,
        description="Justificativa concisa do motivo da extração ou por que não há informação nova."
    )


class MemoryIngestionWorker:
    """Worker assíncrono projetado para rodar em segundo plano (background asyncio tasks),

    extraindo novos fatos e preferências da conversa usando o modelo leve (Flash)
    sem onerar o tempo de resposta do modelo primário.
    """

    def __init__(
        self,
        tool_manager: MemoryToolManager | None = None,
        indexer: MemorySearchEngine | None = None,
    ) -> None:
        self.tool_manager = tool_manager or MemoryToolManager()
        self.indexer = indexer or MemorySearchEngine()

    async def extract_facts_in_background(self, conversation_turn: str) -> dict[str, Any]:
        """Disparado via asyncio.create_task para analisar o turno da conversa e gravar

        automaticamente novas informações persistentes no Segundo Cérebro.
        """
        turn_text = conversation_turn.strip()
        if not turn_text:
            return {"has_new_info": False, "summary_reason": "Turno vazio"}

        # ── Gate de Memória JEV Local (System 1) ───────────────────────────────
        try:
            from core.decision_engine import get_decision_engine
            engine = get_decision_engine()
            jev_decision, jev_probs = await engine.evaluate_memory(turn_text)
            should_extract = jev_decision.should_extract_memory
            conf = jev_probs.get("should_extract_memory", 1.0)
            folder = jev_decision.suggested_folder

            if not should_extract or conf < 0.60 or folder == "none":
                try:
                    print(
                        f"[JEV-Local] Cota poupada na rota BACKGROUND: dialogo sem fatos novos "
                        f"(should_extract={should_extract}, conf={conf:.2f}, folder='{folder}'). Chamada LLM abortada."
                    )
                except Exception:
                    pass
                return {
                    "has_new_info": False,
                    "summary_reason": f"[JEV-Local] Filtrado pelo motor System 1 (conf={conf:.2f}, folder={folder})",
                }
            try:
                print(
                    f"[JEV-Local] Fato novo detectado (conf={conf:.2f}, folder='{folder}'). Despachando para extracao no vault..."
                )
            except Exception:
                pass
        except Exception as jev_err:
            try:
                print(f"[JEV-Local] Aviso no gate de memoria: {jev_err} — prosseguindo fail-open.")
            except Exception:
                pass

        # Consulta catálogo atualizado de notas do vault para linkagem semântica precisa
        from .graph_linker import build_vault_entity_index
        entities = build_vault_entity_index()
        vault_notes_summary = "\n".join(
            f"- [[{e['link_target']}]] ({e['rel_path']}): {e['title']}"
            for e in entities[:25]
        )

        prompt = f"""Você é o extrator de memórias persistentes da Evie (Segundo Cérebro no Obsidian).
Sua missão é analisar o diálogo recente e identificar se há FATOS NOVOS, PREFERÊNCIAS DO USUÁRIO, DADOS DE PROJETOS ou CONFIGURAÇÕES DE HARDWARE/SISTEMA que devam ser lembrados no "Segundo Cérebro".

Notas existentes atualmente no vault:
{vault_notes_summary}

Categorias disponíveis:
- perfil/usuario.md: Nome, gostos, trabalho, rotinas, hábitos, foco pessoal.
- perfil/hardware_pc.md: Especificações de máquina, caminhos locais, apps, periféricos.
- projetos/<nome_projeto>.md: Detalhes, requisitos, bugs ou tarefas de desenvolvimento.
- entidades/pessoas/<nome_pessoa>.md: Contatos, mentores, parceiros, histórico pessoal.
- entidades/organizacoes/<nome_empresa>.md: Empresas, instituições, serviços.
- regras_e_skills/<topico>.md: Novas instruções de comportamento ou estilo de resposta.

DIRETIVA OBRIGATÓRIA DE WIKILINKS OBSIDIAN:
Sempre que o fato extraído mencionar um conceito, projeto, hardware, pessoa ou regra que já possua uma nota na lista do vault, referencie usando obrigatoriamente a sintaxe do Obsidian `[[nome_do_arquivo|Texto]]` (ou `[[nome_do_arquivo]]`) e preencha o campo `related_entities: list[str]` do schema Pydantic com os nomes dos arquivos ou stems relacionados.

DIÁLOGO A SER ANALISADO:
\"\"\"
{turn_text}
\"\"\"

Se o diálogo for apenas uma saudação, comando genérico passageiro ou conversa casual sem fatos relevantes, retorne has_new_info=False.
Caso contrário, extraia em formato Markdown limpo e aponte o arquivo de destino adequado.
"""

        try:
            from .router import aroute_generate, ROUTE_BACKGROUND

            route_res = await aroute_generate(
                route=ROUTE_BACKGROUND,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MemoryExtractionResult,
                    temperature=0.1,
                ),
                timeout_ms=20_000,
                allow_live_overflow=True,
            )

            raw_text = getattr(route_res.response, "text", "") or "{}"
            if "{" in raw_text and "}" in raw_text:
                raw_text = raw_text[raw_text.find("{"): raw_text.rfind("}") + 1]
            parsed_data = json.loads(raw_text)
            result = MemoryExtractionResult(**parsed_data)

            if result.has_new_info and result.target_file and result.content_to_append:
                # Utiliza o reconciliador de estado para evitar append cego e contradições
                from .reconciler import reconcile_note_update
                save_status = await reconcile_note_update(
                    tool_manager=self.tool_manager,
                    relative_path=result.target_file,
                    new_fact=result.content_to_append,
                    related_entities=result.related_entities,
                )

                # Reindexa o arquivo no SQLite FTS5 instantaneamente
                self.indexer.index_single_note(result.target_file)

                return {
                    "has_new_info": True,
                    "target_file": result.target_file,
                    "content_to_append": result.content_to_append,
                    "related_entities": result.related_entities,
                    "summary_reason": result.summary_reason,
                    "status": save_status,
                }

            return {
                "has_new_info": False,
                "summary_reason": result.summary_reason or "Nenhum fato relevante a persistir",
            }

        except Exception as err:
            error_msg = f"[MemoryIngestionWorker] Falha na extração em background: {err}"
            print(error_msg)
            return {"has_new_info": False, "error": str(err)}
