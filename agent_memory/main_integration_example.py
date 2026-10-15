from __future__ import annotations

import asyncio
from google.genai import types

from agent_memory.config import (
    MODEL_PRIMARY,
    get_genai_client,
)
from agent_memory.tools import MemoryToolManager
from agent_memory.indexer import MemorySearchEngine
from agent_memory.extractor import MemoryIngestionWorker
from agent_memory.consolidator import MemoryConsolidator

# Instâncias dos componentes
tool_manager = MemoryToolManager()
search_engine = MemorySearchEngine()
ingestion_worker = MemoryIngestionWorker(tool_manager, search_engine)
consolidator = MemoryConsolidator()


# ── Definição das Ferramentas para Function Calling ─────────────────────────
def read_memory_note(relative_path: str) -> str:
    """Lê uma nota específica do Segundo Cérebro (ex: 'perfil/hardware_pc.md', 'projetos/mark_lv_evie.md').

    Use esta ferramenta sob demanda para carregar informações detalhadas.
    """
    print(f"  -> [TOOL CALL] read_memory_note(relative_path='{relative_path}')")
    result = tool_manager.read_memory_note(relative_path)
    return result


def search_memory(query: str) -> str:
    """Busca termos, tópicos ou palavras-chave no índice FTS5 do Segundo Cérebro.

    Retorna notas relevantes e trechos correspondentes em milissegundos.
    """
    print(f"  -> [TOOL CALL] search_memory(query='{query}')")
    results = search_engine.search(query, limit=4)
    if not results:
        return f"Nenhum resultado encontrado para o termo '{query}'."

    output_lines = [f"Resultados da busca por '{query}':"]
    for r in results:
        output_lines.append(f"- [{r['path']}] {r['title']}: {r['snippet']}")
    return "\n".join(output_lines)


def update_or_create_note(relative_path: str, content: str, mode: str = "append") -> str:
    """Cria ou atualiza uma nota de forma persistente no Segundo Cérebro.

    :param relative_path: Caminho relativo do arquivo (ex: 'projetos/novo_projeto.md').
    :param content: Conteúdo formatado em Markdown.
    :param mode: 'append' para adicionar ou 'overwrite' para reescrever.
    """
    print(f"  -> [TOOL CALL] update_or_create_note(relative_path='{relative_path}', mode='{mode}')")
    res = tool_manager.update_or_create_note(relative_path, content, mode)
    search_engine.index_single_note(relative_path)
    return res


# Mapeamento para execução manual de Function Calls caso necessário
TOOL_REGISTRY = {
    "read_memory_note": read_memory_note,
    "search_memory": search_memory,
    "update_or_create_note": update_or_create_note,
}


async def run_example() -> None:
    print("=" * 70)
    print("[SEGUNDO CEREBRO] INICIANDO SUBSISTEMA DE MEMORIA (AGENT MEMORY)")
    print("=" * 70)

    # 1. Sincroniza o banco de dados SQLite FTS5 com os arquivos Markdown
    total_indexed = search_engine.sync_all()
    print(f"[OK] Indice FTS5 sincronizado: {total_indexed} notas catalogadas em .cache/memory_index.db")

    # 2. Carrega apenas o MEMORY_MAP.md no System Instruction (Lazy Loading rigoroso)
    memory_map = tool_manager.get_memory_map()
    system_instruction = f"""Voce e um assistente pessoal com Segundo Cerebro persistente.
Diretiva de Memoria: Voce NAO tem todas as notas carregadas previamente.
Abaixo esta o seu INDICE MESTRE (MEMORY_MAP.md). Use as ferramentas 'search_memory' ou 'read_memory_note'
para carregar o conteudo das notas apenas quando o contexto for necessario.

{memory_map}
"""

    client = get_genai_client()

    # 3. Simula uma pergunta do usuario exigindo contexto que esta no Segundo Cerebro
    user_query = "Consulte as notas de perfil no meu Segundo Cerebro e me diga qual e a configuracao de hardware do meu PC e minha placa de video."
    print(f"\n[Usuario]: {user_query}")

    # Configura ferramentas nativas no SDK
    tools_list = [read_memory_note, search_memory, update_or_create_note]

    # Chat com suporte a Automatic Function Calling nativo do SDK via dict config
    chat = client.chats.create(
        model=MODEL_PRIMARY,
        config={
            "system_instruction": system_instruction,
            "tools": tools_list,
            "temperature": 0.2,
        },
    )

    response = chat.send_message(user_query)
    print(f"\n[Evie / Modelo Primario ({MODEL_PRIMARY})]:")
    print(response.text)

    # 4. Simulacao de Extracao em Segundo Plano (Background Task sem latencia)
    print("\n" + "-" * 70)
    print("[EXTRACTION] SIMULANDO EXTRACAO ASSINCRONA DE NOVOS FATOS EM BACKGROUND...")
    conversation_turn_to_remember = (
        "Usuario: 'A partir de hoje, anote que estou estudando Rust toda terca-feira "
        "e preciso que voce me lembre de revisar ponteiros as 19h.'"
    )
    print(f"[Turno da Conversa]: \"{conversation_turn_to_remember}\"")

    # Dispara a extracao assincrona
    extraction_task = asyncio.create_task(
        ingestion_worker.extract_facts_in_background(conversation_turn_to_remember)
    )
    extraction_result = await extraction_task
    print(f"[OK] Resultado da Ingestao: {extraction_result}")

    # 5. Backup e Versionamento Git Local
    print("\n" + "-" * 70)
    print("[GIT] TESTANDO AUTO-COMMIT NO REPOSITORIO GIT...")
    success, msg = consolidator.git_backup_and_commit("Auto memory update: rotina de estudos")
    print(f"Status do Git: {msg}")

    print("\n" + "=" * 70)
    print("[SUCESSO] SUBSISTEMA DO SEGUNDO CEREBRO VALIDADO COM SUCESSO!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_example())
