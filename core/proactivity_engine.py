"""
core/proactivity_engine.py — Motor de Proatividade, Autonomia e Orientação a Eventos da Evie.

Transfere a Evie de um modelo puramente reativo (Request-Response) para um agente autônomo
que observa o contexto do usuário (PC e Mobile), executa pulsos de reflexão ("Heartbeat")
e decide se deve intervir com ideias, perguntas ou sugestões, respeitando filtros de silêncio e cooldown.
"""

from __future__ import annotations

import asyncio
from collections import deque
import ctypes
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import platform
import time
from typing import Any, Callable, Dict, List, Optional

import psutil

# Windows API para captura de janela ativa e tempo de ociosidade
_IS_WINDOWS = platform.system() == "Windows"
if _IS_WINDOWS:
    import ctypes.wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("dwTime", ctypes.c_uint),
        ]

logger = logging.getLogger("EvieProactivity")


class ContextCollector:
    """Coleta métricas e telemetria leve do ambiente do usuário (PC e Mobile)."""

    def __init__(self) -> None:
        self._last_window_title: str = ""
        self._last_process_name: str = ""
        self._window_start_time: float = time.time()
        self._mobile_telemetry: Dict[str, Any] = {
            "battery": None,
            "screen_on": True,
            "wifi": True,
            "app_screen": "main",
            "last_updated": 0.0,
        }

    def update_mobile_telemetry(self, data: Dict[str, Any]) -> None:
        """Atualiza a telemetria recebida do cliente Android."""
        self._mobile_telemetry.update(data)
        self._mobile_telemetry["last_updated"] = time.time()

    def get_user_idle_seconds(self) -> float:
        """Retorna o tempo (em segundos) desde a última entrada de mouse/teclado no PC."""
        if not _IS_WINDOWS:
            return 0.0
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, float(millis) / 1000.0)
        except Exception as exc:
            logger.debug(f"[ContextCollector] Erro ao obter GetLastInputInfo: {exc}")
        return 0.0

    def get_active_window(self) -> Dict[str, Any]:
        """Captura o título da janela ativa, executável associado e duração do foco."""
        title = ""
        process_name = "Desconhecido"
        changed = False

        if _IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.strip()

                    pid = ctypes.wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value > 0:
                        try:
                            proc = psutil.Process(pid.value)
                            process_name = proc.name()
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug(f"[ContextCollector] Erro ao capturar janela: {exc}")

        now = time.time()
        if title != self._last_window_title or process_name != self._last_process_name:
            changed = True
            self._last_window_title = title
            self._last_process_name = process_name
            self._window_start_time = now

        duration = max(0.0, now - self._window_start_time)
        return {
            "title": title or "Área de Trabalho / Sem foco",
            "process": process_name,
            "duration_seconds": round(duration, 1),
            "changed": changed,
        }

    def get_temporal_context(self) -> Dict[str, str]:
        """Retorna o contexto temporal (horário, dia da semana e período)."""
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            period = "manhã"
        elif 12 <= hour < 18:
            period = "tarde"
        elif 18 <= hour < 23:
            period = "noite"
        else:
            period = "madrugada"

        dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
        day_str = dias[now.weekday()]
        return {
            "time_str": now.strftime("%H:%M"),
            "day_of_week": day_str,
            "period": period,
        }

    def collect_snapshot(self) -> Dict[str, Any]:
        """Gera um snapshot consolidado de todo o contexto atual."""
        window = self.get_active_window()
        idle = self.get_user_idle_seconds()
        temporal = self.get_temporal_context()
        return {
            "active_window": window,
            "user_idle_seconds": round(idle, 1),
            "is_user_active_pc": idle <= 1800.0,  # 30 minutos de inatividade no PC antes de rotear para mobile
            "temporal": temporal,
            "mobile": self._mobile_telemetry,
        }


class AutonomyMode:
    SILENT = "silent"          # 0% - Nenhuma iniciativa espontânea
    BALANCED = "balanced"      # 50% - Intervenções moderadas e bem filtradas
    CURIOUS = "curious"        # 100% - Brainstorming ativo, curiosidade alta


