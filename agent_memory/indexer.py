from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Any
from .config import DB_PATH, SECOND_BRAIN_DIR


class MemorySearchEngine:
    """Motor de busca lexical e híbrida local utilizando SQLite com FTS5 (Full-Text Search).

    Garante buscas em milissegundos sem consumo de tokens de API.
    """

    def __init__(self, db_path: Path | None = None, base_dir: Path | None = None) -> None:
        self.db_path: Path = (db_path or DB_PATH).resolve()
        self.base_dir: Path = (base_dir or SECOND_BRAIN_DIR).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Inicializa a tabela virtual SQLite FTS5 para indexação rápida."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    path UNINDEXED,
                    title,
                    content,
                    tokenize='porter unicode61'
                )
            """)
            conn.commit()

    def sync_all(self) -> int:
        """Varre o diretório second_brain/ e sincroniza todas as notas Markdown com o índice FTS5.

        :return: Total de notas indexadas com sucesso.
        """
        indexed_count = 0
        notes_data: list[tuple[str, str, str]] = []

        if not self.base_dir.exists():
            return 0

        for md_file in self.base_dir.rglob("*.md"):
            # Ignora pastas de cache ou internas
            if ".cache" in md_file.parts or ".obsidian" in md_file.parts:
                continue

            try:
                rel_path = md_file.relative_to(self.base_dir).as_posix()
                content = md_file.read_text(encoding="utf-8", errors="replace").strip()
                if not content:
                    continue

                # Extrai o primeiro título como metadado se existir
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else md_file.stem

                notes_data.append((rel_path, title, content))
            except Exception as err:
                print(f"[MemorySearchEngine] Erro ao ler nota {md_file}: {err}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Limpa e repovla o índice de forma atômica
            cursor.execute("DELETE FROM notes_fts")
            cursor.executemany(
                "INSERT INTO notes_fts(path, title, content) VALUES (?, ?, ?)",
                notes_data
            )
            conn.commit()
            indexed_count = len(notes_data)

        return indexed_count

    def index_single_note(self, relative_path: str) -> bool:
        """Indexa ou atualiza uma nota individualmente no FTS5."""
        clean_rel = relative_path.strip().lstrip("/\\").replace("\\", "/")
        file_path = self.base_dir / clean_rel

        if not file_path.exists() or file_path.is_dir():
            return False

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace").strip()
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else file_path.stem

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM notes_fts WHERE path = ?", (clean_rel,))
                cursor.execute(
                    "INSERT INTO notes_fts(path, title, content) VALUES (?, ?, ?)",
                    (clean_rel, title, content)
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"[MemorySearchEngine] Erro ao indexar {clean_rel}: {e}")
            return False

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Executa busca textual completa (FTS5) e retorna trechos relevantes ordenados por BM25.

        :param query: Termos de pesquisa do usuário.
        :param limit: Quantidade máxima de notas a retornar.
        :return: Lista com {path, title, snippet, rank}.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # Sanitiza a query para sintaxe segura do FTS5
        sanitized_terms = re.findall(r"\w+", clean_query)
        if not sanitized_terms:
            return []
        
        # Cria consulta booleana com match por prefixo (*), permitindo flexibilidade
        fts_expr = " OR ".join([f'"{term}"*' for term in sanitized_terms])

        sql = """
            SELECT 
                path, 
                title, 
                snippet(notes_fts, 2, '<b>', '</b>', '...', 24) AS match_snippet,
                bm25(notes_fts) AS rank
            FROM notes_fts 
            WHERE notes_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
        """

        results: list[dict[str, Any]] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (fts_expr, limit))
                for row in cursor.fetchall():
                    results.append({
                        "path": row["path"],
                        "title": row["title"],
                        "snippet": row["match_snippet"],
                        "score": round(float(row["rank"]), 4)
                    })
        except sqlite3.OperationalError:
            # Fallback caso a expressão gere erro de operador no FTS5
            try:
                simple_expr = f'"{sanitized_terms[0]}"*'
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, (simple_expr, limit))
                    for row in cursor.fetchall():
                        results.append({
                            "path": row["path"],
                            "title": row["title"],
                            "snippet": row["match_snippet"],
                            "score": round(float(row["rank"]), 4)
                        })
            except Exception:
                return []

        return results
