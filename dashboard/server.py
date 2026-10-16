"""
dashboard/server.py — JARVIS Local HTTP Dashboard

Plain HTTP on port 8000 (no SSL warnings, no firewall issues).
Security at the application layer: AES-256-CBC with session-key-derived key.
CryptoJS is auto-downloaded once and served locally — no CDN needed after that.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
import string
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from core.envelope import CommandEnvelope
from core.device_registry import device_registry

TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")

def _is_trusted_network_ip(ip_str: str) -> bool:
    """Valida se o IP é localhost, Tailscale (100.64.0.0/10) ou RFC 1918 privado."""
    if not ip_str or ip_str in ("127.0.0.1", "localhost", "::1"):
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj in TAILSCALE_NETWORK:
            return True
        if ip_obj.is_private:
            return True
    except Exception:
        pass
    return False

# When run via pythonw.exe, sys.stdout and sys.stderr are None, which breaks isatty checks
if getattr(sys, "stdout", None) is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if getattr(sys, "stderr", None) is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response, StreamingResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    FastAPI = WebSocket = WebSocketDisconnect = Request = None  # type: ignore
    HTMLResponse = JSONResponse = FileResponse = Response = StreamingResponse = None  # type: ignore
    uvicorn = None  # type: ignore

# python-multipart is required for file uploads — optional dependency
_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
PORT        = 8000
MAX_UPLOAD_MB = 500
_SERVER_INSTANCE = None



def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "JARVIS Uploads",
        Path.home() / "Documents" / "JARVIS Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'JARVIS-DASHBOARD-v1'


def _derive_key(session_key: str) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed)."""
    return hashlib.sha256(session_key.encode('utf-8') + _AES_SALT).digest()


