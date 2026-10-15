"""
Procedural UI Contract & Schema Engine — Evie (Mark LV)
Defines Server-Driven Generative UI (SDUI) models, visual states, and payload builders.
Synchronized between Python PC Client and Android Kotlin Client.
"""

from __future__ import annotations
import json
import uuid
import time
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


class VisualState(str, Enum):
    IDLE_OBSERVING = "IDLE_OBSERVING"  # Neon cyan/teal capsule eyes, calm blinking
    HAPPY          = "HAPPY"           # Cheerful upward arcs ^ ^, blush, hop & sparkles
    CURIOUS_SPARK  = "CURIOUS_SPARK"   # Asymmetric arched eyebrow, warm amber glow
    THINKING_DEEP  = "THINKING_DEEP"   # Upward half-closed gaze, magenta pulse
    SPEAKING       = "SPEAKING"        # Dynamic voice amplitude reactivity
    FOCUS_CALM     = "FOCUS_CALM"      # Inward slanted focused gaze, deep azure
    FOCUSED        = "FOCUSED"         # Inward slanted focused gaze
    SLEEPY         = "SLEEPY"          # Heavy eyelids, dim cyan
    ALERT_URGENT   = "ALERT_URGENT"    # Wide rounded squash/stretch alert, crimson
    SURPRISED      = "SURPRISED"       # Wide rounded alert, shockwave, crimson neon
    LOVE           = "LOVE"            # Heart glyphs, pink glow, floating hearts
    EXCITED        = "EXCITED"         # Star glyphs, golden glow, sparkles & hop
    SAD            = "SAD"             # Drooping eyelids, blue glow, tears
    ANGRY          = "ANGRY"           # Angular slanted brows, red glow, pulsing anger mark
    WINK           = "WINK"            # Playful wink with sparkle
    ASLEEP         = "ASLEEP"          # Fully closed eyes with floating Zzz
    DANCE          = "DANCE"           # Happy dancing eyes hopping rhythmically side to side


class ComponentType(str, Enum):
    METRIC_CARD       = "MetricCard"
    INTERACTIVE_CHECK = "InteractiveChecklist"
    ACTION_CARD       = "ActionDecisionCard"
    CODE_SNIPPET      = "CodeSnippetDiff"
    TIMELINE_BLOCK    = "TimelineBlock"
    EPHEMERAL_TOAST   = "EphemeralToast"
    GEO_MAP_CARD      = "GeoMapCard"


@dataclass
class MetricItem:
    label: str
    value: str
    change: Optional[str] = None
    color: Optional[str] = None  # hex or token e.g. #00ff88, #ffaa00


@dataclass
class ChecklistItem:
    id: str
    text: str
    done: bool = False


@dataclass
class ActionItem:
    id: str
    label: str
    style: str = "primary"  # primary, danger, secondary, outline
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimelineEvent:
    time: str
    title: str
    category: str = "general"
    status: str = "upcoming"  # done, in_progress, upcoming


@dataclass
class GeoMarker:
    lat: float
    lon: float
    label: str
    status_color: str = "#00f0ff"
    marker_type: str = "device"
    pulse: bool = True


@dataclass
class GeoMapData:
    lat: float = -23.5505
    lon: float = -46.6333
    location_name: str = "São Paulo, SP - Brasil"
    zoom_level: int = 12
    markers: List[GeoMarker | Dict[str, Any]] = field(default_factory=list)
    weather_info: str = "24°C • Céu Limpo"
    ping_ms: int = 18
    satellites: int = 14
    heading: str = "042° NE"


@dataclass
class UIComponent:
    id: str
    type: str
    title: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "data": self.data,
        }
        if isinstance(self.data, dict):
            for k, v in self.data.items():
                if k not in res:
                    res[k] = v
        return res


