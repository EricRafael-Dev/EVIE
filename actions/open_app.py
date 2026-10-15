import time
import subprocess
import platform
import shutil

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

import os
import difflib
import threading

if _SYSTEM == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

# Cache de aplicativos instalados no Windows
_WIN_APPS_CACHE: dict[str, str] = {}
_WIN_APPS_LOCK = threading.Lock()
_WIN_APPS_INITIALIZED = False


def _scan_windows_installed_apps() -> dict[str, str]:
    """Varre atalhos do Menu Iniciar, Desktop, Registro e UWP sem precisar digitar no teclado."""
    apps: dict[str, str] = {}

    # 1. Atalhos do Menu Iniciar e Desktop
    dirs = [
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        os.path.join(os.environ.get("PUBLIC", ""), "Desktop"),
    ]
    for d in dirs:
        if d and os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        name = os.path.splitext(f)[0].strip().lower()
                        full_path = os.path.join(root, f)
                        if name not in apps:
                            apps[name] = full_path

    # 2. Executáveis registrados no Windows (App Paths)
    if winreg:
        for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root_key, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                val, _ = winreg.QueryValueEx(subkey, "")
                                if val:
                                    base = subkey_name.lower().replace(".exe", "")
                                    clean_val = val.strip('\"')
                                    if base not in apps and os.path.exists(clean_val):
                                        apps[base] = clean_val
                        except Exception:
                            pass
            except Exception:
                pass

    # 3. Aplicativos UWP da Windows Store (Get-StartApps)
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=6,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if _SYSTEM == "Windows" else 0,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if "|" in line:
                    parts = line.split("|", 1)
                    name = parts[0].strip().lower()
                    appid = parts[1].strip()
                    if name and name not in apps:
                        apps[name] = f"shell:AppsFolder\\{appid}"
    except Exception:
        pass

    return apps


def _ensure_win_apps_cache() -> None:
    global _WIN_APPS_INITIALIZED
    with _WIN_APPS_LOCK:
        if not _WIN_APPS_INITIALIZED:
            _WIN_APPS_INITIALIZED = True
            try:
                scanned = _scan_windows_installed_apps()
                _WIN_APPS_CACHE.update(scanned)
            except Exception as e:
                print(f"[open_app] Erro ao escanear apps do Windows: {e}")


def _find_windows_app_target(query: str) -> tuple[str | None, str | None]:
    """Busca um aplicativo instalado sem usar o teclado. Retorna (alvo, nome_amigável)."""
    _ensure_win_apps_cache()
    q = query.lower().strip()

    with _WIN_APPS_LOCK:
        # Correspondência exata
        if q in _WIN_APPS_CACHE:
            return _WIN_APPS_CACHE[q], q

        # Substring: termo dentro do nome do app ou nome do app dentro do termo
        for name, target in _WIN_APPS_CACHE.items():
            if q == name or q in name or name in q:
                return target, name

        # Similaridade aproximada (difflib)
        matches = difflib.get_close_matches(q, _WIN_APPS_CACHE.keys(), n=1, cutoff=0.6)
        if matches:
            best = matches[0]
            return _WIN_APPS_CACHE[best], best

    return None, None


def _launch_windows(app_name: str, allow_keyboard: bool = False) -> tuple[bool, str]:
    """
    Abre o aplicativo no Windows diretamente sem roubar foco ou interagir com o teclado.
    Retorna (sucesso, mensagem_ou_detalhe).
    """
    # 1. Se for comando de sistema ou caminho direto existente
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.0)
            return True, f"Abri {app_name} via executável de sistema."
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # 2. Protocolos especiais (ms-settings:, steam://, etc.)
    if ":" in app_name and "\\" not in app_name:
        try:
            os.startfile(app_name)
            time.sleep(1.0)
            return True, f"Abri o protocolo {app_name}."
        except Exception:
            try:
                subprocess.Popen(f"start {app_name}", shell=True)
                time.sleep(1.0)
                return True, f"Abri o protocolo {app_name}."
            except Exception:
                pass

    # 3. Busca direta entre os aplicativos instalados (Start Menu, Desktop, UWP, Registry)
    target, friendly_name = _find_windows_app_target(app_name)
    if target:
        try:
            print(f"[open_app] Abrindo nativamente: '{friendly_name}' -> '{target}'")
            if target.startswith("shell:AppsFolder\\"):
                # UWP Store App
                os.startfile(target)
            elif os.path.exists(target):
                os.startfile(target)
            else:
                subprocess.Popen(target, shell=True)
            time.sleep(1.2)
            return True, f"Abri o aplicativo {friendly_name}."
        except Exception as e:
            print(f"[open_app] Falha ao abrir {target}: {e}")
            try:
                subprocess.Popen(f'start "" "{target}"', shell=True)
                time.sleep(1.0)
                return True, f"Abri o aplicativo {friendly_name}."
            except Exception as e2:
                print(f"[open_app] start fallback failed: {e2}")

    # 4. Caso NÃO encontre entre os instalados:
    # Se o teclado NÃO foi expressamente autorizado, NÃO mexer no teclado do usuário!
    if not allow_keyboard:
        return False, (
            f"Não encontrei o aplicativo '{app_name}' instalado no computador. "
            f"Deseja que eu pesquise no Menu Iniciar usando o teclado?"
        )

    # 5. Fallback via teclado apenas quando expressamente autorizado
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.0)
        return True, f"Pesquisei e abri '{app_name}' pelo Menu Iniciar."
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")
        return False, f"Falha ao pesquisar pelo Menu Iniciar: {e}"



def _launch_macos(app_name: str, allow_keyboard: bool = False) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    if not allow_keyboard:
        return False

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str, allow_keyboard: bool = False) -> bool:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    app_name = params.get("app_name", "").strip()
    allow_keyboard = bool(params.get("allow_keyboard_search", False))

    if not app_name:
        return "Nenhum nome de aplicativo informado."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' -> '{normalized}' ({_SYSTEM}, allow_keyboard={allow_keyboard})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        def _invoke(cand: str) -> tuple[bool, str]:
            if _SYSTEM == "Windows":
                return _launch_windows(cand, allow_keyboard=allow_keyboard)
            ok = launcher(cand, allow_keyboard=allow_keyboard)
            return (ok, f"Opened {app_name}." if ok else "")

        ok, msg = _invoke(normalized)
        if ok:
            return msg or f"Abri {app_name} com sucesso."
        if normalized.lower() != app_name.lower():
            ok2, msg2 = _invoke(app_name)
            if ok2:
                return msg2 or f"Abri {app_name} com sucesso."
            if msg2:
                return msg2
        if msg:
            return msg
        return (
            f"Não foi possível confirmar a inicialização de {app_name}. "
            f"O aplicativo pode não estar instalado ou ainda estar carregando."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Falha ao abrir {app_name}: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": (
        "Abre qualquer aplicativo no computador diretamente a partir dos aplicativos instalados, "
        "sem roubar o foco nem mexer no teclado. "
        "Se o aplicativo não for encontrado entre os instalados, ele avisa com segurança sem digitar nada, "
        "a menos que allow_keyboard_search tenha sido expressamente autorizado pelo usuário."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Nome do aplicativo solicitado (ex: 'Premiere', 'Discord', 'Brave', 'Spotify', 'Word')"
            },
            "allow_keyboard_search": {
                "type": "BOOLEAN",
                "description": "Defina como True APENAS se o usuário confirmou ou solicitou expressamente a pesquisa com digitação pelo Menu Iniciar."
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": open_app,
}

