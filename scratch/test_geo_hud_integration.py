import sys
import os
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def run_tests():
    print("=== TESTE DE INTEGRAÇÃO DA INTERFACE GEOGRÁFICA E PROCEDURAL ===")

    # 1. Testar schema do GeoMapCard
    from core.ui_schema import (
        ComponentType, ProceduralUIBuilder, VisualState, parse_llm_response_to_procedural_ui
    )
    assert ComponentType.GEO_MAP_CARD.value == "GeoMapCard", "ComponentType.GEO_MAP_CARD inválido"

    builder = ProceduralUIBuilder(visual_state=VisualState.IDLE_OBSERVING)
    builder.add_geo_map(
        title="RADAR TÁTICO HOLOGRÁFICO",
        lat=-23.5505,
        lon=-46.6333,
        location_name="São Paulo - SP",
        weather_info="23°C • Chuva Leve"
    )
    payload = builder.build().to_dict()
    assert len(payload["ui_tree"]) == 1, "ui_tree deve ter 1 componente"
    assert payload["ui_tree"][0]["type"] == "GeoMapCard", "Tipo de componente deve ser GeoMapCard"
    assert payload["ui_tree"][0]["data"]["latitude"] == -23.5505
    print("[OK] Teste 1: Schema e Builder do GeoMapCard validados com sucesso.")

    # 2. Testar heurística do LLM para termos geográficos
    sample_text = "Com certeza, posso mostrar o radar e a localização do trânsito e o clima atual."
    inferred_payload = parse_llm_response_to_procedural_ui(sample_text)
    types = [c.get("type") if isinstance(c, dict) else c.type for c in inferred_payload.ui_tree]
    assert ComponentType.GEO_MAP_CARD.value in types, f"Heurística deveria incluir GeoMapCard, obteve: {types}"
    print("[OK] Teste 2: Heurística geográfica do LLM validada.")

    # 3. Testar instâncias do PyQt6 (GeoMapHUDWidget e ProceduralHUDOverlay)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from ui import GeoMapHUDWidget, ProceduralHUDOverlay
    geo_widget = GeoMapHUDWidget()
    assert geo_widget._lat == -23.550520, "Latitude inicial padrão incorreta"
    assert len(geo_widget._markers) >= 2, "Deveria ter marcadores PC e Mobile padrão"

    # Atualiza localização do mobile
    geo_widget.update_mobile_marker(-23.5400, -46.6200, label="POCO X7 PRO")
    poco_marker = next((m for m in geo_widget._markers if "POCO" in m["label"]), None)
    assert poco_marker is not None, "Marcador Poco deve existir"
    assert poco_marker["lat"] == -23.5400, "Latitude do Poco deve estar atualizada"
    print("[OK] Teste 3: GeoMapHUDWidget instanciado e manipulado com sucesso.")

    # 4. Testar renderização de GeoMapCard no ProceduralHUDOverlay
    overlay = ProceduralHUDOverlay()
    overlay.render_tree(payload["ui_tree"])
    assert len(overlay._rendered_widgets) == 1, "Deveria ter renderizado 1 widget"
    print("[OK] Teste 4: ProceduralHUDOverlay renderizou o GeoMapCard com sucesso.")

    # 5. Testar sincronização de telemetria no DashboardServer
    from dashboard.server import DashboardServer
    server = DashboardServer()
    geo_received = []
    server.set_geo_callback(lambda lat, lon, dev: geo_received.append((lat, lon, dev)))
    assert server._geo_callback is not None, "Callback de geolocalização deve estar registrado"
    server._geo_callback(-23.5461, -46.6289, "Poco X7")
    assert len(geo_received) == 1 and geo_received[0][0] == -23.5461
    print("[OK] Teste 5: DashboardServer geo_callback validado.")

    print("\nTODOS OS TESTES DE INTEGRAÇÃO PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    run_tests()
