"""Carrega expressões de presets.yaml.

Formato: cada preset lista parâmetros comuns aos dois olhos; as chaves
opcionais `left:` e `right:` sobrescrevem um olho específico, e `fx:`
lista os efeitos animados da expressão (lágrimas, Zzz, brilhos...).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import yaml

from .params import EyeParams

DEFAULT_PRESETS_PATH = Path(__file__).with_name("presets.yaml")


@dataclass
class Preset:
    name: str
    left: EyeParams
    right: EyeParams
    fx: Tuple[str, ...] = ()


def load_presets(path: Union[str, Path, None] = None) -> Dict[str, Preset]:
    source = Path(path) if path is not None else DEFAULT_PRESETS_PATH
    with open(source, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    presets: Dict[str, Preset] = {}
    for name, spec in raw.items():
        spec = dict(spec or {})
        left_over = spec.pop("left", None) or {}
        right_over = spec.pop("right", None) or {}
        fx = spec.pop("fx", None) or []
        if isinstance(fx, str) or not all(isinstance(kind, str) for kind in fx):
            raise ValueError(f"Preset {name!r}: `fx` precisa ser uma lista de nomes, recebeu {fx!r}")
        common = EyeParams.from_dict(spec)
        presets[name] = Preset(
            name=name,
            left=EyeParams.from_dict(left_over, base=common),
            right=EyeParams.from_dict(right_over, base=common),
            fx=tuple(fx),
        )
    if "neutral" not in presets:
        raise ValueError(f"{source} precisa definir o preset 'neutral'")
    return presets


def preset_names(presets: Optional[Dict[str, Preset]] = None) -> list:
    return list((presets or load_presets()).keys())
