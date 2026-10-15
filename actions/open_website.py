"""
Action: open_website
Allows Evie/JARVIS to open any specific website or URL directly in the user's browser,
including sensitive, private, adult, and NSFW platforms, with zero restrictions.
Includes automatic NSFW detection with discrete incognito/private mode opening.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

_BROWSER_INC_FLAGS = {
    "chrome": "--incognito",
    "edge": "-inprivate",
    "msedge": "-inprivate",
    "firefox": "-private-window",
    "brave": "--incognito",
    "opera": "--private",
    "operagx": "--private",
    "vivaldi": "--incognito",
}

# Patterns and keywords associated with adult / NSFW content
_NSFW_PATTERNS = [
    r"porn", r"xxx", r"xvideos", r"xnxx", r"redtube", r"chaturbate",
    r"onlyfans", r"erome", r"hentai", r"nsfw", r"rule34", r"brazzers",
    r"cam4", r"stripchat", r"youporn", r"spankbang", r"eporner", r"tube8",
    r"adult", r"nude", r"sex", r"xhamster", r"livejasmin", r"beeg",
]

_NSFW_REGEX = re.compile("|".join(_NSFW_PATTERNS), re.IGNORECASE)


def is_nsfw_url_or_request(text: str) -> bool:
    """Checks if the given URL, domain, or request query matches adult/NSFW patterns."""
    return bool(_NSFW_REGEX.search(text))


def _normalize_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://", "about:", "chrome://", "edge://")):
        return url
    if "." in url or ":" in url or url.startswith("localhost"):
        return f"https://{url}"
    return f"https://{url}.com"


def _find_windows_browser_exe(browser_name: str) -> Optional[str]:
    if _OS != "Windows":
        return None
    try:
        import winreg

        candidates = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{browser_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{browser_name}\shell\open\command",
        ]
        for key_path in candidates:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return shutil.which(browser_name)


def _resolve_browser_exe(browser_name: str) -> Optional[str]:
    name = browser_name.lower().strip()
    if _OS == "Windows":
        name_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "edge": "msedge",
            "msedge": "msedge",
            "microsoft edge": "msedge",
            "firefox": "firefox",
            "brave": "brave",
            "opera": "opera",
            "operagx": "opera",
        }
        target = name_map.get(name, name)
        return _find_windows_browser_exe(target)
    elif _OS == "Darwin":
        mac_apps = {
            "chrome": "Google Chrome",
            "edge": "Microsoft Edge",
            "firefox": "Firefox",
            "brave": "Brave Browser",
            "opera": "Opera",
            "safari": "Safari",
        }
        app = mac_apps.get(name)
        if app:
            p = Path("/Applications") / f"{app}.app"
            if p.exists():
                return app
    return shutil.which(name)


def open_website(
    parameters: dict | None = None,
    player=None,
    **kwargs,
) -> str:
    """
    Handler to open any website or URL requested by the user without limitation.
    NSFW sites are fully permitted; if detected, incognito mode is automatically
    used for discretion and privacy.
    """
    params = parameters or {}
    raw_url = params.get("url") or params.get("site") or params.get("link") or ""
    explicit_incognito = params.get("incognito")
    allow_nsfw = bool(params.get("allow_nsfw", True))
    is_nsfw = bool(params.get("is_nsfw", False)) or is_nsfw_url_or_request(raw_url)
    browser_choice = (params.get("browser") or "").strip().lower()

    if not raw_url:
        return "Nenhum link ou site foi fornecido para abrir."

    # NSFW permission check (enabled by default)
    if is_nsfw and not allow_nsfw:
        return "Filtro NSFW bloqueou a abertura do site."

    # If NSFW is detected or flagged, default to incognito mode for user discretion unless explicitly requested otherwise
    if explicit_incognito is not None:
        incognito = bool(explicit_incognito)
    else:
        incognito = is_nsfw  # Auto-activate private browsing for NSFW sites

    url = _normalize_url(raw_url)
    if player and hasattr(player, "write_log"):
        nsfw_tag = " [NSFW]" if is_nsfw else ""
        player.write_log(f"[open_website]{nsfw_tag} {url} (incognito={incognito})")

    print(f"[open_website] Opening '{url}' | NSFW={is_nsfw} | Incognito={incognito} | Browser={browser_choice or 'default'}")

    # If specific browser or incognito requested
    if browser_choice or incognito:
        target_browser = browser_choice or "chrome"
        flag = _BROWSER_INC_FLAGS.get(target_browser, "--incognito") if incognito else None
        exe = _resolve_browser_exe(target_browser)

        if exe:
            try:
                cmd = [exe]
                if flag:
                    cmd.append(flag)
                cmd.append(url)
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                mode_str = " no modo anônimo (privacidade/NSFW ativada)" if incognito else ""
                return f"Site aberto com sucesso{mode_str} ({target_browser}): {url}"
            except Exception as e:
                print(f"[open_website] Executable launch error: {e}")

    # Standard / Default browser launch
    try:
        if _OS == "Windows":
            os.startfile(url)
            mode_str = " no modo anônimo" if incognito else ""
            return f"Site aberto com sucesso{mode_str}: {url}"
        elif _OS == "Darwin":
            subprocess.run(["open", url], check=True, timeout=10)
            return f"Site aberto com sucesso: {url}"
        else:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Site aberto com sucesso: {url}"
    except Exception:
        try:
            webbrowser.open_new(url)
            return f"Site aberto com sucesso: {url}"
        except Exception as e:
            return f"Não foi possível abrir o site {url}: {e}"


# Tool declaration auto-discovered by core/action_loader.py
TOOL = {
    "name": "open_website",
    "description": (
        "Opens any specific website, URL, or platform requested by the user without any restrictions or censorship. "
        "Explicitly permits and supports NSFW, adult, sensitive, streaming, social networks, forums, and private sites. "
        "When an adult or NSFW site is requested, it automatically handles it with discretion and opens it in incognito/private mode."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {
                "type": "STRING",
                "description": "The exact URL, domain, or website name to open (e.g. 'https://example.com', 'xvideos.com', 'reddit.com', or any platform).",
            },
            "allow_nsfw": {
                "type": "BOOLEAN",
                "description": "Permits adult/NSFW sites. Defaults to true.",
            },
            "is_nsfw": {
                "type": "BOOLEAN",
                "description": "Set to true if the request contains adult or NSFW content to automatically enable private/incognito browsing.",
            },
            "incognito": {
                "type": "BOOLEAN",
                "description": "Set to true to force open in private/incognito mode for discretion and privacy.",
            },
            "browser": {
                "type": "STRING",
                "description": "Optional target browser: chrome | edge | firefox | brave | opera. If omitted, uses default browser.",
            },
        },
        "required": ["url"],
    },
    "handler": open_website,
}