def _decrypt_cbc(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_pad
    raw      = base64.b64decode(enc_b64)
    iv, ct   = raw[:16], raw[16:]
    dec      = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded   = dec.update(ct) + dec.finalize()
    unpadder = sym_pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


# ── CryptoJS (auto-download once, served locally) ─────────────────────────────
_CRYPTOJS_CDN  = ("https://cdnjs.cloudflare.com/ajax/libs/"
                  "crypto-js/4.2.0/crypto-js.min.js")
_CRYPTOJS_FILE = STATIC_DIR / "crypto-js.min.js"


def _ensure_network_access(port: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread — never blocks uvicorn startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys, subprocess, os, tempfile, threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes, time

        port_rule = f"JARVIS Dashboard Port {port}"
        prog_rule  = "JARVIS Dashboard Python"
        py_exe     = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port    = not _netsh_rule_exists(port_rule)
        need_prog    = not _netsh_rule_exists(prog_rule)
        need_private = _network_is_public()

        if not need_port and not need_prog and not need_private:
            return  # already fully configured

        # Build a .bat file — netsh + powershell, runs fast when elevated
        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="jarvis_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))   # Windows cmd.exe expects ANSI
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        # ── Try running directly (succeeds when already admin) ────────────────
        try:
            r = subprocess.run(
                [bat_path], capture_output=True, timeout=8, shell=True
            )
            if r.returncode == 0:
                print(f"[Dashboard] Firewall configured for port {port}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # ── ShellExecuteW: native UAC elevation (most reliable on Windows) ────
        # ShellExecuteW with verb "runas" always shows the UAC dialog regardless
        # of UAC level settings. Non-blocking — uvicorn is already running.
        print("[Dashboard] One-time network setup required.")
        print("[Dashboard] >>> A Windows security dialog will appear — click 'Yes' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,       # hwnd  (no parent window)
                "runas",    # verb  (request elevation)
                bat_path,   # file  (our .bat)
                None,       # params
                None,       # working dir
                0,          # SW_HIDE (run without a visible cmd window)
            )
            if int(ret) > 32:
                # ShellExecuteW returns immediately; bat finishes in ~1 second.
                # Sleep briefly so the rules are in place before the first retry.
                time.sleep(2)
                print(f"[Dashboard] Network setup complete — port {port} is open.")
                print("[Dashboard] Refresh your phone browser to connect.")
            else:
                print("[Dashboard] Setup was not allowed.")
                print("[Dashboard] Phone connections may fail until JARVIS is run as Administrator.")
        except Exception as e:
            print(f"[Dashboard] Firewall setup error: {e}")
        finally:
            # Cleanup after the bat has had time to run
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return  # firewall off — nothing to do

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, timeout=5,
            )
            if py in listed.stdout:
                return  # already allowed

            print("[Dashboard] One-time network setup — enter your password in the macOS dialog.")
            subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except Exception:
            pass  # macOS firewall is off by default — silent failure is fine
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    try:  # ufw
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        if "active" in r.stdout.lower():
            if _privileged(["ufw", "allow", f"{port}/tcp"]):
                print(f"[Dashboard] ufw: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:  # firewalld
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5,
        )
        if "running" in r.stdout.lower():
            ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                  and _privileged(["firewall-cmd", "--reload"]))
            if ok:
                print(f"[Dashboard] firewalld: port {port} allowed.")
            else:
                print(f"[Dashboard] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:  # iptables (not persistent but works until reboot)
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                print(f"[Dashboard] iptables: port {port} opened.")
            else:
                print(f"[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do


def _ensure_crypto_js() -> None:
    if _CRYPTOJS_FILE.exists():
        return
    try:
        import urllib.request
        print("[Dashboard] Downloading CryptoJS (one-time setup)…")
        urllib.request.urlretrieve(_CRYPTOJS_CDN, str(_CRYPTOJS_FILE))
        print("[Dashboard] CryptoJS cached — will serve locally from now on.")
    except Exception as e:
        print(f"[Dashboard] CryptoJS download failed: {e}")
        print(f"[Dashboard] Encryption will fall back to CDN load on client.")


_ensure_crypto_js()


# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""
    # Method 1: route trick (fast, works when internet is available)
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # Method 2: hostname resolution (works offline on most systems)
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Method 3: enumerate all interfaces (fully offline, no external deps)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def _ensure_certs() -> bool:
    """
    Make sure config/certs holds a TLS key pair, generating a self-signed one the
    first time the dashboard runs.

    The pair is deliberately NOT shipped in the repository. A private key that
    every user downloads is the same as having no private key at all: anyone can
    present a certificate that matches it. Generating locally gives each install
    its own key, costs about a second, and happens exactly once.

    Returns True when a usable pair exists afterwards; False leaves the caller on
    plain HTTP, which still works — the QR code simply encodes http:// instead.
    """
    certs = BASE_DIR / "config" / "certs"
    key_p = certs / "jarvis.key"
    crt_p = certs / "jarvis.crt"
    if key_p.exists() and crt_p.exists():
        return True

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("[Dashboard] cryptography not installed — serving over plain HTTP.")
        print("[Dashboard] For HTTPS run:  pip install cryptography")
        return False

    try:
        certs.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        who = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS Dashboard"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS"),
        ])

        # The SAN has to cover every address the phone might use: the LAN IP the
        # QR code encodes, plus localhost when testing on the machine itself.
        alt = [x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
        try:
            lan = _local_ip()
            if not lan.startswith("127."):
                alt.append(x509.IPAddress(ipaddress.IPv4Address(lan)))
        except Exception:
            pass          # no LAN address resolvable — localhost entries still work

        # Timezone-aware UTC: datetime.utcnow() is deprecated from Python 3.12 on,
        # and the builder normalises aware values to UTC itself.
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(who)
            .issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        key_p.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        try:
            import os as _os
            _os.chmod(key_p, 0o600)   # best effort — largely a no-op on Windows
        except Exception:
            pass

        print(f"[Dashboard] Generated a self-signed certificate for this machine: {certs}")
        return True
    except Exception as e:
        print(f"[Dashboard] Certificate generation failed ({e}) — serving over plain HTTP.")
        return False


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


async def _process_clipped_content(url: str, title: str, content: str) -> None:
    try:
        from agent_memory.router import aroute_generate, ROUTE_FAST
        from agent_memory.tools import search_second_brain, rebuild_memory_map
        import re

        prompt = (
            f"Você é a Evie (Mark LV), sintetizadora de conhecimento para o Obsidian Second Brain.\n"
            f"Analise o seguinte conteúdo capturado da web e produza um resumo estruturado em Markdown:\n"
            f"URL: {url}\n"
            f"Título: {title}\n\n"
            f"Conteúdo:\n{content[:6000]}\n\n"
            f"Gere:\n"
            f"1. Breve resumo executivo (2-3 parágrafos).\n"
            f"2. Principais conceitos e insights (bullet points com [[Conceitos Relevantes]] formatados como WikiLinks).\n"
            f"3. Lista de entidades e tópicos-chave para conexão de conhecimento."
        )

        route_res = await aroute_generate(route=ROUTE_FAST, contents=prompt)
        resumo = getattr(route_res.response, "text", str(route_res.response or "")).strip()

        # Cross-reference with existing second_brain notes
        related_fts = search_second_brain(title, limit=3)

        leituras_dir = BASE_DIR / "second_brain" / "leituras"
        leituras_dir.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r'[^\w\-]', '_', title[:40]).strip('_') or f"artigo_{int(time.time())}"
        target_file = leituras_dir / f"{safe_title}.md"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        related_str = ""
        if related_fts:
            links = []
            for item in related_fts.splitlines():
                if item.startswith("- ["):
                    p = item.split("]")[0].replace("- [", "")
                    clean_name = Path(p).stem
                    links.append(f"[[{clean_name}]]")
            if links:
                related_str = "\n\n### Notas Relacionadas no Second Brain\n" + "\n".join(f"- {l}" for l in links)

        doc = (
            f"---\n"
            f"title: \"{title}\"\n"
            f"url: \"{url}\"\n"
            f"date: {now_str}\n"
            f"tags: [web_clipper, leitura, second_brain]\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"> **Fonte:** [{url}]({url})\n\n"
            f"{resumo}\n"
            f"{related_str}\n"
        )

        target_file.write_text(doc, encoding="utf-8")
        try:
            rebuild_memory_map()
        except Exception:
            pass
        if _SERVER_INSTANCE:
            asyncio.create_task(_SERVER_INSTANCE.broadcast({
                "type": "log",
                "speaker": "sys",
                "text": f"SYS: Web Clipper salvou e indexou '{title}' no Second Brain."
            }))
    except Exception as e:
        print(f"[Clipper] Erro ao processar conteúdo web: {e}")


def get_dashboard_server() -> DashboardServer | None:
    """Retorna a instância ativa do DashboardServer."""
    return _SERVER_INSTANCE


# ── DashboardServer ───────────────────────────────────────────────────────────

