"""
core/device_registry.py — Modular Registry for Tailscale Network Devices

Manages device metadata (name, IP, auth tokens) in config/devices.json.
Allows dynamic discovery, lookup, and registration without hardcoding IPs in the codebase.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DeviceRegistry")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "devices.json"
_LOCK = threading.RLock()


class DeviceRegistry:
    """Thread-safe dynamic device registry."""

    def __init__(self, path: Path = _CONFIG_PATH) -> None:
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {
                "devices": [],
                "settings": {
                    "allow_registered_only": False,
                    "tailscale_interface_preferred": True
                }
            }
            self.path.write_text(json.dumps(initial_data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> Dict[str, Any]:
        with _LOCK:
            try:
                text = self.path.read_text(encoding="utf-8")
                return json.loads(text)
            except Exception as e:
                logger.error("Failed to load %s: %s", self.path, e)
                return {"devices": [], "settings": {}}

    def save(self, data: Dict[str, Any]) -> bool:
        with _LOCK:
            try:
                self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                return True
            except Exception as e:
                logger.error("Failed to save %s: %s", self.path, e)
                return False

    def list_devices(self) -> List[Dict[str, Any]]:
        data = self.load()
        return data.get("devices", [])

    def get_by_ip(self, ip: str) -> Optional[Dict[str, Any]]:
        ip = (ip or "").strip()
        for dev in self.list_devices():
            if dev.get("tailscale_ip") == ip or dev.get("ip") == ip:
                return dev
        return None

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        name_lower = (name or "").strip().lower()
        for dev in self.list_devices():
            if dev.get("name", "").strip().lower() == name_lower:
                return dev
        return None

    def register_device(
        self,
        name: str,
        ip: str,
        os_name: str = "",
        role: str = "mobile_client",
        auth_token: str = ""
    ) -> Dict[str, Any]:
        """Add or update a device registration in devices.json."""
        with _LOCK:
            data = self.load()
            devices = data.get("devices", [])
            existing = None
            for dev in devices:
                if dev.get("name", "").strip().lower() == name.strip().lower():
                    existing = dev
                    break

            if existing:
                existing["tailscale_ip"] = ip
                if os_name:
                    existing["os"] = os_name
                if role:
                    existing["role"] = role
                if auth_token:
                    existing["auth_token"] = auth_token
                existing["enabled"] = True
                device_record = existing
            else:
                device_record = {
                    "name": name.strip(),
                    "tailscale_ip": ip.strip(),
                    "os": os_name,
                    "enabled": True,
                    "role": role,
                    "auth_token": auth_token
                }
                devices.append(device_record)

            data["devices"] = devices
            self.save(data)
            return device_record

    def remove_device(self, name: str) -> bool:
        with _LOCK:
            data = self.load()
            devices = data.get("devices", [])
            initial_len = len(devices)
            devices = [d for d in devices if d.get("name", "").strip().lower() != name.strip().lower()]
            if len(devices) != initial_len:
                data["devices"] = devices
                self.save(data)
                return True
            return False

    def validate_token(self, token_str: str) -> Optional[Dict[str, Any]]:
        """Valida via hmac.compare_digest se o token corresponde a algum dispositivo registrado."""
        import hmac
        if not token_str:
            return None
        clean_tok = token_str.removeprefix("Bearer ").strip()
        if not clean_tok:
            return None
        for dev in self.list_devices():
            if not dev.get("enabled", True):
                continue
            registered_token = str(dev.get("auth_token", "")).strip()
            if registered_token and hmac.compare_digest(clean_tok, registered_token):
                return dev
        return None

    def upgrade_weak_tokens(self) -> None:
        """Utilitário de boot: substitui tokens previsíveis por tokens de 32 bytes e ativa allow_registered_only."""
        import secrets
        with _LOCK:
            data = self.load()
            settings = data.setdefault("settings", {})
            settings["allow_registered_only"] = True
            
            devices = data.get("devices", [])
            modified = False
            for dev in devices:
                tok = str(dev.get("auth_token", "")).strip()
                if not tok or len(tok) < 24 or tok.startswith("evie-client-"):
                    new_token = secrets.token_urlsafe(32)
                    dev["auth_token"] = new_token
                    modified = True
                    logger.info("Token de pareamento seguro gerado para [%s]: %s", dev.get("name"), new_token)
                    print(f"[DeviceRegistry] [AUTH] Novo token seguro gerado para [{dev.get('name')}]: {new_token}")

            if modified or not settings.get("allow_registered_only"):
                self.save(data)


# Global singleton instance
device_registry = DeviceRegistry()
device_registry.upgrade_weak_tokens()
