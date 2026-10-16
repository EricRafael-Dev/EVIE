"""core/decision_engine.py — Motor de Decisão Local JEV (System 1).

Executa decisões estruturadas ultrarrápidas em background para:
1. Filtragem inteligente de memória (evita chamadas redundantes a LLMs de background).
2. Roteamento dinâmico (AUTO -> SEARCH, SMART ou FAST).
3. Pré-aquecimento preditivo de visão (warm-up com captura silenciosa de tela).

Arquitetura:
- 100% não-bloqueante para asyncio e UI (inferência pesada executada via asyncio.to_thread).
- Singleton com inicialização preguiçosa (lazy loading).
- Integração nativa com `laya` e classificadores zero-shot estruturados em Pydantic.
- Camada determinística de micro-latência (<1ms) com regras em PT-BR.
- Resiliência Fail-Open: se o modelo local estiver ausente ou falhar, retorna
  um fallback seguro preservando o funcionamento normal da Evie / Mark LV.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Any, Literal, TypeVar
from pydantic import BaseModel, Field

logger = logging.getLogger("JEV-Local")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[JEV-Local] %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)

T = TypeVar("T", bound=BaseModel)


# ── Schemas Estruturados para Inferência System 1 ──────────────────────────────

class MemoryDecision(BaseModel):
    """Classificação estruturada do conteúdo da conversa para o Segundo Cérebro."""
    should_extract_memory: bool = Field(
        default=False,
        description="User message contains new personal facts, preferences, projects, relationships or rules to remember in the second brain vault, excluding greetings and generic requests"
    )
    suggested_folder: Literal["perfil", "projetos", "entidades", "regras_e_skills", "none"] = Field(
        default="none",
        description="Target vault folder: perfil, projetos, entidades, regras_e_skills, or none if no relevant fact"
    )


class RouteDecision(BaseModel):
    """Classificação para roteamento do tier LLM (AUTO)."""
    needs_web_search: bool = Field(
        default=False,
        description="Request requires real-time web search, latest internet news, weather forecast, stock prices or online web search, NOT local files or PC folders"
    )
    needs_deep_reasoning: bool = Field(
        default=False,
        description="Request requires deep reasoning, writing/debugging code, desktop apps, calculators, scripts, git commands, terminal execution or analytical planning"
    )


class VisionWarmupDecision(BaseModel):
    """Classificação para pré-aquecimento de captura de tela."""
    wants_visual_inspection: bool = Field(
        default=False,
        description="User asks to look at, inspect, view, or analyze the computer screen or display"
    )


# ── Motor Singleton JEV ────────────────────────────────────────────────────────

class DecisionEngine:
    """Motor de decisão System 1 local de ultrabaixa latência."""

    _instance: DecisionEngine | None = None
    _init_lock = threading.Lock()

    def __init__(self) -> None:
        self._laya_agent: Any = None
        self._is_loading = False
        self._load_failed = False
        self._load_lock = threading.Lock()
        self._warmup_done = False

    @classmethod
    def get_instance(cls) -> DecisionEngine:
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_model_loaded(self) -> Any:
        """Carrega o modelo Laya de forma lazy e thread-safe."""
        if self._laya_agent is not None:
            return self._laya_agent
        if self._load_failed:
            return None

        with self._load_lock:
            if self._laya_agent is not None:
                return self._laya_agent
            if self._load_failed:
                return None

            try:
                logger.info("Carregando modelo local System 1 (laya)...")
                t0 = time.monotonic()
                import laya

                # Tenta carregar o checkpoint multilingual ("ml") otimizado para PT-BR, com fallback para "typed-decisions"
                try:
                    agent = laya.load("ml", device="cpu")
                except Exception:
                    agent = laya.load("typed-decisions", backend="eager")
                self._laya_agent = agent
                elapsed = time.monotonic() - t0
                logger.info(f"Modelo local JEV carregado com sucesso em {elapsed:.2f}s.")
                return self._laya_agent
            except Exception as exc:
                self._load_failed = True
                logger.warning(f"Falha ao carregar modelo Laya local ({exc}). Ativando fallback heurístico seguro.")
                return None

    # ── Camada Heurística Rápida (PT-BR) ────────────────────────────────────────

    def _fast_heuristics_memory(self, text: str) -> tuple[MemoryDecision, dict[str, float]] | None:
        """Avaliação em sub-milissegundo para saudações e comandos comuns em PT-BR."""
        cleaned = text.strip().lower()

        # Saudações simples, perguntas de cortesia e comandos triviais que jamais contêm fatos para o Segundo Cérebro
        greeting_words = r"\b(oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|e\s+a[ií]|fala\s+a[ií]|salve|evie|jarvis|amig[ao]|tudo\s+bem(\s+com\s+voc[eê])?|como\s+(vai|voc[eê]\s+est[aá]|est[aá])|beleza|tranquilo|obrigad[oa]|valeu|show|perfeito|entendi|ok|certo|t[aá]\s+bom|tchau|at[eé]\s+(logo|mais|amanh[aã])|falou|abrir|fecha|pausa|desliga|mudo|cancela|para|sil[eê]ncio|que\s+horas\s+s[aã]o|qual\s+a\s+data\s+de\s+hoje|que\s+dia\s+[eé]\s+hoje)\b"
        tokens_only = re.sub(r"[!?,.;:()\-]", " ", cleaned).strip()
        remaining = re.sub(greeting_words, "", tokens_only).strip()
        if not remaining or len(remaining.split()) == 0:
            return (
                MemoryDecision(should_extract_memory=False, suggested_folder="none"),
                {"should_extract_memory": 0.99, "suggested_folder": 0.99},
            )

        trivial_patterns = [
            r"^(oi|ol[aá]|bom dia|boa tarde|boa noite|e a[ií]|fala a[ií]|salve)((\s*,\s*|\s+)(evie|jarvis|amig[ao]))?[!., ]*$",
            r"^(tudo bem|como vai|como est[aá]|beleza|tranquilo)((\s*,\s*|\s+)(evie|jarvis))?[?., ]*$",
            r"^(obrigad[oa]|valeu|show|perfeito|entendi|ok|beleza|certo|t[aá] bom)[!., ]*$",
            r"^(tchau|at[eé] logo|at[eé] mais|falou|at[eé] amanh[aã])[!., ]*$",
            r"^(abrir|fecha|pausa|desliga|mudo|cancela|para|sil[eê]ncio)[!., ]*$",
            r"^(que horas s[aã]o|qual a data de hoje|que dia [eé] hoje)[?., ]*$",
        ]
        for pattern in trivial_patterns:
            if re.match(pattern, cleaned):
                return (
                    MemoryDecision(should_extract_memory=False, suggested_folder="none"),
                    {"should_extract_memory": 0.99, "suggested_folder": 0.99},
                )

        # Expressões fortes de fatos pessoais / regras / projetos
        personal_patterns = [
            (r"(meu nome [eé]|me chamo|eu sou|moro em|trabalho como|minha idade|meu anivers[aá]rio)", "perfil"),
            (r"(meu hardware|minha gpu|minha cpu|minha placa de v[ií]deo|meu pc|meu monitor)", "perfil"),
            (r"(meu projeto|estou desenvolvendo|estou criando|o reposit[oó]rio|a branch|o software|c[oó]digo do mark|projeto mark)", "projetos"),
            (r"(sempre que eu falar|a partir de agora|regra permanente|nunca fa[cç]a|lembre-se de que)", "regras_e_skills"),
            (r"(meu amigo|minha amiga|meu chefe|meu colega|minha esposa|minha namorada|meu irm[aã]o)", "entidades"),
        ]
        for pattern, folder in personal_patterns:
            if re.search(pattern, cleaned):
                return (
                    MemoryDecision(should_extract_memory=True, suggested_folder=folder),  # type: ignore[arg-type]
                    {"should_extract_memory": 0.92, "suggested_folder": 0.88},
                )

        return None

    def _fast_heuristics_route(self, text: str) -> tuple[str, RouteDecision, dict[str, float]] | None:
        """Detecção rápida de roteamento (SEARCH / SMART / FAST)."""
        cleaned = text.strip().lower()

        # 1. Padrões explícitos de raciocínio profundo / código / git / terminal / calculadora
        smart_patterns = [
            r"\b(git\s+(push|pull|commit|init|status|checkout|branch|add|clone|merge|diff|log|remote))\b",
            r"\b(terminal|cmd|powershell|prompt|linha\s+de\s+comando)\b",
            r"\b(calculadora|calculator)\b",
            r"(execut(e|ar|a)|rod(e|ar|a))\s+.*?\b(comando|script|c[oó]digo|calculadora|app)\b",
            r"(cria|crie|faz|fa[cç]a|gerar?)\s+.*?\b(calculadora|script|c[oó]digo|programa|app)\b",
            r"(c[oó]digo|program|fun[cç][aã]o|classe|script|algoritmo|debug|refator)",
            r"(resolva|equa[cç][aã]o|calcule|derivada|integral|l[oó]gica|planeje|estrat[eé]gia)",
            r"(analise detalhadamente|compare os pr[oó]s e contras|fa[cç]a uma reda[cç][aã]o)",
            r"(arquitetura de software|banco de dados|migra[cç][aã]o|pull request)",
        ]
        for pattern in smart_patterns:
            if re.search(pattern, cleaned):
                return (
                    "SMART",
                    RouteDecision(needs_web_search=False, needs_deep_reasoning=True),
                    {"needs_web_search": 0.05, "needs_deep_reasoning": 0.95},
                )

        # 2. Detecção de arquivos / pastas locais (para não disparar busca na internet acidentalmente)
        local_file_patterns = [
            r"\b(arquivo|arquivos|pasta|pastas|diret[oó]rio|diret[oó]rios)\b",
            r"\b(no\s+meu\s+computador|no\s+computador|no\s+pc|no\s+desktop|na\s+[aá]rea\s+de\s+trabalho|nos\s+documentos|no\s+onedrive|no\s+disco)\b",
        ]
        is_local_file_query = any(re.search(p, cleaned) for p in local_file_patterns)

        # 3. Padrões explícitos de busca web (apenas quando não é busca de arquivos locais)
        if not is_local_file_query:
            search_patterns = [
                r"(pesquis|busqu|procur|google|na internet|web search)",
                r"(not[ií]cias|noticia de|previs[aã]o do tempo|temperatura em|clima em)",
                r"(cota[cç][aã]o|d[oó]lar|euro|a[cç][oõ]es da|quanto est[aá] o)",
                r"(quem ganhou|resultado do jogo|tabela do|plac[aá]r|campeonato)",
                r"(lan[cç]amento|pre[cç]o de|comprar|onde vende)",
            ]
            for pattern in search_patterns:
                if re.search(pattern, cleaned):
                    return (
                        "SEARCH",
                        RouteDecision(needs_web_search=True, needs_deep_reasoning=False),
                        {"needs_web_search": 0.95, "needs_deep_reasoning": 0.10},
                    )

        # 4. Diálogos conversacionais casuais / saudações -> FAST
        fast_dialog_patterns = [
            r"^(como\s+voc[eê]\s+est[aá]|tudo\s+bem(\s+com\s+voc[eê])?|como\s+vai|quem\s+[eé]\s+voc[eê]|qual\s+o?\s*seu\s+nome)[?., ]*$",
            r"^(oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|valeu|obrigad[oa]|tchau)[?., !]*$",
        ]
        for pattern in fast_dialog_patterns:
            if re.match(pattern, cleaned):
                return (
                    "FAST",
                    RouteDecision(needs_web_search=False, needs_deep_reasoning=False),
                    {"needs_web_search": 0.01, "needs_deep_reasoning": 0.01},
                )

        # 5. Comandos curtos ou saudações diretas -> FAST (desde que não sejam técnicos nem busca local)
        if len(cleaned.split()) <= 4 and not re.search(r"\?", cleaned) and not is_local_file_query:
            return (
                "FAST",
                RouteDecision(needs_web_search=False, needs_deep_reasoning=False),
                {"needs_web_search": 0.01, "needs_deep_reasoning": 0.01},
            )

        return None

    def _fast_heuristics_vision(self, text: str) -> tuple[bool, float] | None:
        """Detecção rápida de intenção de olhar a tela do usuário."""
        cleaned = text.strip().lower()

        # Gatilhos explícitos de visão de tela
        vision_triggers = [
            r"(olh(e|a)|vej(a|e)|ver|leia|l[eê]|analis(e|a)).*?\b(tela|ecr[aã]|monitor|display|print|screenshot)\b",
            r"\b(o que|oque)\b.*?\b(na tela|no ecr[aã]|no monitor|aberto)\b",
            r"\b(printa|tira um print|captura a tela|screenshot)\b",
            r"\b(d[aá] uma olhada|observa aqui|olha aqui|olha isso)\b",
        ]
        for pattern in vision_triggers:
            if re.search(pattern, cleaned):
                return True, 0.95

        # Se for comando de áudio puro ou sem relação visual
        pure_audio = [
            r"\b(aument(a|e)|abaix(a|e)|volume|mudo|para a m[uú]sica|toc(a|e))\b",
            r"^(ol[aá]|bom dia|boa tarde|boa noite|quem [eé] voc[eê])",
        ]
        for pattern in pure_audio:
            if re.search(pattern, cleaned):
                return False, 0.99

        return None

    # ── Execução de Inferência (Síncrona interna / Worker thread) ───────────────

    def _run_laya_inference(self, text: str, schema_cls: type[T]) -> tuple[T, dict[str, float]]:
        """Executa a inferência laya.decide em worker thread."""
        agent = self._ensure_model_loaded()
        if agent is None:
            raise RuntimeError("Modelo Laya não disponível")

        import laya
        res = laya.decide(agent, text, schema=schema_cls, return_details=True)
        values = res.values if hasattr(res, "values") else {}
        confidences = res.confidence if hasattr(res, "confidence") else {}

        # Mapeia valores em instância Pydantic validada
        parsed = schema_cls.model_validate(values)
        return parsed, confidences

    # ── APIs Públicas Assíncronas (Non-Blocking) ──────────────────────────────

    async def evaluate_memory(self, text: str) -> tuple[MemoryDecision, dict[str, float]]:
        """Avalia se um turno de diálogo deve ser persistido no Segundo Cérebro.

        Retorna: (MemoryDecision, probabilidades/confiança)
        """
        if not text or not text.strip():
            return MemoryDecision(should_extract_memory=False, suggested_folder="none"), {}

        # 1. Camada determinística instantânea (<1ms)
        fast_res = self._fast_heuristics_memory(text)
        if fast_res is not None:
            return fast_res

        # 2. Inferência JEV via worker thread para jamais bloquear o loop
        try:
            decision, confs = await asyncio.to_thread(
                self._run_laya_inference, text, MemoryDecision
            )
            return decision, confs
        except Exception as exc:
            logger.warning(f"Fallback no filtro de memória JEV: {exc}")
            # Fail-open seguro: se houver dúvida ou falha, permite a extração
            return (
                MemoryDecision(should_extract_memory=True, suggested_folder="perfil"),
                {"should_extract_memory": 0.65, "suggested_folder": 0.50},
            )

    async def evaluate_route(self, text: str) -> tuple[str, RouteDecision, dict[str, float]]:
        """Determina a melhor rota LLM (SEARCH, SMART ou FAST) para um prompt.

        Retorna: (tier_sugerido, RouteDecision, probabilidades/confiança)
        """
        if not text or not text.strip():
            return "FAST", RouteDecision(), {}

        # 1. Camada rápida
        fast_res = self._fast_heuristics_route(text)
        if fast_res is not None:
            return fast_res

        # 2. Inferência Laya
        try:
            decision, confs = await asyncio.to_thread(
                self._run_laya_inference, text, RouteDecision
            )
            if decision.needs_web_search:
                tier = "SEARCH"
            elif decision.needs_deep_reasoning:
                tier = "SMART"
            else:
                tier = "FAST"
            return tier, decision, confs
        except Exception as exc:
            logger.warning(f"Fallback no roteamento JEV: {exc}")
            # Fail-open: se falhar, FAST é seguro e econômico
            return "FAST", RouteDecision(), {"fallback": 1.0}

    def evaluate_route_sync(self, text: str) -> tuple[str, RouteDecision, dict[str, float]]:
        """Versão síncrona para código que não esteja rodando em corrotina."""
        if not text or not text.strip():
            return "FAST", RouteDecision(), {}

        fast_res = self._fast_heuristics_route(text)
        if fast_res is not None:
            return fast_res

        try:
            decision, confs = self._run_laya_inference(text, RouteDecision)
            if decision.needs_web_search:
                tier = "SEARCH"
            elif decision.needs_deep_reasoning:
                tier = "SMART"
            else:
                tier = "FAST"
            return tier, decision, confs
        except Exception:
            return "FAST", RouteDecision(), {"fallback": 1.0}

    async def evaluate_vision_warmup(self, text: str) -> tuple[bool, float]:
        """Avalia se o usuário quer inspecionar a tela para acionar pré-captura silenciosa.

        Retorna: (wants_visual_inspection: bool, confidence: float)
        """
        if not text or not text.strip():
            return False, 0.0

        # 1. Fast heuristics
        fast_res = self._fast_heuristics_vision(text)
        if fast_res is not None:
            return fast_res

        # 2. Laya inference
        try:
            decision, confs = await asyncio.to_thread(
                self._run_laya_inference, text, VisionWarmupDecision
            )
            prob = confs.get("wants_visual_inspection", 0.0)
            return decision.wants_visual_inspection, prob
        except Exception as exc:
            logger.debug(f"Vision warmup check fallback: {exc}")
            return False, 0.0

    async def evaluate(self, text: str, schema_cls: type[T]) -> tuple[T, dict[str, float]]:
        """Método público genérico para avaliar qualquer schema estruturado."""
        return await asyncio.to_thread(self._run_laya_inference, text, schema_cls)


def get_decision_engine() -> DecisionEngine:
    """Retorna a instância singleton do DecisionEngine."""
    return DecisionEngine.get_instance()