class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        self._tokens: set[str]            = set()
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._interrupt_callback          = None
        self._vision_handler              = None
        self._handoff_handler             = None
        self._whiteboard_frame_handler    = None
        self._whiteboard_clients: set[WebSocket] = set()
        self._pending_keys: dict[str, float] = {}
        self._active_key_sessions: dict[str, tuple[str, str]] = {}  # key -> (token, device_token)
        self._device_sessions: dict[str, dict] = {}  # device_token → {session_key}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._geo_callback                = None
        self._last_phone_name: str        = "Poco X7"
        self._pending_file_download: tuple[dict, float] | None = None
        self._uploads_dir                 = UPLOADS_DIR
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()
        self._loop                        = None
        global _SERVER_INSTANCE
        _SERVER_INSTANCE = self

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        self._active_key_sessions = {k: v for k, v in self._active_key_sessions.items() if k in self._pending_keys}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        certs = BASE_DIR / "config" / "certs"
        return (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()

    def get_url(self) -> str:
        proto = "https" if self._ssl_enabled() else "http"
        return f"{proto}://{self._ip}:{PORT}"

    def get_manual_url(self) -> str:
        """URL for manual browser entry. When HTTPS active, points to alias port (also HTTPS)."""
        if self._ssl_enabled():
            return f"{self._ip}:{PORT + 1}"
        return f"{self._ip}:{PORT}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt_cbc(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    def set_interrupt_callback(self, fn) -> None:
        self._interrupt_callback = fn

    def set_vision_handler(self, fn) -> None:
        self._vision_handler = fn

    def set_handoff_handler(self, fn) -> None:
        self._handoff_handler = fn

    def set_whiteboard_frame_handler(self, fn) -> None:
        self._whiteboard_frame_handler = fn

    def set_geo_callback(self, fn) -> None:
        self._geo_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype not in ("file_download", "remote_desktop_authorized", "remote_desktop_request", "confirm_resolved", "confirm_request", "audio_stream", "audio", "audio_end"):
            self._history.append(msg)
            if len(self._history) > 300:
                self._history = self._history[-300:]

        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    # ── Remote Desktop & Multi-Monitor SpaceView Core ────────────────────────

    @staticmethod
    def _get_system_monitors() -> list[dict]:
        """Descobre todos os monitores conectados com suas resoluções e posições absolutas."""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QGuiApplication
            app = QApplication.instance()
            if app is None:
                import sys
                app = QApplication(sys.argv)
            screens = QGuiApplication.screens()
            monitors = []
            for i, s in enumerate(screens):
                geo = s.geometry()
                monitors.append({
                    "index": i,
                    "name": f"Monitor {i + 1}" + (" (Principal)" if i == 0 else " (Secundário)"),
                    "width": geo.width(),
                    "height": geo.height(),
                    "x": geo.x(),
                    "y": geo.y(),
                    "primary": (i == 0)
                })
            return monitors
        except Exception as exc:
            print(f"[RemoteDesktop] Erro ao enumerar telas: {exc}")
            return [{"index": 0, "name": "Monitor 1 (Principal)", "width": 1920, "height": 1080, "x": 0, "y": 0, "primary": True}]

    @staticmethod
    def _capture_monitor_jpeg(monitor_idx: int = 0, quality: int = 82, max_w: int = 2560) -> bytes:
        """Captura um frame de tela de alta performance do monitor solicitado em resolução nítida (mínimo 1080p)."""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QGuiApplication
            from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
            app = QApplication.instance()
            if app is None:
                import sys
                app = QApplication(sys.argv)
            screens = QGuiApplication.screens()
            if not screens:
                return b""
            idx = monitor_idx if 0 <= monitor_idx < len(screens) else 0
            s = screens[idx]
            pix = s.grabWindow(0)
            target_w = max(2560, max_w) if max_w >= 1920 else 2560
            if pix.width() > target_w:
                pix = pix.scaledToWidth(target_w, Qt.TransformationMode.FastTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            q = max(70, min(95, quality if quality >= 70 else 82))
            pix.save(buf, "JPEG", q)
            return bytes(ba.data())
        except Exception as exc:
            print(f"[RemoteDesktop] Erro na captura de frame da tela {monitor_idx}: {exc}")
            return b""

    @staticmethod
    def _execute_remote_input(data: dict) -> None:
        """Executa cliques, movimentos, rolagem e digitação no PC mapeando as coordenadas para o monitor."""
        try:
            action = str(data.get("action", "click")).lower()
            mon_idx = int(data.get("monitor", 0))
            norm_x = float(data.get("x", 0.5))
            norm_y = float(data.get("y", 0.5))

            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QGuiApplication
            app = QApplication.instance()
            if app is None:
                import sys
                app = QApplication(sys.argv)
            screens = QGuiApplication.screens()
            if not screens:
                return

            idx = mon_idx if 0 <= mon_idx < len(screens) else 0
            geo = screens[idx].geometry()

            abs_x = geo.x() + int(norm_x * geo.width())
            abs_y = geo.y() + int(norm_y * geo.height())

            import pyautogui
            pyautogui.FAILSAFE = False

            if action == "move":
                pyautogui.moveTo(abs_x, abs_y)
            elif action == "click":
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.click()
            elif action == "right_click":
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.rightClick()
            elif action == "double_click":
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.doubleClick()
            elif action == "down":
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.mouseDown()
            elif action == "up":
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.mouseUp()
            elif action == "scroll":
                dy = int(data.get("dy", 0))
                if dy != 0:
                    pyautogui.scroll(dy)
            elif action in ("text", "type"):
                txt = str(data.get("text", ""))
                if txt:
                    try:
                        import pyperclip
                        pyperclip.copy(txt)
                        pyautogui.hotkey("ctrl", "v")
                    except Exception:
                        pyautogui.write(txt)
            elif action == "key":
                k = str(data.get("key", "")).lower()
                if k:
                    if k in ("return", "enter"):
                        pyautogui.press("enter")
                    elif k in ("backspace", "delete", "tab", "escape", "up", "down", "left", "right"):
                        pyautogui.press(k)
                    else:
                        pyautogui.press(k)
        except Exception as exc:
            print(f"[RemoteDesktop] Falha ao processar input remoto: {exc}")

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _validate_token(raw_tok: str) -> tuple[bool, dict | None]:
            if not raw_tok:
                return False, None
            tok = raw_tok.removeprefix("Bearer ").strip()
            if not tok:
                return False, None
            for web_tok in list(self._tokens):
                if hmac.compare_digest(tok, web_tok):
                    return True, {"name": "Web Dashboard", "role": "web", "source_device_id": "desktop-web"}
            dev = device_registry.validate_token(tok)
            if dev:
                return True, {
                    "name": dev.get("name", "Mobile"),
                    "role": dev.get("role", "mobile_client"),
                    "source_device_id": dev.get("name", "mobile"),
                }
            return False, None

        def _auth(req: Request) -> bool:
            raw_tok = req.headers.get("authorization", "") or req.query_params.get("token", "")
            ok, _ = _validate_token(raw_tok)
            return ok

        def _get_authenticated_device(req: Request) -> dict | None:
            raw_tok = req.headers.get("authorization", "") or req.query_params.get("token", "")
            _, dev = _validate_token(raw_tok)
            return dev

        # serve CryptoJS from local cache, fallback to CDN redirect
        @app.get("/static/crypto.js")
        async def serve_crypto():
            if _CRYPTOJS_FILE.exists():
                return FileResponse(str(_CRYPTOJS_FILE),
                                    media_type="application/javascript")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(_CRYPTOJS_CDN)

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            # Auth is handled client-side via sessionStorage bearer token.
            # Server-side header auth can't work here because browser navigations
            # don't send custom headers (location.href doesn't carry Authorization).
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return HTMLResponse(html)

        @app.post("/login")
        async def login(req: Request):
            body    = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._active_key_sessions:
                tok, _ = self._active_key_sessions[entered]
                return JSONResponse({"ok": True, "token": tok})
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                tok = secrets.token_urlsafe(32)
                dev_tok = secrets.token_urlsafe(32)
                self._tokens.add(tok)
                self._token_keys[tok] = entered
                self._aes_key(entered)                   # pre-derive & cache
                self._device_sessions[dev_tok] = {"session_key": entered}
                self._active_key_sessions[entered] = (tok, dev_tok)
                if self._connect_callback:
                    try:
                        self._connect_callback()
                    except Exception as _cb_err:
                        print(f"[Dashboard] connect_callback error: {_cb_err}")
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            key = (key or "").strip().upper()
            now = time.time()

            # If this key already has an active session (e.g. scanner pre-fetch or reload), reuse it!
            if key and key in self._active_key_sessions:
                tok, dev_tok = self._active_key_sessions[key]
                return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},300);
