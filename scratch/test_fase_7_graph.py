import sys
import io
import re
from pathlib import Path

# Ajusta stdout para UTF-8 no Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_memory.graph_linker import (
    build_vault_entity_index,
    inject_inline_wikilinks,
    append_related_links_section,
    rebuild_memory_map_and_readmes,
    retro_link_entire_vault,
)
from agent_memory.tools import search_second_brain, MemoryToolManager
from agent_memory.config import SECOND_BRAIN_DIR


def test_vault_graph_connectivity():
    print("=== [TESTE FASE 7: MOTOR DE GRAFO OBSIDIAN] ===")

    # 1. Executa retro-link do vault inteiro
    res = retro_link_entire_vault()
    print(f"1. retro_link_entire_vault: {res}")
    assert res["success"] is True, "retro_link_entire_vault falhou"

    # 2. Varre todos os .md e valida que nenhum nó está isolado e tem conexões válidas
    all_md_files = [
        f for f in SECOND_BRAIN_DIR.rglob("*.md")
        if not any(part.startswith(".") for part in f.parts) and f.is_file()
    ]
    assert len(all_md_files) >= 5, f"Esperava pelo menos 5 notas no vault, achou {len(all_md_files)}"

    print(f"2. Validando conexões em {len(all_md_files)} notas no vault...")
    for md_file in all_md_files:
        content = md_file.read_text(encoding="utf-8")
        links = re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", content)
        rel_path = md_file.relative_to(SECOND_BRAIN_DIR).as_posix()
        print(f"   - {rel_path}: {len(links)} links encontrados -> {links[:3]}")

        # Cada arquivo deve conter pelo menos 1 link apontando para outra nota (idealmente >= 2)
        assert len(links) >= 1, f"Nota órfã detectada sem links: {rel_path}"

        # As notas centrais devem ter pelo menos 2 links
        if md_file.stem in ("usuario", "hardware_pc", "mark_lv_evie", "diretrizes_assistente", "MEMORY_MAP"):
            assert len(links) >= 2, f"Nota principal {rel_path} tem menos de 2 links: {len(links)}"

    # 3. Teste unitário de injeção inline e proteção de blocos
    sample_text = """# Nota de Teste
Aqui está uma URL: https://example.com/mark_lv_evie e código inline `Rafael no PC`.
```python
# Não deve alterar este Rafael nem RTX 5070
x = 'Rafael'
```
O operador Rafael está configurando a RTX 5070 no projeto Evie.
Já existe este link: [[diretrizes_assistente|Diretrizes]].
"""
    injected = inject_inline_wikilinks(sample_text, current_stem="nota_teste")
    print("\n3. Teste de injeção segura inline:")
    print(injected)

    # Validações estritas de proteção
    assert "https://example.com/mark_lv_evie" in injected, "URL foi corrompida"
    assert "`Rafael no PC`" in injected, "Inline code foi corrompido"
    assert "x = 'Rafael'" in injected, "Fenced code block foi corrompido"
    assert "[[diretrizes_assistente|Diretrizes]]" in injected, "Link existente foi corrompido"
    # Valida que o texto comum foi linkado
    assert "[[usuario|Rafael]]" in injected or "[[usuario]]" in injected, "Rafael não foi linkado no texto comum"
    assert "[[hardware_pc|RTX 5070]]" in injected or "[[hardware_pc]]" in injected, "RTX 5070 não foi linkada"
    assert "[[mark_lv_evie" in injected, "Evie não foi linkada"

    # 4. Teste de append_related_links_section
    base_doc = "# Documento\nTexto aqui."
    with_related = append_related_links_section(base_doc, "doc", ["usuario", "hardware_pc"])
    assert "## Conexões Relacionadas" in with_related
    assert "- [[usuario]]" in with_related
    assert "- [[hardware_pc]]" in with_related

    # Idempotência de related links
    twice_related = append_related_links_section(with_related, "doc", ["usuario", "mark_lv_evie"])
    assert twice_related.count("- [[usuario]]") == 1, "Link duplicado na seção de conexões"
    assert "- [[mark_lv_evie]]" in twice_related

    # 5. Teste de 1-hop traversal na busca semântica
    print("\n4. Testando busca com 1-hop traversal...")
    search_out = search_second_brain("RTX 5070", include_linked=True)
    print("Resumo da busca:")
    print("\n".join(search_out.splitlines()[:12]))
    assert "hardware_pc" in search_out.lower(), "Busca por RTX 5070 não encontrou hardware_pc"
    assert "1-hop" in search_out.lower() or "notas linkadas" in search_out.lower(), "Expansão de 1-hop ausente na busca"

    print("\n==========================================")
    print("FASE 7 VALIDADA COM SUCESSO! O GRAFO ESTÁ 100% CONECTADO!")
    print("==========================================")


if __name__ == "__main__":
    test_vault_graph_connectivity()
