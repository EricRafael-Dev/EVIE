"""Parâmetros normalizados de um olho."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

Color = Tuple[float, float, float]

DEFAULT_COLOR: Color = (76.0, 200.0, 183.0)  # ciano padrão
GLYPHS = ("", "heart", "star")  # "" = olho normal; os outros trocam o corpo do olho por um símbolo

NUMERIC_FIELDS = (
    "w", "h", "radius", "x", "y", "lid_top", "lid_tilt", "lid_bottom", "arc", "glow", "highlight", "shade",
    "blush", "tremble", "wet",
)


@dataclass
class EyeParams:
    w: float = 1.0           # largura (1 = tamanho base do layout)
    h: float = 1.0           # altura (piscar = h -> 0)
    radius: float = 0.55     # 0 = cantos retos, 1 = pílula/círculo
    x: float = 0.0           # olhar horizontal, -1..1
    y: float = 0.0           # olhar vertical, -1..1 (positivo = baixo)
    lid_top: float = 0.0     # cobertura da pálpebra superior, 0..1
    lid_tilt: float = 0.0    # -1 triste (canto externo cai) ... +1 bravo (canto interno cai)
    lid_bottom: float = 0.0  # cobertura inferior ("bochecha"), 0..1
    arc: float = 0.0         # 0 = retângulo, 1 = arco feliz (^)
    glow: float = 0.5        # intensidade do brilho, 0..1
    highlight: float = 1.0   # reflexo especular, 0..1
    shade: float = 0.3       # escurecimento da base do olho (volume), 0..1
    blush: float = 0.0       # bochecha rosada abaixo do olho, 0..1
    tremble: float = 0.0     # tremor + brilho pulsando como batimento (raiva), 0..1
    wet: float = 0.0         # olho marejado: linha d'água e reflexo maior, 0..1
    color: Color = DEFAULT_COLOR
    glyph: str = ""          # "", "heart" ou "star"; não é interpolado (troca escondida num piscar)

    def copy(self) -> "EyeParams":
        return dataclasses.replace(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], base: Optional["EyeParams"] = None) -> "EyeParams":
        """Cria a partir de um dict, sobrescrevendo `base` (ou os defaults)."""
        params = base.copy() if base is not None else cls()
        for key, value in data.items():
            if key == "color":
                if len(value) != 3:
                    raise ValueError(f"color precisa de 3 canais, recebeu {value!r}")
                params.color = tuple(float(c) for c in value)  # type: ignore[assignment]
            elif key == "glyph":
                value = value or ""
                if value not in GLYPHS:
                    raise ValueError(f"glyph desconhecido {value!r}. Disponíveis: {list(GLYPHS[1:])}")
                params.glyph = value
            elif key in NUMERIC_FIELDS:
                setattr(params, key, float(value))
            else:
                raise ValueError(f"Parâmetro de olho desconhecido: {key!r}")
        return params

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {name: getattr(self, name) for name in NUMERIC_FIELDS}
        out["color"] = tuple(self.color)
        out["glyph"] = self.glyph
        return out