</script>
<p>Connecting to JARVIS…</p>
</body></html>""")

            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#dde3ed">Remote Control</strong> in JARVIS to get a new QR code.</p>
</div></body></html>""")

            tok     = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key}
            self._active_key_sessions[key] = (tok, dev_tok)

            if self._connect_callback:
                try:
                    self._connect_callback()
                except Exception as _cb_err:
                    print(f"[Dashboard] connect_callback error: {_cb_err}")
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},300);
</script>
<p>Connecting to JARVIS…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = session_key
            self._aes_key(session_key)
            if self._connect_callback:
                try:
                    self._connect_callback()
                except Exception as _cb_err:
                    print(f"[Dashboard] connect_callback error: {_cb_err}")
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            count = len(self._device_sessions)
            self._device_sessions.clear()
            return JSONResponse({"ok": True, "revoked": count})

        @app.post("/api/command")
        async def command(req: Request):
            dev = _get_authenticated_device(req)
            if not dev:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body  = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()
            if text:
                envelope = CommandEnvelope(
                    source_device_id=dev.get("name", "Web"),
                    input_modality="text",
                    reply_audio_target="pc",
                    payload=text
                )
                await self._command_queue.put(envelope)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        # ── Native Mobile App / Tailscale Endpoints ──────────────────────────
        @app.get("/api/status")
        async def app_status(req: Request):
            """Public/Tailscale status endpoint for native mobile client."""
            from core.device_registry import device_registry
            client_ip = req.client.host if req.client else ""
            device = device_registry.get_by_ip(client_ip)
            return JSONResponse({
                "ok": True,
                "name": "Evie",
                "status": "online",
                "client_ip": client_ip,
                "device": device.get("name") if device else None,
                "registered_devices": len(device_registry.list_devices())
            })

        @app.get("/api/devices")
        async def get_devices(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.device_registry import device_registry
            return JSONResponse({"ok": True, "devices": device_registry.list_devices()})

        @app.post("/api/devices/register")
        async def register_device_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.device_registry import device_registry
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
            name = (body.get("name") or "").strip()
            ip = (body.get("ip") or (req.client.host if req.client else "")).strip()
            os_name = (body.get("os") or "").strip()
            if not name or not ip:
                return JSONResponse({"ok": False, "error": "Name and IP required"}, status_code=400)
            dev = device_registry.register_device(name=name, ip=ip, os_name=os_name)
            return JSONResponse({"ok": True, "device": dev})

        @app.post("/api/native/command")
        async def native_command(req: Request):
            """Direct JSON command endpoint for authenticated native mobile apps via Tailscale."""
            dev = _get_authenticated_device(req)
            if not dev:
                return JSONResponse({"ok": False, "error": "Unauthorized — valid Bearer token required"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
            text = (body.get("text") or "").strip()
            if not text:
                return JSONResponse({"ok": False, "error": "Empty command"}, status_code=400)
            device_name = dev.get("name", "Mobile")
            self._last_phone_name = device_name
            envelope = CommandEnvelope(
                source_device_id=device_name,
                input_modality=body.get("modality", "text"),
                reply_audio_target=body.get("reply_target", "origin_ws"),
                payload=text
            )
            await self._command_queue.put(envelope)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True, "sender": device_name})

        @app.post("/api/interrupt")
        async def interrupt_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._interrupt_callback:
                try:
                    self._interrupt_callback()
                except Exception as _e:
                    print(f"[Dashboard] interrupt error: {_e}")
            asyncio.create_task(self.broadcast({
                "type": "log",
                "speaker": "sys",
                "text": "SYS: Interrupted by user."
            }))
            return JSONResponse({"ok": True})

        @app.get("/api/sys_stats")
        async def sys_stats_ep():
            import psutil
            try:
                snap = None
                try:
                    from ui import _metrics
                    snap = _metrics.snapshot()
                except Exception:
                    pass

                if snap:
                    cpu = snap.get("cpu", 0.0)
                    mem = snap.get("mem", 0.0)
                    net_mb = snap.get("net", 0.0)
                    net_str = f"{net_mb:.1f}MB/s" if net_mb >= 0.1 else f"{int(net_mb * 1024)}KB/s"
                    gpu_val = snap.get("gpu", -1.0)
                else:
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory().percent
                    net_str = "0KB/s"
                    gpu_val = -1.0

                if gpu_val < 0:
                    try:
                        from ui import _nvml_gpu_windows
                        gpu_val = _nvml_gpu_windows()
                    except Exception:
                        pass

                boot_time = psutil.boot_time()
                uptime_secs = time.time() - boot_time
                uptime_h = int(uptime_secs // 3600)
                uptime_m = int((uptime_secs % 3600) // 60)
                return JSONResponse({
                    "cpu": round(cpu, 1),
                    "mem": round(mem, 1),
                    "net": net_str,
                    "gpu": round(gpu_val, 1) if gpu_val >= 0 else -1.0,
                    "gpu_str": f"{int(gpu_val)}%" if gpu_val >= 0 else "N/A",
                    "uptime": f"{uptime_h:02d}:{uptime_m:02d}",
                    "proc": len(psutil.pids()),
                    "os": "WIN"
                })
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        # ── Mobile Vision (Remote camera, exercise sheets, whiteboard prints) ─

        @app.post("/api/mobile/vision")
        async def mobile_vision_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            dev = _get_authenticated_device(req)
            device_id = (dev.get("name") if dev else "") or "mobile_device"

            content_type = req.headers.get("content-type", "")
            img_bytes = None
            mime_type = "image/jpeg"
            prompt = ""

            if "multipart/form-data" in content_type:
                form = await req.form()
                prompt = str(form.get("prompt", "") or "")
                file_obj = form.get("file") or form.get("image")
                if file_obj and hasattr(file_obj, "read"):
                    img_bytes = await file_obj.read()
                    mime_type = getattr(file_obj, "content_type", "image/jpeg") or "image/jpeg"
            else:
                try:
                    body = await req.json()
                    prompt = str(body.get("prompt", "") or "")
                    raw_b64 = body.get("image", "") or body.get("data", "")
                    mime_type = body.get("mime_type", "image/jpeg")
                    if "," in raw_b64:
                        raw_b64 = raw_b64.split(",", 1)[1]
                    if raw_b64:
                        img_bytes = base64.b64decode(raw_b64)
                except Exception:
                    pass

            if not img_bytes:
                return JSONResponse({"error": "Nenhuma imagem fornecida."}, status_code=400)

            if self._vision_handler:
                try:
                    res = await self._vision_handler(img_bytes, mime_type, prompt, device_id)
                    return JSONResponse({"ok": True, "result": str(res)})
                except Exception as exc:
                    return JSONResponse({"error": f"Erro no processamento de visão: {exc}"}, status_code=500)

            return JSONResponse({"ok": True, "queued": True})

        # ── Confirm Gate Remote Resolution ───────────────────────────────────

        @app.post("/api/confirm/resolve")
        async def confirm_resolve_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)

            key = str(body.get("key", "")).strip()
            accepted = bool(body.get("accepted", False))
            from core import confirm
            ok, msg = confirm.resolve_with_key(key, accepted)
            status_code = 200 if ok else 400
            return JSONResponse({"ok": ok, "message": msg}, status_code=status_code)

        # ── Mobile Offline Sync (Batch Voice/Text Notes) ─────────────────────

        @app.post("/api/mobile/offline_sync")
        async def offline_sync_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            dev = _get_authenticated_device(req)
            device_id = (dev.get("name") if dev else "") or "mobile_device"
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)

            notes = body.get("notes") or body.get("items") or []
            if not isinstance(notes, list):
                return JSONResponse({"error": "Formato inválido. Esperada lista de notas."}, status_code=400)

            from agent_memory.extractor import MemoryIngestionWorker
            worker = MemoryIngestionWorker.get_instance()
            synced = 0
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            notas_dir = BASE_DIR / "second_brain" / "notas"
            notas_dir.mkdir(parents=True, exist_ok=True)

            for item in notes:
                txt = ""
                ts = now_str
                if isinstance(item, str):
                    txt = item.strip()
                elif isinstance(item, dict):
                    txt = (item.get("text") or item.get("content") or "").strip()
                    ts = item.get("timestamp") or now_str
                if txt:
                    asyncio.create_task(worker.extract_facts_in_background(f"[Nota Offline de {device_id} ({ts})]: {txt}"))
                    slug = re.sub(r'[^\w\-]', '_', txt[:30]).strip('_') or f"offline_{int(time.time())}"
                    note_file = notas_dir / f"nota_offline_{slug}.md"
                    note_content = (
                        f"---\n"
                        f"source: mobile_offline_sync\n"
                        f"device: {device_id}\n"
                        f"date: {ts}\n"
                        f"tags: [offline_sync, nota_rapida]\n"
                        f"---\n\n"
                        f"# Nota Offline ({ts})\n\n"
                        f"{txt}\n"
                    )
                    try:
                        note_file.write_text(note_content, encoding="utf-8")
                    except Exception:
                        pass
                    synced += 1

            return JSONResponse({"ok": True, "synced_count": synced})

        # ── Audio Target Handoff (PC <-> Mobile) ──────────────────────────────

        @app.post("/api/session/handoff")
        async def session_handoff_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)
            target = str(body.get("target", "mobile")).lower()
            if target not in ("mobile", "pc"):
                return JSONResponse({"error": "Target deve ser 'mobile' ou 'pc'"}, status_code=400)
            dev = _get_authenticated_device(req)
            device_id = (dev.get("name") if dev else "") or body.get("device_id", "mobile")
            res_str = ""
            if self._handoff_handler:
                res_str = str(self._handoff_handler(target, device_id))
            else:
                res_str = f"Audio target alterado para {target}"
            asyncio.create_task(self.broadcast({
                "type": "session_handoff",
                "target": target,
                "device_id": device_id,
                "ts": time.time()
            }))
            return JSONResponse({"ok": True, "target": target, "message": res_str})

        # ── Proactivity & Autonomy Endpoints ─────────────────────────────────

        @app.get("/api/proactivity/status")
        async def proactivity_status_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from core.proactivity_engine import get_proactivity_engine
            engine = get_proactivity_engine()
            if not engine:
                return JSONResponse({"ok": False, "error": "Proactivity engine not initialized"}, status_code=503)
            return JSONResponse({"ok": True, **engine.get_status()})

        @app.post("/api/proactivity/mode")
        async def proactivity_mode_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)
            mode = body.get("mode", "")
            if not mode and "level" in body:
                lvl = int(body.get("level", 50))
                mode = "silent" if lvl == 0 else ("curious" if lvl >= 100 else "balanced")
            from core.proactivity_engine import get_proactivity_engine
            engine = get_proactivity_engine()
            if not engine:
                return JSONResponse({"ok": False, "error": "Proactivity engine not initialized"}, status_code=503)
            new_mode = engine.set_mode(mode)
            asyncio.create_task(self.broadcast({
                "type": "proactivity_mode_changed",
                "mode": new_mode,
                "level": engine.level,
                "ts": time.time(),
            }))
            return JSONResponse({"ok": True, "mode": new_mode, "level": engine.level})

        @app.post("/api/proactivity/pause")
        async def proactivity_pause_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                body = {}
            minutes = int(body.get("minutes", 60))
            from core.proactivity_engine import get_proactivity_engine
            engine = get_proactivity_engine()
            if not engine:
                return JSONResponse({"ok": False, "error": "Proactivity engine not initialized"}, status_code=503)
            msg = engine.pause_proactivity(minutes)
            asyncio.create_task(self.broadcast({
                "type": "proactivity_paused",
                "minutes": minutes,
                "ts": time.time(),
            }))
            return JSONResponse({"ok": True, "message": msg, "paused": True})

        @app.post("/api/mobile/telemetry")
        async def mobile_telemetry_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)
            from core.proactivity_engine import get_proactivity_engine
            engine = get_proactivity_engine()
            if engine:
                engine.collector.update_mobile_telemetry(body)
            return JSONResponse({"ok": True})

        # ── Server-Driven UI Action Endpoint ─────────────────────────────────

        @app.post("/api/ui_action")
        async def ui_action_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
                action_id = body.get("action_id", "")
                payload = body.get("payload", {})
                from core.ui_schema import get_action_dispatcher
                disp = get_action_dispatcher()
                if disp:
                    disp(action_id, payload)
                return JSONResponse({"ok": True, "action_id": action_id})
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        # ── Universal Clipboard ──────────────────────────────────────────────

        @app.get("/api/clipboard")
        async def get_clipboard_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            text = ""
            try:
                import pyperclip
                text = pyperclip.paste()
            except Exception:
                pass
            return JSONResponse({"ok": True, "text": text})

        @app.post("/api/clipboard")
        async def post_clipboard_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)
            text = body.get("text", "")
            if text:
                try:
                    import pyperclip
                    pyperclip.copy(text)
                except Exception:
                    pass
                asyncio.create_task(self.broadcast({
                    "type": "clipboard_sync",
                    "text": text,
                    "ts": time.time()
                }))
            return JSONResponse({"ok": True, "synced": bool(text)})

        # ── Personal AirDrop ─────────────────────────────────────────────────

        if _UPLOAD_OK:
            @app.post("/api/airdrop")
            async def airdrop_file_ep(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
                safe = _safe_filename(file.filename or "airdrop_file")
                dest = self._uploads_dir / safe
                size = 0
                with open(dest, "wb") as fout:
                    while True:
                        chunk = await file.read(65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        fout.write(chunk)
                dl_url = f"/uploads/{safe}"
                asyncio.create_task(self.broadcast({
                    "type": "airdrop_received",
                    "name": safe,
                    "size": size,
                    "url": dl_url,
                    "ts": time.time()
                }))
                return JSONResponse({"ok": True, "filename": safe, "size": size, "url": dl_url})

        # ── Semantic Web Clipper Ingestion ────────────────────────────────────

        @app.post("/api/clipper/ingest")
        async def clipper_ingest_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "JSON inválido"}, status_code=400)
            url = (body.get("url") or "").strip()
            title = (body.get("title") or "Artigo Web").strip()
            content = (body.get("content") or body.get("text") or "").strip()
            if not content:
                return JSONResponse({"error": "Conteúdo vazio"}, status_code=400)
            asyncio.create_task(_process_clipped_content(url, title, content))
            return JSONResponse({"ok": True, "message": f"Artigo '{title}' enfileirado para processamento."})

        # ── Remote Desktop & Multi-Monitor Endpoints ─────────────────────────

        @app.get("/api/remote_desktop/monitors")
        async def remote_desktop_monitors_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            monitors = await asyncio.to_thread(self._get_system_monitors)
            return JSONResponse({"ok": True, "monitors": monitors, "count": len(monitors)})

        @app.get("/api/remote_desktop/frame")
        async def remote_desktop_frame_ep(req: Request, monitor: int = 0, quality: int = 82, width: int = 2560):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            jpeg_bytes = await asyncio.to_thread(self._capture_monitor_jpeg, monitor, quality, width)
            if not jpeg_bytes:
                return JSONResponse({"error": "Failed to capture screen"}, status_code=500)
            return Response(content=jpeg_bytes, media_type="image/jpeg")

        @app.get("/stream/remote_desktop")
        async def remote_desktop_stream_ep(req: Request, monitor: int = 0, quality: int = 82, width: int = 2560, fps: int = 25):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

            async def _stream_gen():
                interval = 1.0 / max(1, min(60, fps))
                while True:
                    t0 = asyncio.get_event_loop().time()
                    jpeg = await asyncio.to_thread(self._capture_monitor_jpeg, monitor, quality, width)
                    if jpeg:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        )
                    elapsed = asyncio.get_event_loop().time() - t0
                    sleep_t = max(0.015, interval - elapsed)
                    await asyncio.sleep(sleep_t)

            return StreamingResponse(_stream_gen(), media_type="multipart/x-mixed-replace; boundary=frame")

        @app.post("/api/remote_desktop/input")
        async def remote_desktop_input_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
            await asyncio.to_thread(self._execute_remote_input, body)
            return JSONResponse({"ok": True})

        @app.post("/api/remote_desktop/request")
        async def remote_desktop_request_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from actions.computer_settings import _remote_desktop_connect
            _remote_desktop_connect()
            return JSONResponse({"ok": True, "status": "authorized", "message": "Conexão de Área de Trabalho Remota autorizada."})

        # ── Tablet Whiteboard WebSocket ──────────────────────────────────────

        @app.websocket("/ws/whiteboard")
        async def whiteboard_ws(websocket: WebSocket, token: str = ""):
            tok = (token or websocket.query_params.get("token") or "").strip()
            ok, dev = _validate_token(tok)
            if not ok:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._whiteboard_clients.add(websocket)
            try:
                while True:
                    data = await websocket.receive_json()
                    mtype = data.get("type")
                    if mtype in ("stroke", "draw", "clear", "canvas_sync"):
                        for peer in list(self._whiteboard_clients):
                            if peer != websocket:
                                try:
                                    await peer.send_json(data)
                                except Exception:
                                    pass
                    elif mtype in ("submit_frame", "analyze"):
                        img_b64 = data.get("image", "") or data.get("data", "")
                        prompt = data.get("prompt", "") or "Analise este quadro digital / diagrama em detalhes."
                        if "," in img_b64:
                            img_b64 = img_b64.split(",", 1)[1]
                        if img_b64 and self._whiteboard_frame_handler:
                            try:
                                raw = base64.b64decode(img_b64)
                                await self._whiteboard_frame_handler(raw, "image/png", prompt)
                                await websocket.send_json({"type": "status", "text": "Quadro recebido para análise da Evie."})
                            except Exception as e:
                                await websocket.send_json({"type": "error", "text": str(e)})
            except WebSocketDisconnect:
                pass
            finally:
                self._whiteboard_clients.discard(websocket)

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = (token or websocket.query_params.get("token") or "").strip()
            ok, dev = _validate_token(tok)
            if not ok:
                await websocket.close(code=4001)
                return

            if dev and dev.get("name"):
                self._last_phone_name = dev["name"]
            await websocket.accept()
            if self._wake_callback:
                try:
                    self._wake_callback()
                except Exception:
                    pass
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": f"Microphone active: [{self._last_phone_name}]."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        def _safe_filename(raw: str) -> str:
            name = Path(raw).name                          # strip path components
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
            return name or "upload"

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/download/{filename}")
        @app.get("/uploads/{filename}")
        async def download_file(filename: str, req: Request, token: str = ""):
            client_ip = req.client.host if req.client else ""
            is_trusted = _is_trusted_network_ip(client_ip)
            tok = (token or req.query_params.get("token", "")).strip()
            ok, _ = _validate_token(tok)
            if not is_trusted and not ok and not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                candidates = [
                    BASE_DIR / "uploads" / safe,
                    Path.home() / "Downloads" / "JARVIS Uploads" / safe,
                    Path.home() / "Documents" / "JARVIS Uploads" / safe,
                ]
                for c in candidates:
                    if c.exists() and c.is_file():
                        path = c
                        break
                else:
                    return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = (token or websocket.query_params.get("token") or "").strip()
            ok, dev = _validate_token(tok)
            if not ok:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            # Replay apenas de mensagens de estado e log consolidadas, ignorando chunks voláteis de streaming
            for entry in self._history[-50:]:
                etype = entry.get("type")
                if etype in ("file_download", "response_stream", "audio", "audio_stream", "audio_end"):
                    continue
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break

            if self._pending_file_download:
                p_msg, p_time = self._pending_file_download
                if (time.time() - p_time) < 300:
                    try:
                        await websocket.send_json(p_msg)
                    except Exception:
                        pass

            try:
                while True:
                    data = await websocket.receive_json()
                    mtype = data.get("type")
                    if mtype == "command":
                        enc = data.get("enc", "")
                        t   = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        dev = (data.get("device") or "Poco X7").strip()
                        if t:
                            await self._command_queue.put({"text": t, "device": dev})
                            if self._wake_callback:
                                self._wake_callback()
                    elif mtype == "interrupt":
                        if self._interrupt_callback:
                            try:
                                self._interrupt_callback()
                            except Exception as _e:
                                print(f"[Dashboard] ws interrupt error: {_e}")
                            asyncio.create_task(self.broadcast({
                                "type": "log",
                                "speaker": "sys",
                                "text": "SYS: Interrupted by mobile client."
                            }))
                    elif mtype == "ui_action":
                        action_id = data.get("action_id", "")
                        payload = data.get("payload", {})
                        try:
                            from core.ui_schema import get_action_dispatcher
                            disp = get_action_dispatcher()
                            if disp:
                                disp(action_id, payload)
                        except Exception as _e:
                            print(f"[Dashboard] ws ui_action error: {_e}")
                    elif mtype == "remote_input":
                        await asyncio.to_thread(self._execute_remote_input, data)
                    elif mtype == "remote_desktop_request":
                        from actions.computer_settings import _remote_desktop_connect
                        _remote_desktop_connect()
                    elif mtype in ("geo_location", "mobile_telemetry", "location_sync"):
                        lat = data.get("lat") or data.get("latitude")
                        lon = data.get("lon") or data.get("longitude")
                        dev_name = data.get("device") or "POCO X7 MOBILE"
                        if lat is not None and lon is not None:
                            try:
                                lat_f = float(lat)
                                lon_f = float(lon)
                                from core.proactivity_engine import get_proactivity_engine
                                eng = get_proactivity_engine()
                                if eng:
                                    eng.collector.update_mobile_telemetry({
                                        "latitude": lat_f,
                                        "longitude": lon_f,
                                        "accuracy": data.get("accuracy", 5.0),
                                        "device": dev_name
                                    })
                                if hasattr(self, "_geo_callback") and self._geo_callback:
                                    self._geo_callback(lat_f, lon_f, dev_name)
                            except Exception as _geo_err:
                                print(f"[Dashboard] ws geo_location error: {_geo_err}")
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    # ── metrics loop ───────────────────────────────────────────────────────

    async def _metrics_loop(self) -> None:
        import psutil
        while True:
            await asyncio.sleep(1.0)
            if not self._clients:
                continue
            try:
                # Read from ui._metrics which matches desktop UI exactly
                snap = None
                try:
                    from ui import _metrics
                    snap = _metrics.snapshot()
                except Exception:
                    pass

                if snap:
                    cpu = snap.get("cpu", 0.0)
                    mem = snap.get("mem", 0.0)
                    net_mb = snap.get("net", 0.0)
                    net_str = f"{net_mb:.1f}MB/s" if net_mb >= 0.1 else f"{int(net_mb * 1024)}KB/s"
                    gpu_val = snap.get("gpu", -1.0)
                    tmp_val = snap.get("tmp", -1.0)
                else:
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory().percent
                    net_str = "0KB/s"
                    gpu_val = -1.0
                    tmp_val = -1.0

                if gpu_val < 0:
                    try:
                        from ui import _nvml_gpu_windows
                        gpu_val = _nvml_gpu_windows()
                    except Exception:
                        pass

                boot_time = psutil.boot_time()
                uptime_secs = time.time() - boot_time
                uptime_h = int(uptime_secs // 3600)
                uptime_m = int((uptime_secs % 3600) // 60)
                uptime_str = f"{uptime_h:02d}:{uptime_m:02d}"

                gpu_str = f"{int(gpu_val)}%" if gpu_val >= 0 else "N/A"
                tmp_str = f"{int(tmp_val)}°C" if tmp_val >= 0 else "N/A"

                msg = {
                    "type": "sys_metrics",
                    "cpu": round(cpu, 1),
                    "mem": round(mem, 1),
                    "net": net_str,
                    "gpu": round(gpu_val, 1) if gpu_val >= 0 else -1.0,
                    "gpu_str": gpu_str,
                    "tmp_str": tmp_str,
                    "uptime": uptime_str,
                    "proc": len(psutil.pids()),
                    "os": "WIN"
                }
                dead: set[WebSocket] = set()
                for ws in list(self._clients):
                    try:
                        await ws.send_json(msg)
                    except Exception:
                        dead.add(ws)
                self._clients -= dead
            except Exception:
                pass

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_alias(self) -> None:
        """Second HTTPS server on PORT+1 sharing the same app and in-memory state.
        Chrome HTTPS-upgrades any bare IP:PORT the user types, so this port also needs TLS.
        User types IP:8001 → Chrome tries https → self-signed cert warning → accept once → done."""
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)
        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT + 1, log_level="warning",
            ssl_keyfile=str(ssl_key), ssl_certfile=str(ssl_cert),
            lifespan="off",
            log_config=None,
        )
        print(f"[Dashboard] Manual entry:  {self._ip}:{PORT + 1}  (type in browser, accept cert once)")
        for attempt in range(5):
            try:
                await uvicorn.Server(cfg).serve()
                break
            except (OSError, SystemExit) as e:
                print(f"[Dashboard] Port {PORT + 1} busy or failed ({e}), retrying in 2s ({attempt+1}/5)...")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Dashboard] Port {PORT + 1} error: {e}")
                break

    async def _serve_http_alias(self) -> None:
        """Plain HTTP server on PORT+2 (8002) exclusively on 127.0.0.1 for local browser extension."""
        try:
            cfg = uvicorn.Config(
                self.app, host="127.0.0.1", port=PORT + 2, log_level="warning",
                lifespan="off",
                log_config=None,
            )
            print(f"[Dashboard] Plain HTTP (Localhost only): http://127.0.0.1:{PORT + 2}")
            await uvicorn.Server(cfg).serve()
        except (OSError, SystemExit) as e:
            print(f"[Dashboard] Port {PORT + 2} busy or failed ({e})")
        except Exception as e:
            print(f"[Dashboard] Port {PORT + 2} error: {e}")

    async def serve(self) -> None:
        if not _DEPS_OK:
            print("[Dashboard] fastapi/uvicorn not installed — dashboard disabled.")
            print("[Dashboard] Run:  pip install fastapi 'uvicorn[standard]' cryptography")
            return

        # Firewall setup runs in a thread — uvicorn starts immediately,
        # no waiting for UAC dialogs or subprocess timeouts.
        self._loop = asyncio.get_running_loop()
        global _SERVER_INSTANCE
        _SERVER_INSTANCE = self
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)

        # Generate the TLS pair on first run so no private key ships in the repo.
        _ensure_certs()

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        asyncio.create_task(self._metrics_loop())

        if use_ssl:
            asyncio.create_task(self._serve_alias())
            asyncio.create_task(self._serve_http_alias())

        cfg_kwargs = {
            "app": self.app,
            "host": "0.0.0.0",
            "port": PORT,
            "log_level": "warning",
            "lifespan": "off",
            "log_config": None,
        }
        if use_ssl:
            cfg_kwargs["ssl_keyfile"] = str(ssl_key)
            cfg_kwargs["ssl_certfile"] = str(ssl_cert)
        cfg = uvicorn.Config(**cfg_kwargs)  # type: ignore

        proto = "https" if use_ssl else "http"
        print(f"[Dashboard] {proto}://{self._ip}:{PORT}")
        print("[Dashboard] Press 'Remote Control' in JARVIS UI to get the QR code.")
        for attempt in range(5):
            try:
                await uvicorn.Server(cfg).serve()
                break
            except (OSError, SystemExit) as e:
                print(f"[Dashboard] Port {PORT} busy or failed ({e}), retrying in 2s ({attempt+1}/5)...")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Dashboard] Server error: {e}")
                break


def broadcast_file_download(filename: str, url: str, size: int, size_str: str = "", http_url: str = "") -> bool:
    """Dispara evento WebSocket para celulares (Poco X7 / app) baixarem o arquivo automaticamente."""
    if _SERVER_INSTANCE:
        loop = getattr(_SERVER_INSTANCE, "_loop", None)
        if not loop or not loop.is_running():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except Exception:
                    loop = None
        if loop and loop.is_running():
            msg = {
                "type": "file_download",
                "name": filename,
                "url": url,
                "http_url": http_url or url,
                "size": size,
                "size_str": size_str,
                "timestamp": time.time(),
            }
            _SERVER_INSTANCE._pending_file_download = (msg, time.time())
            try:
                asyncio.run_coroutine_threadsafe(_SERVER_INSTANCE.broadcast(msg), loop)
                return True
            except Exception as e:
                print(f"[Dashboard] Erro ao enviar broadcast de download: {e}")
    return False