@dataclass
class ProceduralUIPayload:
    visual_state: str = VisualState.IDLE_OBSERVING.value
    voice_text: str = ""
    ui_tree: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    component_id: Optional[str] = None  # for in-place component mutations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "procedural_ui",
            "visual_state": self.visual_state,
            "voice_text": self.voice_text,
            "ui_tree": self.ui_tree,
            "timestamp": self.timestamp,
            "component_id": self.component_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class ProceduralUIBuilder:
    """Helper fluente para construir árvores procedurais de interface dinamicamente."""

    def __init__(self, visual_state: str = VisualState.IDLE_OBSERVING.value, voice_text: str = ""):
        self.visual_state = visual_state
        self.voice_text = voice_text
        self.components: List[Dict[str, Any]] = []

    def set_visual_state(self, state: VisualState | str) -> ProceduralUIBuilder:
        self.visual_state = state.value if isinstance(state, VisualState) else str(state)
        return self

    def set_voice_text(self, text: str) -> ProceduralUIBuilder:
        self.voice_text = text
        return self

    def add_metric_card(self, title: str, metrics: List[MetricItem | Dict[str, Any]], comp_id: Optional[str] = None, card_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or card_id or f"metric_{uuid.uuid4().hex[:8]}"
        m_list = [asdict(m) if isinstance(m, MetricItem) else m for m in metrics]
        comp = UIComponent(
            id=cid,
            type=ComponentType.METRIC_CARD.value,
            title=title,
            data={"metrics": m_list}
        )
        self.components.append(comp.to_dict())
        return self

    def add_checklist(self, title: str, items: List[ChecklistItem | Dict[str, Any]], comp_id: Optional[str] = None, card_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or card_id or f"chk_{uuid.uuid4().hex[:8]}"
        i_list = [asdict(i) if isinstance(i, ChecklistItem) else i for i in items]
        comp = UIComponent(
            id=cid,
            type=ComponentType.INTERACTIVE_CHECK.value,
            title=title,
            data={"items": i_list}
        )
        self.components.append(comp.to_dict())
        return self

    def add_action_decision(self, title: str, description: str, actions: List[ActionItem | Dict[str, Any]], comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or f"action_{uuid.uuid4().hex[:8]}"
        a_list = [asdict(a) if isinstance(a, ActionItem) else a for a in actions]
        comp = UIComponent(
            id=cid,
            type=ComponentType.ACTION_CARD.value,
            title=title,
            data={"description": description, "body": description, "actions": a_list}
        )
        self.components.append(comp.to_dict())
        return self

    def add_code_snippet(self, code: str, language: str = "python", filename: Optional[str] = None, comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or f"code_{uuid.uuid4().hex[:8]}"
        comp = UIComponent(
            id=cid,
            type=ComponentType.CODE_SNIPPET.value,
            title=filename or f"Código ({language})",
            data={"code": code, "language": language, "filename": filename}
        )
        self.components.append(comp.to_dict())
        return self

    def add_timeline(self, title: str, events: List[TimelineEvent | Dict[str, Any]], comp_id: Optional[str] = None, card_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or card_id or f"timeline_{uuid.uuid4().hex[:8]}"
        e_list = [asdict(e) if isinstance(e, TimelineEvent) else e for e in events]
        comp = UIComponent(
            id=cid,
            type=ComponentType.TIMELINE_BLOCK.value,
            title=title,
            data={"events": e_list}
        )
        self.components.append(comp.to_dict())
        return self

    def add_ephemeral_toast(self, text: str, duration_secs: int = 6, tone: str = "info", comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or f"toast_{uuid.uuid4().hex[:8]}"
        comp = UIComponent(
            id=cid,
            type=ComponentType.EPHEMERAL_TOAST.value,
            title=None,
            data={"text": text, "duration": duration_secs, "tone": tone}
        )
        self.components.append(comp.to_dict())
        return self

    def add_stat_grid(self, title: str, metrics: List[Dict[str, Any]], comp_id: Optional[str] = None, card_id: Optional[str] = None) -> ProceduralUIBuilder:
        return self.add_metric_card(title=title, metrics=metrics, comp_id=comp_id or card_id)

    def add_action_card(self, title: str, body: str, actions: List[Dict[str, Any]], card_id: Optional[str] = None, comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        return self.add_action_decision(title=title, description=body, actions=actions, comp_id=comp_id or card_id)

    def add_code_diff(self, code_content: str, file_path: str = "", language: str = "python", actions: Optional[List[Dict[str, Any]]] = None, card_id: Optional[str] = None, comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or card_id or f"code_{uuid.uuid4().hex[:8]}"
        comp = UIComponent(
            id=cid,
            type=ComponentType.CODE_SNIPPET.value,
            title=file_path or f"Código ({language})",
            data={"code": code_content, "code_content": code_content, "language": language, "file_path": file_path, "actions": actions or []}
        )
        self.components.append(comp.to_dict())
        return self

    def add_toast(self, text: str, duration_seconds: int = 5, card_id: Optional[str] = None, comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        return self.add_ephemeral_toast(text=text, duration_secs=duration_seconds, comp_id=comp_id or card_id)

    def add_geo_map(self, title: str = "RADAR TÁTICO & GEOLOCALIZAÇÃO",
                    lat: float = -23.5505, lon: float = -46.6333,
                    location_name: str = "São Paulo, SP - Brasil",
                    markers: Optional[List[Dict[str, Any]]] = None,
                    weather_info: str = "24°C • Céu Limpo",
                    zoom_level: int = 12,
                    card_id: Optional[str] = None, comp_id: Optional[str] = None) -> ProceduralUIBuilder:
        cid = comp_id or card_id or f"geo_{uuid.uuid4().hex[:8]}"
        m_list = markers if markers is not None else [
            {"lat": lat, "lon": lon, "label": "BASE PC HOST", "status_color": "#00f0ff", "marker_type": "base", "pulse": True},
            {"lat": lat + 0.005, "lon": lon + 0.008, "label": "POCO X7 MOBILE", "status_color": "#00e676", "marker_type": "mobile", "pulse": True}
        ]
        comp = UIComponent(
            id=cid,
            type=ComponentType.GEO_MAP_CARD.value,
            title=title,
            data={
                "latitude": lat,
                "longitude": lon,
                "location_name": location_name,
                "zoom_level": zoom_level,
                "markers": m_list,
                "weather_info": weather_info,
                "ping_ms": 18,
                "satellites": 14,
                "heading": "042° NE"
            }
        )
        self.components.append(comp.to_dict())
        return self

    def build(self) -> ProceduralUIPayload:
        return ProceduralUIPayload(
            visual_state=self.visual_state,
            voice_text=self.voice_text,
            ui_tree=self.components,
            timestamp=time.time(),
        )


def parse_llm_response_to_procedural_ui(text: str, context: Optional[Dict[str, Any]] = None) -> ProceduralUIPayload:
    """
    Analisa a resposta do LLM. Se contiver JSON de UI estruturada, carrega diretamente.
    Caso seja texto natural, infere inteligentemente os componentes procedurais
    (blocos de código -> CodeSnippetDiff, listas com [ ] -> InteractiveChecklist, etc.).
    """
    raw = (text or "").strip()
    # 1. Tenta extrair bloco JSON explícito ```json ... ```
    if "```json" in raw:
        try:
            start = raw.index("```json") + 7
            end = raw.index("```", start)
            snippet = raw[start:end].strip()
            data = json.loads(snippet)
            if "ui_tree" in data:
                return ProceduralUIPayload(
                    visual_state=data.get("visual_state", VisualState.SPEAKING.value),
                    voice_text=data.get("voice_text", raw[:150]),
                    ui_tree=data.get("ui_tree", []),
                )
        except Exception:
            pass

    builder = ProceduralUIBuilder()
    builder.set_voice_text(raw[:180])

    # 2. Heurística de código
    if "```" in raw:
        lines = raw.splitlines()
        in_code = False
        cur_code = []
        cur_lang = "python"
        for line in lines:
            if line.startswith("```"):
                if in_code:
                    in_code = False
                    builder.add_code_snippet("\n".join(cur_code), language=cur_lang)
                    cur_code = []
                else:
                    in_code = True
                    cur_lang = line[3:].strip() or "python"
            elif in_code:
                cur_code.append(line)

    # 3. Heurística de checklist (- [ ] ou - [x])
    chk_items = []
    for line in raw.splitlines():
        l_str = line.strip()
        if l_str.startswith("- [ ]") or l_str.startswith("* [ ]"):
            chk_items.append(ChecklistItem(id=f"chk_{len(chk_items)}", text=l_str[5:].strip(), done=False))
        elif l_str.startswith("- [x]") or l_str.startswith("* [x]"):
            chk_items.append(ChecklistItem(id=f"chk_{len(chk_items)}", text=l_str[5:].strip(), done=True))
    if chk_items:
        builder.add_checklist("Tarefas Propostas", chk_items)

    # 4. Heurística geográfica / radar / clima / mapa
    geo_keywords = ("onde", "localização", "localizacao", "mapa", "radar", "clima", "tempo", "trânsito", "transito", "rota", "cidade", "coordenadas", "satélite", "satelite", "viagem", "distância", "distancia", "gps")
    if any(k in raw.lower() for k in geo_keywords):
        builder.add_geo_map(
            title="RADAR TÁTICO & TELEMETRIA GEOGRÁFICA",
            location_name="São Paulo, SP - Brasil",
            weather_info="24°C • Céu Limpo"
        )

    # 5. Análise de Sentimento Procedural Completa para os Olhos Expressivos da Evie
    detected_state = extract_speech_emotion(raw)
    builder.set_visual_state(detected_state)

    if detected_state == VisualState.CURIOUS_SPARK:
        builder.add_action_decision(
            title="Decisão Rápida",
            description=raw,
            actions=[
                ActionItem(id="act_confirm", label="Sim, prossiga", style="primary", payload={"intent": "confirm", "text": raw}),
                ActionItem(id="act_dismiss", label="Agora não", style="outline", payload={"intent": "dismiss"}),
            ]
        )

    return builder.build()


def _matches_any(patterns: tuple[str, ...], text: str) -> bool:
    for p in patterns:
        if " " in p:
            if p in text:
                return True
        else:
            if re.search(r"\b" + re.escape(p) + r"\b", text, re.IGNORECASE):
                return True
    return False


def extract_speech_emotion(text: str) -> VisualState:
    """Extrai em tempo real a emoção da fala para sincronização com os olhos procedurais."""
    raw = (text or "").strip()
    if not raw:
        return VisualState.IDLE_OBSERVING
    low = raw.lower()

    # 1. Amor / Afeto / Carinho (Olhos de Coração + Partículas Hearts)
    love_words = (
        "amo", "eu amo", "amar", "te amo", "amo você", "amo voce", "meu amor", "querido", "querida",
        "carinho", "apaixonada", "apaixonado", "fofa", "fofo", "coração",
        "coracao", "gratidão", "gratidao", "muito amor", "fofura",
        "te adoro", "amada", "amado"
    )
    if _matches_any(love_words, low):
        return VisualState.LOVE

    # 2. Empolgação / Vitória / Energia (Olhos de Estrela + Brilhos)
    excited_words = (
        "incrível", "incrivel", "sensacional", "espetacular", "fantástico", "fantastico",
        "uau", "wow", "demais", "arrasou", "empolgada", "empolgado", "empolgante",
        "animação", "animado", "animada", "vamos lá", "vamo lá", "bora", "vitória",
        "vitoria", "conseguimos", "máximo", "maximo", "show de bola", "energia",
        "eletrizante", "extraordinário", "extraordinario"
    )
    if _matches_any(excited_words, low):
        return VisualState.EXCITED

    # 3. Tristeza / Pesar / Empatia (Olhos Marejados + Lágrimas)
    sad_words = (
        "triste", "tristeza", "infelizmente", "lamento", "sinto muito", "desculpe",
        "desculpa", "perdoe", "perdão", "perdao", "chato", "decepção", "decepcao",
        "pena", "que pena", "lágrimas", "lagrimas", "choro", "chorando",
        "perdi", "falhou", "coitado", "coitada", "sozinho", "sozinha", "doloroso"
    )
    if _matches_any(sad_words, low):
        return VisualState.SAD

    # 4. Raiva / Irritação (Olhos Angulares + Pulso de Raiva)
    angry_words = (
        "raiva", "irritada", "irritado", "furiosa", "furioso", "brava", "bravo",
        "odeio", "droga", "inaceitável", "inaceitavel", "absurdo", "revoltada",
        "revoltado", "péssimo", "pessimo", "horroroso", "injusto", "chega",
        "revoltante", "maldito", "maldita"
    )
    if _matches_any(angry_words, low):
        return VisualState.ANGRY

    # 5. Piscadinha / Cumplicidade (Wink + Sparkle)
    wink_words = (
        "wink", "piscadinha", "piscou", "segredo", "só entre nós", "so entre nos",
        "combinado", "combinadinho", "fechado", "fechadinho", "rsrs",
        "deixa comigo", "confia", "tá combinado", "ta combinado"
    )
    if _matches_any(wink_words, low):
        return VisualState.WINK

    # 6. Alerta Urgente / Perigo
    alert_words = (
        "cuidado", "atenção", "atencao", "urgente", "alerta", "perigo", "perigoso",
        "erro crítico", "erro critico", "falha grave", "emergência", "emergencia",
        "socorro", "fogo", "ameaça", "ameaca", "invasão", "invasao"
    )
    if _matches_any(alert_words, low):
        return VisualState.ALERT_URGENT

    # 7. Surpresa / Espanto
    surprised_words = (
        "surpresa", "inesperado", "choque", "caramba", "nossa", "meu deus",
        "como assim", "não acredito", "nao acredito", "uai", "eita"
    )
    if _matches_any(surprised_words, low):
        return VisualState.SURPRISED

    # 8. Sono / Cansaço
    sleepy_words = (
        "sono", "cansada", "cansado", "exausta", "exausto", "dormir",
        "descansar", "boa noite", "hora de dormir", "cochilo", "preguiça", "preguica"
    )
    if _matches_any(sleepy_words, low):
        return VisualState.SLEEPY

    # 9. Alegria / Felicidade / Sorriso (Arco Sorridente ^ ^ + Bochechas Rosadas)
    happy_words = (
        "feliz", "felicidade", "alegre", "alegria", "radiante", "contente",
        "maravilha", "perfeito", "excelente", "muito bom", "ótimo", "otimo",
        "adorei", "adoro", "bom demais", "legal", "obrigado", "obrigada",
        "valeu", "comemora", "celebra", "haha", "hehe", "sorriso", "sorrindo",
        "sorria", "bom dia", "boa tarde", "tudo bem", "prazer", "sucesso",
        "parabéns", "parabens", "show", "gostei", "tranquilo", "ótima", "otima",
        "lindo", "linda"
    )
    if _matches_any(happy_words, low):
        return VisualState.HAPPY

    # 10. Curiosidade / Pergunta
    curious_words = (
        "gostaria", "quer que", "posso", "será que", "sera que", "o que acha",
        "que tal", "interessante", "quem sabe", "me pergunto", "você sabia",
        "voce sabia", "por que", "porque"
    )
    if raw.endswith("?") or _matches_any(curious_words, low):
        return VisualState.CURIOUS_SPARK

    # 11. Foco Técnico / Concentração
    focus_words = (
        "analisando", "compilando", "executando", "depurando", "refatorando",
        "diagnóstico", "diagnostico", "algoritmo", "focado", "focada", "processando",
        "código", "codigo", "calculando", "otimizando"
    )
    if _matches_any(focus_words, low):
        return VisualState.FOCUSED

    # Fala padrão viva
    return VisualState.SPEAKING


_action_dispatcher = None

def set_action_dispatcher(dispatcher):
    """Set global handler for procedural UI actions triggered by PC or Mobile buttons/checklists."""
    global _action_dispatcher
    _action_dispatcher = dispatcher

def get_action_dispatcher():
    """Retrieve the current action dispatcher."""
    return _action_dispatcher
