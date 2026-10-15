from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, NamedTuple
from google import genai
from google.genai import types

# Diretório base do projeto
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"
LEDGER_PATH = CONFIG_DIR / "quota_ledger.json"

# Rótulo de rotas de processamento
ROUTE_BACKGROUND = "background"  # Extração de memória, resumos, consolidação (somente modelos 500 RPD)
ROUTE_FAST = "fast"              # Classificações rápidas, decisões curtas (Live -> 3.5 Lite -> 3.1 Lite)
ROUTE_REASONING = "reasoning"    # Código, leitura de tela, planejamento complexo (3.8 -> 3.7 -> 3.6 -> ...)
ROUTE_SEARCH = "search"          # Busca com grounding (somente modelos REST compatíveis)
ROUTE_AUTO = "auto"              # Roteamento inteligente JEV (System 1)

# Limite mínimo de deadline exigido pela API do Gemini
DEFAULT_TIMEOUT_MS = 15_000
MIN_TIMEOUT_MS = 10_000


class ModelSpec(NamedTuple):
    name: str
    rpm: int
    tpm: int
    rpd: int
    category: str


# Catálogo exato baseado no diagnóstico de cotas da conta
MODEL_CATALOG: dict[str, ModelSpec] = {
    "gemini-3.5-flash-lite": ModelSpec("gemini-3.5-flash-lite", rpm=15, tpm=250_000, rpd=500, category="lite"),
    "gemini-3.1-flash-lite": ModelSpec("gemini-3.1-flash-lite", rpm=15, tpm=250_000, rpd=500, category="lite"),
    "gemini-3.1-flash-lite-preview": ModelSpec("gemini-3.1-flash-lite-preview", rpm=15, tpm=250_000, rpd=500, category="lite"),
    "gemini-flash-lite-latest": ModelSpec("gemini-flash-lite-latest", rpm=15, tpm=250_000, rpd=500, category="lite"),

    "gemini-3.8-flash": ModelSpec("gemini-3.8-flash", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-3.7-flash": ModelSpec("gemini-3.7-flash", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-3.6-flash": ModelSpec("gemini-3.6-flash", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-3.5-flash": ModelSpec("gemini-3.5-flash", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-3-flash-preview": ModelSpec("gemini-3-flash-preview", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-2.5-flash": ModelSpec("gemini-2.5-flash", rpm=5, tpm=250_000, rpd=20, category="premium"),
    "gemini-2.5-flash-lite": ModelSpec("gemini-2.5-flash-lite", rpm=10, tpm=250_000, rpd=20, category="premium"),
}

# Definição unificada das cascatas de roteamento (fonte única da verdade)
LADDERS: dict[str, tuple[str, ...]] = {
    ROUTE_BACKGROUND: (
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
    ),
    ROUTE_FAST: (
        "live",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-lite-latest",
    ),
    ROUTE_REASONING: (
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "live",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ),
    ROUTE_SEARCH: (
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
    ),
}

# Aliases de compatibilidade para tiers legados e rotas alternativas
LADDERS["smart"] = LADDERS[ROUTE_REASONING]
LADDERS["reasoning"] = LADDERS[ROUTE_REASONING]
LADDERS["fast"] = LADDERS[ROUTE_FAST]
LADDERS["search"] = LADDERS[ROUTE_SEARCH]
LADDERS["background"] = LADDERS[ROUTE_BACKGROUND]
LADDERS[ROUTE_AUTO] = LADDERS[ROUTE_FAST]
LADDERS["auto"] = LADDERS[ROUTE_FAST]


def _extract_prompt_text(contents: Any) -> str:
    """Extrai texto representativo de contents (str, list de Parts, dict, etc.) para o motor de decisão JEV."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, (list, tuple)):
        parts = []
        for c in contents:
            if isinstance(c, str):
                parts.append(c)
            elif hasattr(c, "text") and c.text:
                parts.append(str(c.text))
            elif isinstance(c, dict) and "text" in c:
                parts.append(str(c["text"]))
        return " ".join(parts)
    if hasattr(contents, "text") and contents.text:
        return str(contents.text)
    return str(contents)


class RouteResult(NamedTuple):
    response: Any
    model_used: str
    degraded: bool
    fallback_count: int


class QuotaLedger:
    """Gerencia estado persistente de consumo diário (RPD), cotas por minuto (RPM)
    e períodos de suspensão (cooldown) por modelo com debounced atomic save.
    """

    def __init__(self, ledger_file: Path = LEDGER_PATH) -> None:
        self.ledger_file = ledger_file
        self._lock = threading.RLock()
        self._cooldown: dict[str, float] = {}  # modelo -> timestamp unix até expirar
        self._sliding_rpm: dict[str, list[float]] = {}  # modelo -> timestamps de requisições recentes
        self._daily_counts: dict[str, int] = {}
        self._current_date: str = ""
        self._dirty: bool = False
        self._last_save_time: float = 0.0
        self._load()
        import atexit
        atexit.register(self.flush)

    def _get_pacific_date(self) -> str:
        # A API Gemini reinicia o RPD à meia-noite no horário do Pacífico (respeitando PDT/PST via ZoneInfo)
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

    def _get_pacific_midnight_timestamp(self) -> float:
        now_la = datetime.now(ZoneInfo("America/Los_Angeles"))
        next_day = now_la.date() + timedelta(days=1)
        next_midnight_la = datetime(
            next_day.year, next_day.month, next_day.day, 0, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")
        )
        return next_midnight_la.timestamp()

    def _load(self) -> None:
        with self._lock:
            cur_date = self._get_pacific_date()
            self._current_date = cur_date
            if self.ledger_file.exists():
                try:
                    data = json.loads(self.ledger_file.read_text(encoding="utf-8"))
                    saved_date = data.get("date", "")
                    if saved_date == cur_date:
                        self._daily_counts = data.get("daily_counts", {})
                    else:
                        self._daily_counts = {}

                    # Restaura cooldowns válidos
                    now = time.time()
                    for model, until in data.get("cooldowns", {}).items():
                        if until > now:
                            self._cooldown[model] = until
                except Exception:
                    self._daily_counts = {}
                    self._cooldown = {}

    def _save(self, force: bool = False) -> None:
        with self._lock:
            now = time.time()
            if not force:
                self._dirty = True
                if now - self._last_save_time < 10.0:
                    return

            valid_cooldowns = {m: u for m, u in self._cooldown.items() if u > now}
            data = {
                "date": self._current_date,
                "daily_counts": self._daily_counts,
                "cooldowns": valid_cooldowns,
                "updated_at": now,
            }
            tmp_file = self.ledger_file.with_suffix(".tmp")
            try:
                tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                tmp_file.replace(self.ledger_file)
                self._dirty = False
                self._last_save_time = now
            except Exception:
                pass

    def flush(self) -> None:
        """Força a persistência atômica caso haja alterações pendentes."""
        with self._lock:
            if self._dirty:
                self._save(force=True)

    def is_available(self, model: str) -> bool:
        """Verifica se o modelo está livre de cooldown e dentro dos limites teóricos."""
        with self._lock:
            now = time.time()
            until = self._cooldown.get(model, 0.0)
            if until and now < until:
                return False
            if model == "live":
                return True

            # Verifica contagem diária se o modelo tiver limite cadastrado
            spec = MODEL_CATALOG.get(model)
            if spec:
                cur_date = self._get_pacific_date()
                if self._current_date != cur_date:
                    self._current_date = cur_date
                    self._daily_counts.clear()
                    self._save(force=True)
                used_today = self._daily_counts.get(model, 0)
                if used_today >= spec.rpd:
                    # Marca como esgotado até a virada do dia
                    self._cooldown[model] = self._get_pacific_midnight_timestamp()
                    self._save(force=True)
                    return False
            return True

    def record_success(self, model: str) -> None:
        """Registra requisição bem-sucedida atualizando RPM e RPD."""
        if model == "live":
            return
        with self._lock:
            now = time.time()
            cur_date = self._get_pacific_date()
            if self._current_date != cur_date:
                self._current_date = cur_date
                self._daily_counts.clear()

            self._daily_counts[model] = self._daily_counts.get(model, 0) + 1

            # Janela deslizante de 60 segundos
            timestamps = self._sliding_rpm.setdefault(model, [])
            timestamps.append(now)
            cutoff = now - 60.0
            self._sliding_rpm[model] = [t for t in timestamps if t > cutoff]

            self._save(force=False)

    def mark_exhausted_daily(self, model: str) -> None:
        """Atingiu quota diaria (PerDay) - suspende ate a meia-noite do Pacifico (~04:00 BRT)."""
        with self._lock:
            spec = MODEL_CATALOG.get(model)
            if spec:
                self._daily_counts[model] = max(self._daily_counts.get(model, 0), spec.rpd)
            until = self._get_pacific_midnight_timestamp()
            self._cooldown[model] = until
            self._save(force=True)
            print(f"[ModelRouter] [RPD-EXHAUSTED] {model}: cota diaria esgotada. Em suspensao ate virada do Pacifico.")

    def mark_rate_limited_minute(self, model: str, retry_delay_seconds: float = 60.0) -> None:
        """Atingiu limite por minuto (PerMinute / RPM) - suspende pelo tempo de retryDelay."""
        with self._lock:
            wait = max(5.0, retry_delay_seconds)
            self._cooldown[model] = time.time() + wait
            self._save(force=True)
            print(f"[ModelRouter] [RPM-LIMIT] {model}: RPM atingido. Pausado por {wait:.1f}s.")

    def mark_unavailable(self, model: str, seconds: float = 1800.0) -> None:
        """503 / 504 / Deadline - descanso temporario de 30 minutos."""
        with self._lock:
            self._cooldown[model] = time.time() + seconds
            self._save(force=True)
            print(f"[ModelRouter] [UNAVAILABLE] {model}: indisponivel/timeout. Suspenso por {seconds / 60:.0f} min.")

    def mark_gone(self, model: str, seconds: float = 21600.0) -> None:
        """404 / 403 / Modelo inexistente ou nao suportado - suspende por 6 horas."""
        with self._lock:
            self._cooldown[model] = time.time() + seconds
            self._save(force=True)
            print(f"[ModelRouter] [GONE] {model}: nao suportado ou sem permissao. Desativado por 6h.")

    def get_status(self) -> dict[str, Any]:
        """Retorna snapshot do estado atual de todas as cotas para o Dashboard/Logs."""
        with self._lock:
            now = time.time()
            status: dict[str, Any] = {}
            for name, spec in MODEL_CATALOG.items():
                used = self._daily_counts.get(name, 0)
                cd = self._cooldown.get(name, 0.0)
                is_cd = cd > now
                remaining_sec = max(0.0, cd - now) if is_cd else 0.0
                status[name] = {
                    "category": spec.category,
                    "rpd_limit": spec.rpd,
                    "rpd_used": used,
                    "rpd_available": max(0, spec.rpd - used),
                    "in_cooldown": is_cd,
                    "cooldown_remaining_seconds": round(remaining_sec, 1),
                }
            return status


# Singleton global de controle de quotas
ledger = QuotaLedger()


def get_api_key() -> str:
    """Obtém a chave de API de forma segura."""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    if API_CONFIG_PATH.exists():
        try:
            data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            k = str(data.get("gemini_api_key") or "").strip()
            if k:
                return k
        except Exception:
            pass
    return ""


def get_genai_client(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> genai.Client:
    key = get_api_key()
    if not key:
        raise RuntimeError("Nenhuma chave Gemini configurada (gemini_api_key ausente).")
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=max(MIN_TIMEOUT_MS, int(timeout_ms))),
    )


def classify_api_error(error: Exception) -> tuple[str, float]:
    """Analisa o erro retornado pelo SDK e classifica em:

    'per_day', 'per_minute', 'unavailable', 'gone' ou 'generic',
    junto com o delay sugerido se houver.
    """
    msg = str(error)
    low = msg.lower()

    if "429" in msg or "resource_exhausted" in low:
        # Tenta verificar se é cota diária ou cota por minuto
        if "perday" in low or "per_day" in low or "daily" in low:
            return "per_day", 0.0

        # Tenta extrair retryDelay se fornecido pelo Google
        retry_delay = 60.0
        if "retry in" in low:
            try:
                part = low.split("retry in")[1].split("s")[0].strip()
                retry_delay = float(part)
            except Exception:
                pass
        return "per_minute", retry_delay

    if "503" in msg or "504" in msg or "unavailable" in low or "deadline_exceeded" in low:
        return "unavailable", 1800.0

    if "404" in msg or "not found" in low or "is not supported" in low or "permission" in low or "403" in msg:
        return "gone", 21600.0

    return "generic", 0.0


async def aroute_generate(
    route: str,
    contents: Any,
    config: Any = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    allow_live_overflow: bool = True,
) -> RouteResult:
    """Executa a chamada assíncrona respeitando a cascata da rota especificada,

    isolando cotas e fazendo fallback automático.
    """
    if route.lower() == ROUTE_AUTO:
        try:
            from core.decision_engine import get_decision_engine
            engine = get_decision_engine()
            text_prompt = _extract_prompt_text(contents)
            tier, decision, confs = await engine.evaluate_route(text_prompt)
            if tier == "SEARCH":
                route = ROUTE_SEARCH
            elif tier == "SMART":
                route = ROUTE_REASONING
            else:
                route = ROUTE_FAST
            try:
                print(f"[JEV-Local] Roteamento AUTO dinamico -> {route} (tier={tier})")
            except Exception:
                pass
        except Exception as jev_err:
            try:
                print(f"[JEV-Local] Erro no roteamento AUTO: {jev_err} -> fallback para FAST")
            except Exception:
                pass
            route = ROUTE_FAST

    ladder = LADDERS.get(route, LADDERS[ROUTE_BACKGROUND])
    client = get_genai_client(timeout_ms=timeout_ms)
    fallback_count = 0

    for model in ladder:
        if model == "live":
            # Caso seja o passo Live, delega para o executor Live do core/gemini se disponível de forma assíncrona
            try:
                from core import gemini as core_gemini
                reply = await asyncio.to_thread(
                    core_gemini._live_call, contents, config, timeout_ms, get_api_key()
                )
                if reply is not None:
                    return RouteResult(response=reply, model_used="gemini-3.8-live", degraded=True, fallback_count=fallback_count)
            except Exception as live_err:
                print(f"[ModelRouter] Fallback Live na rota {route} falhou: {live_err}")
                fallback_count += 1
                continue

        if not ledger.is_available(model):
            fallback_count += 1
            continue

        try:
            kwargs: dict[str, Any] = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config

            response = await client.aio.models.generate_content(**kwargs)
            if response and (getattr(response, "text", None) or getattr(response, "candidates", None)):
                ledger.record_success(model)
                is_degraded = (route in (ROUTE_REASONING, "smart") and "lite" in model)
                return RouteResult(
                    response=response,
                    model_used=model,
                    degraded=is_degraded,
                    fallback_count=fallback_count,
                )
        except Exception as exc:
            fallback_count += 1
            err_type, delay = classify_api_error(exc)
            if err_type == "per_day":
                ledger.mark_exhausted_daily(model)
            elif err_type == "per_minute":
                ledger.mark_rate_limited_minute(model, retry_delay_seconds=delay)
            elif err_type == "unavailable":
                ledger.mark_unavailable(model)
            elif err_type == "gone":
                ledger.mark_gone(model)
            else:
                print(f"[ModelRouter] {model} retornou erro: {type(exc).__name__}: {str(exc)[:120]}")

    # Se a rota de background esgotou todos os Lites e o Live é permitido como último recurso
    if route == ROUTE_BACKGROUND and allow_live_overflow:
        try:
            from core import gemini as core_gemini
            print("[ModelRouter] 🔄 Background esgotou Lites. Utilizando Live como último recurso...")
            reply = await asyncio.to_thread(
                core_gemini._live_call, contents, config, timeout_ms, get_api_key()
            )
            if reply is not None:
                return RouteResult(response=reply, model_used="gemini-3.8-live(overflow)", degraded=True, fallback_count=fallback_count)
        except Exception as overflow_err:
            print(f"[ModelRouter] Overflow Live falhou: {overflow_err}")

    raise RuntimeError(f"Todos os modelos da rota '{route}' falharam ou esgotaram suas cotas.")


def route_generate(
    route: str,
    contents: Any,
    config: Any = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    allow_live_overflow: bool = True,
) -> RouteResult:
    """Versão síncrona de rotação com fallback."""
    if route.lower() == ROUTE_AUTO:
        try:
            from core.decision_engine import get_decision_engine
            engine = get_decision_engine()
            text_prompt = _extract_prompt_text(contents)
            tier, decision, confs = engine.evaluate_route_sync(text_prompt)
            if tier == "SEARCH":
                route = ROUTE_SEARCH
            elif tier == "SMART":
                route = ROUTE_REASONING
            else:
                route = ROUTE_FAST
            try:
                print(f"[JEV-Local] Roteamento sincrono AUTO dinamico -> {route} (tier={tier})")
            except Exception:
                pass
        except Exception as jev_err:
            try:
                print(f"[JEV-Local] Erro no roteamento sincrono AUTO: {jev_err} -> fallback para FAST")
            except Exception:
                pass
            route = ROUTE_FAST

    ladder = LADDERS.get(route, LADDERS[ROUTE_FAST])
    client = get_genai_client(timeout_ms=timeout_ms)
    fallback_count = 0

    for model in ladder:
        if model == "live":
            try:
                from core import gemini as core_gemini
                reply = core_gemini._live_call(contents, config, timeout_ms, get_api_key())
                if reply is not None:
                    return RouteResult(response=reply, model_used="gemini-3.8-live", degraded=False, fallback_count=fallback_count)
            except Exception:
                fallback_count += 1
                continue

        if not ledger.is_available(model):
            fallback_count += 1
            continue

        try:
            kwargs: dict[str, Any] = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config

            response = client.models.generate_content(**kwargs)
            if response and (getattr(response, "text", None) or getattr(response, "candidates", None)):
                ledger.record_success(model)
                is_degraded = (route in (ROUTE_REASONING, "smart") and "lite" in model)
                return RouteResult(
                    response=response,
                    model_used=model,
                    degraded=is_degraded,
                    fallback_count=fallback_count,
                )
        except Exception as exc:
            fallback_count += 1
            err_type, delay = classify_api_error(exc)
            if err_type == "per_day":
                ledger.mark_exhausted_daily(model)
            elif err_type == "per_minute":
                ledger.mark_rate_limited_minute(model, retry_delay_seconds=delay)
            elif err_type == "unavailable":
                ledger.mark_unavailable(model)
            elif err_type == "gone":
                ledger.mark_gone(model)
            else:
                print(f"[ModelRouter] {model} retornou erro: {type(exc).__name__}: {str(exc)[:120]}")

    raise RuntimeError(f"Todos os modelos da rota síncrona '{route}' falharam.")
