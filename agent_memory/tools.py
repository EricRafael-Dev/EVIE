from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any
from .config import SECOND_BRAIN_DIR, MEMORY_MAP_PATH


class MemoryPathSecurityError(Exception):
    """Exceção levantada quando há tentativa de Path Traversal fora do second_brain."""
    pass


class MemoryToolManager:
    """Gerenciador de leitura segura, escrita atômica com locks por arquivo,

    expansão de grafo de 1 salto (WikiLinks) e geração de índice para o Segundo Cérebro.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir: Path = (base_dir or SECOND_BRAIN_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_locks: dict[str, threading.Lock] = {}
        self._locks_mutex = threading.Lock()

    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """Obtém ou cria um Lock dedicado para o arquivo específico, evitando race conditions concorrentes."""
        norm_key = str(Path(file_path).resolve())
        with self._locks_mutex:
            if norm_key not in self._file_locks:
                self._file_locks[norm_key] = threading.Lock()
            return self._file_locks[norm_key]

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolve o caminho relativo e valida estritamente contra Path Traversal."""
        cleaned = relative_path.strip().lstrip("/\\")
        if not cleaned:
            raise ValueError("O caminho relativo da nota não pode ser vazio.")

        target = (self.base_dir / cleaned).resolve()

        # Validação estrita de contenção no diretório base
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            raise MemoryPathSecurityError(
                f"Violação de segurança: Tentativa de acesso fora do diretório de memória: {relative_path}"
            )

        return target

    def get_memory_map(self) -> str:
        """Lê e retorna o conteúdo do MEMORY_MAP.md (Índice Mestre semântico)."""
        map_path = MEMORY_MAP_PATH.resolve()
        if not map_path.exists():
            return self.rebuild_memory_map()
        try:
            return map_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Erro ao ler MEMORY_MAP.md: {e}"

    def rebuild_memory_map(self) -> str:
        """Varre second_brain/ (perfil/, projetos/, entidades/, regras_e_skills/),

        extrai títulos '#'/ '##' e tags, atualiza second_brain/MEMORY_MAP.md e retorna
        uma versão compacta (<= 600 chars) para injeção no prompt do sistema.
        """
        categories = ["perfil", "projetos", "entidades", "regras_e_skills"]
        map_lines = [
            "# 🧠 ÍNDICE MESTRE DO SEGUNDO CÉREBRO (MEMORY_MAP.md)",
            "",
            "> [!IMPORTANT]",
            "> **DIRETIVA DE LAZY LOADING PARA A IA:**",
            "> Utilize este catálogo semântico e invoque `read_memory_note(target_file)` ou",
            "> `search_second_brain(query)` **sob demanda** quando necessitar de contexto profundo.",
            "",
            "---",
            "",
            "## 🗺️ Mapa Estrutural de Notas",
            ""
        ]

        compact_parts = ["[SEGUNDO CÉREBRO]"]

        for cat in categories:
            cat_dir = self.base_dir / cat
            if not cat_dir.exists():
                cat_dir.mkdir(parents=True, exist_ok=True)

            md_files = sorted([
                f for f in cat_dir.rglob("*.md")
                if ".cache" not in f.parts and ".obsidian" not in f.parts and f.is_file()
            ])

            map_lines.append(f"### 📁 `{cat}/`")
            cat_compact_entries = []

            for md_file in md_files:
                try:
                    rel_p = md_file.relative_to(self.base_dir).as_posix()
                    content = md_file.read_text(encoding="utf-8", errors="replace")
                    
                    # Extrai títulos
                    titles = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
                    main_title = titles[0].strip() if titles else md_file.stem
                    sub_titles = [t.strip() for t in titles[1:4]]
                    
                    # Extrai tags (#palavra)
                    tags = re.findall(r"(?:^|\s)#([a-zA-Z0-9_\-]+)", content)
                    tags_str = f" [tags: {', '.join(set(tags[:3]))}]" if tags else ""

                    subs_str = f" ({', '.join(sub_titles)})" if sub_titles else ""
                    map_lines.append(f"- **`{rel_p}`**: {main_title}{subs_str}{tags_str}")
                    cat_compact_entries.append(md_file.stem)
                except Exception as _e:
                    map_lines.append(f"- **`{md_file.name}`**: (Erro ao ler: {_e})")

            if cat_compact_entries:
                compact_parts.append(f"{cat.title()}: {', '.join(cat_compact_entries[:4])}")
            map_lines.append("")

        map_lines.extend([
            "---",
            "",
            "## ⚡ Regras de Leitura e Escrita",
            "1. **Buscar primeiro:** Invoque `search_second_brain(query)` antes de ler notas aleatórias.",
            "2. **Leitura específica:** Use `read_memory_note(target_file)` com o caminho exato.",
            "3. **Links Obsidian:** Formate referências entre notas como `[[pasta/nome]]`."
        ])

        full_map_text = "\n".join(map_lines) + "\n"
        
        # Gravação atômica do MEMORY_MAP.md
        lock = self._get_file_lock(str(MEMORY_MAP_PATH))
        with lock:
            tmp_map = MEMORY_MAP_PATH.with_suffix(".tmp")
            tmp_map.write_text(full_map_text, encoding="utf-8")
            os.replace(tmp_map, MEMORY_MAP_PATH)

        # Constrói versão compacta (<= 600 chars) para o prompt
        compact_str = " | ".join(compact_parts)
        if len(compact_str) > 550:
            compact_str = compact_str[:547] + "..."
        return compact_str

    def read_memory_note(self, relative_path: str) -> str:
        """Lê o conteúdo de uma nota específica em Markdown dentro de second_brain/."""
        try:
            safe_file = self._resolve_safe_path(relative_path)
            if not safe_file.exists() and not relative_path.endswith(".md"):
                safe_file = self._resolve_safe_path(f"{relative_path}.md")

            if not safe_file.exists():
                # Busca resiliente por nome de arquivo em subpastas caso a IA omita o prefixo da pasta
                candidate_name = safe_file.name if safe_file.name.endswith(".md") else f"{safe_file.name}.md"
                matches = [
                    f for f in self.base_dir.rglob(candidate_name)
                    if ".cache" not in f.parts and ".obsidian" not in f.parts and f.is_file()
                ]
                if matches:
                    safe_file = matches[0]
                else:
                    return f"Nota não encontrada: '{relative_path}'."

            if safe_file.is_dir():
                return f"O caminho '{relative_path}' é um diretório, não um arquivo de nota."

            lock = self._get_file_lock(str(safe_file))
            with lock:
                content = safe_file.read_text(encoding="utf-8")
            return content if content.strip() else f"Nota '{relative_path}' está vazia."
        except MemoryPathSecurityError as sec_err:
            return f"Erro de Segurança: {sec_err}"
        except Exception as err:
            return f"Erro ao ler nota '{relative_path}': {err}"

    def search_second_brain(self, query: str, include_linked: bool = True, limit: int = 3) -> str:
        """Executa busca híbrida/FTS5 BM25 nas notas do Segundo Cérebro.

        Quando include_linked=True, extrai WikiLinks [[...]] dos trechos encontrados
        e anexa o resumo/cabeçalho das notas linkadas (expansão de grafo de 1 salto).
        """
        try:
            from .indexer import MemorySearchEngine
            engine = MemorySearchEngine(base_dir=self.base_dir)
            results = engine.search(query, limit=limit)
            if not results:
                return f"Nenhum resultado encontrado para a busca '{query}' no Segundo Cérebro."

            output_lines = [f"Resultados da busca por '{query}':"]
            linked_candidates = set()

            for idx, res in enumerate(results, 1):
                p = res.get("path", "")
                t = res.get("title", "")
                s = res.get("snippet", "")
                output_lines.append(f"\n{idx}. [{t}] (arquivo: {p}):\n   {s}")

                if include_linked:
                    # Encontra WikiLinks no snippet ou lê trecho da nota
                    found_links = re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", s)
                    # Também checa na nota em si se o snippet foi pequeno
                    try:
                        safe_f = self._resolve_safe_path(p)
                        if safe_f.exists():
                            raw = safe_f.read_text(encoding="utf-8", errors="ignore")
                            found_links.extend(re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", raw[:2000]))
                    except Exception:
                        pass
                    for lk in found_links:
                        clean_link = lk.strip()
                        if clean_link and clean_link != p:
                            linked_candidates.add(clean_link)

            # Expansão de grafo de 1 salto (1-hop)
            if include_linked and linked_candidates:
                output_lines.append("\n--- [GRAFO DE CONTEXTO 1-HOP: NOTAS LINKADAS] ---")
                for link_name in list(linked_candidates)[:4]:
                    linked_content = self.read_memory_note(link_name)
                    if not linked_content.startswith("Nota não encontrada") and not linked_content.startswith("Erro"):
                        summary_snippet = " ".join(linked_content.splitlines()[:4])[:220]
                        output_lines.append(f"- [[{link_name}]]: {summary_snippet}...")

            return "\n".join(output_lines)
        except Exception as e:
            return f"Erro ao pesquisar no Segundo Cérebro: {e}"

    def update_or_create_note(
        self, relative_path: str, content: str, mode: str = "append"
    ) -> str:
        """Cria ou atualiza uma nota de forma idempotente, atômica e protegida por Lock de arquivo.

        :param relative_path: Caminho relativo dentro de second_brain/ (ex: 'perfil/usuario.md').
        :param content: Conteúdo a ser gravado ou anexado.
        :param mode: 'append' (anexa ao final) ou 'overwrite' (sobrescreve todo o arquivo).
        :return: Mensagem de status confirmando o resultado da operação.
        """
        try:
            if not relative_path.endswith(".md"):
                relative_path = f"{relative_path}.md"

            safe_file = self._resolve_safe_path(relative_path)
            safe_file.parent.mkdir(parents=True, exist_ok=True)

            text_to_write = content.strip()
            if not text_to_write:
                return f"Aviso: Conteúdo vazio fornecido para '{relative_path}'. Nenhuma alteração feita."

            # Auto-Linker: Injeta WikiLinks inline para entidades conhecidas
            from .graph_linker import inject_inline_wikilinks, append_related_links_section, rebuild_memory_map_and_readmes
            stem = safe_file.stem
            if stem.upper() != "MEMORY_MAP":
                text_to_write = inject_inline_wikilinks(text_to_write, current_stem=stem)

            lock = self._get_file_lock(str(safe_file))
            with lock:
                if mode == "append" and safe_file.exists():
                    current_text = safe_file.read_text(encoding="utf-8")
                    # Evita duplicação exata imediata
                    if text_to_write in current_text:
                        return f"Nota '{relative_path}' já continha essa informação. Nenhuma duplicação feita."

                    separator = "\n\n" if current_text.strip() else ""
                    new_full_content = current_text.rstrip() + separator + text_to_write + "\n"
                    action_desc = "anexado com sucesso"
                else:
                    new_full_content = text_to_write + "\n"
                    action_desc = "gravado/sobrescrito com sucesso"

                # Assegura seção de conexões se for nota de conteúdo
                if stem.upper() != "MEMORY_MAP" and not stem.lower().startswith("readme"):
                    new_full_content = append_related_links_section(
                        content=new_full_content,
                        current_stem=stem,
                        related_stems=["MEMORY_MAP"],
                    )

                # Gravação atômica
                tmp_file = safe_file.with_suffix(".tmp")
                tmp_file.write_text(new_full_content, encoding="utf-8")
                os.replace(tmp_file, safe_file)

            # Mantém MEMORY_MAP.md sincronizado se não for o próprio mapa
            if stem.upper() != "MEMORY_MAP":
                try:
                    rebuild_memory_map_and_readmes(self.base_dir)
                except Exception as _m_err:
                    print(f"[MemoryToolManager] Aviso ao atualizar mapa: {_m_err}")

            return f"Sucesso: Conteúdo {action_desc} na nota '{relative_path}'."
        except MemoryPathSecurityError as sec_err:
            return f"Erro de Segurança: {sec_err}"
        except Exception as err:
            return f"Erro ao atualizar nota '{relative_path}': {err}"


_default_tools = MemoryToolManager()

def get_second_brain_tools() -> MemoryToolManager:
    return _default_tools

def search_second_brain(query: str, include_linked: bool = True, limit: int = 3) -> str:
    return _default_tools.search_second_brain(query, include_linked=include_linked, limit=limit)

def read_memory_note(relative_path: str) -> str:
    return _default_tools.read_memory_note(relative_path)

def rebuild_memory_map() -> str:
    return _default_tools.rebuild_memory_map()

def get_memory_map() -> str:
    return _default_tools.get_memory_map()

