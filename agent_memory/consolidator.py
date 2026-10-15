from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from google.genai import types

from .config import MODEL_LIGHTWEIGHT, SECOND_BRAIN_DIR, get_genai_client
from .tools import MemoryToolManager
from .indexer import MemorySearchEngine


class MemoryConsolidator:
    """Responsável pela manutenção periódica, consolidação inteligente de notas extensas

    e versionamento automático (Git local) do Segundo Cérebro.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        tool_manager: MemoryToolManager | None = None,
        indexer: MemorySearchEngine | None = None,
    ) -> None:
        self.base_dir: Path = (base_dir or SECOND_BRAIN_DIR).resolve()
        self.tool_manager = tool_manager or MemoryToolManager(self.base_dir)
        self.indexer = indexer or MemorySearchEngine(base_dir=self.base_dir)

    def git_backup_and_commit(self, commit_message: str = "Auto memory update") -> tuple[bool, str]:
        """Executa um commit silencioso das alterações do Segundo Cérebro no Git local."""
        try:
            # Garante que o diretório é um repositório git local inicializado
            check_repo = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check_repo.returncode != 0:
                init_proc = subprocess.run(
                    ["git", "init"],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if init_proc.returncode != 0:
                    return False, f"Falha ao inicializar git no segundo cérebro: {init_proc.stderr.strip()}"

            # git add .
            add_proc = subprocess.run(
                ["git", "add", "."],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if add_proc.returncode != 0:
                return False, f"Falha no git add: {add_proc.stderr.strip()}"

            # Verifica se há algo staged para commit
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if not status_proc.stdout.strip():
                return True, "Nenhuma alteração pendente para commit."

            # git commit -m
            commit_proc = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )

            if commit_proc.returncode == 0:
                result_msg = f"Commit realizado com sucesso: '{commit_message}'"
                
                # Sincronização remota (git push) é opt-in via flag git_remote_sync em config/api_keys.json (desativada por padrão)
                git_remote_sync = False
                try:
                    import json
                    from .config import API_CONFIG_PATH
                    if API_CONFIG_PATH.exists():
                        cfg_data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
                        git_remote_sync = bool(cfg_data.get("git_remote_sync", False))
                except Exception:
                    git_remote_sync = False

                if git_remote_sync:
                    try:
                        remote_check = subprocess.run(
                            ["git", "remote", "get-url", "origin"],
                            cwd=str(self.base_dir),
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if remote_check.returncode == 0 and remote_check.stdout.strip():
                            push_proc = subprocess.run(
                                ["git", "push", "origin", "main"],
                                cwd=str(self.base_dir),
                                capture_output=True,
                                text=True,
                                timeout=25,
                            )
                            if push_proc.returncode == 0:
                                result_msg += " (Sincronizado com GitHub com sucesso)"
                            else:
                                result_msg += f" (Aviso: git push falhou: {push_proc.stderr.strip()[:100]})"
                    except Exception:
                        pass
                return True, result_msg
            return False, f"Falha no git commit: {commit_proc.stderr.strip()}"

        except FileNotFoundError:
            return False, "Git não está instalado ou acessível no PATH do sistema."
        except Exception as err:
            return False, f"Erro inesperado no backup Git: {err}"

    async def consolidate_long_notes(self, threshold_lines: int = 150) -> list[dict[str, Any]]:
        """Varre as notas do Segundo Cérebro e consolida via modelo leve qualquer nota

        que tenha acumulado mais de `threshold_lines` linhas, eliminando redundâncias.
        """
        consolidated_reports: list[dict[str, Any]] = []
        client = get_genai_client()

        for md_file in self.base_dir.rglob("*.md"):
            if ".cache" in md_file.parts or ".obsidian" in md_file.parts or md_file.name == "MEMORY_MAP.md":
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                lines = content.splitlines()
                if len(lines) <= threshold_lines:
                    continue

                rel_path = md_file.relative_to(self.base_dir).as_posix()
                print(f"[MemoryConsolidator] Consolidando nota extensa ({len(lines)} linhas): {rel_path}")

                prompt = f"""Você é o editor e arquivista do Segundo Cérebro.
Esta nota em Markdown acumulou muitas entradas e repetições ao longo do tempo ({len(lines)} linhas).
Sua tarefa é reescrever e consolidar o conteúdo:
- Mantenha TODOS os fatos, especificações técnicas, preferências e entidades importantes.
- Elimine dados repetidos, redundâncias e contradições antigas (mantendo a versão mais recente).
- Organize com títulos, tópicos e formatação limpa e legível no Obsidian.
- Não perca detalhes úteis.

CONTEÚDO ORIGINAL DA NOTA:
\"\"\"
{content}
\"\"\"

Responda APENAS com o texto consolidado em Markdown puro, sem blocos de código extras ao redor.
"""

                from .router import aroute_generate, ROUTE_BACKGROUND

                route_res = await aroute_generate(
                    route=ROUTE_BACKGROUND,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                    timeout_ms=30_000,
                    allow_live_overflow=True,
                )

                consolidated_text = (getattr(route_res.response, "text", "") or "").strip()
                if consolidated_text:
                    # Sobrescreve a nota com a versão consolidada
                    md_file.write_text(consolidated_text + "\n", encoding="utf-8")
                    self.indexer.index_single_note(rel_path)

                    consolidated_reports.append({
                        "path": rel_path,
                        "original_lines": len(lines),
                        "consolidated_lines": len(consolidated_text.splitlines()),
                        "status": "Consolidado com sucesso"
                    })

            except Exception as err:
                print(f"[MemoryConsolidator] Erro ao consolidar {md_file.name}: {err}")

        return consolidated_reports
