from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any

from .config import SECOND_BRAIN_DIR, MEMORY_MAP_PATH


# ── Dicionário de Aliases e Sinônimos Padrão por Entidade Central ───────────────
DEFAULT_ENTITY_ALIASES: dict[str, list[str]] = {
    "usuario": [
        "Rafael", "Perfil do Usuário", "Usuário"
    ],
    "hardware_pc": [
        "Hardware e Rede do PC", "Especificações de Hardware", "RTX 5070",
        "i5-14600K", "Poco X7", "Tailscale", "Hardware"
    ],
    "mark_lv_evie": [
        "Projeto: Mark-LV / Evie AI Assistant", "Projeto Evie", "Evie AI Assistant",
        "Evie AI", "Mark-LV", "Mark LV", "JarvisLive", "Evie"
    ],
    "diretrizes_assistente": [
        "Diretrizes e Regras Operacionais da Assistente", "Diretrizes e Regras Operacionais",
        "Diretrizes da Assistente", "Regras Operacionais", "MemoryIngestionWorker"
    ],
    "MEMORY_MAP": [
        "MEMORY_MAP", "Índice Mestre", "Mapa de Memória", "Catálogo Semântico"
    ],
}


def build_vault_entity_index(vault_dir: Path | None = None) -> list[dict[str, Any]]:
    """Varre todos os arquivos Markdown (.md) em second_brain/ e extrai catálogo de entidades,

    títulos, caminhos e aliases para injeção automática de WikiLinks.
    """
    base = (vault_dir or SECOND_BRAIN_DIR).resolve()
    if not base.exists():
        return []

    index: list[dict[str, Any]] = []

    for md_file in sorted(base.rglob("*.md")):
        # Ignora pastas internas do Obsidian, git e cache
        if any(part.startswith(".") for part in md_file.parts):
            continue

        rel_path = md_file.relative_to(base).as_posix()
        stem = md_file.stem
        raw_text = md_file.read_text(encoding="utf-8", errors="replace")

        # Título principal (# Título)
        title_match = re.search(r"^#\s+(.+)$", raw_text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else stem

        # Target link format: se for README em subpasta, usa caminho relativo sem extensão
        # para evitar colisão entre múltiplos READMEs no grafo Obsidian
        if stem.lower() == "readme":
            link_target = str(Path(rel_path).with_suffix("")).replace("\\", "/")
        else:
            link_target = stem

        aliases: set[str] = set()

        # 1. Aliases do Frontmatter YAML (se houver)
        fm_match = re.search(r"^---\s*\n(.*?)\n---", raw_text, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            alias_match = re.search(r"aliases:\s*\[(.*?)\]", fm_text)
            if alias_match:
                for a in alias_match.group(1).split(","):
                    c = a.strip().strip("'\"")
                    if c:
                        aliases.add(c)

        # 2. Aliases padrão heurísticos conhecidos
        if stem in DEFAULT_ENTITY_ALIASES:
            aliases.update(DEFAULT_ENTITY_ALIASES[stem])

        # 3. Adiciona o título e variações limpas se forem significativos
        clean_title = re.sub(r"[^\w\s\-]", "", title).strip()
        if len(clean_title) >= 3 and clean_title.lower() != stem.lower():
            aliases.add(clean_title)

        # Adiciona o próprio stem se for legível
        if len(stem) >= 3 and not stem.lower().startswith("readme"):
            aliases.add(stem.replace("_", " ").title())
            aliases.add(stem)

        # Ordena aliases por tamanho decrescente para priorizar termos mais longos
        sorted_aliases = sorted(
            [a for a in aliases if len(a.strip()) >= 3],
            key=lambda x: len(x),
            reverse=True,
        )

        index.append({
            "stem": stem,
            "rel_path": rel_path,
            "link_target": link_target,
            "title": title,
            "aliases": sorted_aliases,
            "path": md_file,
        })

    return index


def inject_inline_wikilinks(
    content: str,
    current_stem: str,
    entity_index: list[dict[str, Any]] | None = None,
) -> str:
    """Injeta WikiLinks [[nota|termo]] inline no texto Markdown na primeira ocorrência de

    cada entidade/alias, preservando integralmente blocos de código, URLs, cabeçalhos
    e links já existentes. Nunca cria auto-link para a própria nota (current_stem).
    """
    if not content or not content.strip():
        return content

    index = entity_index or build_vault_entity_index()
    if not index:
        return content

    # ── Fase 1: Proteção de blocos imutáveis via Tokens ───────────────────────
    protected_tokens: list[str] = []

    def _mask_token(match: re.Match) -> str:
        token = f"@@@MASK_TOKEN_{len(protected_tokens)}@@@"
        protected_tokens.append(match.group(0))
        return token

    text = content

    # 1. Frontmatter YAML
    text = re.sub(r"^---\s*\n.*?\n---\n?", _mask_token, text, flags=re.DOTALL)
    # 2. Blocos de código fenced (```...```)
    text = re.sub(r"```[\s\S]*?```", _mask_token, text)
    # 3. Inline code (`...`)
    text = re.sub(r"`[^`\n]+`", _mask_token, text)
    # 4. WikiLinks existentes ([[...]])
    text = re.sub(r"\[\[[^\]]+\]\]", _mask_token, text)
    # 5. Markdown links padrão ([texto](url))
    text = re.sub(r"\[[^\]]+\]\([^\)]+\)", _mask_token, text)
    # 6. Cabeçalhos Markdown (# Cabeçalho)
    text = re.sub(r"^#{1,6}\s+.*$", _mask_token, text, flags=re.MULTILINE)
    # 7. URLs (http/https)
    text = re.sub(r"https?://[^\s\)\>\]]+", _mask_token, text)

    # ── Fase 2: Injeção de WikiLinks nas partes desprotegidas ───────────────────
    linked_stems_in_turn: set[str] = set()
    norm_current_stem = current_stem.lower().strip()

    for item in index:
        target_stem = item["stem"]
        link_target = item["link_target"]

        # Nunca auto-linkar a própria nota
        if target_stem.lower().strip() == norm_current_stem:
            continue

        if target_stem in linked_stems_in_turn:
            continue

        for alias in item["aliases"]:
            if target_stem in linked_stems_in_turn:
                break

            alias_clean = alias.strip()
            if not alias_clean or len(alias_clean) < 3:
                continue

            # Word boundary regex resiliente para pontuação e acentos
            pattern = re.compile(
                r"(?<![a-zA-Z0-9_\-\[\]])(" + re.escape(alias_clean) + r")(?![a-zA-Z0-9_\-\[\]])",
                re.IGNORECASE,
            )

            match = pattern.search(text)
            if match:
                matched_text = match.group(1)
                # Formata [[link_target]] ou [[link_target|texto_original]]
                if matched_text == link_target:
                    replacement = f"[[{link_target}]]"
                else:
                    replacement = f"[[{link_target}|{matched_text}]]"

                # Mascara o novo WikiLink para não ser re-processado por aliases seguintes
                replacement_token = f"@@@MASK_TOKEN_{len(protected_tokens)}@@@"
                protected_tokens.append(replacement)

                # Substitui apenas a primeira ocorrência
                text = text[:match.start()] + replacement_token + text[match.end():]
                linked_stems_in_turn.add(target_stem)
                break

    # ── Fase 3: Desmascaramento / Restauração dos Tokens ───────────────────────
    for idx, original in enumerate(protected_tokens):
        token = f"@@@MASK_TOKEN_{idx}@@@"
        text = text.replace(token, original)

    return text


def append_related_links_section(
    content: str,
    current_stem: str,
    related_stems: list[str],
) -> str:
    """Garante que no rodapé da nota exista a seção padronizada '## Conexões Relacionadas',

    fazendo merge sem duplicar e sem auto-referências.
    """
    clean_content = content.rstrip()
    norm_current = current_stem.lower().strip()

    # Filtra os links a adicionar
    to_add: list[str] = []
    for s in related_stems:
        clean_s = s.strip().lstrip("[").rstrip("]").strip()
        if not clean_s or clean_s.lower() == norm_current:
            continue
        # Se for link formatado como stem ou path, normaliza
        link_str = f"[[{clean_s}]]" if not clean_s.startswith("[[") else clean_s
        to_add.append(link_str)

    # Verifica se já existe seção de conexões relacionadas
    section_pattern = re.compile(r"##\s+Conexões Relacionadas\s*\n([\s\S]*?)(?=\n##|\Z)", re.IGNORECASE)
    match = section_pattern.search(clean_content)

    if match:
        existing_block = match.group(1)
        existing_links = set(re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", existing_block))
        new_links = []
        for lk in to_add:
            target = re.search(r"\[\[([^\]\|]+)", lk)
            if target and target.group(1).strip() not in existing_links:
                new_links.append(f"- {lk}")
                existing_links.add(target.group(1).strip())

        if new_links:
            merged_block = existing_block.rstrip() + "\n" + "\n".join(new_links) + "\n"
            clean_content = (
                clean_content[:match.start(1)] +
                merged_block +
                clean_content[match.end(1):]
            )
        return clean_content.rstrip() + "\n"
    else:
        if not to_add:
            return clean_content + "\n"
        # Cria a seção no final
        unique_list: list[str] = []
        seen = set()
        for lk in to_add:
            target = re.search(r"\[\[([^\]\|]+)", lk)
            t_key = target.group(1).strip() if target else lk
            if t_key not in seen:
                seen.add(t_key)
                unique_list.append(f"- {lk}")

        section = "\n\n## Conexões Relacionadas\n" + "\n".join(unique_list) + "\n"
        return clean_content + section


def rebuild_memory_map_and_readmes(vault_dir: Path | None = None) -> None:
    """Reescreve second_brain/MEMORY_MAP.md usando [[WikiLinks]] explícitos para todas as notas

    organizadas por categoria, e sincroniza os READMEs das subpastas conectando-os
    ao MEMORY_MAP, eliminando qualquer nó órfão no grafo Obsidian.
    """
    base = (vault_dir or SECOND_BRAIN_DIR).resolve()
    base.mkdir(parents=True, exist_ok=True)

    categories = [
        ("perfil", "Perfil e Ambiente", "Especificações pessoais e hardware"),
        ("projetos", "Projetos Ativos", "Iniciativas de software e arquitetura"),
        ("entidades", "Entidades e Contatos", "Pessoas, contatos e organizações"),
        ("regras_e_skills", "Regras e Skills", "Diretrizes de inteligência e conduta"),
    ]

    map_lines = [
        "# 🧠 ÍNDICE MESTRE DO SEGUNDO CÉREBRO (MEMORY_MAP)",
        "",
        "> [!IMPORTANT]",
        "> **DIRETIVA DE LAZY LOADING PARA A IA:**",
        "> Utilize este catálogo semântico e invoque `read_memory_note(target_file)` ou",
        "> `search_second_brain(query)` **sob demanda** quando necessitar de contexto profundo.",
        "",
        "---",
        "",
        "## 🗺️ Mapa Estrutural de Notas",
        "",
    ]

    for cat_slug, cat_title, cat_desc in categories:
        cat_dir = base / cat_slug
        cat_dir.mkdir(parents=True, exist_ok=True)

        map_lines.append(f"### 📁 `{cat_slug}/` — {cat_title}")
        map_lines.append(f"*{cat_desc}*")
        map_lines.append("")

        files = sorted([
            f for f in cat_dir.rglob("*.md")
            if not any(part.startswith(".") for part in f.parts) and f.is_file()
        ])

        for f in files:
            rel_p = f.relative_to(base).as_posix()
            stem = f.stem
            content = f.read_text(encoding="utf-8", errors="replace")
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else stem

            # Constrói o WikiLink explícito
            if stem.lower() == "readme":
                parent_name = f.parent.name
                link_ref = f"[[{f.parent.relative_to(base).as_posix()}/README|Índice: {parent_name.title()}]]"
            else:
                link_ref = f"[[{stem}|{title}]]"

            map_lines.append(f"- **{link_ref}** (`{rel_p}`)")

        map_lines.append("")

    # Rodapé do MEMORY_MAP com conexões de hub
    map_lines.extend([
        "---",
        "",
        "## ⚡ Regras de Leitura e Escrita",
        "1. **Buscar primeiro:** Invoque `search_second_brain(query)` antes de ler notas aleatórias.",
        "2. **Leitura específica:** Use `read_memory_note(target_file)` com o caminho exato.",
        "3. **Links Obsidian:** Formate referências entre notas como `[[pasta/nome|Alias]]` ou `[[stem]]`.",
        "",
        "## Conexões Centrais do Grafo",
        "- [[usuario|Perfil do Usuário]]",
        "- [[hardware_pc|Hardware e Rede do PC]]",
        "- [[mark_lv_evie|Projeto Mark-LV / Evie]]",
        "- [[diretrizes_assistente|Diretrizes da Assistente]]",
        "",
    ])

    map_path = base / "MEMORY_MAP.md"
    tmp_map = map_path.with_suffix(".tmp")
    tmp_map.write_text("\n".join(map_lines), encoding="utf-8")
    os.replace(tmp_map, map_path)

    # ── Atualização / Conexão dos README.md de subpastas ──────────────────────
    # Garante que cada README tenha conexão explícita de volta para [[MEMORY_MAP]]
    # e para os nós filhos da pasta correspondente
    for readme_path in base.rglob("README.md"):
        if any(part.startswith(".") for part in readme_path.parts):
            continue
        try:
            folder = readme_path.parent
            parent_rel = folder.relative_to(base).as_posix()
            r_content = readme_path.read_text(encoding="utf-8", errors="replace")

            # Localiza notas filhas nessa mesma pasta (exceto o próprio README)
            sibling_notes = [
                sf for sf in folder.glob("*.md")
                if sf.name.lower() != "readme.md" and not sf.name.startswith(".")
            ]

            related = ["MEMORY_MAP"]
            for sf in sibling_notes:
                related.append(sf.stem)

            updated_readme = append_related_links_section(
                content=r_content,
                current_stem=f"{parent_rel}/README",
                related_stems=related,
            )
            readme_path.write_text(updated_readme, encoding="utf-8")
        except Exception as _r_err:
            print(f"[GraphLinker] Aviso ao conectar {readme_path}: {_r_err}")


def retro_link_entire_vault(vault_dir: Path | None = None) -> dict[str, Any]:
    """Percorre todas as notas em second_brain/, aplica links inline automáticos via aliases,

    adiciona rodapés de conexões relacionadas semânticas cruzadas e atualiza o FTS5.
    """
    base = (vault_dir or SECOND_BRAIN_DIR).resolve()
    entity_index = build_vault_entity_index(base)
    modified_files: list[str] = []

    # Mapas de conexões semânticas recomendadas para os nós principais
    core_relationships: dict[str, list[str]] = {
        "usuario": ["MEMORY_MAP", "hardware_pc", "mark_lv_evie", "diretrizes_assistente"],
        "hardware_pc": ["MEMORY_MAP", "usuario", "mark_lv_evie"],
        "mark_lv_evie": ["MEMORY_MAP", "hardware_pc", "usuario", "diretrizes_assistente"],
        "diretrizes_assistente": ["MEMORY_MAP", "mark_lv_evie", "usuario"],
    }

    for item in entity_index:
        stem = item["stem"]
        md_file: Path = item["path"]

        # Não alterar MEMORY_MAP diretamente no loop pois ele é reconstruído depois
        if stem.upper() == "MEMORY_MAP":
            continue

        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")

            # 1. Injeta WikiLinks inline para menções de outras entidades
            linked_content = inject_inline_wikilinks(
                content=content,
                current_stem=stem,
                entity_index=entity_index,
            )

            # 2. Conexões semânticas adicionais do mapa ou genéricas
            related = core_relationships.get(stem, ["MEMORY_MAP"])

            # 3. Adiciona seção de Conexões Relacionadas
            final_content = append_related_links_section(
                content=linked_content,
                current_stem=stem,
                related_stems=related,
            )

            if final_content != content:
                md_file.write_text(final_content, encoding="utf-8")
                modified_files.append(item["rel_path"])

        except Exception as e:
            print(f"[GraphLinker] Erro ao processar nota {md_file}: {e}")

    # 4. Reconstrói MEMORY_MAP.md e READMEs
    rebuild_memory_map_and_readmes(base)

    # 5. Sincroniza o índice SQLite FTS5 BM25
    from .indexer import MemorySearchEngine
    search_engine = MemorySearchEngine(base_dir=base)
    indexed_count = search_engine.sync_all()

    return {
        "success": True,
        "modified_files": modified_files,
        "total_entities": len(entity_index),
        "indexed_notes": indexed_count,
    }