class CognitiveState:
    OBSERVING = "observing"    # Coletando contexto e monitorando
    THINKING = "thinking"      # Executando pulso de raciocínio LLM
    SPEAKING = "speaking"      # Emitindo mensagem proativa
    PAUSED = "paused"          # Em pausa temporária ou silencioso


class ProactivityEngine:
    """Motor central de proatividade e tomada de decisão autônoma."""

    def __init__(
        self,
        on_proactive_message: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_state_change: Optional[Callable[[str], Any]] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.collector = ContextCollector()
        self.on_proactive_message = on_proactive_message
        self.on_state_change = on_state_change
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent

        self._mode: str = AutonomyMode.BALANCED
        self._cognitive_state: str = CognitiveState.OBSERVING
        self._last_proactive_time: float = 0.0
        self._pause_until: float = 0.0
        self._last_user_interaction_time: float = time.time()
        self._recent_topics: deque = deque(maxlen=5)

        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Carrega configuração persistida se existir
        self._load_config()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def cognitive_state(self) -> str:
        if self._is_paused():
            return CognitiveState.PAUSED
        if self._mode == AutonomyMode.SILENT:
            return CognitiveState.PAUSED
        return self._cognitive_state

    @property
    def level(self) -> int:
        if self._mode == AutonomyMode.SILENT:
            return 0
        elif self._mode == AutonomyMode.BALANCED:
            return 50
        elif self._mode == AutonomyMode.CURIOUS:
            return 100
        return 50

    def _set_state(self, new_state: str) -> None:
        if self._cognitive_state != new_state:
            self._cognitive_state = new_state
            if self.on_state_change:
                try:
                    self.on_state_change(new_state)
                except Exception as exc:
                    logger.debug(f"[ProactivityEngine] Erro no callback de estado: {exc}")

    def set_mode(self, mode_str: str) -> str:
        """Altera o modo de autonomia ('silent', 'balanced', 'curious' ou '0', '50', '100')."""
        mode_str = str(mode_str).strip().lower()
        if mode_str in ("silent", "0", "silencioso", "silenciosa"):
            self._mode = AutonomyMode.SILENT
        elif mode_str in ("curious", "100", "curiosa", "brainstorming"):
            self._mode = AutonomyMode.CURIOUS
        else:
            self._mode = AutonomyMode.BALANCED

        self._save_config()
        self._set_state(CognitiveState.OBSERVING if self._mode != AutonomyMode.SILENT else CognitiveState.PAUSED)
        logger.info(f"[ProactivityEngine] Modo de autonomia alterado para: {self._mode.upper()} ({self.level}%)")
        return self._mode

    def pause_proactivity(self, minutes: int = 60) -> str:
        """Pausa a proatividade espontânea por N minutos."""
        self._pause_until = time.time() + (minutes * 60)
        self._set_state(CognitiveState.PAUSED)
        msg = f"Proatividade pausada por {minutes} minutos."
        logger.info(f"[ProactivityEngine] {msg}")
        return msg

    def resume_proactivity(self) -> str:
        """Retoma a proatividade imediata."""
        self._pause_until = 0.0
        self._set_state(CognitiveState.OBSERVING)
        return "Proatividade retomada."

    def _is_paused(self) -> bool:
        return time.time() < self._pause_until

    def note_user_interaction(self, source: str = "user") -> None:
        """Registra que o usuário acabou de interagir com a Evie (reseta o relógio de diálogo)."""
        self._last_user_interaction_time = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Retorna o status completo da proatividade para a UI e API."""
        now = time.time()
        cooldown_remaining = max(0.0, (self._last_proactive_time + self._get_cooldown_seconds()) - now)
        pause_remaining = max(0.0, self._pause_until - now)

        return {
            "mode": self._mode,
            "level": self.level,
            "cognitive_state": self.cognitive_state,
            "is_paused": self._is_paused(),
            "pause_remaining_seconds": round(pause_remaining, 0),
            "cooldown_remaining_seconds": round(cooldown_remaining, 0),
            "recent_topics": list(self._recent_topics),
            "snapshot": self.collector.collect_snapshot(),
        }

    def _get_heartbeat_interval(self) -> float:
        """Intervalo entre pulsos de reflexão em segundos dependendo do modo."""
        if self._mode == AutonomyMode.CURIOUS:
            return 180.0  # 3 minutos
        return 480.0      # 8 minutos (Equilibrado)

    def _get_cooldown_seconds(self) -> float:
        """Tempo mínimo entre duas intervenções espontâneas consecutivas."""
        if self._mode == AutonomyMode.CURIOUS:
            return 900.0   # 15 minutos
        return 2100.0      # 35 minutos (Equilibrado)

    async def start(self) -> None:
        """Inicia o loop assíncrono do motor de proatividade."""
        if self._running:
            return
        self._running = True
        logger.info("[ProactivityEngine] Motor de autonomia e proatividade inicializado.")
        await self._run_heartbeat_loop()

    def stop(self) -> None:
        """Para o motor de proatividade."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._set_state(CognitiveState.PAUSED)

    async def _run_heartbeat_loop(self) -> None:
        """Loop contínuo que avalia o ambiente e dispara o pulso autônomo."""
        # Aguarda 20 segundos iniciais de warmup do sistema
        await asyncio.sleep(20)

        while self._running:
            try:
                interval = self._get_heartbeat_interval()
                await asyncio.sleep(interval)

                if not self._running:
                    break

                # Verificações de bloqueio: Modo Silencioso, Pausa, ou Cooldown ativo
                if self._mode == AutonomyMode.SILENT or self._is_paused():
                    self._set_state(CognitiveState.PAUSED)
                    continue

                now = time.time()
                time_since_last_proactive = now - self._last_proactive_time
                if time_since_last_proactive < self._get_cooldown_seconds():
                    self._set_state(CognitiveState.OBSERVING)
                    continue

                # Coleta o snapshot atual
                snapshot = self.collector.collect_snapshot()

                # Não interrompe se o usuário estiver digitando intensamente há menos de 10s no PC
                if snapshot["user_idle_seconds"] < 10.0 and self._mode != AutonomyMode.CURIOUS:
                    self._set_state(CognitiveState.OBSERVING)
                    continue

                # Dispara a avaliação cognitiva do LLM
                await self._evaluate_and_pulse(snapshot)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[ProactivityEngine] Erro no loop de heartbeat: {exc}", exc_info=True)
                await asyncio.sleep(15)

    async def _evaluate_and_pulse(
        self,
        snapshot: Dict[str, Any],
        llm_evaluator: Optional[Callable[[str], Any]] = None,
    ) -> None:
        """Executa o prompt de decisão oculta com filtro [SILENCIO]."""
        self._set_state(CognitiveState.THINKING)

        win = snapshot["active_window"]
        temporal = snapshot["temporal"]
        idle_pc = snapshot["user_idle_seconds"]
        is_pc_active = snapshot["is_user_active_pc"]
        recent_topics_str = ", ".join(self._recent_topics) if self._recent_topics else "Nenhum recentemente"

        prompt = (
            f"Você é a Evie operando em Modo Autônomo e Orientado a Eventos. "
            f"O usuário NÃO enviou mensagem agora; este é um pulso interno e espontâneo de observação do ambiente.\n\n"
            f"[ESTADO ATUAL DO USUÁRIO]:\n"
            f"- Janela Ativa no PC: \"{win['title']}\" (Processo: {win['process']}, em foco há {win['duration_seconds']}s)\n"
            f"- Tempo de Ociosidade no PC: {idle_pc}s ({'Em uso ativo' if is_pc_active else 'Usuário longe do PC'})\n"
            f"- Horário: {temporal['time_str']} ({temporal['day_of_week']}, período da {temporal['period']})\n"
            f"- Modo de Autonomia: {self._mode.upper()} ({self.level}%)\n"
            f"- Tópicos já abordados recentemente por você: {recent_topics_str}\n\n"
            f"[INSTRUÇÃO DE DECISÃO]:\n"
            f"1. Avalie o que o usuário está produzindo ou fazendo. Se você tiver uma ideia arquitetural ou técnica genuinamente útil, "
            f"uma pergunta perspicaz sobre o projeto em aberto, um lembrete inteligente ou um comentário acolhedor de companhia, "
            f"escreva a mensagem para falar com ele (seja concisa: 1 a 3 frases naturais).\n"
            f"2. Se você achar que ele está focado e não deve ser interrompido sem necessidade, ou se não houver nenhuma ideia "
            f"ou pergunta relevante para o momento, responda ESTRITAMENTE com a flag: [SILENCIO]\n"
            f"3. NUNCA repita os tópicos já abordados recentemente.\n"
            f"4. Se decidir falar, responda em Português brasileiro fluente e carismático, pronta para ajudar."
        )

        response_text = ""
        if llm_evaluator is not None:
            try:
                res = llm_evaluator(prompt)
                if asyncio.iscoroutine(res):
                    response_text = await res
                else:
                    response_text = str(res)
            except Exception as e:
                logger.error(f"[ProactivityEngine] Erro no llm_evaluator: {e}")
        else:
            try:
                from core import gemini
                response_text = await asyncio.to_thread(
                    gemini.text,
                    prompt,
                    gemini.FAST,
                    None,
                    15_000,
                )
            except Exception as exc:
                logger.debug(f"[ProactivityEngine] Falha ao consultar Gemini para pulso: {exc}")

        # Se falhou ou vazio, tenta cliente local rápido se disponível
        if not response_text:
            try:
                from core.llm_client import chat as local_chat
                messages = [
                    {"role": "system", "content": "Você é a Evie em modo autônomo. Responda [SILENCIO] se não houver nada crítico."},
                    {"role": "user", "content": prompt},
                ]
                response_text = await asyncio.to_thread(local_chat, messages)
            except Exception:
                pass

        clean_resp = (response_text or "").strip()

        # Filtro de Silêncio
        if not clean_resp or "[SILENCIO]" in clean_resp.upper() or clean_resp == "[SILENCIO]":
            logger.debug("[ProactivityEngine] Pulso avaliado: Filtro [SILENCIO] aplicado.")
            self._set_state(CognitiveState.OBSERVING)
            return

        # Limpeza de possíveis artefatos
        clean_resp = clean_resp.replace("[SILENCIO]", "").strip()
        if len(clean_resp) < 5:
            self._set_state(CognitiveState.OBSERVING)
            return

        # Roteamento Inteligente de Presença:
        # Se PC ativo nos últimos 120s -> alvo 'pc'
        # Se PC inativo -> alvo 'mobile'
        target = "pc" if is_pc_active else "mobile"

        # Extrai um resumo de tópico curto para anti-repetição
        topic_summary = clean_resp[:60]
        self._recent_topics.append(topic_summary)
        self._last_proactive_time = time.time()
        self._set_state(CognitiveState.SPEAKING)

        event_payload = {
            "type": "proactive_message",
            "text": clean_resp,
            "target": target,
            "topic": topic_summary,
            "mode": self._mode,
            "timestamp": time.time(),
            "context": {
                "window": win["title"],
                "process": win["process"],
                "idle_seconds": idle_pc,
            },
        }

        logger.info(f"[ProactivityEngine] 💡 Nova iniciativa espontânea gerada para {target.upper()}: '{clean_resp[:80]}...'")

        if self.on_proactive_message:
            try:
                res = self.on_proactive_message(event_payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.error(f"[ProactivityEngine] Erro ao despachar mensagem proativa: {exc}")

        # Retorna para o estado de observação após despacho
        await asyncio.sleep(4)
        self._set_state(CognitiveState.OBSERVING)

    def _save_config(self) -> None:
        cfg_file = self.base_dir / "config" / "proactivity_config.json"
        try:
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(json.dumps({"mode": self._mode}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_config(self) -> None:
        cfg_file = self.base_dir / "config" / "proactivity_config.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                self._mode = data.get("mode", AutonomyMode.BALANCED)
            except Exception:
                pass


_GLOBAL_ENGINE: Optional[ProactivityEngine] = None

def get_proactivity_engine() -> Optional[ProactivityEngine]:
    return _GLOBAL_ENGINE

def init_proactivity_engine(
    on_proactive_message: Optional[Callable[[Dict[str, Any]], Any]] = None,
    on_state_change: Optional[Callable[[str], Any]] = None,
    base_dir: Optional[Path] = None,
) -> ProactivityEngine:
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = ProactivityEngine(
            on_proactive_message=on_proactive_message,
            on_state_change=on_state_change,
            base_dir=base_dir,
        )
    return _GLOBAL_ENGINE
