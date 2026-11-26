# -*- coding: utf-8 -*-
"""
Wallura – Live-Wallpaper-Engine für Windows 10/11

Quellen : lokale Dateien (mp4, webm, mkv, gif, Bilder ...), Web-Links (direkte Video-Links
          oder alles, was yt-dlp kann) und YouTube-Links.
Rendering: mpv, eingebettet hinter den Desktop-Icons (Progman/WorkerW-Trick).

Copyright (c) 2026 MorreTv. MIT-Lizenz (siehe LICENSE).
"""
import ctypes
import hashlib
import hmac
import io
import json
import os
import queue
import random
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import pystray
import win32api
import win32con
import win32event
import win32gui
import win32job
import win32process
import winerror
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

# ----------------------------------------------------------------------------- Pfade
APP_NAME = "Wallura"
COPYRIGHT = "© 2026 MorreTv. Open Source (MIT)"
APP_VERSION = "2.2.0"   # wird vom Build / GitHub-Workflow aus dem Release-Tag gesetzt
# GitHub-Repo für automatische Updates ("benutzername/repo"). Dort muss pro Version ein Release
# mit der Datei Wallura-Setup.exe liegen (Repo bzw. Releases müssen öffentlich sein).
GITHUB_REPO = "MorreTv/Wallura"
# Server für die zentrale Kontenliste (Code im Ordner "cloud/"). Leer = Konten bleiben nur lokal.
CLOUD_URL = "https://wallura-konten-1jomkz.freebuff.site"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
# Mitgelieferte Bilder (PyInstaller entpackt sie nach _MEIPASS, sonst neben wallura.py)
ASSET_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "assets"
DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / APP_NAME
# Umzug von der alten Version: %APPDATA%\\LiveWall -> %APPDATA%\\Wallura (Einstellungen, Downloads, Tools)
OLD_APP_NAME = "LiveWall"
_OLD_DIR = DATA_DIR.parent / OLD_APP_NAME
if _OLD_DIR.exists() and not DATA_DIR.exists():
    try:
        shutil.move(str(_OLD_DIR), str(DATA_DIR))
    except Exception:
        pass
LIB_DIR = DATA_DIR / "downloads"
THUMB_DIR = DATA_DIR / "thumbs"


def log_exception(exc_type, exc, tb):
    """Fehler auch ohne Konsole festhalten (%APPDATA%/Wallura/error.log)."""
    try:
        import traceback
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DATA_DIR / "error.log", "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S\n"))
            traceback.print_exception(exc_type, exc, tb, file=fh)
            fh.write("\n")
    except Exception:
        pass
    try:
        sys.__excepthook__(exc_type, exc, tb)
    except Exception:
        pass


sys.excepthook = log_exception
TOOLS_USER = DATA_DIR / "tools"
TOOLS_APP = APP_DIR / "tools"
UPDATE_DIR = DATA_DIR / "update"
CONFIG_FILE = DATA_DIR / "config.json"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
SESSION_FILE = DATA_DIR / "session.json"
PASSWORD_ROUNDS = 200_000
MIN_PW_LEN = 4
USER_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,32}$")
ROLES = {"admin": "Administrator", "user": "Nutzer"}
ADMIN_NAME = "Admin"   # Besitzerkonto: nur dieses Konto ist von Anfang an Administrator
GAST = "Gast"
for _d in (DATA_DIR, LIB_DIR, THUMB_DIR, TOOLS_USER, UPDATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CREATE_NO_WINDOW = 0x08000000
ACCENT = "#5cc8ff"
ACCENT_HOVER = "#8adcff"
ACCENT_DIM = "#2d7d9d"
ON_ACCENT = "#041e2a"
BG = "#08090d"
SURFACE = "#111319"
SURFACE2 = "#191c24"
SURFACE3 = "#20242e"
BORDER = "#262b36"
TEXT = "#f3f5f9"
MUTED = "#8d96a8"
DANGER_TEXT = "#ff8f94"
FONT = "Segoe UI"
STATUS_OK = "#c9d1dd"
STATUS_ERR = "#ff8489"
SIDEBAR_W = 252
CARD_RADIUS = 18
BTN_RADIUS = 11
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Wallura"}

VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".gif")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MEDIA_EXT = VIDEO_EXT + IMAGE_EXT
YT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.I)
YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")

FIT_MAP = {"Füllen (zuschneiden)": "cover", "Einpassen (Balken)": "contain", "Strecken": "stretch"}
QUALITIES = ["720", "1080", "1440", "2160"]
FPS_MAP = {"Original": 0, "60 FPS": 60, "30 FPS": 30, "24 FPS (sparsam)": 24}
# Premium: eigener Desktop (Hintergrund + Uhr/Datum/Text wie bei Rainmeter)
DESK_ID = "desk"
DESK_THEMES = {"Anime-Dämmerung": "anime.jpg", "Neon-Auto": "auto.jpg",
               "Bergmorgen": "natur.jpg", "Neon-Wellen": "neon.jpg"}
DESK_POS = {"Unten links": "bl", "Unten rechts": "br", "Unten mitte": "bc",
            "Oben links": "tl", "Oben rechts": "tr"}
DESK_COLORS = {"Weiß": "FFFFFF", "Anthrazit": "16181D", "Akzent": "FFC24C",
               "Gold": "3FBFF5", "Mint": "C0F07E", "Rosé": "AE6FFF"}
DESK_COLOR_RGB = {"Weiß": (255, 255, 255), "Anthrazit": (22, 24, 29), "Akzent": (76, 194, 255),
                  "Gold": (245, 191, 63), "Mint": (126, 240, 192), "Rosé": (255, 111, 174)}
# Schriftarten für Uhr, Datum und Text: (normale Datei, fette Datei, Name im Live-Overlay)
DESK_FONTS = {
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf", "Segoe UI"),
    "Segoe UI Semibold": ("seguisb.ttf", "seguisb.ttf", "Segoe UI Semibold"),
    "Segoe UI Light": ("seguil.ttf", "seguisb.ttf", "Segoe UI Light"),
    "Arial": ("arial.ttf", "arialbd.ttf", "Arial"),
    "Arial Black": ("ariblk.ttf", "ariblk.ttf", "Arial Black"),
    "Verdana": ("verdana.ttf", "verdanab.ttf", "Verdana"),
    "Tahoma": ("tahoma.ttf", "tahomabd.ttf", "Tahoma"),
    "Trebuchet MS": ("trebuc.ttf", "trebucbd.ttf", "Trebuchet MS"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "Calibri"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "Georgia"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "Times New Roman"),
    "Consolas": ("consola.ttf", "consolab.ttf", "Consolas"),
    "Courier New": ("cour.ttf", "courbd.ttf", "Courier New"),
    "Impact": ("impact.ttf", "impact.ttf", "Impact"),
    "Comic Sans MS": ("comic.ttf", "comicbd.ttf", "Comic Sans MS"),
}
DESK_WEEK = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
DESK_MONTH = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
              "September", "Oktober", "November", "Dezember")
ROTATE_MAP = {"Aus": 0, "Alle 5 Minuten": 5, "Alle 15 Minuten": 15, "Alle 30 Minuten": 30,
              "Jede Stunde": 60, "Alle 3 Stunden": 180}
SORTS = {"Zuletzt hinzugefügt": "new", "Titel A–Z": "az", "Meistgesehen": "plays",
         "Favoriten zuerst": "fav"}
SPEED_MAP = {"0,5×": 0.5, "0,75×": 0.75, "Normal": 1.0, "1,25×": 1.25, "1,5×": 1.5, "2×": 2.0}
BRIGHT_MAP = {"100 %": 100, "85 %": 85, "70 %": 70, "50 %": 50}
BELOW_NORMAL_PRIORITY = 0x00004000
KIND_LABEL = {"local": "Lokal", "youtube": "YouTube", "web": "Web"}
KIND_FILTER = {"Alle": None, "★ Favoriten": "fav", "Lokal": "local", "YouTube": "youtube", "Web": "web"}

DEFAULTS = {
    "items": [],
    "current": None,      # alt (vor 1.1) – wird zu "assign" migriert
    "assign": {},         # Monitor-Index (als Text) -> Wallpaper-ID
    "volume": 0,
    "fit": "cover",
    "monitor": "all",
    "quality": "1080",
    "fps_limit": 30,
    "rotate_min": 0,      # automatischer Wechsel in Minuten (0 = aus)
    "sort": "new",       # Reihenfolge der Bibliothek
    "fav_playlist": False,  # Wechsel nur mit Favoriten
    "quiet_hours": False,   # nachts (22–7 Uhr) nicht automatisch wechseln
    "pause_battery": False,  # im Akkubetrieb pausieren
    "random_start": False,   # beim Start ein zufälliges Wallpaper
    "notify_rotate": True,   # Hinweis beim automatischen Wechsel
    "speed": 1.0,        # Wiedergabegeschwindigkeit
    "flip": False,       # Bild horizontal spiegeln
    "rotate180": False,  # Bild um 180° drehen
    "brightness": 100,   # Helligkeit in Prozent
    "grayscale": False,  # Schwarzweiß
    "night_id": "",      # Wallpaper für die Nacht (20–7 Uhr)
    "last_kind": "Alle", # zuletzt gewählter Bibliotheksfilter
    "pause_fullscreen": True,
    "autostart": False,
    "auto_update": True,
    "update_repo": "",    # optional: überschreibt GITHUB_REPO
    "cloud_token": "",    # Zugang zur Konten-Übersicht (wird beim Freischalten gesetzt)
    "desk": {             # Premium: eigener Desktop mit Uhr/Datum/Text
        "bg": "",         # eigener Hintergrund (Bild/Video), leer = Thema
        "theme": "Anime-Dämmerung",
        "clock": True,
        "date": True,
        "text": "",
        "pos": "Unten links",
        "color": "Weiß",
        "font": "Segoe UI",
        "size": 72,
    },
}


# ----------------------------------------------------------------------------- UI-Helfer
def ui_font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


MENU_STYLE = dict(fg_color=SURFACE2, button_color=SURFACE3, button_hover_color=BORDER,
                  dropdown_fg_color=SURFACE2, dropdown_hover_color=SURFACE3, dropdown_text_color=TEXT,
                  text_color=TEXT, corner_radius=10, height=34)


# ----------------------------------------------------------------------------- Config
_CONFIG_LOCK = threading.Lock()


def _write_json(path, data):
    """Schreibt JSON atomar (erst .tmp, dann ersetzen), damit bei einem Absturz keine halbe Datei bleibt."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _CONFIG_LOCK:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "ja")
    return default


def _clean_item(item):
    """Prüft einen Bibliothekseintrag aus der Config. -> bereinigtes dict oder None."""
    if not isinstance(item, dict):
        return None
    iid, src = item.get("id"), item.get("src")
    if not isinstance(iid, str) or not iid or not isinstance(src, str) or not src.strip():
        return None
    kind = item.get("kind") if item.get("kind") in KIND_LABEL else detect_kind(src)
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        title = src
    clean = dict(item)
    clean.update({"id": iid, "src": src, "kind": kind, "title": title})
    return clean


def load_config():
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    # Ungültige oder alte Werte reparieren, damit ein kaputter Eintrag nicht den Start verhindert.
    raw_items = cfg.get("items")
    cfg["items"] = [it for it in (_clean_item(i) for i in raw_items) if it] if isinstance(raw_items, list) else []
    if DATA_DIR.exists() and not _OLD_DIR.exists():  # Pfade heruntergeladener Dateien auf den neuen Ordner umbiegen
        old = str(_OLD_DIR)
        for it in cfg["items"]:
            src = it["src"]
            if src == old or src.startswith(old + os.sep):
                it["src"] = str(DATA_DIR) + src[len(old):]
    raw_assign = cfg.get("assign")
    cfg["assign"] = ({str(k): v for k, v in raw_assign.items() if str(k).isdigit() and isinstance(v, str)}
                     if isinstance(raw_assign, dict) else {})
    if cfg.get("fit") not in FIT_MAP.values():
        cfg["fit"] = DEFAULTS["fit"]
    try:
        cfg["volume"] = max(0, min(100, int(cfg.get("volume", 0))))
    except (TypeError, ValueError):
        cfg["volume"] = DEFAULTS["volume"]
    quality = str(cfg.get("quality", ""))
    cfg["quality"] = quality if quality in QUALITIES else DEFAULTS["quality"]
    try:
        fps = int(cfg.get("fps_limit", DEFAULTS["fps_limit"]))
    except (TypeError, ValueError):
        fps = DEFAULTS["fps_limit"]
    cfg["fps_limit"] = fps if fps in FPS_MAP.values() else DEFAULTS["fps_limit"]
    try:
        rot = int(cfg.get("rotate_min", 0))
    except (TypeError, ValueError):
        rot = 0
    cfg["rotate_min"] = rot if rot in ROTATE_MAP.values() else DEFAULTS["rotate_min"]
    cfg["monitor"] = str(cfg.get("monitor") or "all")
    cfg["update_repo"] = cfg["update_repo"] if isinstance(cfg.get("update_repo"), str) else ""
    for key in ("pause_fullscreen", "autostart", "auto_update"):
        cfg[key] = _as_bool(cfg.get(key), DEFAULTS[key])
    cfg["sort"] = cfg.get("sort") if cfg.get("sort") in SORTS.values() else DEFAULTS["sort"]
    try:
        speed = float(cfg.get("speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    cfg["speed"] = speed if speed in SPEED_MAP.values() else DEFAULTS["speed"]
    try:
        bright = int(cfg.get("brightness", 100))
    except (TypeError, ValueError):
        bright = 100
    cfg["brightness"] = bright if bright in BRIGHT_MAP.values() else DEFAULTS["brightness"]
    raw_desk = cfg.get("desk") if isinstance(cfg.get("desk"), dict) else {}
    base_desk = DEFAULTS["desk"]
    try:
        desk_size = max(32, min(140, int(raw_desk.get("size", base_desk["size"]))))
    except (TypeError, ValueError):
        desk_size = base_desk["size"]
    cfg["desk"] = {
        "bg": raw_desk.get("bg") if isinstance(raw_desk.get("bg"), str) else "",
        "theme": raw_desk.get("theme") if raw_desk.get("theme") in DESK_THEMES else base_desk["theme"],
        "clock": _as_bool(raw_desk.get("clock", True), True),
        "date": _as_bool(raw_desk.get("date", True), True),
        "text": " ".join(str(raw_desk.get("text") or "").split())[:80],
        "pos": raw_desk.get("pos") if raw_desk.get("pos") in DESK_POS else base_desk["pos"],
        "color": raw_desk.get("color") if raw_desk.get("color") in DESK_COLORS else base_desk["color"],
        "font": raw_desk.get("font") if raw_desk.get("font") in DESK_FONTS else base_desk["font"],
        "size": desk_size,
    }
    cfg["night_id"] = cfg.get("night_id") if isinstance(cfg.get("night_id"), str) else ""
    cfg["last_kind"] = cfg.get("last_kind") if cfg.get("last_kind") in KIND_FILTER else DEFAULTS["last_kind"]
    for key in ("fav_playlist", "quiet_hours", "pause_battery", "random_start", "notify_rotate",
                "flip", "rotate180", "grayscale"):
        cfg[key] = _as_bool(cfg.get(key), DEFAULTS[key])
    return cfg


def save_config(cfg):
    try:
        _write_json(CONFIG_FILE, cfg)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------- Konten
def _hash_password(pw):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(pw).encode("utf-8"), salt, PASSWORD_ROUNDS)
    return f"pbkdf2_sha256${PASSWORD_ROUNDS}${salt.hex()}${digest.hex()}"


def _password_ok(pw, stored):
    try:
        algo, rounds, salt_hex, digest_hex = str(stored).split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", str(pw).encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def load_accounts():
    data = None
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    raw = data.get("users") if isinstance(data, dict) else None
    users = {}
    for key, user in (raw if isinstance(raw, dict) else {}).items():
        if not isinstance(user, dict) or not isinstance(user.get("pw"), str):
            continue
        key = str(key).strip().lower()
        if not key:
            continue
        name = user.get("name")
        users[key] = {"name": name if isinstance(name, str) and name.strip() else key,
                      "pw": user["pw"],
                      "role": ("admin" if user.get("role") == "admin" or key == ADMIN_NAME.lower()
                               else "user"),
                      "premium": bool(user.get("premium")),
                      "created": user.get("created") if isinstance(user.get("created"), int) else 0}
    # Kein automatischer Aufstieg zum Administrator: neue Konten bleiben normale Nutzer,
    # auch wenn auf dem PC noch kein Administrator existiert.
    return {"users": users}


def save_accounts(acc):
    try:
        _write_json(ACCOUNTS_FILE, acc)
        return True
    except Exception:
        return False


def has_accounts(acc=None):
    return bool((acc or load_accounts())["users"])


def find_account(acc, name):
    return acc["users"].get(str(name).strip().lower())


def create_account(acc, name, pw, role="user"):
    """-> (ok, Fehlertext)"""
    name = str(name).strip()
    if not USER_NAME_RE.match(name):
        return False, "Name: 2–32 Zeichen, nur Buchstaben, Zahlen, Punkt, _ und -"
    if len(str(pw)) < MIN_PW_LEN:
        return False, f"Das Passwort braucht mindestens {MIN_PW_LEN} Zeichen."
    if name.lower() in acc["users"]:
        return False, "Diesen Benutzernamen gibt es schon."
    if role not in ROLES:
        return False, "Unbekannte Rolle."
    entry = {"name": name, "pw": _hash_password(pw), "role": role, "premium": False,
             "created": int(time.time())}
    acc["users"][name.lower()] = entry
    if not save_accounts(acc):
        acc["users"].pop(name.lower(), None)
        return False, "Die Konten-Datei ließ sich nicht speichern."
    return True, ""


def authenticate(acc, name, pw):
    user = find_account(acc, name)
    if user and _password_ok(pw, user.get("pw")):
        return user
    return None


def admin_count(acc):
    return sum(1 for u in acc["users"].values() if u.get("role") == "admin")


def set_password(acc, name, pw):
    user = find_account(acc, name)
    if not user:
        return False, "Konto nicht gefunden."
    if len(str(pw)) < MIN_PW_LEN:
        return False, f"Das Passwort braucht mindestens {MIN_PW_LEN} Zeichen."
    old = user.get("pw")
    user["pw"] = _hash_password(pw)
    if not save_accounts(acc):
        user["pw"] = old
        return False, "Die Konten-Datei ließ sich nicht speichern."
    return True, ""


def set_role(acc, name, role):
    user = find_account(acc, name)
    if not user:
        return False, "Konto nicht gefunden."
    if role not in ROLES:
        return False, "Unbekannte Rolle."
    if user.get("role") == "admin" and role != "admin" and admin_count(acc) <= 1:
        return False, "Der letzte Administrator kann nicht herabgestuft werden."
    old = user.get("role")
    user["role"] = role
    if not save_accounts(acc):
        user["role"] = old
        return False, "Die Konten-Datei ließ sich nicht speichern."
    return True, ""


def set_premium(acc, name, on):
    """Premium für ein Konto setzen (nur der Desktop-Editor nutzt das)."""
    user = find_account(acc, name)
    if not user:
        return False, "Konto nicht gefunden."
    old = user.get("premium", False)
    user["premium"] = bool(on)
    if not save_accounts(acc):
        user["premium"] = old
        return False, "Die Konten-Datei ließ sich nicht speichern."
    return True, ""


def delete_account(acc, name):
    user = find_account(acc, name)
    if not user:
        return False, "Konto nicht gefunden."
    if user.get("role") == "admin" and admin_count(acc) <= 1:
        return False, "Der letzte Administrator kann nicht gelöscht werden."
    key = str(name).strip().lower()
    removed = acc["users"].pop(key, None)
    if not save_accounts(acc):
        if removed is not None:
            acc["users"][key] = removed
        return False, "Die Konten-Datei ließ sich nicht speichern."
    return True, ""


def _pw_fingerprint(user):
    """Kurzer Fingerabdruck des Passwort-Hashes – merkt eine Änderung/ Zurücksetzung."""
    return hashlib.sha256(str(user.get("pw", "")).encode("utf-8")).hexdigest()[:16]


def clear_session():
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def save_session(name, remember=True):
    """Merkt die Anmeldung für den nächsten Start („Angemeldet bleiben“)."""
    if not remember:
        clear_session()
        return True
    user = find_account(load_accounts(), name)
    if not user:
        return False
    try:
        _write_json(SESSION_FILE, {"user": str(name).strip().lower(), "fp": _pw_fingerprint(user)})
        return True
    except Exception:
        return False


def load_session():
    """-> {"name", "role"} der gemerkten Anmeldung oder None (dann Gastmodus)."""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    key = str(data.get("user", "")).strip().lower()
    user = find_account(load_accounts(), key)
    if not user or data.get("fp") != _pw_fingerprint(user):
        clear_session()  # Konto gelöscht oder Passwort geändert -> wieder Anmeldung nötig
        return None
    return {"name": user.get("name", key), "role": user.get("role", "user"),
            "premium": bool(user.get("premium"))}


# ----------------------------------------------------------------------------- Konten-Übersicht
# Jeder PC meldet seine Konten an den Server; die Liste sieht nur der Administrator,
# der sie einmal mit seinem Passwort freischaltet.
def _device_name():
    return (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "PC")[:64]


CLOUD_HOST = (urllib.parse.urlparse(CLOUD_URL).hostname or "").lower()


def cloud_log(text):
    """Technische Hinweise zur Kontenliste in %APPDATA%/Wallura/error.log festhalten."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DATA_DIR / "error.log", "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S  Kontenliste: ") + str(text) + "\n")
    except Exception:
        pass


def is_cert_error(exc):
    text = str(exc).lower()
    return "certificate verify failed" in text or "certificate_verify_failed" in text


def cloud_error_text(exc, what):
    """Lesbare Meldung statt des rohen OpenSSL-Textes."""
    if is_cert_error(exc):
        return (f"{what}: Die Zertifikatsprüfung ist auf diesem PC fehlgeschlagen – meist ein "
                "abgelaufenes Zertifikat im Windows-Speicher oder ein Virenscanner/Proxy dazwischen. "
                "Details stehen in der Datei error.log.")
    return f"{what} ({exc})."


_TRUST_CONTEXTS = None


def _trust_contexts():
    """Mögliche Vertrauensspeicher für HTTPS: Windows-Speicher und (falls vorhanden) certifi.

    Der Zertifikatsspeicher mancher PCs enthält abgelaufene Zertifikate oder wurde von
    Virenscannern verändert – dann scheitert die Prüfung, obwohl der Server in Ordnung ist.
    """
    global _TRUST_CONTEXTS
    if _TRUST_CONTEXTS is not None:
        return _TRUST_CONTEXTS
    contexts = []
    try:
        contexts.append(("Windows", ssl.create_default_context()))
    except Exception as e:
        cloud_log(f"Systemspeicher nicht nutzbar: {e}")
    try:
        import certifi
        contexts.append(("certifi", ssl.create_default_context(cafile=certifi.where())))
    except Exception:
        pass
    _TRUST_CONTEXTS = contexts
    return contexts


def _cloud_open(req, timeout, allow_unverified=False):
    """Anfrage an die Kontenliste – mit mehreren Versuchen, damit ein kaputter
    Zertifikatsspeicher oder ein Proxy den Abruf nicht dauerhaft blockiert.

    Ohne Zertifikatsprüfung darf nur eine Anfrage ohne Zugangsdaten laufen: sonst
    könnte ein Angreifer im Netz den Administrator-Token mitlesen.
    """
    errors = []
    for direct in (False, True):  # erst normal, dann am System-Proxy vorbei
        for label, ctx in _trust_contexts():
            handlers = [urllib.request.HTTPSHandler(context=ctx)]
            if direct:
                handlers.append(urllib.request.ProxyHandler({}))
            opener = urllib.request.build_opener(*handlers)
            try:
                with opener.open(req, timeout=timeout) as r:
                    return r.read()
            except urllib.error.HTTPError:
                raise  # der Server hat geantwortet, TLS war also in Ordnung
            except Exception as e:
                errors.append((f"{label}{' ohne Proxy' if direct else ''}", e))
                if not is_cert_error(e):
                    break  # Netzwerkfehler – ein anderer Zertifikatsspeicher hilft nicht
    # Letzter Ausweg, nur für die eigene Konten-Adresse: Manche PCs können die Kette
    # dauerhaft nicht prüfen. Dann ohne Prüfung, aber nur wenn es wirklich daran lag.
    if (allow_unverified and not req.has_header("Authorization")
            and any(is_cert_error(e) for _, e in errors)
            and (urllib.parse.urlparse(req.full_url).hostname or "").lower() == CLOUD_HOST):
        cloud_log("Zertifikatsprüfung fehlgeschlagen – Abruf ohne Prüfung: "
                  + " | ".join(f"{label}: {e}" for label, e in errors))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                             urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return r.read()
    if errors:
        raise errors[-1][1]
    raise OSError("Kein HTTPS-Zugriff möglich")


def _cloud_json(path, payload=None, token="", timeout=10):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = dict(UA)
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(CLOUD_URL.rstrip("/") + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    # Nur unkritische Anfragen (ohne Token und ohne Token im Body) dürfen im Notfall
    # ohne Zertifikatsprüfung laufen – der Administrator-Token nie.
    unverified = not token and data is None
    return json.loads(_cloud_open(req, timeout, allow_unverified=unverified).decode("utf-8") or "{}")


def report_account(name):
    """Meldet ein Konto dieses PCs an die zentrale Liste (Fehler bleiben still)."""
    if not CLOUD_URL:
        return
    try:
        _cloud_json("/api/register", {"name": name, "device": _device_name(),
                                      "platform": "Windows", "version": APP_VERSION})
    except Exception:
        pass


def report_account_async(name):
    threading.Thread(target=report_account, args=(name,), daemon=True).start()


def fetch_cloud_accounts(token):
    return _cloud_json("/api/accounts", token=token).get("accounts") or []


def claim_cloud(token):
    """Erster Administrator übernimmt die Übersicht. -> (ok, Fehlertext)"""
    try:
        res = _cloud_json("/api/claim", {"token": token})
        return bool(res.get("ok")), ""
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return False, "Die Übersicht wurde bereits übernommen. Bitte auf dem PC öffnen, der sie freigeschaltet hat."
        return False, f"Server-Fehler {e.code}."
    except Exception as e:
        return False, cloud_error_text(e, "Server nicht erreichbar")


# ----------------------------------------------------------------------------- Tools & Helfer
def find_tool(name):
    exe = f"{name}.exe"
    links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
    for base in (TOOLS_USER, TOOLS_APP, APP_DIR, links):
        p = base / exe
        if p.exists():
            return str(p)
    return shutil.which(name)


def run_hidden(cmd, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=CREATE_NO_WINDOW, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def detect_kind(src):
    if re.match(r"https?://", src, re.I):
        return "youtube" if YT_RE.search(src) else "web"
    return "local"


def is_direct_media(url):
    return urllib.parse.urlparse(url).path.lower().endswith(MEDIA_EXT)


def shorten(text, n):
    return text if len(text) <= n else text[: n - 1] + "…"


def refresh_wallpaper():
    """Zeigt nach dem Beenden wieder das normale Windows-Hintergrundbild."""
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, None, 0x03)
    except Exception:
        pass


# ----------------------------------------------------------------------------- Thumbnails & Metadaten
def placeholder(w=480, h=270):
    img = Image.new("RGB", (w, h), (32, 34, 40))
    ImageDraw.Draw(img).polygon([(w * .43, h * .35), (w * .43, h * .65), (w * .60, h * .5)], fill=(90, 95, 110))
    return img


def make_icon(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 2, size - 2), radius=size // 4, fill=(76, 194, 255, 255))
    d.polygon([(size * .38, size * .28), (size * .38, size * .72), (size * .74, size * .5)], fill=(255, 255, 255, 255))
    return img


def save_thumb(item_id, img):
    img = ImageOps.fit(img.convert("RGB"), (480, 270))
    img.save(THUMB_DIR / f"{item_id}.jpg", quality=85)


def make_local_thumb(item_id, path):
    path = Path(path)
    try:
        if path.suffix.lower() in IMAGE_EXT:
            save_thumb(item_id, Image.open(path))
            return
        mpv = find_tool("mpv")
        if not mpv:
            return
        tmp = THUMB_DIR / f"tmp_{item_id}"
        tmp.mkdir(exist_ok=True)
        try:
            run_hidden([mpv, "--no-config", "--no-audio", "--hwdec=no", "--vo=image", "--vo-image-format=jpg",
                        f"--vo-image-outdir={tmp}", "--start=10%", "--frames=1", "--no-terminal", str(path)], 45)
            files = sorted(tmp.glob("*.jpg"))
            if files:
                save_thumb(item_id, Image.open(files[0]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass


def fetch_meta(url):
    """-> (Titel, Thumbnail-URL oder None)"""
    if YT_RE.search(url):
        m = YT_ID_RE.search(url)
        thumb = f"https://img.youtube.com/vi/{m.group(1)}/mqdefault.jpg" if m else None
        try:
            data = json.loads(http_get("https://www.youtube.com/oembed?format=json&url="
                                       + urllib.parse.quote(url, safe="")))
            return data.get("title", url), thumb or data.get("thumbnail_url")
        except Exception:
            return url, thumb
    if is_direct_media(url):
        return Path(urllib.parse.urlparse(url).path).name or url, None
    ytdlp = find_tool("yt-dlp")
    if ytdlp:
        try:
            code, out = run_hidden([ytdlp, "--no-playlist", "--skip-download", "--no-warnings",
                                    "--print", "%(title)s", "--print", "%(thumbnail)s", url], 45)
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if code == 0 and lines:
                thumb = lines[1] if len(lines) > 1 and lines[1].startswith("http") else None
                return lines[0], thumb
        except Exception:
            pass
    return urllib.parse.urlparse(url).netloc or url, None


# ----------------------------------------------------------------------------- Download
def download_item(item, quality, progress):
    """Lädt item['src'] in den Download-Ordner. -> Pfad der Datei"""
    url = item["src"]
    if is_direct_media(url):
        ext = Path(urllib.parse.urlparse(url).path).suffix or ".mp4"
        dest, tmp = LIB_DIR / f"{item['id']}{ext}", LIB_DIR / f"{item['id']}.part"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r, \
                    open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        progress(done * 100 / total)
            tmp.replace(dest)
        except BaseException:
            tmp.unlink(missing_ok=True)  # keine halbe Datei im Download-Ordner zurücklassen
            raise
        return dest

    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp fehlt – bitte unter Einstellungen auf „Tools installieren“ klicken.")
    ffmpeg = find_tool("ffmpeg")
    q = quality
    fmt = (f"bv*[height<=?{q}]+ba/b[height<=?{q}]/b" if ffmpeg
           else f"b[height<=?{q}][ext=mp4]/b[height<=?{q}]/b")
    cmd = [ytdlp, "--no-playlist", "--newline", "--no-warnings", "-f", fmt,
           "-o", str(LIB_DIR / f"{item['id']}.%(ext)s"),
           "--progress-template", "download:%(progress._percent_str)s"]
    if ffmpeg:
        cmd += ["--merge-output-format", "mp4", "--ffmpeg-location", str(Path(ffmpeg).parent)]
    cmd.append(url)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
    last = ""
    for line in proc.stdout:
        last = line.strip() or last
        m = re.search(r"(\d+(?:\.\d+)?)%", line)
        if m:
            progress(float(m.group(1)))
    proc.wait()
    files = [p for p in LIB_DIR.glob(f"{item['id']}.*") if p.suffix not in (".part", ".ytdl")]
    if proc.returncode != 0 or not files:
        for p in LIB_DIR.glob(f"{item['id']}.*"):
            if p.suffix in (".part", ".ytdl"):
                p.unlink(missing_ok=True)
        raise RuntimeError(last or "Download fehlgeschlagen")
    return max(files, key=lambda p: p.stat().st_mtime)


def install_tools(say):
    """yt-dlp direkt von GitHub laden, mpv über winget installieren (falls es fehlt)."""
    msgs = []
    tmp = TOOLS_USER / "yt-dlp.exe.tmp"
    try:
        say("Lade yt-dlp …")
        data = http_get("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", timeout=180)
        tmp.write_bytes(data)
        tmp.replace(TOOLS_USER / "yt-dlp.exe")
        msgs.append("yt-dlp aktualisiert")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        msgs.append(f"yt-dlp-Download fehlgeschlagen ({e})")
    if not find_tool("mpv"):
        for pkg in ("shinchiro.mpv", "mpv"):
            say(f"Installiere mpv über winget ({pkg}) …")
            try:
                run_hidden(["winget", "install", "-e", "--id" if "." in pkg else "--name", pkg,
                            "--accept-source-agreements", "--accept-package-agreements"], 900)
            except Exception:
                pass
            if find_tool("mpv"):
                break
        msgs.append("mpv installiert" if find_tool("mpv")
                    else f"mpv konnte nicht installiert werden – mpv.exe bitte manuell nach {TOOLS_USER} kopieren")
    return " · ".join(msgs)


# ----------------------------------------------------------------------------- Updates (GitHub-Releases)
def parse_version(v):
    nums = [int(x) for x in re.findall(r"\d+", str(v))][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def check_update(repo):
    """Fragt das neueste GitHub-Release ab. -> Info-Dict oder None, wenn nichts Neueres da ist."""
    data = json.loads(http_get(f"https://api.github.com/repos/{repo}/releases/latest", 15))
    tag = str(data.get("tag_name", ""))
    if parse_version(tag) <= parse_version(APP_VERSION):
        return None
    for a in data.get("assets", []):
        url = a.get("browser_download_url", "")
        if a.get("name", "").lower().endswith("setup.exe") and url.startswith("https://github.com/"):
            return {"version": tag.lstrip("vV"), "url": url, "digest": a.get("digest") or "",
                    "page": data.get("html_url", "")}
    return None


def _sha256_ok(path, digest):
    if not digest.lower().startswith("sha256:"):
        return True  # GitHub liefert nicht für jedes Asset eine Prüfsumme
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().lower() == digest[7:].lower()


def download_update(info, progress):
    """Lädt den Installer nach %APPDATA%\\Wallura\\update. -> Pfad"""
    dest = UPDATE_DIR / f"Wallura-Setup-{info['version']}.exe"
    if dest.exists() and _sha256_ok(dest, info.get("digest", "")):
        return dest
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(urllib.request.Request(info["url"], headers=UA), timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(done * 100 / total)
    if tmp.stat().st_size < 1_000_000 or not _sha256_ok(tmp, info.get("digest", "")):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Download beschädigt (Prüfsumme stimmt nicht)")
    tmp.replace(dest)
    return dest


def cleanup_old_updates():
    """Löscht alte / halbfertige Installer aus dem Update-Ordner."""
    for p in UPDATE_DIR.glob("*"):
        if p.is_dir():  # unlink() würde hier scheitern und das Aufräumen komplett abbrechen
            continue
        try:
            m = re.search(r"Setup-([\d.]+)\.exe$", p.name)
            if p.suffix == ".part" or (m and parse_version(m.group(1)) <= parse_version(APP_VERSION)):
                p.unlink(missing_ok=True)
        except OSError:
            pass


# ----------------------------------------------------------------------------- Windows-Desktop-Magie
def get_monitors():
    mons = []
    for hm, _hdc, _rect in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(hm)
        l, t, r, b = info["Monitor"]
        mons.append({"rect": (l, t, r - l, b - t), "primary": bool(info["Flags"] & 1)})
    mons.sort(key=lambda m: (not m["primary"], m["rect"][0], m["rect"][1]))
    return mons


def get_wallpaper_parent():
    """Liefert (hwnd, progman_modus). Klassisch: WorkerW hinter den Icons.
    Windows 11 24H2: WorkerW liegt als Kind in Progman -> dann direkt in Progman einbetten."""
    progman = win32gui.FindWindow("Progman", None)
    for wparam, lparam in ((0, 0), (0xD, 0), (0xD, 1)):
        try:
            win32gui.SendMessageTimeout(progman, 0x052C, wparam, lparam, win32con.SMTO_NORMAL, 1000)
        except Exception:
            pass
    found = {"w": 0}

    def cb(hwnd, _):
        if win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None):
            w = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)
            if w:
                found["w"] = w
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    if found["w"]:
        return found["w"], False
    return progman, True


def embed(hwnd, rect):
    """Hängt das mpv-Fenster hinter die Desktop-Icons und positioniert es auf dem Monitor."""
    parent, progman_mode = get_wallpaper_parent()
    if not parent:  # Explorer startet gerade neu / Desktop noch nicht bereit
        raise RuntimeError("Desktop (Progman) nicht gefunden")
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~(win32con.WS_POPUP | win32con.WS_CAPTION | win32con.WS_THICKFRAME | win32con.WS_SYSMENU
               | win32con.WS_MINIMIZEBOX | win32con.WS_MAXIMIZEBOX | win32con.WS_BORDER | win32con.WS_DLGFRAME)
    style |= win32con.WS_CHILD | win32con.WS_VISIBLE
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    ex = (ex | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE) & ~(
        win32con.WS_EX_APPWINDOW | win32con.WS_EX_WINDOWEDGE | win32con.WS_EX_CLIENTEDGE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
    win32gui.SetParent(hwnd, parent)
    place(hwnd, rect, parent, progman_mode)
    if win32gui.GetParent(hwnd) != parent:
        raise RuntimeError("SetParent hat nicht gegriffen")
    return parent


def wait_for_shell(timeout=120):
    """Wartet, bis Explorer / Desktop bereit sind (wichtig beim Autostart direkt nach dem Windows-Start)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            progman = win32gui.FindWindow("Progman", None)
            if progman and win32gui.FindWindow("Shell_TrayWnd", None):
                if win32gui.FindWindowEx(progman, 0, "SHELLDLL_DefView", None):
                    return True
                found = []

                def cb(h, _):
                    if win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None):
                        found.append(h)
                    return True

                win32gui.EnumWindows(cb, None)
                if found:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def place(hwnd, rect, parent=None, progman_mode=None):
    if parent is None:
        parent = win32gui.GetParent(hwnd)
        progman_mode = win32gui.GetClassName(parent) == "Progman"
    x, y, w, h = rect
    cx, cy = win32gui.ScreenToClient(parent, (x, y))
    insert_after = win32con.HWND_TOP
    if progman_mode:  # direkt unter die Icon-Ebene (SHELLDLL_DefView), über das Standard-Hintergrundbild
        dv = win32gui.FindWindowEx(parent, 0, "SHELLDLL_DefView", None)
        if dv:
            insert_after = dv
    win32gui.SetWindowPos(hwnd, insert_after, cx, cy, w, h,
                          win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED)


_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "mpv",
                 "XamlExplorerHostIslandWindow", "Windows.UI.Core.CoreWindow"}


def fullscreen_app_active():
    """True, wenn gerade eine Vollbild-App (Spiel, F11-Video ...) im Vordergrund ist."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return False
        if win32gui.GetClassName(hwnd) in _SKIP_CLASSES:
            return False
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        ml, mt, mr, mb = win32api.GetMonitorInfo(
            win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))["Monitor"]
        return l <= ml and t <= mt and r >= mr and b >= mb
    except Exception:
        return False


class _POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("Reserved1", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def on_battery():
    """True, wenn der PC gerade nicht am Strom hängt (z. B. Laptop im Akkubetrieb)."""
    try:
        status = _POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return False
        return status.ACLineStatus == 0
    except Exception:
        return False


def session_locked():
    """True, wenn Windows gesperrt ist (Anmeldebildschirm) – dann muss nichts gerendert werden."""
    try:
        handle = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not handle:
            return True  # gesperrt oder sicherer Desktop (z. B. UAC)
        ctypes.windll.user32.CloseDesktop(handle)
        return False
    except Exception:
        return False


def covered_monitor_rects():
    """Monitore, die gerade von einem maximierten Fenster im Vordergrund verdeckt werden."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if (not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd)
                or win32gui.GetClassName(hwnd) in _SKIP_CLASSES or not win32gui.IsZoomed(hwnd)):
            return set()
        l, t, r, b = win32api.GetMonitorInfo(
            win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))["Monitor"]
        return {(l, t, r - l, b - t)}
    except Exception:
        return set()


# Begrenzt die Bildrate nur bei Videos, die schneller sind als das Limit (kein Ruckeln bei 24/30 fps)
FPS_LUA = """local limit = tonumber(mp.get_opt("wallura-fps")) or 0
local hflip = mp.get_opt("wallura-hflip") == "yes"
local capped = false
local function apply(cap)
    local parts = {}
    if cap and limit > 0 then parts[#parts + 1] = "fps=" .. limit end
    if hflip then parts[#parts + 1] = "hflip" end
    local chain = table.concat(parts, ",")
    if chain == "" then
        mp.commandv("vf", "clr", "")
    else
        mp.commandv("vf", "set", chain)
    end
end
if hflip then apply(false) end
    mp.observe_property("container-fps", "number", function(_, fps)
    if limit <= 0 or not fps then return end
    local want = fps > limit + 1
    if want ~= capped then
        capped = want
        apply(capped)
    end
end)
"""


def fps_script():
    path = DATA_DIR / "fps_limit.lua"
    try:
        if not path.exists() or path.read_text(encoding="utf-8") != FPS_LUA:
            path.write_text(FPS_LUA, encoding="utf-8")
    except OSError:
        return None
    return str(path).replace("\\", "/")


# ----------------------------------------------------------------------------- Eigener Desktop (Premium)
def desk_font_dirs():
    """Ordner mit den Windows-Schriften (System und pro Benutzer installierte)."""
    dirs = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs.append(Path(windir) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return dirs


def desk_font(size, bold=True, family=None):
    """Schriftdatei für Vorschau und Export: gewählte Schrift, danach sinnvolle Ersatzschriften.

    Die Dateien werden auch direkt im Windows-Schriftordner gesucht – sonst findet Pillow
    sie auf manchen PCs nicht und die Uhr würde in einer winzigen Ersatzschrift erscheinen.
    """
    regular, bold_file, _ = DESK_FONTS.get(family, DESK_FONTS[DEFAULTS["desk"]["font"]])
    names = []
    for name in (bold_file if bold else regular, regular,
                 "arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf",
                 "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if name not in names:
            names.append(name)
    for name in names:
        paths = [name]
        if not os.path.isabs(name):
            paths += [str(d / name) for d in desk_font_dirs() if (d / name).exists()]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    if hasattr(ImageFont, "load_default"):
        try:  # Pillow >= 10.1: Ersatzschrift in der richtigen Größe statt mini
            return ImageFont.load_default(size)
        except TypeError:
            pass
    return ImageFont.load_default()


def desk_utc_offset():
    """Zeitzone des PCs in Sekunden – damit die Live-Uhr nie in UTC läuft."""
    try:
        return int(time.localtime().tm_gmtoff)
    except (AttributeError, OSError, ValueError):
        try:
            local = time.localtime()
            return -int(time.altzone if local.tm_isdst > 0 else time.timezone)
        except Exception:
            return 0


def desk_fallback_background():
    """Falls die mitgelieferten Motive fehlen: ruhiger Verlauf als Ersatz."""
    path = DATA_DIR / "desk_fallback.jpg"
    if not path.exists():
        w, h = 1920, 1080
        img = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(img)
        top, bottom = (16, 24, 44), (5, 7, 12)
        for y in range(h):
            k = y / (h - 1)
            d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
        img.save(path, quality=88)
    return str(path)


def desk_background_path(desk):
    """Bild/Video des eigenen Desktops (eigene Datei/Link vor mitgeliefertem Thema)."""
    desk = desk if isinstance(desk, dict) else {}
    bg = desk.get("bg")
    if isinstance(bg, str) and bg:
        if re.match(r"https?://", bg, re.I) or Path(bg).exists():
            return bg
    asset = ASSET_DIR / "desktop" / DESK_THEMES.get(desk.get("theme"), "anime.jpg")
    return str(asset) if asset.exists() else desk_fallback_background()


def desk_still_path(desk):
    """Vorschaubild für den Hintergrund: Bilder direkt, aus Videos/Links einen Frame ziehen."""
    src = desk_background_path(desk)
    if str(src).lower().endswith(IMAGE_EXT):
        return src
    cache, meta = DATA_DIR / "desk_still.jpg", DATA_DIR / "desk_still.txt"
    try:
        stamp = f"{src}|{Path(src).stat().st_mtime:.0f}"
    except OSError:
        stamp = f"{src}|0"
    try:
        if cache.exists() and meta.read_text(encoding="utf-8") == stamp:
            return str(cache)
    except OSError:
        pass
    mpv = find_tool("mpv")
    if not mpv:
        return None
    tmp = DATA_DIR / "desk_still_tmp"
    tmp.mkdir(exist_ok=True)
    try:
        run_hidden([mpv, "--no-config", "--no-audio", "--hwdec=no", "--vo=image", "--vo-image-format=jpg",
                    f"--vo-image-outdir={tmp}", "--start=10%", "--frames=1", "--no-terminal", str(src)], 45)
        files = sorted(tmp.glob("*.jpg"))
        if files:
            shutil.move(str(files[0]), cache)
            meta.write_text(stamp, encoding="utf-8")
            return str(cache)
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def desk_text_lines(desk, when=None):
    """-> [(Text, Schriftgröße für 1080p, fett)] – Uhr, Datum und eigener Text."""
    t = time.localtime() if when is None else when
    size = int(desk.get("size", 72) or 72)
    out = []
    if desk.get("clock", True):
        out.append((time.strftime("%H:%M", t), size, True))
    sub = max(13, int(size * 0.36))
    if desk.get("date", True):
        out.append((f"{DESK_WEEK[t.tm_wday]}, {t.tm_mday}. {DESK_MONTH[t.tm_mon - 1]}", sub, False))
    text = " ".join(str(desk.get("text") or "").split())[:80]
    if text:
        out.append((text, sub, False))
    return out


def render_desk_image(desk, size=(1920, 1080), when=None, still=None):
    """Zeichnet Hintergrund + Overlay als Bild (Vorschau und Export)."""
    W, H = size
    source = still if still is not None else (desk_still_path(desk) or "")
    try:
        img = Image.open(source).convert("RGB")
    except Exception:
        img = Image.new("RGB", (W, H), (10, 12, 18))
    img = ImageOps.fit(img, (W, H)).convert("RGBA")
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    start = int(H * 0.42)  # unten abdunkeln, damit die Schrift immer lesbar bleibt
    for y in range(start, H):
        alpha = int(125 * ((y - start) / max(1, H - start)) ** 1.5)
        sd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, scrim)
    lines = desk_text_lines(desk, when)
    if not lines:
        return img.convert("RGB")
    d = ImageDraw.Draw(img)
    pos = desk.get("pos", "Unten links")
    top = str(pos).startswith("Oben")
    align = "r" if str(pos).endswith("rechts") else ("l" if str(pos).endswith("links") else "m")
    m = max(24, int(min(W, H) * 0.06))
    heights = [int(s * H / 1080 * 1.3) for _, s, _ in lines]
    y = m if top else H - m - sum(heights)
    x = m if align == "l" else (W - m if align == "r" else W // 2)
    color = DESK_COLOR_RGB.get(desk.get("color"), (255, 255, 255))
    for (text, fsize, bold), hh in zip(lines, heights):
        font = desk_font(max(10, int(fsize * H / 1080)), bold, desk.get("font"))
        d.text((x, y), text, font=font, fill=color + (255,), anchor=align + "t")
        y += hh
    return img.convert("RGB")


DESK_LUA_BODY = r'''
-- osd-overlay erwartet eine Ganzzahl 0-63 als id, keine Zeichenkette
local OVL = 27
local function esc(s)
    return (s:gsub("\\", ""):gsub("{", "("):gsub("}", ")"))
end
local WEEK = {"Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"}
local MONTH = {"Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"}
-- Datum und Uhrzeit aus der Epoche berechnen: os.date liefert je nach mpv-Build
-- UTC oder Ortszeit. So gilt immer die Zeitzone des PCs (CFG.offset, in Sekunden).
local function civil(days)
    local z = days + 719468
    local era = math.floor(z / 146097)
    local doe = z - era * 146097
    local yoe = math.floor((doe - math.floor(doe / 1460) + math.floor(doe / 36524)
                            - math.floor(doe / 146096)) / 365)
    local y = yoe + era * 400
    local doy = doe - (365 * yoe + math.floor(yoe / 4) - math.floor(yoe / 100))
    local mp = math.floor((5 * doy + 2) / 153)
    local d = doy - math.floor((153 * mp + 2) / 5) + 1
    local m = mp + ((mp < 10) and 3 or -9)
    if m <= 2 then y = y + 1 end
    return y, m, d
end

local function local_parts()
    local ok, t = pcall(function()
        local secs = os.time() + (CFG.offset or 0)
        local days = math.floor(secs / 86400)
        local sod = secs - days * 86400
        local _, month, day = civil(days)
        return {hour = math.floor(sod / 3600), min = math.floor((sod % 3600) / 60),
                day = day, month = month, wday = ((days + 4) % 7) + 1, isdst = false}
    end)
    if ok and t then return t end
    return os.date("*t")
end

local function draw()
    local t = local_parts()
    local scale = CFG.h / 1080
    local lines = {}
    if CFG.clock then
        lines[#lines + 1] = {string.format("%02d:%02d", t.hour, t.min), CFG.size, true}
    end
    local sub = math.max(13, math.floor(CFG.size * 0.36))
    if CFG.date then
        lines[#lines + 1] = {string.format("%s, %d. %s", WEEK[t.wday] or "", t.day, MONTH[t.month] or ""),
                             sub, false}
    end
    if CFG.text ~= "" then
        lines[#lines + 1] = {esc(CFG.text), sub, false}
    end
    if #lines == 0 then
        mp.command_native({name = "osd-overlay", id = OVL, format = "none"})
        return
    end
    local hs, total = {}, 0
    for i = 1, #lines do
        hs[i] = math.floor(lines[i][2] * scale * 1.3)
        total = total + hs[i]
    end
    local m = math.max(24, math.floor(math.min(CFG.w, CFG.h) * 0.06))
    local top = (CFG.pos == "tl" or CFG.pos == "tr")
    local x = m
    if CFG.pos == "br" or CFG.pos == "tr" then x = CFG.w - m end
    if CFG.pos == "bc" then x = math.floor(CFG.w / 2) end
    local events = {}
    for i = 1, #lines do
        local an
        if top then
            an = (CFG.pos == "tl" and 7) or (CFG.pos == "tr" and 9) or 8
        else
            an = (CFG.pos == "bl" and 1) or (CFG.pos == "br" and 3) or 2
        end
        local y
        if top then
            y = m
            for k = 1, i - 1 do y = y + hs[k] end
        else
            y = CFG.h - m
            for k = #lines, i + 1, -1 do y = y - hs[k] end
        end
        -- ass-events erwartet nur den ASS-Text (eine Zeile = ein Event),
        -- KEIN "Dialogue: ..."-Präfix - das würde als Text angezeigt.
        -- Sauberer Text: kein schwarzer Rand, kein Schatten, dafür die gewählte Schrift.
        events[#events + 1] = string.format(
            "{\\an%d\\pos(%d,%d)\\fs%d\\c&H%s&\\bord0\\shad0\\b%d\\fn%s}%s",
            an, x, y, math.floor(lines[i][2] * scale), CFG.color, lines[i][3] and 1 or 0,
            CFG.font, lines[i][1])
    end
    mp.command_native({name = "osd-overlay", id = OVL, format = "ass-events",
                       data = table.concat(events, "\n"), res_x = CFG.w, res_y = CFG.h})
end
local function safe_draw()
    local ok, err = pcall(draw)
    if not ok then mp.msg.error("Wallura-Uhr: " .. tostring(err)) end
end
safe_draw()
mp.add_periodic_timer(1.0, safe_draw)
mp.register_event("file-loaded", safe_draw)
'''


def desk_lua_string(value):
    """Python-Text als gültiges Lua-String-Literal (JSON ist kein Lua!)."""
    out = []
    for ch in str(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32:
            out.append(" ")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def desk_lua_source(desk, w, h):
    cfg = {
        "clock": bool(desk.get("clock", True)),
        "date": bool(desk.get("date", True)),
        "text": " ".join(str(desk.get("text") or "").split())[:80],
        "pos": DESK_POS.get(desk.get("pos"), "bl"),
        "color": DESK_COLORS.get(desk.get("color"), "FFFFFF"),
        "font": DESK_FONTS.get(desk.get("font"), DESK_FONTS[DEFAULTS["desk"]["font"]])[2],
        "offset": desk_utc_offset(),
        "size": int(desk.get("size", 72) or 72),
        "w": int(w),
        "h": int(h),
    }
    header = "local CFG = {" + ", ".join(
        f"{key} = {desk_lua_string(val) if isinstance(val, str) else ('true' if val is True else 'false' if val is False else int(val))}"
        for key, val in cfg.items()) + "}"
    return header + "\n" + DESK_LUA_BODY


def desk_script(desk, w, h):
    """Schreibt das Overlay-Skript für genau diese Monitor-Auflösung (mpv liest es beim Start)."""
    try:
        path = DATA_DIR / f"desk_{int(w)}x{int(h)}.lua"
        source = desk_lua_source(desk, w, h)
        if not path.exists() or path.read_text(encoding="utf-8") != source:
            path.write_text(source, encoding="utf-8")
        return str(path).replace("\\", "/")
    except OSError:
        return None


# ----------------------------------------------------------------------------- Player
class Player:
    def __init__(self, cfg, on_error):
        self.cfg = cfg
        self.on_error = on_error
        self.instances = {}  # Monitor-Index -> Instanz (jeder Monitor hat seinen eigenen mpv-Prozess)
        self.paused_manual = False
        self._paused = False
        self._restarts = {}
        self._tick = 0
        self.lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._quit = threading.Event()
        self.job = self._make_job()
        threading.Thread(target=self._watchdog, daemon=True).start()

    @property
    def active(self):
        return bool(self.instances)

    # -- mpv-Prozesse sterben automatisch mit Wallura (auch bei Task-Manager-Kill)
    @staticmethod
    def _make_job():
        try:
            job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
            return job
        except Exception:
            return None

    def _desk_args(self, rect):
        script = desk_script(self.cfg.get("desk") or {}, rect[2], rect[3])
        if not script:
            return []
        # level 1: eigene osd-overlays werden gezeichnet, mpv blendet aber
        # keine eigene Uhrzeit/Statuszeile oben links ein (das macht level 2).
        return [f"--script={script}", "--osd-level=1"]

    def _add_to_job(self, proc):
        if self.job:
            try:
                win32job.AssignProcessToJobObject(self.job, int(proc._handle))
            except Exception:
                pass

    def _base_cmd(self, mpv, ytdlp):
        q = self.cfg.get("quality", "1080")
        vol = int(self.cfg.get("volume", 0))
        audio = vol > 0
        fit = self.cfg.get("fit", "cover")
        base = [mpv, "--no-config", "--force-window=immediate", "--no-border", "--no-osc", "--osd-level=0",
                "--no-input-default-bindings", "--window-dragging=no", "--input-cursor=no", "--loop-file=inf", "--keep-open=yes",
                "--image-display-duration=inf", "--stop-screensaver=no", "--hwdec=auto-safe",
                "--audio-display=no", "--scale=bilinear", "--cscale=bilinear", "--dscale=bilinear", "--dither=no",
                "--correct-downscaling=no", "--interpolation=no", "--deband=no",
                "--framedrop=vo", "--sub-auto=no", "--sid=no", "--demuxer-max-bytes=32MiB",
                "--demuxer-max-back-bytes=8MiB", f"--volume={vol}", f"--mute={'no' if audio else 'yes'}",
                "--ytdl=yes",
                "--ytdl-format=" + (f"bv*[height<=?{q}]+ba/b[height<=?{q}]/b" if audio
                                    else f"bv*[height<=?{q}]/b[height<=?{q}]/b"),
                "--ytdl-raw-options=no-playlist=", "--no-terminal", "--msg-level=all=warn"]
        if audio:
            base.append("--video-sync=audio")
        else:  # stumm: keine Audiospur laden, kein Audio-Takt -> weniger CPU, ruhigeres Bild
            base += ["--aid=no", "--ao=null", "--video-sync=desync"]
        if ytdlp:
            base.append("--script-opts=ytdl_hook-ytdl_path=" + ytdlp.replace("\\", "/"))
        fps_limit = int(self.cfg.get("fps_limit", 30) or 0)
        flip = bool(self.cfg.get("flip"))
        script = fps_script() if (fps_limit or flip) else None
        if script:
            base += [f"--script={script}", f"--script-opts-append=wallura-fps={fps_limit}",
                     f"--script-opts-append=wallura-hflip={'yes' if flip else 'no'}"]
        speed = float(self.cfg.get("speed", 1.0) or 1.0)
        if speed != 1.0:
            base.append(f"--speed={speed}")
        if self.cfg.get("rotate180"):
            base.append("--video-rotate=180")
        if self.cfg.get("grayscale"):
            base.append("--saturation=-100")
        dim = int(self.cfg.get("brightness", 100) or 100)
        if 0 < dim < 100:
            base.append(f"--brightness={dim - 100}")
        if fit == "cover":
            base.append("--panscan=1.0")
        elif fit == "stretch":
            base.append("--keepaspect=no")
        if self.paused_manual or self._paused:
            base.append("--pause")
        return base

    def _ipc(self, inst, command):
        try:
            with open(inst["pipe"], "wb", buffering=0) as f:
                f.write((json.dumps({"command": command}) + "\n").encode("utf-8"))
        except OSError:
            pass

    @staticmethod
    def _find_window(proc, deadline):
        while time.time() < deadline:
            if proc.poll() is not None:
                return None
            found = []

            def cb(h, _):
                try:
                    if (win32process.GetWindowThreadProcessId(h)[1] == proc.pid
                            and win32gui.GetClassName(h) == "mpv" and win32gui.IsWindowVisible(h)):
                        found.append(h)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(cb, None)
            if found:
                return found[0]
            time.sleep(0.15)
        return None

    # -- öffentliche API
    def apply(self, assign, force=False):
        """assign: {Monitor-Index: item}. Startet / wechselt / beendet nur die Monitore, die sich ändern.
        force=True startet alle neu, force={0, 2} nur diese Monitore. -> True, wenn alles geklappt hat."""
        with self._start_lock:
            return self._apply(assign, force)

    def _apply(self, assign, force=False):
        mons = get_monitors()
        desired = {i: it for i, it in assign.items() if 0 <= i < len(mons)}
        ok = True
        cleared = False
        for idx in list(self.instances):
            inst = self.instances[idx]
            forced = force is True or (isinstance(force, (set, frozenset)) and idx in force)
            if idx in desired and desired[idx]["id"] == inst["item"]["id"] and not forced \
                    and inst["proc"].poll() is None:
                inst["rect"] = mons[idx]["rect"]
                continue
            with self.lock:
                self.instances.pop(idx, None)
            self._kill(inst)
            if idx not in desired:
                cleared = True
        if cleared:
            refresh_wallpaper()
        todo = {i: it for i, it in desired.items() if i not in self.instances}
        if not todo:
            if not self.instances:
                self._paused = False
            return True

        wait_for_shell(60)
        mpv = find_tool("mpv")
        if not mpv:
            self.on_error("mpv fehlt – bitte unter Einstellungen auf „Tools installieren“ klicken.")
            return False
        ytdlp = find_tool("yt-dlp")
        if not self.instances:
            self._paused = self.paused_manual
        base = self._base_cmd(mpv, ytdlp)

        new = {}
        for idx, item in todo.items():
            src, kind = item["src"], item["kind"]
            if item.get("id") == DESK_ID:  # Motiv immer frisch aus den Desktop-Einstellungen
                src = desk_background_path(self.cfg.get("desk") or {})
                kind = detect_kind(src)
            if kind == "local" and not Path(src).exists():
                self.on_error(f"Datei nicht gefunden: {src}")
                ok = False
                continue
            if kind == "youtube" and not ytdlp:
                self.on_error("yt-dlp fehlt (für YouTube nötig) – bitte unter Einstellungen auf „Tools installieren“ klicken.")
                ok = False
                continue
            pipe = rf"\\.\pipe\wallura_{os.getpid()}_{idx}"
            log = DATA_DIR / f"mpv_{idx}.log"
            extra = ["--cache=no"] if kind == "local" else []  # lokale Dateien brauchen keinen Puffer
            if item.get("id") == DESK_ID:  # Premium-Desktop: Uhr/Datum/Text als Live-Overlay
                extra += self._desk_args(mons[idx]["rect"])
            cmd = base + extra + [f"--title=Wallura-{os.getpid()}-{idx}", f"--input-ipc-server={pipe}",
                                  f"--log-file={log}", src]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY)
            self._add_to_job(proc)
            new[idx] = {"proc": proc, "pipe": pipe, "rect": mons[idx]["rect"], "hwnd": None, "log": log, "item": item}

        for idx, inst in new.items():
            hwnd = self._find_window(inst["proc"], time.time() + 30)
            if not hwnd:
                tail = ""
                try:
                    tail = " | ".join(inst["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-3:])
                except Exception:
                    pass
                self._kill(inst)
                self.on_error(f"mpv konnte auf Monitor {idx + 1} nicht starten. " + tail)
                ok = False
                continue
            inst["hwnd"] = hwnd
            err = None
            for _attempt in range(6):
                try:
                    inst["parent"] = embed(hwnd, inst["rect"])
                    err = None
                    break
                except Exception as e:
                    err = e
                    time.sleep(1.0)
            if err is not None:
                self._kill(inst)
                self.on_error(f"Einbetten in den Desktop fehlgeschlagen: {err}")
                ok = False
                continue
            with self.lock:
                self.instances[idx] = inst
        return ok

    def _restart_one(self, idx):
        with self._start_lock:
            if self._quit.is_set() or idx not in self.instances:
                return
            assign = {i: inst["item"] for i, inst in self.instances.items()}
            self._apply(assign, force={idx})

    def _drop(self, idx):
        with self._start_lock:
            inst = self.instances.pop(idx, None)
            if inst:
                self._kill(inst)
                refresh_wallpaper()
                self.on_error(f"Wallpaper auf Monitor {idx + 1} ist mehrfach abgestürzt und wurde gestoppt.")

    @staticmethod
    def _kill(inst):
        try:
            inst["proc"].terminate()
            inst["proc"].wait(timeout=3)
        except Exception:
            try:
                inst["proc"].kill()
            except Exception:
                pass

    def stop(self):
        self.apply({})

    def shutdown(self):
        self._quit.set()
        self.stop()

    def set_volume(self, vol):
        for inst in list(self.instances.values()):
            self._ipc(inst, ["set_property", "volume", vol])
            self._ipc(inst, ["set_property", "mute", vol == 0])

    def set_manual_pause(self, paused):
        self.paused_manual = paused
        self._apply_pause(paused)

    def screenshot(self, folder):
        """Speichert das laufende Bild jedes Monitors als PNG (mpv-Screenshot). -> [Pfade]"""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        paths = []
        for idx, inst in list(self.instances.items()):
            path = folder / f"Wallura-{stamp}-Monitor{idx + 1}.png"
            self._ipc(inst, ["screenshot-to-file", str(path), "window"])
            paths.append(path)
        return paths

    def _apply_pause(self, paused):
        self._paused = paused
        for inst in list(self.instances.values()):
            inst["cover_paused"] = False
            self._ipc(inst, ["set_property", "pause", paused])

    # -- Überwachung: Auto-Pause, Neustart nach Crash, Position halten
    def _watchdog(self):
        while not self._quit.wait(1.0):
            insts = dict(self.instances)
            if not insts:
                continue
            for gone in [i for i in list(self._restarts) if i not in insts]:
                self._restarts.pop(gone, None)  # alte Neustart-Zähler beendeter Monitore vergessen
            self._tick += 1
            now = time.time()
            for idx, inst in insts.items():
                if inst["proc"].poll() is None or inst.get("restarting"):
                    continue
                inst["restarting"] = True  # nur einmal pro Absturz neu starten
                r = [t for t in self._restarts.get(idx, []) if now - t < 120]
                if len(r) < 3:
                    r.append(now)
                    self._restarts[idx] = r
                    threading.Thread(target=self._restart_one, args=(idx,), daemon=True).start()
                else:
                    threading.Thread(target=self._drop, args=(idx,), daemon=True).start()
            alive = [i for i in insts.values() if i["proc"].poll() is None]
            want = (self.paused_manual
                    or (self.cfg.get("pause_fullscreen", True)
                        and (fullscreen_app_active() or session_locked()))
                    or (self.cfg.get("pause_battery", False) and on_battery()))
            if want != self._paused:
                self._apply_pause(want)
            covered = covered_monitor_rects() if (self.cfg.get("pause_fullscreen", True) and not self._paused) else set()
            for inst in alive:
                should = inst["rect"] in covered
                if should != inst.get("cover_paused", False):
                    inst["cover_paused"] = should
                    self._ipc(inst, ["set_property", "pause", should])
            if self._tick % 3 == 0:  # seltener prüfen: jedes SetWindowPos kostet einen Frame
                for inst in alive:
                    try:
                        hwnd = inst["hwnd"]
                        if not win32gui.IsWindow(hwnd):
                            continue
                        parent = inst.get("parent")
                        is_child = bool(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) & win32con.WS_CHILD)
                        if (not parent or not win32gui.IsWindow(parent)
                                or win32gui.GetParent(hwnd) != parent or not is_child):
                            inst["parent"] = embed(hwnd, inst["rect"])  # war nach vorne gerutscht -> zurück hinter die Icons
                            continue
                        l, t, r, b = win32gui.GetWindowRect(hwnd)
                        x, y, w, h = inst["rect"]
                        # ein paar Pixel Toleranz: sonst wird bei DPI-Rundung jedes Mal neu gesetzt (Ruckler)
                        if (abs(l - x) > 2 or abs(t - y) > 2
                                or abs((r - l) - w) > 2 or abs((b - t) - h) > 2):
                            place(hwnd, inst["rect"])
                    except Exception:
                        pass

# ----------------------------------------------------------------------------- Autostart
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}" --minimized'
            else:
                py = Path(sys.executable)
                pyw = py.with_name("pythonw.exe")
                cmd = f'"{pyw if pyw.exists() else py}" "{Path(__file__).resolve()}" --minimized'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def migrate_autostart():
    """Alter Autostart-Eintrag „LiveWall“ -> „Wallura“ (zeigt auf die aktuelle Version)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                winreg.QueryValueEx(k, OLD_APP_NAME)
            except FileNotFoundError:
                return
            winreg.DeleteValue(k, OLD_APP_NAME)
        set_autostart(True)
    except OSError:
        pass


def is_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


# ----------------------------------------------------------------------------- GUI
# ----------------------------------------------------------------------------- Anmeldung
class LoginDialog(ctk.CTkToplevel):
    """Modaler Anmelde-/Einrichtungsdialog im laufenden Fenster.
    .result = {"name", "role", "remember"} oder None (abgebrochen)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self._done = False
        self.acc = load_accounts()
        self.setup_mode = not has_accounts(self.acc)  # noch kein Konto: das erste ist ein normaler Nutzer
        self.title("Wallura – Konto einrichten" if self.setup_mode else "Wallura – Anmelden")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        try:
            self.transient(parent)
        except Exception:
            pass

        box = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=22, border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True, padx=18, pady=18)

        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(20, 4))
        try:
            self._logo = ctk.CTkImage(make_icon(128), size=(38, 38))
            ctk.CTkLabel(head, image=self._logo, text="").pack(side="left", padx=(0, 12))
        except Exception:
            pass
        ctk.CTkLabel(head, text="Wallura", font=ui_font(20, "bold"), text_color=TEXT).pack(side="left")

        ctk.CTkLabel(box, text="Willkommen bei Wallura" if self.setup_mode else "Anmelden",
                     font=ui_font(19, "bold"), text_color=TEXT, anchor="w").pack(fill="x", padx=26, pady=(10, 2))
        ctk.CTkLabel(box, text=(f"Das Konto ist ein normaler Nutzer. Administratorrechte hat nur das "
                               f"Besitzerkonto „{ADMIN_NAME}“ (bzw. wer von ihm zum Administrator gemacht wird)."
                               if self.setup_mode else "Bitte mit Name und Passwort anmelden. Wallpaper und "
                               "Bibliothek bleiben beim Anmelden erhalten."),
                     font=ui_font(11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=340).pack(fill="x", padx=24, pady=(0, 4))

        self.e_name = self._entry(box, "Benutzername", placeholder="z. B. Admin")
        self.e_pw = self._entry(box, "Passwort", show="•")
        self.e_pw2 = self._entry(box, "Passwort wiederholen", show="•") if self.setup_mode else None

        self.err = ctk.CTkLabel(box, text="", font=ui_font(11), text_color=STATUS_ERR, anchor="w",
                                justify="left", wraplength=340)
        self.err.pack(fill="x", padx=24, pady=(8, 0))

        self.remember_var = ctk.BooleanVar(value=True)
        if not self.setup_mode:
            ctk.CTkCheckBox(box, text="Angemeldet bleiben (beim nächsten Start nicht erneut anmelden)",
                            variable=self.remember_var, font=ui_font(11), text_color=MUTED,
                            fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=BORDER,
                            checkbox_width=18, checkbox_height=18).pack(fill="x", padx=24, pady=(10, 0))
        ctk.CTkButton(box, text="Konto erstellen" if self.setup_mode else "Anmelden", height=40,
                      corner_radius=BTN_RADIUS, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color=ON_ACCENT, font=ui_font(13, "bold"),
                      command=self.submit).pack(fill="x", padx=26, pady=(14, 6))
        ctk.CTkButton(box, text="Abbrechen", height=34, corner_radius=BTN_RADIUS, fg_color="transparent",
                      hover_color=SURFACE2, text_color=MUTED, font=ui_font(12),
                      command=self.cancel).pack(fill="x", padx=26, pady=(0, 20))

        self.bind("<Return>", lambda e: self.submit())
        self.bind("<Escape>", lambda e: self.cancel())
        self._center(parent)
        self.after(120, self._activate)

    def _entry(self, parent, label, show="", placeholder=""):
        ctk.CTkLabel(parent, text=label, font=ui_font(12), text_color=TEXT, anchor="w").pack(
            fill="x", padx=26, pady=(10, 4))
        e = ctk.CTkEntry(parent, height=38, corner_radius=BTN_RADIUS, fg_color=SURFACE2,
                         border_color=BORDER, border_width=1, text_color=TEXT, show=show,
                         placeholder_text=placeholder, placeholder_text_color=MUTED, font=ui_font(13))
        e.pack(fill="x", padx=26)
        return e

    def submit(self):
        if self._done:
            return
        name, pw = self.e_name.get().strip(), self.e_pw.get()
        if not name or not pw:
            self.err.configure(text="Bitte Name und Passwort eingeben.")
            return
        if self.setup_mode:
            if pw != self.e_pw2.get():
                self.err.configure(text="Die Passwörter sind nicht gleich.")
                return
            role = "admin" if name.lower() == ADMIN_NAME.lower() else "user"
            ok, err = create_account(self.acc, name, pw, role)
            if not ok:
                self.err.configure(text=err)
                return
            user = find_account(self.acc, name)
            self._finish({"name": user.get("name", name), "role": user.get("role", role),
                          "premium": bool(user.get("premium")), "remember": True})
        else:
            user = authenticate(self.acc, name, pw)
            if not user:
                self.err.configure(text="Name oder Passwort ist falsch.")
                return
            # Passwort-Hash bewusst nicht in die Sitzung übernehmen
            self._finish({"name": user.get("name", name), "role": user.get("role", "user"),
                          "premium": bool(user.get("premium")),
                          "remember": bool(self.remember_var.get())})

    def _finish(self, session):
        self._done = True
        self.result = session
        report_account_async(session.get("name", ""))
        self._release()
        self.destroy()

    def cancel(self):
        if self._done:
            return
        self._done = True
        self.result = None
        self._release()
        self.destroy()

    def _release(self):
        try:
            self.grab_release()
        except Exception:
            pass

    def _activate(self):
        try:
            self.grab_set()
        except Exception:
            pass
        try:
            self.e_name.focus_set()
        except Exception:
            pass

    def _center(self, parent):
        self.update_idletasks()
        w, h = max(420, self.winfo_reqwidth()), self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 3)}")


class PasswordDialog(tk.Toplevel):
    """Modaler Passwort-Dialog auf Basis von reinem Tk.

    Bewusst ohne CustomTkinter: Tk berechnet die Fenstergröße selbst aus dem
    Inhalt. Dadurch können weder Felder noch Buttons abgeschnitten werden.
    .result ist None (abgebrochen) oder {key: wert}.
    """

    def __init__(self, parent, title, subtitle, fields, ok_text, validate):
        super().__init__(parent)
        self.result = None
        self._vars, self._entries = {}, []
        self._validate = validate
        self._done = False
        self.title(title)
        self.configure(bg=BG)
        try:
            self.transient(parent)
        except Exception:
            pass

        card = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(card, text=title, bg=SURFACE, fg=TEXT, anchor="w",
                 font=("Segoe UI", 14, "bold")).pack(fill="x", padx=18, pady=(16, 2))
        if subtitle:
            tk.Label(card, text=subtitle, bg=SURFACE, fg=MUTED, anchor="w", justify="left",
                     wraplength=420, font=("Segoe UI", 9)).pack(fill="x", padx=18, pady=(0, 4))

        self._first = None
        for field in fields:
            tk.Label(card, text=field["label"], bg=SURFACE, fg=TEXT, anchor="w",
                     font=("Segoe UI", 10)).pack(fill="x", padx=18, pady=(10, 2))
            wrap = tk.Frame(card, bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER)
            wrap.pack(fill="x", padx=18)
            var = tk.StringVar()
            entry = tk.Entry(wrap, textvariable=var, show="•", bd=0, relief="flat",
                             bg=SURFACE2, fg=TEXT, insertbackground=TEXT, font=("Segoe UI", 11))
            entry.pack(fill="x", padx=8, pady=6)
            entry.bind("<FocusIn>", lambda e, f=wrap: f.configure(highlightbackground=ACCENT))
            entry.bind("<FocusOut>", lambda e, f=wrap: f.configure(highlightbackground=BORDER))
            self._entries.append(entry)
            if self._first is None:
                self._first = entry
            self._vars[field["key"]] = var

        self._show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="Passwort anzeigen", variable=self._show_var,
                       command=self._toggle_show, bg=SURFACE, fg=MUTED, activebackground=SURFACE,
                       activeforeground=TEXT, selectcolor=SURFACE2, highlightthickness=0, bd=0,
                       anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=15, pady=(8, 0))

        self._err = tk.Label(card, text="", bg=SURFACE, fg=STATUS_ERR, anchor="w", justify="left",
                             wraplength=420, font=("Segoe UI", 9))
        self._err.pack(fill="x", padx=18, pady=(6, 0))

        row = tk.Frame(card, bg=SURFACE)
        row.pack(fill="x", padx=18, pady=(12, 14))
        tk.Button(row, text=ok_text, command=self._ok, bd=0, relief="flat", cursor="hand2",
                  bg=ACCENT, fg=ON_ACCENT, activebackground=ACCENT_HOVER, activeforeground=ON_ACCENT,
                  font=("Segoe UI", 10, "bold"), padx=18, pady=7).pack(side="right")
        tk.Button(row, text="Abbrechen", command=self.cancel, bd=0, relief="flat", cursor="hand2",
                  bg=SURFACE2, fg=MUTED, activebackground=BORDER, activeforeground=TEXT,
                  font=("Segoe UI", 10), padx=14, pady=7).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.cancel())
        try:
            self.protocol("WM_DELETE_WINDOW", self.cancel)
        except Exception:
            pass

        # Größe NICHT setzen: Tk nimmt die angeforderte Größe des Inhalts und
        # wächst mit, wenn z. B. eine Fehlermeldung mehr Zeilen braucht.
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            px, py, pw, ph = (parent.winfo_rootx(), parent.winfo_rooty(),
                              parent.winfo_width(), parent.winfo_height())
        except Exception:
            px, py, pw, ph = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(px + max(0, (pw - w) // 2), self.winfo_screenwidth() - w - 20))
        y = max(0, min(py + max(0, (ph - h) // 3), self.winfo_screenheight() - h - 40))
        self.geometry(f"+{x}+{y}")
        self.after(30, self._activate)

    def _toggle_show(self):
        show = "" if self._show_var.get() else "•"
        for entry in self._entries:
            try:
                entry.configure(show=show)
            except Exception:
                pass

    def _activate(self):
        try:
            self.grab_set()
        except Exception:
            pass
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        if self._first is not None:
            self._first.focus_set()

    def _ok(self):
        if self._done:
            return
        values = {k: v.get() for k, v in self._vars.items()}
        err = self._validate(values) if self._validate else None
        if err:
            self._err.configure(text=err)
            if self._first is not None:
                self._first.focus_set()
            return
        self._done = True
        self.result = values
        self.cancel()

    def cancel(self):
        self._done = True
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class FormDialog(ctk.CTkToplevel):
    """Modaler Dialog mit Eingabefeldern. .result ist None (abgebrochen) oder {key: wert}."""

    def __init__(self, parent, title, fields, subtitle=None, ok_text="Speichern"):
        super().__init__(parent)
        self.result = None
        self._vars = {}
        self.title(title)
        self.configure(fg_color=BG)
        self.resizable(False, False)
        try:
            self.transient(parent)
        except Exception:
            pass

        box = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(box, text=title, font=ui_font(18, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=20, pady=(18, 2))
        if subtitle:
            ctk.CTkLabel(box, text=subtitle, font=ui_font(11), text_color=MUTED, anchor="w", justify="left",
                         wraplength=340).pack(fill="x", padx=20, pady=(0, 2))

        self._first = None
        for field in fields:
            ctk.CTkLabel(box, text=field["label"], font=ui_font(12), text_color=TEXT,
                         anchor="w").pack(fill="x", padx=20, pady=(10, 3))
            if field.get("type") == "menu":
                var = ctk.StringVar(value=field.get("value") or field["values"][0])
                ctk.CTkOptionMenu(box, values=field["values"], variable=var,
                                  **MENU_STYLE).pack(fill="x", padx=20)
            else:
                var = ctk.StringVar(value=field.get("value") or "")
                entry = ctk.CTkEntry(box, textvariable=var, show="•" if field.get("type") == "pw" else "",
                                     height=34, corner_radius=10, fg_color=SURFACE2, border_color=BORDER,
                                     text_color=TEXT, font=ui_font(13))
                entry.pack(fill="x", padx=20)
                if self._first is None:
                    self._first = entry
            self._vars[field["key"]] = var

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(fill="x", padx=22, pady=(20, 20))
        ctk.CTkButton(btns, text=ok_text, height=38, corner_radius=BTN_RADIUS, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, text_color=ON_ACCENT, font=ui_font(13, "bold"),
                      command=self._ok).pack(side="right", width=150)
        ctk.CTkButton(btns, text="Abbrechen", height=38, corner_radius=BTN_RADIUS, fg_color="transparent",
                      hover_color=SURFACE2, text_color=MUTED, border_width=1, border_color=BORDER,
                      font=ui_font(13), command=self.cancel).pack(side="right", padx=(0, 10), width=110)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.cancel())
        self._center(parent)
        self.after(120, self._activate)

    def _activate(self):
        try:
            self.grab_set()
        except Exception:
            pass
        if self._first is not None:
            self._first.focus_set()

    def _center(self, parent):
        self.update_idletasks()
        w, h = max(400, self.winfo_reqwidth()), self.winfo_reqheight()
        try:
            px, py, pw, ph = parent.winfo_rootx(), parent.winfo_rooty(), parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 3)}")

    def _ok(self):
        self.result = {k: v.get() for k, v in self._vars.items()}
        self.cancel()

    def cancel(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class LibraryPickerDialog(ctk.CTkToplevel):
    """Wallpaper aus der eigenen Bibliothek als Desktop-Hintergrund wählen."""

    def __init__(self, parent, items):
        super().__init__(parent)
        self.result = None
        self._thumbs = []
        self.title("Wallpaper aus der Bibliothek")
        self.configure(fg_color=BG)
        self.resizable(False, True)
        try:
            self.transient(parent)
        except Exception:
            pass

        ctk.CTkLabel(self, text="Hintergrund aus der Bibliothek", font=ui_font(19, "bold"),
                     text_color=TEXT, anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text="Alles, was du schon hinzugefügt hast – direkt als Desktop-Hintergrund.",
                     font=ui_font(11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=22)

        box = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=BORDER,
                                     scrollbar_button_hover_color=MUTED)
        box.pack(fill="both", expand=True, padx=16, pady=(10, 4))
        for it in items:
            row = ctk.CTkFrame(box, fg_color=SURFACE2, corner_radius=12, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=3)
            thumb = None
            try:
                p = THUMB_DIR / f"{it['id']}.jpg"
                if p.exists():
                    thumb = ctk.CTkImage(ImageOps.fit(Image.open(p).convert("RGB"), (256, 144)), size=(128, 72))
                    self._thumbs.append(thumb)
            except Exception:
                thumb = None
            if thumb is not None:
                ctk.CTkLabel(row, image=thumb, text="").pack(side="left", padx=(10, 12), pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(info, text=shorten(str(it.get("title") or "?" ), 52), font=ui_font(13, "bold"),
                         text_color=TEXT, anchor="w").pack(fill="x")
            ctk.CTkLabel(info, text=f"{KIND_LABEL.get(it.get('kind'), '?')}  ·  "
                                   f"{shorten(str(it.get('src') or ''), 58)}", font=ui_font(10),
                         text_color=MUTED, anchor="w").pack(fill="x")
            ctk.CTkButton(row, text="Wählen", width=96, height=32, corner_radius=BTN_RADIUS,
                          fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                          font=ui_font(12, "bold"), command=lambda i=it: self._pick(i)).pack(
                side="right", padx=10, pady=8)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=(2, 16))
        ctk.CTkButton(bar, text="Abbrechen", height=38, width=130, corner_radius=BTN_RADIUS,
                      fg_color="transparent", hover_color=SURFACE2, text_color=MUTED, border_width=1,
                      border_color=BORDER, font=ui_font(13), command=self.cancel).pack(side="right")

        self.bind("<Escape>", lambda e: self.cancel())
        self.update_idletasks()
        w = 600
        h = max(420, min(660, self.winfo_reqheight()))
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 3)}")
        self.after(120, self._activate)

    def _activate(self):
        try:
            self.grab_set()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _pick(self, item):
        self.result = item
        self._close()

    def cancel(self):
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class App(ctk.CTk):

    def report_callback_exception(self, exc, val, tb):
        # Ohne Konsole würde ein Fehler in einem Button-Callback sonst
        # spurlos verschwinden und ein halb aufgebautes Fenster zurücklassen.
        log_exception(exc, val, tb)
    def __init__(self, session=None, start_hidden=False):
        super().__init__()
        self.user = session or {"name": GAST, "role": "user"}
        self.guest = session is None  # ohne Anmeldung starten – Anmelden geht jederzeit über den Button
        self._login_open = False
        self.acc = load_accounts()
        if not self.guest:  # dieses Konto in der zentralen Kontenliste aktualisieren
            report_account_async(self.user.get("name", GAST))
        self.tools_desc = None
        self._update_title()
        self.geometry("1280x860")
        self.minsize(1120, 700)
        try:  # eigenes Fenster-Symbol statt des Tk-Feders
            self._win_icon = ImageTk.PhotoImage(make_icon(64))
            self.iconphoto(True, self._win_icon)
        except Exception:
            pass
        self.cfg = load_config()
        self._migrate_config()
        self._q = queue.Queue()
        self._resize_job = None
        self._last_cols = 0
        self._mon_rects = []
        self._mon_img = None
        self._on_map = {}
        self._mon_count = 1
        self.update_info = None
        self.update_file = None
        self.player = Player(self.cfg, on_error=lambda m: self.ui(lambda: self.set_status(m, True)))
        self.tray = None
        self._closing = False
        self._volume_job = None
        self._downloads = set()
        self._update_lock = threading.Lock()
        self._rotate_job = None
        self._night_job = None
        self._night_on = False
        self._night_backup = {}
        self._recent_random = []
        if self.cfg.get("random_start") and self.cfg["items"]:
            pick = random.choice(self.cfg["items"])
            a = dict(self.cfg.get("assign", {}))
            for i in range(len(get_monitors())):
                a[str(i)] = pick["id"]
            self.cfg["assign"] = a
            save_config(self.cfg)

        self._build_ui()
        self.refresh_library()
        self._update_tools_banner()
        try:
            self._setup_tray()
        except Exception:
            self.tray = None  # ohne Tray darf das Schließen das Fenster nicht unerreichbar machen
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.bind("<Configure>", self._on_resize)
        self.after(100, self._poll)
        if start_hidden:
            self.withdraw()
        if self._assign_items():
            threading.Thread(target=self._startup_worker, args=(start_hidden,), daemon=True).start()
        cleanup_old_updates()
        self._schedule_rotate()
        self._night_check()
        self.after(20000, self._auto_check)

    def _startup_worker(self, boot=False):
        if boot:  # Start mit Windows: Explorer braucht einen Moment, bis der Desktop wirklich bereit ist
            wait_for_shell(120)
            time.sleep(3)
        for attempt in range(4 if boot else 1):
            if self.player.apply(self._assign_items()):
                break
            time.sleep(10)
        self.ui(self.refresh_library)

    def _migrate_config(self):
        """Alte Configs (ein Wallpaper für alle) -> Zuordnung pro Monitor."""
        a = self.cfg.get("assign")
        if not isinstance(a, dict):
            a = {}
        cur = self.cfg.get("current")
        sel = str(self.cfg.get("monitor", "all"))
        if not a and cur:
            idxs = [int(sel)] if sel.isdigit() else range(max(1, len(get_monitors())))
            a = {str(i): cur for i in idxs}
        self.cfg["assign"] = a
        self.cfg["current"] = None
        if sel != "all" and not sel.isdigit():
            self.cfg["monitor"] = "all"
        save_config(self.cfg)

    def _assign_items(self, assign=None):
        """{Monitor-Index: item} der gespeicherten Zuordnung (nur gültige Monitore und vorhandene Einträge)."""
        assign = self.cfg.get("assign", {}) if assign is None else assign
        n = len(get_monitors())
        out = {}
        for k, iid in assign.items():
            if iid == DESK_ID and not self.is_premium:
                continue  # Premium-Desktop läuft nur für Premium-/Administratorkonten
            item = self.find_item(iid)
            if item and str(k).isdigit() and int(k) < n:
                out[int(k)] = item
        return out

    def _target_indices(self):
        """Auf welche Monitore wirkt ein Klick in der Bibliothek gerade?"""
        n = len(get_monitors())
        sel = str(self.cfg.get("monitor", "all"))
        if sel.isdigit() and int(sel) < n:
            return [int(sel)]
        return list(range(n))

    # -- Thread-sichere UI-Aufrufe
    def ui(self, fn):
        self._q.put(fn)

    def _poll(self):
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        self.after(100, self._poll)

    # -- Aufbau
    @property
    def is_admin(self):
        return self.user.get("role") == "admin"

    @property
    def is_premium(self):
        """Premium-Features: Administratoren immer, sonst das im Konto gesetzte Premium."""
        return self.is_admin or bool(self.user.get("premium"))

    def _update_title(self):
        self.title(f"Wallura {APP_VERSION}" if self.guest
                   else f"Wallura {APP_VERSION} – {self.user.get('name', GAST)}")

    def _require_admin(self):
        if self.is_admin:
            return True
        self.set_status("Nur Administratoren dürfen das ändern.", True)
        return False

    def _font(self, size=13, weight="normal"):
        return ui_font(size, weight)

    def _btn(self, parent, text, command, kind="secondary", **kw):
        styles = {
            "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT),
            "secondary": dict(fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT,
                              border_width=1, border_color=BORDER),
            "ghost": dict(fg_color="transparent", hover_color=SURFACE2, text_color=MUTED),
            "danger": dict(fg_color="transparent", hover_color="#3a1c1f", text_color=DANGER_TEXT,
                           border_width=1, border_color="#5a2a2e"),
        }[kind]
        opts = dict(height=36, corner_radius=BTN_RADIUS, command=command,
                    font=self._font(13, "bold" if kind == "primary" else "normal"))
        opts.update(styles)
        opts.update(kw)
        return ctk.CTkButton(parent, text=text, **opts)

    def _menu_style(self):
        return dict(MENU_STYLE, font=self._font(13), dropdown_font=self._font(13))

    # -- Bausteine für die Einstellungen
    def _section(self, parent, title, desc=None):
        box = ctk.CTkFrame(parent, corner_radius=CARD_RADIUS, fg_color=SURFACE)
        box.pack(fill="x", pady=(0, 16))
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(20, 4))
        line = ctk.CTkFrame(head, fg_color="transparent")
        line.pack(fill="x")
        ctk.CTkFrame(line, width=3, height=16, corner_radius=2, fg_color=ACCENT).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(line, text=title, font=self._font(15, "bold"), text_color=TEXT,
                     anchor="w").pack(side="left")
        if desc:
            ctk.CTkLabel(head, text=desc, font=self._font(11), text_color=MUTED, anchor="w",
                         justify="left", wraplength=560).pack(anchor="w", padx=(13, 0), pady=(3, 0))
        return box

    def _row(self, parent, title, desc=None):
        """Zeile mit Titel + Beschreibung links; das Steuerelement kommt per grid in Spalte 1."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=8)
        row.grid_columnconfigure(0, weight=1)
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(txt, text=title, font=self._font(13), text_color=TEXT, anchor="w").pack(anchor="w")
        row.desc = None
        if desc:
            row.desc = ctk.CTkLabel(txt, text=desc, font=self._font(11), text_color=MUTED, anchor="w",
                                    justify="left", wraplength=420)
            row.desc.pack(anchor="w")
        return row

    def _switch_row(self, parent, title, desc, command, value):
        row = self._row(parent, title, desc)
        sw = ctk.CTkSwitch(row, text="", width=44, command=command, progress_color=ACCENT,
                           button_color=TEXT, button_hover_color="white", fg_color=BORDER)
        sw.grid(row=0, column=1, sticky="e", padx=(16, 0))
        if value:
            sw.select()
        return sw

    def _nav_btn(self, parent, text, page):
        holder = ctk.CTkFrame(parent, fg_color="transparent", height=42)
        holder.pack(fill="x", padx=12, pady=2)
        bar = ctk.CTkFrame(holder, width=3, height=22, corner_radius=2, fg_color="transparent")
        bar.pack(side="left", padx=(4, 0))
        b = ctk.CTkButton(holder, text=text, anchor="w", height=40, corner_radius=BTN_RADIUS,
                          font=self._font(14, "bold"), fg_color="transparent", hover_color=SURFACE2,
                          text_color=MUTED, command=lambda: self._show_page(page))
        b.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._nav[page] = {"btn": b, "bar": bar}

    def _show_page(self, page):
        if page == "desk":
            self._build_desk_page()  # bei jedem Öffnen neu: Premium kann sich geändert haben
        self._page = page
        for name, frame in self._pages.items():
            if name == page:
                frame.grid()
            else:
                frame.grid_remove()
        for name, parts in self._nav.items():
            on = name == page
            parts["btn"].configure(fg_color=SURFACE2 if on else "transparent",
                                   text_color=TEXT if on else MUTED)
            parts["bar"].configure(fg_color=ACCENT if on else "transparent")

    def _build_ui(self):
        self.configure(fg_color=BG)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._nav, self._pages = {}, {}

        # ================= Seitenleiste: Navigation + Monitor
        side = ctk.CTkFrame(self, width=SIDEBAR_W, corner_radius=0, fg_color=SURFACE)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(side="top", fill="x", padx=18, pady=(22, 18))
        try:
            self._logo = ctk.CTkImage(make_icon(128), size=(40, 40))
            ctk.CTkLabel(head, image=self._logo, text="").pack(side="left", padx=(0, 12))
        except Exception:
            pass
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Wallura", font=self._font(22, "bold"), text_color=TEXT,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text="LIVE-WALLPAPER-ENGINE", font=self._font(9, "bold"), text_color=MUTED,
                     anchor="w").pack(anchor="w", pady=(1, 0))

        ctk.CTkLabel(side, text="MENÜ", font=self._font(9, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=20, pady=(4, 6))
        self._nav_btn(side, "Bibliothek", "library")
        self._nav_btn(side, "Eigener Desktop", "desk")
        self._nav_btn(side, "Einstellungen", "settings")

        # Angemeldetes Konto
        usercard = ctk.CTkFrame(side, corner_radius=CARD_RADIUS, fg_color=SURFACE2)
        usercard.pack(side="top", fill="x", padx=14, pady=(14, 4))
        urow = ctk.CTkFrame(usercard, fg_color="transparent")
        urow.pack(fill="x", padx=12, pady=(12, 0))
        who = (self.user.get("name", GAST) or GAST).strip() if not self.guest else GAST
        ctk.CTkLabel(urow, text=(who[:1].upper() or "G"), width=36, height=36, corner_radius=18,
                     fg_color=ACCENT_DIM if not self.guest else SURFACE3,
                     text_color=ON_ACCENT if not self.guest else MUTED,
                     font=self._font(15, "bold")).pack(side="left", padx=(0, 10))
        uinfo = ctk.CTkFrame(urow, fg_color="transparent")
        uinfo.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(uinfo, text="GASTMODUS" if self.guest else "ANGEMELDET",
                     font=self._font(9, "bold"), text_color=MUTED, anchor="w").pack(fill="x")
        ctk.CTkLabel(uinfo, text=who, font=self._font(14, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x")
        role_text = ("Ohne Konto" if self.guest else ROLES.get(self.user.get("role"), "Nutzer"))
        if not self.guest and self.is_premium and not self.is_admin:
            role_text = "Premium"
        ctk.CTkLabel(uinfo, text=role_text,
                     font=self._font(11), text_color=ACCENT if self.is_premium else MUTED,
                     anchor="w").pack(fill="x")
        self._btn(usercard, "Anmelden" if self.guest else "Abmelden",
                  self.login if self.guest else self.logout,
                  "primary" if self.guest else "ghost", height=30,
                  font=self._font(12)).pack(fill="x", padx=10, pady=(8, 10))

        ctk.CTkLabel(side, text=COPYRIGHT, font=self._font(9), text_color="#5f6878", anchor="center",
                     wraplength=SIDEBAR_W - 24).pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(side, text=f"Version {APP_VERSION}", font=self._font(10), text_color=MUTED,
                     anchor="center").pack(side="bottom", fill="x", padx=12, pady=(0, 2))

        mon = ctk.CTkFrame(side, corner_radius=CARD_RADIUS, fg_color=SURFACE2)
        mon.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(mon, text="MONITORE", font=self._font(9, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=14, pady=(14, 6))
        self.mon_preview = ctk.CTkLabel(mon, text="", cursor="hand2")
        self.mon_preview.pack(padx=10, pady=(0, 6))
        self.mon_preview.bind("<Button-1>", self._on_preview_click)
        self.mon_hint = ctk.CTkLabel(mon, text="", anchor="w", font=self._font(13, "bold"), text_color=TEXT)
        self.mon_hint.pack(fill="x", padx=14)
        ctk.CTkLabel(mon, text="Monitor anklicken, dann ein Wallpaper wählen.", anchor="w", justify="left",
                     wraplength=SIDEBAR_W - 70, font=self._font(11), text_color=MUTED).pack(
            fill="x", padx=14, pady=(0, 8))
        self.btn_all = self._btn(mon, "Alle Monitore gleich", lambda: self.select_monitor("all"),
                                 "secondary", height=30, font=self._font(12))
        self.btn_all.pack(fill="x", padx=14, pady=(0, 14))

        # ================= Hauptbereich
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=(18, 14))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Hinweise (auf allen Seiten sichtbar): fehlende Tools, fertiges Update
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="we")
        self.banner_frame = ctk.CTkFrame(top, corner_radius=12, fg_color="#2b2314",
                                         border_width=1, border_color="#6b5524")  # nur sichtbar, wenn etwas fehlt
        self.banner = ctk.CTkLabel(self.banner_frame, text="", text_color="#ffb454", anchor="w",
                                   font=self._font(12))
        self.banner.pack(side="left", padx=14, pady=8)
        self._btn(self.banner_frame, "Tools installieren", self.on_install_tools, "secondary",
                  height=28, width=140, font=self._font(12)).pack(side="right", padx=10, pady=6)
        self.upd_frame = ctk.CTkFrame(top, corner_radius=12, fg_color="#12303f",
                                      border_width=1, border_color=ACCENT_DIM)  # erst sichtbar, wenn ein Update da ist
        self.upd_label = ctk.CTkLabel(self.upd_frame, text="", anchor="w", font=self._font(13), text_color=TEXT)
        self.upd_label.pack(side="left", padx=14, pady=10)
        self.upd_btn = self._btn(self.upd_frame, "", None, "primary", width=160, height=32)
        self.upd_btn.pack(side="right", padx=10, pady=8)

        host = ctk.CTkFrame(main, fg_color="transparent")
        host.grid(row=1, column=0, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)

        # ---------- Seite: Bibliothek
        lib = ctk.CTkFrame(host, fg_color="transparent")
        lib.grid(row=0, column=0, sticky="nsew")
        lib.grid_columnconfigure(0, weight=1)
        lib.grid_rowconfigure(2, weight=1)

        mhead = ctk.CTkFrame(lib, fg_color="transparent")
        mhead.grid(row=0, column=0, sticky="we", pady=(0, 12))
        titles = ctk.CTkFrame(mhead, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Bibliothek", font=self._font(28, "bold"), text_color=TEXT,
                     anchor="w").pack(anchor="w")
        self.count_lbl = ctk.CTkLabel(titles, text="", font=self._font(12), text_color=MUTED, anchor="w")
        self.count_lbl.pack(anchor="w", pady=(2, 0))
        self._btn(mhead, "＋  Link", self.add_link, "secondary", width=90, height=34).pack(side="right")
        self._btn(mhead, "＋  Datei", self.add_local, "primary", width=100, height=34).pack(side="right", padx=(0, 8))
        self._search_job = None
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        ctk.CTkEntry(mhead, textvariable=self.search_var, placeholder_text="Suchen …", width=200,
                     height=34, corner_radius=BTN_RADIUS, fg_color=SURFACE, border_width=0,
                     text_color=TEXT, placeholder_text_color=MUTED,
                     font=self._font(13)).pack(side="right", padx=(0, 8))

        frow = ctk.CTkFrame(lib, fg_color="transparent")
        frow.grid(row=1, column=0, sticky="we", pady=(0, 6))
        self.kind_filter = ctk.CTkSegmentedButton(
            frow, values=list(KIND_FILTER), command=self.on_kind,
            fg_color=SURFACE, selected_color=ACCENT_DIM, selected_hover_color=ACCENT_DIM,
            unselected_color=SURFACE, unselected_hover_color=SURFACE2, text_color=TEXT,
            font=self._font(12), height=30, corner_radius=8)
        self.kind_filter.set(self.cfg.get("last_kind", "Alle"))
        self.kind_filter.pack(side="left")
        self.sort_menu = ctk.CTkOptionMenu(frow, values=list(SORTS), command=self.on_sort, width=160,
                                           **self._menu_style())
        self.sort_menu.set(next((k for k, v in SORTS.items() if v == self.cfg.get("sort", "new")),
                                "Zuletzt hinzugefügt"))
        self.sort_menu.pack(side="left", padx=(8, 0))
        self._btn(frow, "★  Zufall", self.random_favorite, "secondary", width=104, height=30,
                  font=self._font(12)).pack(side="right", padx=(6, 0))
        self._btn(frow, "🎲  Zufällig", self.random_wallpaper, "secondary", width=130, height=30,
                  font=self._font(12)).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(lib, corner_radius=0, fg_color="transparent",
                                             scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        self.scroll.grid(row=2, column=0, sticky="nsew", pady=(2, 0))

        # ---------- Seite: Eigener Desktop (Premium)
        deskpage = ctk.CTkScrollableFrame(host, corner_radius=0, fg_color="transparent",
                                          scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        deskpage.grid(row=0, column=0, sticky="nsew")
        self._desk_page = deskpage
        self._desk_host = ctk.CTkFrame(deskpage, fg_color="transparent")
        self._desk_host.pack(fill="x", padx=(0, 10))

        # ---------- Seite: Einstellungen
        sett = ctk.CTkScrollableFrame(host, corner_radius=0, fg_color="transparent",
                                      scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        sett.grid(row=0, column=0, sticky="nsew")
        inner = ctk.CTkFrame(sett, fg_color="transparent")
        inner.pack(fill="x", padx=(0, 10))
        ctk.CTkLabel(inner, text="Einstellungen", font=self._font(28, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(inner, text="Alles, was Wallura auf diesem PC tut – ohne Umwege.",
                     font=self._font(12), text_color=MUTED, anchor="w").pack(fill="x", pady=(2, 16))

        acc_box = self._section(inner, "Konto", "Anmeldung, Rolle und Passwort auf diesem PC.")
        if self.guest:
            row = self._row(acc_box, "Nicht angemeldet",
                            "Wallura läuft ohne Anmeldung. System, Tools und Updates sind frei nutzbar. "
                            "Anmelden für die Benutzerverwaltung und dauerhaftes Angemeldetbleiben – "
                            "Bibliothek und laufende Wallpaper bleiben dabei erhalten.")
            self._btn(row, "Anmelden", self.login, "primary", width=130, height=32,
                      font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        else:
            row = self._row(acc_box, f"{self.user.get('name', GAST)}  ·  "
                                     f"{ROLES.get(self.user.get('role'), 'Nutzer')}",
                            "Angemeldet auf diesem PC – Bibliothek und Wallpaper laufen weiter.")
            self._btn(row, "Abmelden", self.logout, "secondary", width=130, height=32,
                      font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
            row = self._row(acc_box, "Passwort ändern", "Für das eigene Konto (aktuelles Passwort nötig).")
            self._btn(row, "Ändern", self.change_password, "secondary", width=130, height=32,
                      font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        if not self.is_admin:
            ctk.CTkLabel(acc_box, text="System, Tools und Updates sind ohne Konto nutzbar – die "
                                      "Benutzerverwaltung braucht ein Administratorkonto.",
                         font=self._font(11), text_color=MUTED, anchor="w",
                         justify="left", wraplength=520).pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkFrame(acc_box, height=6, fg_color="transparent").pack()

        play = self._section(inner, "Wiedergabe", "Anpassung, Tempo, Effekte und Tag/Nacht.")
        row = self._row(play, "Anpassung", "Wie das Video auf den Monitor gelegt wird.")
        self.fit_menu = ctk.CTkOptionMenu(row, values=list(FIT_MAP), command=self.on_fit, width=200,
                                          **self._menu_style())
        self.fit_menu.set(next((k for k, v in FIT_MAP.items() if v == self.cfg["fit"]), list(FIT_MAP)[0]))
        self.fit_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(play, "Max. FPS",
                        "Weniger Bilder pro Sekunde sparen Leistung und Akku – „24 FPS (sparsam)“ "
                        "reicht für die meisten Wallpaper.")
        self.fps_menu = ctk.CTkOptionMenu(row, values=list(FPS_MAP), command=self.on_fps, width=200,
                                          **self._menu_style())
        self.fps_menu.set(next((k for k, v in FPS_MAP.items() if v == self.cfg.get("fps_limit", 30)), "30 FPS"))
        self.fps_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(play, "Automatisch wechseln",
                        "Wechselt das Wallpaper in festem Abstand – mit Favoriten als Playlist.")
        self.rot_menu = ctk.CTkOptionMenu(row, values=list(ROTATE_MAP), command=self.on_rotate, width=200,
                                          **self._menu_style())
        self.rot_menu.set(next((k for k, v in ROTATE_MAP.items() if v == self.cfg.get("rotate_min", 0)), "Aus"))
        self.rot_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(play, "Geschwindigkeit", "Wiedergabe schneller oder langsamer.")
        self.speed_menu = ctk.CTkOptionMenu(row, values=list(SPEED_MAP), command=self.on_speed, width=200,
                                            **self._menu_style())
        self.speed_menu.set(next((k for k, v in SPEED_MAP.items() if v == self.cfg.get("speed", 1.0)), "Normal"))
        self.speed_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(play, "Helligkeit", "Dunkelt das Wallpaper ab – abends angenehmer.")
        self.br_menu = ctk.CTkOptionMenu(row, values=list(BRIGHT_MAP), command=self.on_brightness, width=200,
                                         **self._menu_style())
        self.br_menu.set(next((k for k, v in BRIGHT_MAP.items() if v == self.cfg.get("brightness", 100)),
                              "100 %"))
        self.br_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.sw_flip = self._switch_row(play, "Bild spiegeln", "Spiegelt das Video horizontal.",
                                        self.on_flip, self.cfg["flip"])
        self.sw_rot180 = self._switch_row(play, "Bild um 180° drehen", "Für kopfüber gefilmte Videos.",
                                          self.on_rotate180, self.cfg["rotate180"])
        self.sw_gray = self._switch_row(play, "Schwarzweiß", "Graustufen statt Farbe.",
                                        self.on_grayscale, self.cfg["grayscale"])
        row = self._row(play, "Tag/Nacht-Wallpaper",
                        "Zwischen 20 und 7 Uhr läuft automatisch das gewählte Nacht-Wallpaper.")
        night_values, self._night_labels = ["Aus"], {}
        for it in self.cfg["items"][:60]:
            label = shorten(it["title"], 28)
            if label in self._night_labels:  # gleiche Kurzfassung -> eindeutig machen
                label = shorten(it["title"], 22) + "…" + it["id"][:4]
            self._night_labels[label] = it["id"]
            night_values.append(label)
        self.night_menu = ctk.CTkOptionMenu(row, values=night_values, command=self.on_night, width=200,
                                            **self._menu_style())
        cur_night = self.find_item(self.cfg.get("night_id") or "")
        cur_label = next((k for k, v in self._night_labels.items() if v == (cur_night or {}).get("id")), "Aus")
        self.night_menu.set(cur_label)
        self.night_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(play, "Max. Qualität (Streams, p)", "Gilt für YouTube/Web-Links und Downloads.")
        self.q_menu = ctk.CTkOptionMenu(row, values=QUALITIES, command=self.on_quality, width=200,
                                        **self._menu_style())
        self.q_menu.set(str(self.cfg["quality"]))
        self.q_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        ctk.CTkFrame(play, height=6, fg_color="transparent").pack()

        # System und Tools & Updates stehen jedem zur Verfügung – auch ohne Konto (Gastmodus).
        sysp = self._section(inner, "System", "Start, Ruhezeiten und Verhalten im Hintergrund.")
        self.sw_pause = self._switch_row(sysp, "Pause, wenn der Desktop verdeckt ist",
                                         "Spart Leistung bei Spielen, Vollbild-Apps und gesperrtem Windows.",
                                         self.on_pause_fs, self.cfg["pause_fullscreen"])
        self.sw_auto = self._switch_row(sysp, "Mit Windows starten",
                                        "Wallura startet im Hintergrund (Tray-Symbol).",
                                        self.on_autostart, is_autostart())
        self.sw_quiet = self._switch_row(sysp, "Ruhezeiten (22–7 Uhr)",
                                         "Nachts nicht automatisch wechseln.", self.on_quiet,
                                         self.cfg["quiet_hours"])
        self.sw_battery = self._switch_row(sysp, "Im Akkubetrieb pausieren",
                                           "Spart Strom, sobald das Netzteil nicht angeschlossen ist.",
                                           self.on_battery_pause, self.cfg["pause_battery"])
        self.sw_random_start = self._switch_row(sysp, "Zufällig beim Start",
                                                "Beim Start ein zufälliges Wallpaper statt des letzten.",
                                                self.on_random_start, self.cfg["random_start"])
        self.sw_notify = self._switch_row(sysp, "Hinweis beim Wechsel",
                                          "Tray-Hinweis, wenn automatisch gewechselt wurde.",
                                          self.on_notify_rotate, self.cfg["notify_rotate"])
        ctk.CTkFrame(sysp, height=6, fg_color="transparent").pack()

        tools = self._section(inner, "Tools & Updates", "Player, Downloader und Aktualisierung.")
        row = self._row(tools, "Tools", "mpv (Player) und yt-dlp (Downloads)")
        self.tools_desc = row.desc
        self._btn(row, "Installieren / aktualisieren", self.on_install_tools, "secondary", width=200,
                  height=32, font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(tools, f"Wallura {APP_VERSION}", "Sucht bei GitHub nach einer neuen Version.")
        self._btn(row, "Nach Updates suchen", lambda: self.check_updates(True), "secondary", width=200,
                  height=32, font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.sw_upd = self._switch_row(tools, "Updates automatisch laden",
                                       "Prüft beim Start und alle 6 Stunden, lädt neue Versionen herunter.",
                                       self.on_auto_update, self.cfg.get("auto_update", True))
        ctk.CTkFrame(tools, height=6, fg_color="transparent").pack()

        if self.is_admin:  # Konten anlegen/ändern bleibt Administratoren vorbehalten
            self._users_box = self._section(inner, "Benutzer", "Konten auf diesem PC – nur für Administratoren.")
            row = self._row(self._users_box, "Konten",
                            "Wer sich anmelden darf und wer Adminrechte hat (nur Administratoren).")
            self._btn(row, "Neues Konto", self.add_user, "secondary", width=140, height=32,
                      font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
            self._user_rows = ctk.CTkFrame(self._users_box, fg_color="transparent")
            self._user_rows.pack(fill="x", padx=18, pady=(4, 0))
            ctk.CTkFrame(self._users_box, height=6, fg_color="transparent").pack()
            self._refresh_users()

            # Konten von allen PCs (fragt den Server im Hintergrund, damit der Start nicht hängt)
            self._cloud_box = self._section(inner, "Konten auf allen PCs",
                                            "Alle Konten, die auf PCs mit Wallura angelegt wurden.")
            row = self._row(self._cloud_box, "Konten-Übersicht",
                            "Alle Konten, die auf PCs mit Wallura angelegt wurden – nur für Administratoren.")
            self._btn(row, "Aktualisieren", self.refresh_cloud, "secondary", width=130, height=32,
                      font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
            self._cloud_unlock = self._btn(row, "Freischalten", self.unlock_cloud, "primary", width=130,
                                           height=32, font=self._font(12))
            self._cloud_unlock.grid(row=0, column=2, sticky="e", padx=(8, 0))
            self._cloud_status = ctk.CTkLabel(self._cloud_box, text="", font=self._font(11), text_color=MUTED,
                                              anchor="w", justify="left", wraplength=520)
            self._cloud_status.pack(fill="x", padx=18)
            self._cloud_rows = ctk.CTkFrame(self._cloud_box, fg_color="transparent")
            self._cloud_rows.pack(fill="x", padx=18, pady=(4, 0))
            ctk.CTkFrame(self._cloud_box, height=6, fg_color="transparent").pack()
            self.after(150, self.refresh_cloud)

        lib_box = self._section(inner, "Bibliothek", "Sortierung, Statistik und Aufräumen.")
        row = self._row(lib_box, "Sortierung", "Reihenfolge der Wallpaper in der Bibliothek.")
        self.sort_menu_settings = ctk.CTkOptionMenu(row, values=list(SORTS), command=self.on_sort, width=200,
                                                   **self._menu_style())
        self.sort_menu_settings.set(next((k for k, v in SORTS.items() if v == self.cfg.get("sort", "new")),
                                         "Zuletzt hinzugefügt"))
        self.sort_menu_settings.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(lib_box, "Statistik", "…")
        self.stats_lbl = row.desc
        row = self._row(lib_box, "Sichern & Teilen",
                        "Bibliotheksliste als JSON exportieren oder importieren (ohne Videodateien).")
        acts = ctk.CTkFrame(row, fg_color="transparent")
        acts.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._btn(acts, "Exportieren", self.export_library, "secondary", height=30, width=104,
                  font=self._font(11)).pack(side="left", padx=2)
        self._btn(acts, "Importieren", self.import_library, "secondary", height=30, width=104,
                  font=self._font(11)).pack(side="left", padx=2)
        row = self._row(lib_box, "Aufräumen", "Doppelte Einträge, Favoriten und Vorschaubilder.")
        acts = ctk.CTkFrame(row, fg_color="transparent")
        acts.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._btn(acts, "Duplikate", self.remove_duplicates, "ghost", height=30, width=88,
                  font=self._font(11)).pack(side="left", padx=2)
        self._btn(acts, "Favoriten löschen", self.clear_favorites, "ghost", height=30, width=132,
                  font=self._font(11)).pack(side="left", padx=2)
        self._btn(acts, "Vorschauen", self.rebuild_thumbs, "ghost", height=30, width=96,
                  font=self._font(11)).pack(side="left", padx=2)
        row = self._row(lib_box, "Screenshot", "Speichert das laufende Wallpaper als PNG im Datenordner.")
        self._btn(row, "Aufnehmen", self.screenshot_now, "secondary", height=30, width=110,
                  font=self._font(11)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        ctk.CTkFrame(lib_box, height=6, fg_color="transparent").pack()

        data = self._section(inner, "Daten", "Speicherort von Einstellungen, Downloads und Vorschaubildern.")
        row = self._row(data, "Datenordner", f"{DATA_DIR}\nEinstellungen, Downloads, Vorschaubilder und mpv-Logs")
        self._btn(row, "Ordner öffnen", self.open_data_dir, "secondary", width=200, height=32,
                  font=self._font(12)).grid(row=0, column=1, sticky="e", padx=(16, 0))
        ctk.CTkFrame(data, height=6, fg_color="transparent").pack()

        self._pages = {"library": lib, "settings": sett, "desk": deskpage}

        # ---------- Player-Leiste unten: Status, Steuerung, Lautstärke
        bar = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=CARD_RADIUS)
        bar.grid(row=2, column=0, sticky="we", pady=(12, 0))
        bar.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="we", padx=(16, 8), pady=10)
        ctk.CTkLabel(left, text="JETZT LÄUFT", font=self._font(9, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x")
        self.now_lbl = ctk.CTkLabel(left, text="Nichts aktiv", anchor="w", font=self._font(13, "bold"),
                                    text_color=TEXT)
        self.now_lbl.pack(fill="x", pady=(1, 1))
        self.status = ctk.CTkLabel(left, text="Bereit.", anchor="w", font=self._font(11), text_color=MUTED)
        self.status.pack(fill="x")
        self.progress = ctk.CTkProgressBar(left, height=3, progress_color=ACCENT, fg_color=BORDER)
        self.progress.set(0)  # wird nur während eines Downloads eingeblendet

        ctrl = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl.grid(row=0, column=1, padx=4)
        self.btn_pause = self._btn(ctrl, "Pause", self.toggle_pause, "secondary", width=80, height=32,
                                   font=self._font(12))
        self.btn_pause.pack(side="left", padx=3)
        self._btn(ctrl, "Nächstes", self.next_wallpaper, "secondary", width=88, height=32,
                  font=self._font(12)).pack(side="left", padx=3)
        self.btn_stop = self._btn(ctrl, "■  Alle stoppen", self.stop_wallpaper, "danger", width=140, height=32,
                                  font=self._font(12))
        self.btn_stop.pack(side="left", padx=3)

        vol = ctk.CTkFrame(bar, fg_color="transparent")
        vol.grid(row=0, column=2, padx=(10, 16))
        ctk.CTkLabel(vol, text="Lautstärke", font=self._font(12), text_color=MUTED).pack(side="left", padx=(0, 8))
        self.vol = ctk.CTkSlider(vol, from_=0, to=100, number_of_steps=100, command=self.on_volume, width=100,
                                 button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                 progress_color=ACCENT, fg_color=BORDER)
        self.vol.set(self.cfg["volume"])
        self.vol.pack(side="left")
        self.vol_lbl = ctk.CTkLabel(vol, text=f"{int(self.cfg['volume'])} %", font=self._font(12),
                                    text_color=MUTED, width=44, anchor="e")
        self.vol_lbl.pack(side="left", padx=(6, 0))

        self._show_page("library")
        self._bind_shortcuts()
        self._update_stats()

    # -- Bibliothek
    def find_item(self, item_id):
        return next((i for i in self.cfg["items"] if i["id"] == item_id), None)

    def _layout(self):
        """-> (Spalten, Breite des Vorschaubilds in px). Die Karten füllen die Breite aus."""
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        w = self.winfo_width()
        if w < 300:  # Fenster noch nicht angezeigt
            w = 1200 * scale
        avail = w / scale - SIDEBAR_W - 40 - 28   # Seitenränder + Scrollbalken
        cols = max(1, int(avail // 296))
        tw = int(avail / cols) - 42               # Kartenrand + Abstand
        return cols, max(200, min(tw, 420)) // 8 * 8

    def _on_resize(self, e):
        if e.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(300, self._relayout)

    def _relayout(self):
        self._resize_job = None
        if not self._closing and self._layout() != self._last_cols:
            self.refresh_library()

    def _on_search(self, *_):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.refresh_library)

    @staticmethod
    def _pil_font(size):
        for name in ("segoeuib.ttf", "arialbd.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass
        return ImageFont.load_default()

    @staticmethod
    def _pill(d, x, y, text, fill, fg, font, right=False):
        """Kleines Abzeichen (Pille) auf das Vorschaubild zeichnen. x ist die linke bzw. (right=True) rechte Kante."""
        try:
            l, t, r, b = d.textbbox((0, 0), text, font=font)
        except Exception:
            return
        px, py = 14, 8
        w, h = r - l + 2 * px, b - t + 2 * py
        if right:
            x -= w
        d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill)
        d.text((x + px - l, y + py - t), text, font=font, fill=fg)

    def _thumb_image(self, item, tw, active_text=None):
        th = tw * 9 // 16
        W, H = tw * 2, th * 2   # doppelt so groß zeichnen = scharf auf hochauflösenden Monitoren
        p = THUMB_DIR / f"{item['id']}.jpg"
        cache = getattr(self, "_thumb_cache", None)
        if cache is None:
            cache = self._thumb_cache = {}
        try:
            mtime = p.stat().st_mtime if p.exists() else 0
        except OSError:
            mtime = 0
        key = (item["id"], tw, active_text, int(item.get("plays", 0) or 0), mtime)
        if key in cache:  # nicht bei jedem Neuaufbau alle Bilder erneut laden und skalieren
            return cache[key]
        try:
            img = Image.open(p).convert("RGB") if p.exists() else placeholder()
        except Exception:
            img = placeholder()
        img = ImageOps.fit(img, (W, H)).convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")
        font = self._pil_font(24)
        self._pill(d, 16, 16, KIND_LABEL.get(item["kind"], "?"), (13, 15, 19, 205), (233, 237, 242, 255), font)
        if active_text:
            self._pill(d, W - 16, 16, active_text, (76, 194, 255, 255), (6, 32, 46, 255), font, right=True)
        plays = int(item.get("plays", 0) or 0)
        if plays:
            self._pill(d, 16, H - 60, f"{plays}×", (13, 15, 19, 205), (233, 237, 242, 255), font)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=28, fill=255)
        img.putalpha(mask)
        image = ctk.CTkImage(img, size=(tw, th))
        if len(cache) > 160:
            cache.clear()  # Speicher begrenzen
        cache[key] = image
        return image

    def refresh_library(self):
        self._refresh_monitor_ui()
        self._update_stats()
        self._refresh_now_playing()
        for w in self.scroll.winfo_children():
            w.destroy()
        on = {}
        for idx, it in self._assign_items().items():
            on.setdefault(it["id"], []).append(idx)
        self._on_map, self._mon_count = on, len(get_monitors())
        layout = self._last_cols = self._layout()
        cols, tw = layout
        for c in range(max(cols, getattr(self, "_prev_cols", 0))):  # Spalten gleichmäßig verteilen
            self.scroll.grid_columnconfigure(c, weight=1 if c < cols else 0)
        self._prev_cols = cols
        n_items = len(self.cfg["items"])
        q = self.search_var.get().strip().lower()
        kind = KIND_FILTER.get(self.kind_filter.get())
        shown = self._visible_items()
        filtering = bool(q or kind)
        if not n_items:
            self.count_lbl.configure(text="")
        else:
            self.count_lbl.configure(text=f"{len(shown)} von {n_items}" if filtering else f"{n_items} Wallpaper")
        if n_items and not shown:
            box = ctk.CTkFrame(self.scroll, corner_radius=CARD_RADIUS, fg_color=SURFACE, border_width=1,
                               border_color=BORDER)
            box.grid(row=0, column=0, columnspan=cols, padx=8, pady=40)
            ctk.CTkLabel(box, text="Keine Treffer", font=self._font(20, "bold"),
                         text_color=TEXT).pack(padx=56, pady=(30, 4))
            ctk.CTkLabel(box, text="Andere Suche oder einen anderen Filter probieren.",
                         font=self._font(13), text_color=MUTED).pack(padx=56)
            self._btn(box, "Filter zurücksetzen", self.reset_filters, "secondary", width=170).pack(
                pady=(16, 30))
            return
        if not n_items:
            box = ctk.CTkFrame(self.scroll, corner_radius=CARD_RADIUS, fg_color=SURFACE, border_width=1,
                               border_color=BORDER)
            box.grid(row=0, column=0, columnspan=cols, padx=8, pady=36)
            ctk.CTkLabel(box, text="Deine Leinwand ist noch leer", font=self._font(22, "bold"),
                         text_color=TEXT).pack(padx=60, pady=(40, 6))
            ctk.CTkLabel(box, text="Füge ein Video, ein Bild oder einen Link (YouTube, Web) hinzu – danach\n"
                                   "läuft es hinter deinen Desktop-Icons, auf einem oder allen Monitoren.",
                         font=self._font(13), text_color=MUTED, justify="center").pack(padx=60)
            brow = ctk.CTkFrame(box, fg_color="transparent")
            brow.pack(padx=60, pady=(22, 40))
            self._btn(brow, "＋  Datei hinzufügen", self.add_local, "primary", width=180, height=38).pack(
                side="left", padx=4)
            self._btn(brow, "＋  Link", self.add_link, "secondary", width=130, height=38).pack(side="left", padx=4)
        for n, item in enumerate(shown):
            self._card(item, n // cols, n % cols, tw)

    def _card(self, item, r, c, tw):
        on = sorted(self._on_map.get(item["id"], []))
        active = bool(on) and self.player.active
        card = ctk.CTkFrame(self.scroll, corner_radius=CARD_RADIUS,
                            fg_color="#0c1f28" if active else SURFACE,
                            border_width=1, border_color=ACCENT_DIM if active else BORDER)
        card.grid(row=r, column=c, padx=9, pady=9, sticky="n")
        where = None
        if active:
            if self._mon_count == 1:
                where = "Aktiv"
            elif len(on) == self._mon_count:
                where = "Alle Monitore"
            else:
                where = "Monitor " + ", ".join(str(i + 1) for i in on)
        lbl = ctk.CTkLabel(card, image=self._thumb_image(item, tw, where), text="", cursor="hand2")
        lbl.pack(padx=12, pady=(12, 10))
        lbl.bind("<Button-1>", lambda e, it=item: self.apply(it))
        lbl.bind("<Double-Button-1>", lambda e, it=item: self.apply_all(it))
        if not active:
            lbl.bind("<Enter>", lambda e, cd=card: cd.configure(border_color=ACCENT_DIM))
            lbl.bind("<Leave>", lambda e, cd=card: cd.configure(border_color=BORDER))
        ctk.CTkLabel(card, text=shorten(item["title"], max(16, tw // 8)), font=self._font(14, "bold"),
                     text_color=TEXT, anchor="w", width=tw).pack(padx=14, anchor="w")
        plays = int(item.get("plays", 0) or 0)
        meta = KIND_LABEL.get(item["kind"], "?") + (f"  ·  {plays}× genutzt" if plays else "")
        ctk.CTkLabel(card, text=meta, font=self._font(11), text_color=MUTED, anchor="w",
                     width=tw).pack(padx=14, anchor="w", pady=(2, 10))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=11, pady=(0, 12))
        row.grid_columnconfigure(0, weight=1)
        self._btn(row, "Aktiv" if active else "▶  Anwenden", lambda it=item: self.apply(it),
                  "secondary" if active else "primary", height=34, width=10,
                  font=self._font(12, "bold")).grid(row=0, column=0, sticky="we")
        col = 1
        self._btn(row, "✎", lambda it=item: self.rename_item(it), "ghost", width=32, height=34).grid(
            row=0, column=col, padx=(6, 0))
        col += 1
        self._btn(row, "★" if item.get("fav") else "☆", lambda it=item: self.toggle_favorite(it),
                  "ghost", width=32, height=34,
                  text_color=ACCENT if item.get("fav") else MUTED).grid(row=0, column=col, padx=(6, 0))
        col += 1
        if item["kind"] != "local":
            self._btn(row, "⬇", lambda it=item: self.download(it), "ghost", width=32, height=34).grid(
                row=0, column=col, padx=(6, 0))
            col += 1
        self._btn(row, "✕", lambda it=item: self.remove(it), "ghost", width=32, height=34,
                  hover_color="#3a1c1f").grid(row=0, column=col, padx=(6, 0))

    # -- Favoriten, Zufall und automatischer Wechsel
    def _refresh_now_playing(self):
        lbl = getattr(self, "now_lbl", None)
        if lbl is None:
            return
        active = self._assign_items()
        if not active or not self.player.active:
            lbl.configure(text="Nichts aktiv")
            return
        item = next(iter(active.values()))
        more = f"  +{len({i['id'] for i in active.values()}) - 1}" if len({i['id'] for i in active.values()}) > 1 else ""
        lbl.configure(text=shorten(item["title"], 44) + more)

    def reset_filters(self):
        self.search_var.set("")
        self.kind_filter.set("Alle")
        self.cfg["last_kind"] = "Alle"
        save_config(self.cfg)
        self.refresh_library()

    def _visible_items(self):
        """Wallpaper, die gerade in der Bibliothek sichtbar sind (Suche + Filter + Sortierung)."""
        q = self.search_var.get().strip().lower()
        kind = KIND_FILTER.get(self.kind_filter.get())
        out = []
        for it in self.cfg["items"]:
            if q and q not in str(it.get("title", "")).lower() and q not in str(it.get("src", "")).lower():
                continue
            if kind == "fav":
                if not it.get("fav"):
                    continue
            elif kind and it["kind"] != kind:
                continue
            out.append(it)
        sort = self.cfg.get("sort", "new")
        if sort == "az":
            out.sort(key=lambda i: str(i.get("title", "")).lower())
        elif sort == "plays":
            out.sort(key=lambda i: (-int(i.get("plays", 0) or 0), str(i.get("title", "")).lower()))
        elif sort == "fav":
            out.sort(key=lambda i: (not bool(i.get("fav")), -int(i.get("plays", 0) or 0),
                                    str(i.get("title", "")).lower()))
        else:
            out.sort(key=lambda i: -float(i.get("added", 0) or 0))
        return out

    def on_kind(self, value):
        self.cfg["last_kind"] = value if value in KIND_FILTER else "Alle"
        save_config(self.cfg)
        self.refresh_library()

    def on_sort(self, label):
        self.cfg["sort"] = SORTS.get(label, "new")
        save_config(self.cfg)
        if hasattr(self, "sort_menu"):
            self.sort_menu.set(label)
        if hasattr(self, "sort_menu_settings"):
            self.sort_menu_settings.set(label)
        self.refresh_library()

    def toggle_favorite(self, item):
        item["fav"] = not bool(item.get("fav"))
        save_config(self.cfg)
        self.refresh_library()
        self.set_status(f"{'Zu Favoriten hinzugefügt' if item['fav'] else 'Aus Favoriten entfernt'}: "
                        f"{shorten(item['title'], 40)}")
        self.toast(f"{'★  Zu Favoriten hinzugefügt' if item['fav'] else '☆  Aus Favoriten entfernt'}")

    def rename_item(self, item):
        res = self._form("Titel ändern", [{"key": "title", "label": "Neuer Titel", "type": "text",
                                           "value": item["title"]}],
                         f"Bisher: {shorten(item['title'], 70)}", "Speichern")
        if res is None:
            return
        title = (res.get("title") or "").strip()
        if not title:
            self.set_status("Der Titel darf nicht leer sein.", True)
            return
        item["title"] = title[:120]
        save_config(self.cfg)
        self.refresh_library()
        self.set_status(f"Titel geändert: {shorten(item['title'], 50)}")

    def _random_pick(self, items):
        """Zufall ohne direkte Wiederholung der zuletzt gezogenen Wallpaper."""
        if not items:
            return None
        pool = [i for i in items if i["id"] not in self._recent_random] or list(items)
        pick = random.choice(pool)
        self._recent_random = ([pick["id"]] + self._recent_random)[:3]
        return pick

    def random_wallpaper(self, favorites=False):
        """Ein zufälliges Wallpaper aus der aktuellen Auswahl (Filter/Suche)."""
        items = self._visible_items()
        if favorites:
            items = [i for i in items if i.get("fav")]
            if not items:
                self.set_status("Keine Favoriten in der aktuellen Auswahl.", True)
                return
        pick = self._random_pick(items)
        if not pick:
            self.set_status("Keine Wallpaper in der aktuellen Auswahl.", True)
            return
        self.apply(pick)

    def random_favorite(self):
        self.random_wallpaper(favorites=True)

    def rotate_favorite(self):
        """Nächstes Favorit der Bibliothek (auch aus dem Tray)."""
        favs = [i for i in self.cfg["items"] if i.get("fav")]
        if not favs:
            self.set_status("Es gibt noch keine Favoriten.", True)
            return
        idxs = self._target_indices()
        cur = self.cfg.get("assign", {}).get(str(idxs[0])) if idxs else None
        ids = [i["id"] for i in favs]
        self.apply(favs[(ids.index(cur) + 1) % len(favs)] if cur in ids else favs[0])

    def apply_all(self, item):
        """Doppelklick auf eine Karte: sofort auf alle Monitore anwenden."""
        self.cfg["monitor"] = "all"
        save_config(self.cfg)
        self.apply(item)

    def _playlist(self):
        """Wallpaper für den automatischen Wechsel (optional nur Favoriten)."""
        items = self._visible_items()
        if self.cfg.get("fav_playlist"):
            favs = [i for i in items if i.get("fav")]
            if favs:
                return favs
        return items

    def rotate_now(self):
        """Nächstes Wallpaper der Playlist – für den automatischen Wechsel."""
        items = self._playlist()
        if not items:
            return None
        idxs = self._target_indices()
        cur = self.cfg.get("assign", {}).get(str(idxs[0])) if idxs else None
        ids = [i["id"] for i in items]
        item = items[(ids.index(cur) + 1) % len(items)] if cur in ids else items[0]
        self.apply(item)
        return item

    def _schedule_rotate(self):
        if self._rotate_job is not None:
            try:
                self.after_cancel(self._rotate_job)
            except Exception:
                pass
            self._rotate_job = None
        minutes = int(self.cfg.get("rotate_min", 0) or 0)
        if minutes > 0 and not self._closing:
            self._rotate_job = self.after(minutes * 60 * 1000, self._rotate_tick)

    def _quiet_now(self):
        if not self.cfg.get("quiet_hours"):
            return False
        hour = time.localtime().tm_hour
        return hour >= 22 or hour < 7

    def _notify(self, text):
        try:
            if self.tray is not None:
                self.tray.notify(text, APP_NAME)
        except Exception:
            pass

    def _rotate_tick(self):
        self._rotate_job = None
        if self._closing:
            return
        if not fullscreen_app_active() and not self._quiet_now():  # nicht in Spiele / Vollbild-Apps wechseln
            item = self.rotate_now()
            if item and self.cfg.get("notify_rotate"):
                self._notify(f"Wechsel: {shorten(item['title'], 40)}")
        self._schedule_rotate()

    # -- Tag/Nacht-Wallpaper
    def _night_now(self):
        hour = time.localtime().tm_hour
        return hour >= 20 or hour < 7

    def _night_check(self):
        self._night_job = None
        if self._closing:
            return
        night = self.find_item(self.cfg.get("night_id") or "")
        want = bool(night) and self._night_now()
        if not self.player.active:  # kein laufendes Wallpaper: nichts automatisch starten
            self._night_job = self.after(5 * 60 * 1000, self._night_check)
            return
        if want and not self._night_on:
            self._night_on = True
            self._night_backup = dict(self.cfg.get("assign", {}))
            a = dict(self.cfg["assign"])
            for i in self._target_indices():
                a[str(i)] = night["id"]
            self.cfg["assign"] = a
            save_config(self.cfg)
            threading.Thread(target=lambda: (self.player.apply(self._assign_items()),
                                             self.ui(self.refresh_library)), daemon=True).start()
            self.set_status(f"Nacht-Wallpaper aktiv: {shorten(night['title'], 40)}")
        elif not want and self._night_on:
            self._night_on = False
            self.cfg["assign"] = dict(self._night_backup or {})
            save_config(self.cfg)
            threading.Thread(target=lambda: (self.player.apply(self._assign_items()),
                                             self.ui(self.refresh_library)), daemon=True).start()
            self.set_status("Tag-Wallpaper wieder aktiv.")
        self._night_job = self.after(5 * 60 * 1000, self._night_check)

    def on_rotate(self, label):
        self.cfg["rotate_min"] = ROTATE_MAP.get(label, 0)
        save_config(self.cfg)
        self._schedule_rotate()
        self.set_status(f"Automatischer Wechsel: {label}." if self.cfg["rotate_min"]
                        else "Automatischer Wechsel aus.")

    def on_speed(self, label):
        self.cfg["speed"] = SPEED_MAP.get(label, 1.0)
        save_config(self.cfg)
        self.restart_current()
        self.set_status(f"Geschwindigkeit: {label}.")

    def on_brightness(self, label):
        self.cfg["brightness"] = BRIGHT_MAP.get(label, 100)
        save_config(self.cfg)
        self.restart_current()
        self.set_status(f"Helligkeit: {label}.")

    def on_flip(self):
        self.cfg["flip"] = bool(self.sw_flip.get())
        save_config(self.cfg)
        self.restart_current()

    def on_rotate180(self):
        self.cfg["rotate180"] = bool(self.sw_rot180.get())
        save_config(self.cfg)
        self.restart_current()

    def on_grayscale(self):
        self.cfg["grayscale"] = bool(self.sw_gray.get())
        save_config(self.cfg)
        self.restart_current()

    def on_night(self, label):
        self.cfg["night_id"] = (getattr(self, "_night_labels", {}) or {}).get(label, "")
        save_config(self.cfg)
        self.set_status("Nacht-Wallpaper aus." if not self.cfg["night_id"]
                        else f"Nacht-Wallpaper (20–7 Uhr): {label}")

    def on_quiet(self):
        self.cfg["quiet_hours"] = bool(self.sw_quiet.get())
        save_config(self.cfg)

    def on_battery_pause(self):
        self.cfg["pause_battery"] = bool(self.sw_battery.get())
        save_config(self.cfg)

    def on_random_start(self):
        self.cfg["random_start"] = bool(self.sw_random_start.get())
        save_config(self.cfg)

    def on_notify_rotate(self):
        self.cfg["notify_rotate"] = bool(self.sw_notify.get())
        save_config(self.cfg)

    # -- Bibliothek: Statistik, Aufräumen, Export und Screenshot
    def _update_stats(self):
        label = getattr(self, "stats_lbl", None)
        if label is None:
            return
        items = self.cfg["items"]
        favs = sum(1 for i in items if i.get("fav"))
        local = sum(1 for i in items if i["kind"] == "local")
        size = 0
        for i in items:
            if i["kind"] == "local":
                try:
                    size += Path(i["src"]).stat().st_size
                except OSError:
                    pass
        text = f"{len(items)} Wallpaper · {favs} Favoriten · {local} lokal · {size / (1024 ** 2):.1f} MB"
        top = max(items, key=lambda i: int(i.get("plays", 0) or 0), default=None)
        if top is not None and int(top.get("plays", 0) or 0) > 0:
            text += f" · meistgesehen: {shorten(top['title'], 24)} ({int(top['plays'])}×)"
        label.configure(text=text)

    def export_library(self):
        path = filedialog.asksaveasfilename(title="Bibliothek exportieren", defaultextension=".json",
                                            initialfile="wallura-bibliothek.json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = {"app": APP_NAME, "version": APP_VERSION, "items": self.cfg["items"]}
        try:
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.set_status(f"Bibliothek exportiert: {Path(path).name}")
            self.toast("Bibliothek exportiert")
        except Exception as e:
            self.set_status(f"Export fehlgeschlagen: {e}", True)

    def import_library(self):
        path = filedialog.askopenfilename(title="Bibliothek importieren",
                                          filetypes=[("JSON", "*.json"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            self.set_status(f"Datei nicht lesbar: {e}", True)
            return
        raw = data.get("items") if isinstance(data, dict) else data
        known = {i["src"].strip().lower() for i in self.cfg["items"]}
        added = 0
        for entry in raw if isinstance(raw, list) else []:
            item = _clean_item(entry)
            if not item or item["src"].strip().lower() in known:
                continue
            item["id"] = uuid.uuid4().hex[:10]
            item["plays"] = 0
            item["added"] = time.time()
            self.cfg["items"].append(item)
            known.add(item["src"].strip().lower())
            added += 1
            if item["kind"] == "local":
                threading.Thread(target=self._thumb_worker, args=(item,), daemon=True).start()
        save_config(self.cfg)
        self.refresh_library()
        self.set_status(f"{added} Wallpaper importiert." if added else "Keine neuen Einträge in der Datei.")

    def remove_duplicates(self):
        seen, keep, dupes = set(), [], []
        for item in self.cfg["items"]:
            key = (item["kind"], item["src"].strip().lower())
            if key in seen:
                dupes.append(item)
            else:
                seen.add(key)
                keep.append(item)
        if not dupes:
            self.set_status("Keine doppelten Einträge gefunden.")
            return
        ids = {i["id"] for i in dupes}
        self.cfg["items"] = keep
        self.cfg["assign"] = {k: v for k, v in self.cfg.get("assign", {}).items() if v not in ids}
        save_config(self.cfg)
        threading.Thread(target=lambda: (self.player.apply(self._assign_items()),
                                         self.ui(self.refresh_library)), daemon=True).start()
        self.set_status(f"{len(dupes)} doppelte Einträge entfernt.")

    def clear_favorites(self):
        count = sum(1 for i in self.cfg["items"] if i.get("fav"))
        if not count:
            self.set_status("Es gibt noch keine Favoriten.")
            return
        for item in self.cfg["items"]:
            item["fav"] = False
        save_config(self.cfg)
        self.refresh_library()
        self.set_status(f"{count} Favoriten entfernt.")

    def rebuild_thumbs(self):
        local_items = [i for i in self.cfg["items"] if i["kind"] == "local"]
        if not local_items:
            self.set_status("Keine lokalen Wallpaper für Vorschaubilder.", True)
            return
        self.set_status(f"Erzeuge {len(local_items)} Vorschaubilder neu …")

        def work():
            for item in local_items:
                make_local_thumb(item["id"], item["src"])
            self.ui(lambda: (self.refresh_library(), self.set_status("Vorschaubilder neu erzeugt.")))

        threading.Thread(target=work, daemon=True).start()

    def screenshot_now(self):
        paths = self.player.screenshot(DATA_DIR / "screenshots")
        if not paths:
            self.set_status("Kein Wallpaper aktiv – Screenshot nicht möglich.", True)
            return
        self.set_status(f"Screenshot gespeichert: {paths[0].name}")
        self.toast(f"Screenshot gespeichert: {paths[0].name}")
        try:
            os.startfile(str(paths[0].parent))
        except Exception:
            pass

    def _hotkey(self, fn):
        try:
            widget = self.focus_get()
        except Exception:
            widget = None
        if widget is not None and widget.winfo_class() in ("Entry", "TEntry", "Text"):
            return
        fn()

    def _bind_shortcuts(self):
        self.bind_all("<space>", lambda e: self._hotkey(self.toggle_pause))
        self.bind_all("<Key-n>", lambda e: self._hotkey(self.next_wallpaper))
        self.bind_all("<Key-r>", lambda e: self._hotkey(self.random_wallpaper))
        self.bind_all("<Key-f>", lambda e: self._hotkey(self.favorite_current))

    def favorite_current(self):
        active = self._assign_items()
        item = next((active[i] for i in self._target_indices() if i in active), None)
        if item is None:
            self.set_status("Kein Wallpaper aktiv.", True)
            return
        self.toggle_favorite(item)

    # -- Hinzufügen / Entfernen
    def add_local(self):
        pats = " ".join(f"*{e}" for e in MEDIA_EXT)
        files = filedialog.askopenfilenames(title="Wallpaper auswählen",
                                            filetypes=[("Videos & Bilder", pats), ("Alle Dateien", "*.*")])
        for f in files:
            item = {"id": uuid.uuid4().hex[:10], "title": Path(f).stem, "kind": "local", "src": f,
                    "added": time.time(), "plays": 0}
            self.cfg["items"].append(item)
            threading.Thread(target=self._thumb_worker, args=(item,), daemon=True).start()
        if files:
            save_config(self.cfg)
            self.refresh_library()

    def add_link(self):
        res = self._form("Link hinzufügen", [
            {"key": "url", "label": "YouTube-, Video- oder Web-Link", "type": "text",
             "placeholder": "https://…"},
        ], "Wallura erkennt YouTube-Links, direkte Videodateien und alles, was yt-dlp kann.", "Hinzufügen")
        if res is None:
            return
        url = (res.get("url") or "").strip()
        if not url:
            return
        if not re.match(r"https?://", url, re.I):
            self.set_status("Das sieht nicht nach einem Link aus (https://…).", True)
            return
        if any(i["src"].strip().lower() == url.lower() for i in self.cfg["items"]):
            self.set_status("Dieser Link ist schon in der Bibliothek.", True)
            return
        item = {"id": uuid.uuid4().hex[:10], "title": url, "kind": detect_kind(url), "src": url,
                "added": time.time(), "plays": 0}
        self.cfg["items"].append(item)
        save_config(self.cfg)
        self.refresh_library()
        threading.Thread(target=self._meta_worker, args=(item,), daemon=True).start()

    def _thumb_worker(self, item):
        make_local_thumb(item["id"], item["src"])
        self.ui(self.refresh_library)

    def _meta_worker(self, item):
        title, thumb = fetch_meta(item["src"])
        item["title"] = title
        save_config(self.cfg)
        if thumb:
            try:
                save_thumb(item["id"], Image.open(io.BytesIO(http_get(thumb))))
            except Exception:
                pass
        self.ui(self.refresh_library)

    def remove(self, item):
        old = self.cfg.get("assign", {})
        a = {k: v for k, v in old.items() if v != item["id"]}
        changed = len(a) != len(old)
        self.cfg["assign"] = a
        self.cfg["items"] = [i for i in self.cfg["items"] if i["id"] != item["id"]]
        (THUMB_DIR / f"{item['id']}.jpg").unlink(missing_ok=True)
        if item["kind"] == "local" and Path(item["src"]).parent == LIB_DIR:
            Path(item["src"]).unlink(missing_ok=True)  # nur selbst heruntergeladene Dateien löschen
        save_config(self.cfg)
        if changed:
            threading.Thread(target=lambda: self.player.apply(self._assign_items()), daemon=True).start()
        self.refresh_library()

    # -- Wallpaper steuern
    def apply(self, item):
        if item.get("id") == DESK_ID and not self.is_premium:
            self._require_premium()
            return
        self.set_status(f"Starte „{shorten(item['title'], 40)}“ …")
        threading.Thread(target=self._apply_worker, args=(item,), daemon=True).start()

    def _apply_worker(self, item):
        idxs = self._target_indices()
        a = dict(self.cfg.get("assign", {}))
        for i in idxs:
            a[str(i)] = item["id"]
        ok = self.player.apply(self._assign_items(a))
        live = {i: inst["item"]["id"] for i, inst in list(self.player.instances.items())}
        for i in idxs:  # nur übernehmen, was wirklich läuft
            if live.get(i) == item["id"]:
                self.cfg["assign"][str(i)] = item["id"]
        if ok:  # Wiedergabe-Statistik
            item["plays"] = int(item.get("plays", 0) or 0) + 1
            item["last_used"] = time.time()
        save_config(self.cfg)
        if ok:
            where = "" if len(idxs) != 1 or self._mon_count == 1 else f" (Monitor {idxs[0] + 1})"
            self.ui(lambda: self.set_status(f"Aktiv: {shorten(item['title'], 60)}{where}"))
            self.ui(lambda: self.toast(f"▶  Läuft jetzt: {shorten(item['title'], 40)}"))
        self.ui(self.refresh_library)

    def stop_wallpaper(self):
        a = dict(self.cfg.get("assign", {}))
        sel = str(self.cfg.get("monitor", "all"))
        if sel.isdigit():
            a.pop(sel, None)
            msg = f"Monitor {int(sel) + 1} gestoppt."
        else:
            a = {}
            msg = "Wallpaper gestoppt."
        self.cfg["assign"] = a
        save_config(self.cfg)
        threading.Thread(target=lambda: (self.player.apply(self._assign_items(a)), self.ui(self.refresh_library)),
                         daemon=True).start()
        self.set_status(msg)

    def restart_current(self):
        if self.player.active:
            threading.Thread(target=lambda: self.player.apply(self._assign_items(), force=True), daemon=True).start()

    # -- Eigener Desktop (Premium)
    def _require_premium(self):
        if self.is_premium:
            return True
        self.set_status("„Eigener Desktop“ ist ein Premium-Feature – ein Administrator kann dein Konto "
                        "unter Einstellungen → Benutzer freischalten.", True)
        return False

    def _desk_cfg(self):
        desk = self.cfg.get("desk")
        if not isinstance(desk, dict):
            desk = dict(DEFAULTS["desk"])
            self.cfg["desk"] = desk
        return desk

    def _desk_changed(self):
        save_config(self.cfg)
        self._desk_preview_async()
        if DESK_ID in self.cfg.get("assign", {}).values():
            threading.Thread(target=lambda: self.player.apply(self._assign_items(), force=True),
                             daemon=True).start()

    def _desk_toggle(self, key, value):
        self._desk_cfg()[key] = bool(value)
        self._desk_changed()

    def _desk_theme(self, label):
        if label not in DESK_THEMES:
            return
        desk = self._desk_cfg()
        desk["bg"] = ""
        desk["theme"] = label
        self._desk_changed()
        self.after(10, self._build_desk_page)

    def _desk_pos(self, label):
        if label in DESK_POS:
            self._desk_cfg()["pos"] = label
            self._desk_changed()

    def _desk_color(self, label):
        if label in DESK_COLORS:
            self._desk_cfg()["color"] = label
            self._desk_changed()

    def _desk_font_choice(self, label):
        if label in DESK_FONTS:
            self._desk_cfg()["font"] = label
            self._desk_changed()

    def _desk_size(self, value):
        size = max(32, min(140, int(float(value))))
        self._desk_cfg()["size"] = size
        lbl = getattr(self, "_desk_size_lbl", None)
        if lbl is not None:
            lbl.configure(text=f"{size} px")
        if getattr(self, "_desk_size_job", None):
            self.after_cancel(self._desk_size_job)
        self._desk_size_job = self.after(350, self._desk_changed)

    def _desk_text(self, value):
        self._desk_cfg()["text"] = " ".join(str(value).split())[:80]
        if getattr(self, "_desk_text_job", None):
            self.after_cancel(self._desk_text_job)
        self._desk_text_job = self.after(450, self._desk_changed)

    def _desk_pick_background(self):
        if not self._require_premium():
            return
        pats = " ".join(f"*{e}" for e in MEDIA_EXT)
        path = filedialog.askopenfilename(title="Hintergrund für deinen Desktop wählen",
                                          filetypes=[("Videos & Bilder", pats), ("Alle Dateien", "*.*")])
        if not path:
            return
        self._desk_cfg()["bg"] = path
        self._desk_changed()
        self.after(10, self._build_desk_page)

    def _desk_clear_background(self):
        self._desk_cfg()["bg"] = ""
        self._desk_changed()
        self.after(10, self._build_desk_page)

    def _desk_pick_library(self):
        if not self._require_premium():
            return
        items = [i for i in self.cfg["items"] if i.get("id") != DESK_ID]
        if not items:
            self.set_status("Deine Bibliothek ist noch leer – füge zuerst ein Wallpaper hinzu.", True)
            return
        dlg = LibraryPickerDialog(self, items)
        dlg.wait_window()
        if dlg.result is None:
            return
        item = dlg.result
        self._desk_cfg()["bg"] = item["src"]
        self._desk_changed()
        if DESK_ID not in self.cfg.get("assign", {}).values():
            self.set_status(f"„{shorten(str(item.get('title') or item['src']), 40)}“ als Hintergrund gewählt – "
                            "„Desktop anwenden“ startet ihn.")
        self.after(10, self._build_desk_page)

    def _update_desk_preview(self, still=None):
        lbl = getattr(self, "_desk_preview", None)
        if lbl is None:
            return
        try:
            img = render_desk_image(self._desk_cfg(), (640, 360), still=still or "")
            self._desk_preview_img = ctk.CTkImage(img, size=(640, 360))
            lbl.configure(image=self._desk_preview_img, text="")
        except Exception:
            lbl.configure(text="Vorschau gerade nicht verfügbar", image=None)

    def _desk_preview_async(self):
        """Vorschau im Hintergrund vorbereiten – Videos brauchen erst ein Standbild."""
        lbl = getattr(self, "_desk_preview", None)
        if lbl is None:
            return
        desk = dict(self._desk_cfg())
        src = desk_background_path(desk)
        if str(src).lower().endswith(IMAGE_EXT) and not re.match(r"https?://", str(src), re.I):
            self._update_desk_preview(src)
            return
        try:
            lbl.configure(image=None, text="Vorschau wird geladen …")
        except Exception:
            pass

        def work():
            still = desk_still_path(desk)
            self.ui(lambda: self._update_desk_preview(still))

        threading.Thread(target=work, daemon=True).start()

    def _build_desk_page(self):
        host = getattr(self, "_desk_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        self._desk_preview = None
        head = ctk.CTkFrame(host, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        title_row = ctk.CTkFrame(head, fg_color="transparent")
        title_row.pack(anchor="w")
        ctk.CTkLabel(title_row, text="Eigener Desktop", font=self._font(28, "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(title_row, text="PREMIUM", font=self._font(9, "bold"), fg_color=ACCENT,
                     text_color=ON_ACCENT, corner_radius=7, height=19, width=66).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(head, text="Hintergrund, Uhr, Datum und eigener Text – dein Desktop, deine Regeln.",
                     font=self._font(12), text_color=MUTED, anchor="w").pack(anchor="w", pady=(3, 0))

        if not self.is_premium:
            box = self._section(host, "Nur mit Premium oder Admin",
                                "Premium-Features sind für Premium-Konten und Administratoren freigeschaltet.")
            if self.guest:
                msg = ("Du bist nicht angemeldet. Melde dich an – ein Administrator kann dein Konto "
                       "anschließend auf Premium stellen.")
            else:
                msg = (f"Das Konto „{self.user.get('name', GAST)}“ ist kein Premium-Konto. Ein Administrator "
                       "kann es unter Einstellungen → Benutzer mit einem Klick freischalten.")
            ctk.CTkLabel(box, text=msg, font=self._font(12), text_color=MUTED, anchor="w", justify="left",
                         wraplength=560).pack(fill="x", padx=20, pady=(0, 10))
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(0, 18))
            if self.guest:
                self._btn(row, "Anmelden", self.login, "primary", width=150, height=38).pack(side="left")
            self._desk_preview = ctk.CTkLabel(box, text="")
            self._desk_preview.pack(padx=20, pady=(0, 18))
            self._desk_preview_async()
            return

        desk = self._desk_cfg()
        bg = self._section(host, "Hintergrund", "Mitgelieferte Motive oder eine eigene Bild-/Videodatei.")
        row = self._row(bg, "Motiv", "Anime, Auto, Natur und Neon sind offline schon dabei.")
        values = list(DESK_THEMES) + (["Eigene Datei"] if desk.get("bg") else [])
        self.desk_theme_menu = ctk.CTkOptionMenu(row, values=values, command=self._desk_theme, width=210,
                                                 **self._menu_style())
        self.desk_theme_menu.set("Eigene Datei" if desk.get("bg") else desk.get("theme", "Anime-Dämmerung"))
        self.desk_theme_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        chosen = desk.get("bg") or ""
        shown = next((i["title"] for i in self.cfg["items"]
                      if i.get("src") == chosen and i.get("id") != DESK_ID), chosen)
        row = self._row(bg, "Eigene Datei",
                        shorten(shown or "Noch keine eigene Datei gewählt.", 70))
        acts = ctk.CTkFrame(row, fg_color="transparent")
        acts.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._btn(acts, "Aus Bibliothek", self._desk_pick_library, "secondary", width=124, height=30,
                  font=self._font(11)).pack(side="left", padx=2)
        self._btn(acts, "Datei wählen", self._desk_pick_background, "secondary", width=114, height=30,
                  font=self._font(11)).pack(side="left", padx=2)
        if desk.get("bg"):
            self._btn(acts, "Entfernen", self._desk_clear_background, "ghost", width=100, height=30,
                      font=self._font(11)).pack(side="left", padx=2)
        self._desk_preview = ctk.CTkLabel(bg, text="")
        self._desk_preview.pack(padx=20, pady=(4, 18))

        ov = self._section(host, "Overlay", "Uhr, Datum und eigener Text – live über dem Hintergrund.")
        self.sw_desk_clock = self._switch_row(ov, "Uhrzeit", "Große Digitaluhr, aktualisiert sich jede Sekunde.",
                                              lambda: self._desk_toggle("clock", bool(self.sw_desk_clock.get())),
                                              desk.get("clock", True))
        self.sw_desk_date = self._switch_row(ov, "Datum", "Wochentag und Datum passend zur Uhr.",
                                             lambda: self._desk_toggle("date", bool(self.sw_desk_date.get())),
                                             desk.get("date", True))
        row = self._row(ov, "Eigener Text", "z. B. dein Name, ein Zitat oder „Fokus“.")
        self.desk_text_var = ctk.StringVar(value=desk.get("text", ""))
        ctk.CTkEntry(row, textvariable=self.desk_text_var, width=260, height=34, corner_radius=BTN_RADIUS,
                     fg_color=SURFACE2, border_color=BORDER, border_width=1, text_color=TEXT,
                     font=self._font(12), placeholder_text="Optional").grid(row=0, column=1, sticky="e",
                                                                             padx=(16, 0))
        self.desk_text_var.trace_add("write", lambda *_: self._desk_text(self.desk_text_var.get()))
        row = self._row(ov, "Position", "Ecke oder untere Mitte – frei wählbar.")
        self.desk_pos_menu = ctk.CTkOptionMenu(row, values=list(DESK_POS), command=self._desk_pos, width=210,
                                               **self._menu_style())
        self.desk_pos_menu.set(desk.get("pos", "Unten links"))
        self.desk_pos_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(ov, "Farbe", "Schrift- und Uhrfarbe.")
        self.desk_color_menu = ctk.CTkOptionMenu(row, values=list(DESK_COLORS), command=self._desk_color,
                                                 width=210, **self._menu_style())
        self.desk_color_menu.set(desk.get("color", "Weiß"))
        self.desk_color_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(ov, "Schriftart", "Gilt für Uhr, Datum und Text – Auswahl aus vielen Windows-Schriften.")
        self.desk_font_menu = ctk.CTkOptionMenu(row, values=list(DESK_FONTS), command=self._desk_font_choice,
                                                width=210, **self._menu_style())
        self.desk_font_menu.set(desk.get("font", "Segoe UI"))
        self.desk_font_menu.grid(row=0, column=1, sticky="e", padx=(16, 0))
        row = self._row(ov, "Schriftgröße", "Größe der Uhr in Pixel (für 1080p).")
        srow = ctk.CTkFrame(row, fg_color="transparent")
        srow.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._desk_size_lbl = ctk.CTkLabel(srow, text=f"{int(desk.get('size', 72))} px", font=self._font(12),
                                           text_color=MUTED, width=52, anchor="e")
        self._desk_size_lbl.pack(side="right", padx=(8, 0))
        ctk.CTkSlider(srow, from_=32, to=140, number_of_steps=108, command=self._desk_size, width=150,
                      button_color=ACCENT, button_hover_color=ACCENT_HOVER, progress_color=ACCENT,
                      fg_color=BORDER).pack(side="right")

        acts = ctk.CTkFrame(host, fg_color="transparent")
        acts.pack(fill="x", pady=(2, 10))
        self._btn(acts, "Desktop anwenden", self.apply_desk, "primary", width=200, height=40).pack(side="left")
        self._btn(acts, "Als Wallpaper speichern", self.export_desk, "secondary", width=210, height=40).pack(
            side="left", padx=8)
        if DESK_ID in self.cfg.get("assign", {}).values():
            self._btn(acts, "Beenden", self.stop_desk, "ghost", width=120, height=40).pack(side="left")
        ctk.CTkLabel(host, text="Tipp: „Als Wallpaper speichern“ legt ein fertiges Bild mit Uhr und Text "
                                "in deiner Bibliothek ab.", font=self._font(11), text_color=MUTED,
                     anchor="w").pack(fill="x", pady=(0, 12))
        self._desk_preview_async()

    def apply_desk(self):
        if not self._require_premium():
            return
        src = desk_background_path(self._desk_cfg())
        item = self.find_item(DESK_ID)
        if item is None:
            item = {"id": DESK_ID, "title": "Mein Desktop", "kind": "local", "src": src,
                    "added": time.time(), "plays": 0}
            self.cfg["items"].append(item)
        item.update({"src": src, "kind": detect_kind(src), "title": "Mein Desktop"})
        save_config(self.cfg)
        threading.Thread(target=lambda: (make_local_thumb(DESK_ID, src), self.ui(self.refresh_library)),
                         daemon=True).start()
        self.apply(item)

    def stop_desk(self):
        a = {k: v for k, v in self.cfg.get("assign", {}).items() if v != DESK_ID}
        self.cfg["assign"] = a
        save_config(self.cfg)
        threading.Thread(target=lambda: (self.player.apply(self._assign_items(a)),
                                         self.ui(self.refresh_library)), daemon=True).start()
        self.set_status("Eigener Desktop beendet.")
        self.after(10, self._build_desk_page)

    def export_desk(self):
        if not self._require_premium():
            return
        desk = dict(self._desk_cfg())
        title = "Mein Desktop " + time.strftime("%d.%m. %H-%M")
        path = LIB_DIR / f"{title}.png"
        self.set_status("Erstelle Wallpaper …")

        def work():
            try:
                render_desk_image(desk, (1920, 1080)).save(path)
            except Exception as e:
                msg = f"Wallpaper ließ sich nicht erstellen: {e}"
                self.ui(lambda: self.set_status(msg, True))
                return

            def done():
                item = {"id": uuid.uuid4().hex[:10], "title": title, "kind": "local", "src": str(path),
                        "added": time.time(), "plays": 0}
                self.cfg["items"].append(item)
                save_config(self.cfg)
                threading.Thread(target=lambda: (make_local_thumb(item["id"], item["src"]),
                                                 self.ui(self.refresh_library)), daemon=True).start()
                self.set_status(f"Wallpaper „{title}“ gespeichert – es liegt jetzt in der Bibliothek.")
                self.toast("Wallpaper gespeichert")

            self.ui(done)

        threading.Thread(target=work, daemon=True).start()

    def next_wallpaper(self):
        items = self._playlist()
        if not items:
            items = self.cfg["items"]
        if not items:
            return
        idxs = self._target_indices()
        ids = [i["id"] for i in items]
        cur = self.cfg.get("assign", {}).get(str(idxs[0])) if idxs else None
        self.apply(items[(ids.index(cur) + 1) % len(items)] if cur in ids else items[0])

    def toggle_pause(self):
        if not self.player.active:
            self.set_status("Kein Wallpaper aktiv – zuerst eines anwenden.", True)
            return
        self.player.set_manual_pause(not self.player.paused_manual)
        self.btn_pause.configure(text="Weiter" if self.player.paused_manual else "Pause")
        self.set_status("Pausiert." if self.player.paused_manual else "Läuft weiter.")

    # -- Download
    def download(self, item):
        if item["id"] in self._downloads:
            self.set_status("Für dieses Wallpaper läuft schon ein Download.", True)
            return
        self._downloads.add(item["id"])
        self.set_status(f"Lade „{shorten(item['title'], 40)}“ herunter …")
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(7, 0))
        threading.Thread(target=self._download_worker, args=(item,), daemon=True).start()

    def _download_worker(self, item):
        try:
            try:
                path = download_item(item, self.cfg["quality"],
                                     lambda p: self.ui(lambda: self.progress.set(p / 100)))
            except Exception as e:
                msg = f"Download fehlgeschlagen: {e}"
                self.ui(lambda: (self.set_status(msg, True), self.progress.set(0),
                                 self.progress.pack_forget()))
                return
            item["origin"] = item["src"]
            item["kind"], item["src"] = "local", str(path)
            save_config(self.cfg)
            if not (THUMB_DIR / f"{item['id']}.jpg").exists():
                make_local_thumb(item["id"], path)
            self.ui(lambda: (self.progress.pack_forget(),
                             self.set_status(f"Heruntergeladen: {path.name} (offline nutzbar)"),
                             self.toast("⬇  Download fertig – jetzt offline nutzbar"),
                             self.refresh_library()))
        finally:
            self._downloads.discard(item["id"])

    # -- Monitor-Auswahl mit Vorschau
    def _monitor_preview(self):
        """Kleine Karte aller Monitore mit dem jeweiligen Wallpaper-Vorschaubild. -> (Bild, [Rechtecke])"""
        PW, PH, M = 400, 200, 10
        img = Image.new("RGB", (PW, PH), (28, 32, 40))   # wie SURFACE2, damit es mit dem Panel verschmilzt
        mons = get_monitors()
        if not mons:
            return img, []
        l = min(m["rect"][0] for m in mons)
        t = min(m["rect"][1] for m in mons)
        r = max(m["rect"][0] + m["rect"][2] for m in mons)
        b = max(m["rect"][1] + m["rect"][3] for m in mons)
        sc = min((PW - 2 * M) / max(1, r - l), (PH - 2 * M) / max(1, b - t))
        ox, oy = (PW - (r - l) * sc) / 2, (PH - (b - t) * sc) / 2
        assign = self._assign_items()
        targets = self._target_indices()
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("segoeuib.ttf", 24)
        except Exception:
            try:
                font = ImageFont.truetype("arialbd.ttf", 24)
            except Exception:
                font = ImageFont.load_default()
        rects = []
        for i, m in enumerate(mons):
            x, y, w, h = m["rect"]
            x0, y0 = int(ox + (x - l) * sc), int(oy + (y - t) * sc)
            x1, y1 = x0 + max(24, int(w * sc)), y0 + max(24, int(h * sc))
            rects.append((x0, y0, x1, y1))
            rad = 10
            item = assign.get(i)
            if item:
                p = THUMB_DIR / f"{item['id']}.jpg"
                try:
                    thumb = Image.open(p).convert("RGB") if p.exists() else placeholder()
                except Exception:
                    thumb = placeholder()
                mask = Image.new("L", (x1 - x0, y1 - y0), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius=rad, fill=255)
                img.paste(ImageOps.fit(thumb, (x1 - x0, y1 - y0)), (x0, y0), mask)
            else:
                d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=rad, fill=(44, 49, 58))
            chosen = i in targets
            d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=rad,
                                outline=(76, 194, 255) if chosen else (74, 80, 92), width=4 if chosen else 2)
            d.ellipse((x0 + 8, y0 + 8, x0 + 38, y0 + 38), fill=(13, 15, 19))
            try:
                d.text((x0 + 23, y0 + 23), str(i + 1), fill=(255, 255, 255), font=font, anchor="mm")
            except Exception:
                d.text((x0 + 18, y0 + 14), str(i + 1), fill=(255, 255, 255), font=font)
        return img, rects

    def _refresh_monitor_ui(self):
        img, rects = self._monitor_preview()
        self._mon_rects = rects
        self._mon_img = ctk.CTkImage(img, size=(196, 98))
        self.mon_preview.configure(image=self._mon_img)
        mons = get_monitors()
        sel = str(self.cfg.get("monitor", "all"))
        single = sel.isdigit() and int(sel) < len(mons)
        if single:
            i = int(sel)
            self.mon_hint.configure(text=f"Ziel: Monitor {i + 1}" + (" (Haupt)" if mons[i]["primary"] else ""))
            self.btn_stop.configure(text=f"■  Monitor {i + 1} stoppen")
            self.btn_all.configure(fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT, border_color=BORDER)
        else:
            self.mon_hint.configure(text="Ziel: Alle Monitore")
            self.btn_stop.configure(text="■  Alle stoppen")
            self.btn_all.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                                   border_color=ACCENT)

    def _on_preview_click(self, e):
        try:
            ww, hh = max(1, e.widget.winfo_width()), max(1, e.widget.winfo_height())
            x, y = e.x / ww * 400, e.y / hh * 200
        except Exception:
            return
        for i, (x0, y0, x1, y1) in enumerate(self._mon_rects):
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.select_monitor(str(i))
                return

    def select_monitor(self, sel):
        self.cfg["monitor"] = sel
        save_config(self.cfg)
        self.refresh_library()

    # -- Updates (GitHub)
    def _auto_check(self):
        if self.cfg.get("auto_update", True):
            threading.Thread(target=self._update_worker, args=(False,), daemon=True).start()
        self.after(6 * 3600 * 1000, self._auto_check)

    def check_updates(self, manual=True):
        self.set_status("Suche nach Updates …")
        threading.Thread(target=self._update_worker, args=(manual,), daemon=True).start()

    def _update_worker(self, manual):
        if not self._update_lock.acquire(blocking=False):
            if manual:
                self.ui(lambda: self.set_status("Eine Update-Prüfung läuft bereits.", True))
            return
        try:
            self._check_update(manual)
        finally:
            self._update_lock.release()

    def _check_update(self, manual):
        def say(text, error=False):
            if manual:
                self.ui(lambda: self.set_status(text, error))

        repo = (self.cfg.get("update_repo") or GITHUB_REPO).strip()
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or repo.startswith("DEIN-"):
            say("Update-Quelle nicht eingestellt: in wallura.py GITHUB_REPO auf „name/repo“ setzen.", True)
            return
        try:
            info = check_update(repo)
        except Exception as e:
            say(f"Update-Suche fehlgeschlagen: {e}", True)
            return
        if not info:
            say(f"Du hast die neueste Version (v{APP_VERSION}).")
            return
        self.update_info = info
        if not getattr(sys, "frozen", False):
            say(f"Neue Version v{info['version']} verfügbar (Quellcode-Modus: Installer neu bauen).")
            return
        if not (manual or self.cfg.get("auto_update", True)):
            return
        self.ui(lambda: self.set_status(f"Lade Update v{info['version']} …"))
        try:
            path = download_update(info, lambda p: self.ui(lambda: self.progress.set(p / 100)))
        except Exception as e:
            msg = f"Update-Download fehlgeschlagen: {e}"
            self.ui(lambda: (self.set_status(msg, True), self.progress.set(0)))
            return
        self.ui(lambda: (self.progress.set(1), self._show_update_bar(info, path)))

    def _show_update_bar(self, info, path):
        self.update_file = path
        self.upd_label.configure(text=f"Update v{info['version']} ist bereit.")
        self.upd_btn.configure(text="Jetzt installieren", command=self.install_update)
        self.upd_frame.pack(fill="x", padx=6, pady=(0, 8))
        self.set_status(f"Update v{info['version']} heruntergeladen.")
        self._show_update_toast(info)

    def _show_update_toast(self, info):
        """Kleiner Hinweis unten rechts (auch bei verstecktem Hauptfenster): Update ist geladen, Nutzer bestätigt."""
        ver = info["version"]
        if getattr(self, "_toast_ver", None) == ver:
            return  # pro Version nur einmal pro Sitzung
        try:
            if fullscreen_app_active():  # nicht in Spiele / Vollbild-Apps hineinplatzen
                self.after(60000, lambda: self._show_update_toast(info))
                return
        except Exception:
            pass
        self._toast_ver = ver
        import tkinter
        t = ctk.CTkToplevel(self)
        t.withdraw()
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(fg_color=SURFACE)
        box = ctk.CTkFrame(t, width=380, height=156, corner_radius=0, fg_color=SURFACE,
                           border_width=1, border_color=ACCENT_DIM)
        box.pack_propagate(False)
        box.pack()
        ctk.CTkLabel(box, text=f"Wallura {ver} ist bereit", font=self._font(16, "bold"), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        ctk.CTkLabel(box, text="Das Update ist heruntergeladen. Nach der Installation startet Wallura "
                               "von selbst neu.", font=self._font(12), text_color=MUTED, anchor="w",
                     justify="left", wraplength=340).pack(fill="x", padx=18)
        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=18, pady=(0, 16))

        def close():
            try:
                t.destroy()
            except Exception:
                pass

        def install():
            close()
            self.install_update()

        self._btn(btns, "Jetzt installieren", install, "primary", height=34, width=150).pack(side="left")
        self._btn(btns, "Später", close, "ghost", height=34, width=80).pack(side="left", padx=(8, 0))

        t.update_idletasks()
        w, h = t.winfo_reqwidth(), t.winfo_reqheight()
        try:
            mon = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
            work = win32api.GetMonitorInfo(mon)["Work"]
            right, bottom = work[2], work[3]
        except Exception:
            right, bottom = t.winfo_screenwidth(), t.winfo_screenheight()
        margin = 16
        tkinter.Wm.geometry(t, f"{w}x{h}+{right - w - margin}+{bottom - h - margin}")
        t.deiconify()
        t.attributes("-topmost", True)

    def install_update(self):
        path = self.update_file
        if not path or not Path(path).exists():
            return
        self.set_status("Installiere Update – Wallura startet danach neu …")
        try:
            subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                             creationflags=0x00000008 | 0x00000200, close_fds=True)
        except Exception as e:
            self.set_status(f"Update-Installer ließ sich nicht starten: {e}", True)
            return
        self.after(800, self.quit_app)

    def on_auto_update(self):
        self.cfg["auto_update"] = bool(self.sw_upd.get())
        save_config(self.cfg)

    # -- Einstellungen
    def on_volume(self, v):
        vol = max(0, min(100, int(round(float(v)))))
        old = int(self.cfg.get("volume", 0) or 0)
        self.vol_lbl.configure(text=f"{vol} %")
        self.cfg["volume"] = vol
        self.player.set_volume(vol)
        if (old == 0) != (vol == 0):  # stumm <-> mit Ton: Audiospur neu laden/abschalten
            self.restart_current()
        if self._volume_job is not None:  # nicht bei jedem Pixel der Leiste auf die Platte schreiben
            self.after_cancel(self._volume_job)
        self._volume_job = self.after(400, self._save_volume)

    def _save_volume(self):
        self._volume_job = None
        save_config(self.cfg)

    def on_fit(self, label):
        self.cfg["fit"] = FIT_MAP[label]
        save_config(self.cfg)
        self.restart_current()

    def on_fps(self, label):
        self.cfg["fps_limit"] = FPS_MAP[label]
        save_config(self.cfg)
        self.restart_current()

    def on_quality(self, q):
        self.cfg["quality"] = q
        save_config(self.cfg)
        self.set_status("Qualität gilt ab dem nächsten Start / Download.")

    def on_pause_fs(self):
        self.cfg["pause_fullscreen"] = bool(self.sw_pause.get())
        save_config(self.cfg)

    def on_autostart(self):
        on = bool(self.sw_auto.get())
        try:
            set_autostart(on)
            self.cfg["autostart"] = on
            save_config(self.cfg)
        except Exception as e:
            self.set_status(f"Autostart ging nicht: {e}", True)

    def on_install_tools(self):
        def work():
            msg = install_tools(lambda s: self.ui(lambda: self.set_status(s)))
            self.ui(lambda: (self.set_status(msg), self._update_tools_banner()))
        threading.Thread(target=work, daemon=True).start()

    # -- Status
    def set_status(self, text, error=False):
        self.status.configure(text=text, text_color=STATUS_ERR if error else STATUS_OK)

    def toast(self, text, error=False):
        """Kurzer Hinweis unten rechts im Fenster (verschwindet von selbst)."""
        old = getattr(self, "_toast", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        try:
            t = ctk.CTkToplevel(self)
            t.withdraw()
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            frame = ctk.CTkFrame(t, corner_radius=14, fg_color=SURFACE2, border_width=1,
                                 border_color="#5a2a2e" if error else BORDER)
            frame.pack()
            ctk.CTkLabel(frame, text=text, font=self._font(12), text_color=STATUS_ERR if error else TEXT,
                         anchor="w", justify="left", wraplength=320).pack(padx=16, pady=12)
            t.update_idletasks()
            w, h = t.winfo_reqwidth(), t.winfo_reqheight()
            x = self.winfo_rootx() + max(0, self.winfo_width() - w - 28)
            y = self.winfo_rooty() + max(0, self.winfo_height() - h - 28)
            t.geometry(f"{w}x{h}+{x}+{y}")
            t.deiconify()
            self._toast = t
            self.after(3600, lambda: self._hide_toast(t))
        except Exception:
            pass

    def _hide_toast(self, t):
        try:
            if getattr(self, "_toast", None) is t:
                self._toast = None
            t.destroy()
        except Exception:
            pass

    def _update_tools_banner(self):
        found = {n: bool(find_tool(n)) for n in ("mpv", "yt-dlp")}
        missing = [n for n, ok in found.items() if not ok]
        if missing:
            self.banner.configure(text="Fehlt noch: " + ", ".join(missing))
            self.banner_frame.pack(fill="x", pady=(0, 8))
        else:
            self.banner_frame.pack_forget()
        if self.tools_desc is not None:
            self.tools_desc.configure(text="  ·  ".join(f"{n}: {'gefunden' if ok else 'fehlt'}" for n, ok in found.items()))

    def open_data_dir(self):
        try:
            os.startfile(str(DATA_DIR))
        except Exception as e:
            self.set_status(f"Ordner ließ sich nicht öffnen: {e}", True)

    # -- Konto & Benutzer
    def _form(self, title, fields, subtitle=None, ok_text="Speichern"):
        d = FormDialog(self, title, fields, subtitle, ok_text)
        d.wait_window()
        return d.result

    def login(self):
        """Anmelden im laufenden Fenster – laufende Wallpaper und Bibliothek bleiben erhalten."""
        if not self.guest or self._login_open or self._closing:
            return
        self.show_window()
        self._login_open = True
        try:
            dlg = LoginDialog(self)
            dlg.wait_window()
            res = dlg.result
        finally:
            self._login_open = False
        if not res:
            return
        self.user = {"name": res["name"], "role": res.get("role", "user"),
                     "premium": bool(res.get("premium"))}
        self.guest = False
        self.acc = load_accounts()
        remembered = bool(res.get("remember")) and save_session(res["name"], True)
        self._rebuild_ui()
        self.set_status(f"Angemeldet als {res['name']}."
                        + (" Angemeldet bleiben ist aktiv." if remembered else ""))

    def logout(self):
        """Zurück in den Gastmodus – Wallpaper laufen weiter."""
        if self.guest or self._closing:
            return
        clear_session()
        self.user = {"name": GAST, "role": "user"}
        self.guest = True
        self.acc = load_accounts()
        self._rebuild_ui()
        self.set_status("Abgemeldet – Wallpaper laufen weiter.")

    def _rebuild_ui(self):
        """Oberfläche neu aufbauen (Adminbereiche erscheinen/verschwinden), ohne den Player anzufassen."""
        page = getattr(self, "_page", "library")
        for job in (self._volume_job, self._search_job, self._resize_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._volume_job = self._search_job = self._resize_job = None
        self.tools_desc = None  # Zeigt sonst auf ein bereits zerstörtes Label
        for w in self.winfo_children():
            w.destroy()
        self._last_cols = 0
        self._prev_cols = 0
        self._build_ui()
        self.refresh_library()
        self._update_tools_banner()
        self._update_title()
        self.btn_pause.configure(text="Weiter" if self.player.paused_manual else "Pause")
        self._show_page(page if page in self._pages else "library")
        if self.update_file and self.update_info:
            self._show_update_bar(self.update_info, self.update_file)

    def change_password(self):
        name = self.user.get("name", GAST)

        def check(values):
            user = find_account(load_accounts(), name)
            if not user or not _password_ok(values.get("old", ""), user.get("pw")):
                return "Das aktuelle Passwort ist falsch."
            if len(values.get("new", "")) < MIN_PW_LEN:
                return f"Das neue Passwort braucht mindestens {MIN_PW_LEN} Zeichen."
            if values.get("new") != values.get("new2"):
                return "Die neuen Passwörter sind nicht gleich."
            return None

        dlg = PasswordDialog(self, "Passwort ändern",
                             "Bestätige zuerst dein aktuelles Passwort und lege dann ein neues fest.",
                             [{"key": "old", "label": "Aktuelles Passwort"},
                              {"key": "new", "label": "Neues Passwort"},
                              {"key": "new2", "label": "Neues Passwort wiederholen"}],
                             "Passwort speichern", check)
        dlg.wait_window()
        res = dlg.result
        if res is None:
            return
        self.acc = load_accounts()
        ok, err = set_password(self.acc, name, res["new"])
        self.set_status("Passwort geändert." if ok else err, not ok)
        if ok:
            save_session(name, True)
            self.toast("Passwort geändert")

    def add_user(self):
        if not self._require_admin():
            return
        res = self._form("Neues Konto", [
            {"key": "name", "label": "Benutzername", "type": "text"},
            {"key": "pw", "label": "Passwort", "type": "pw"},
            {"key": "role", "label": "Rolle", "type": "menu",
             "values": [ROLES["user"], ROLES["admin"]], "value": ROLES["user"]},
        ], "Das Konto kann sich ab sofort bei Wallura anmelden.", "Konto anlegen")
        if res is None:
            return
        role = "admin" if res["role"] == ROLES["admin"] else "user"
        self.acc = load_accounts()
        ok, err = create_account(self.acc, res["name"], res["pw"], role)
        self.set_status(f"Konto „{res['name'].strip()}“ angelegt." if ok else err, not ok)
        if ok:
            report_account_async(res["name"].strip())
        self._refresh_users()

    def reset_user_password(self, key):
        if not self._require_admin():
            return
        self.acc = load_accounts()
        user = self.acc["users"].get(key)
        if not user:
            return
        def check(values):
            if len(values.get("pw", "")) < MIN_PW_LEN:
                return f"Das Passwort braucht mindestens {MIN_PW_LEN} Zeichen."
            if values.get("pw") != values.get("pw2"):
                return "Die Passwörter sind nicht gleich."
            return None

        dlg = PasswordDialog(self, "Passwort zurücksetzen",
                             f"Neues Passwort für „{user.get('name', key)}“.",
                             [{"key": "pw", "label": "Neues Passwort"},
                              {"key": "pw2", "label": "Neues Passwort wiederholen"}],
                             "Speichern", check)
        dlg.wait_window()
        res = dlg.result
        if res is None:
            return
        ok, err = set_password(self.acc, key, res["pw"])
        self.set_status("Passwort geändert." if ok else err, not ok)

    def toggle_role(self, key):
        if not self._require_admin():
            return
        if key == str(self.user.get("name", "")).lower():
            self.set_status("Die eigene Rolle lässt sich nicht ändern.", True)
            return
        self.acc = load_accounts()
        user = self.acc["users"].get(key)
        if not user:
            return
        new_role = "user" if user.get("role") == "admin" else "admin"
        ok, err = set_role(self.acc, key, new_role)
        self.set_status(f"„{user.get('name', key)}“ ist jetzt {ROLES[new_role]}." if ok else err, not ok)
        self._refresh_users()

    def toggle_premium(self, key):
        if not self._require_admin():
            return
        self.acc = load_accounts()
        user = self.acc["users"].get(key)
        if not user:
            return
        on = not bool(user.get("premium"))
        ok, err = set_premium(self.acc, key, on)
        name = user.get("name", key)
        self.set_status(f"„{name}“ ist jetzt Premium." if ok else err, not ok)
        self._refresh_users()
        if getattr(self, "_page", "") == "desk":
            self._build_desk_page()

    def remove_user(self, key):
        if not self._require_admin():
            return
        if key == str(self.user.get("name", "")).lower():
            self.set_status("Das eigene Konto lässt sich nicht löschen.", True)
            return
        self.acc = load_accounts()
        user = self.acc["users"].get(key)
        if not user:
            return
        if self._form("Konto löschen", [],
                      f"„{user.get('name', key)}“ endgültig löschen? Das Konto kann sich danach nicht "
                      "mehr anmelden.", "Löschen") is None:
            return
        ok, err = delete_account(self.acc, key)
        self.set_status(f"Konto „{user.get('name', key)}“ gelöscht." if ok else err, not ok)
        self._refresh_users()

    def _refresh_users(self):
        if not self.is_admin:
            return
        for w in self._user_rows.winfo_children():
            w.destroy()
        self.acc = load_accounts()
        own = str(self.user.get("name", "")).lower()

        def by_name(kv):
            return str(kv[1].get("name") or kv[0]).lower()

        for key, user in sorted(self.acc["users"].items(), key=by_name):
            name = str(user.get("name") or key)
            row = ctk.CTkFrame(self._user_rows, fg_color=SURFACE2, corner_radius=12,
                               border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(0, weight=1)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=0, sticky="w", padx=14, pady=8)
            ctk.CTkLabel(info, text=name + ("  (du)" if key == own else ""),
                         font=self._font(13, "bold"), text_color=TEXT, anchor="w").pack(anchor="w")
            meta = ctk.CTkFrame(info, fg_color="transparent")
            meta.pack(anchor="w")
            ctk.CTkLabel(meta, text=ROLES.get(user.get("role"), "Nutzer"), font=self._font(11),
                         text_color=ACCENT if user.get("role") == "admin" else MUTED,
                         anchor="w").pack(side="left")
            if user.get("premium") or user.get("role") == "admin":
                ctk.CTkLabel(meta, text="PREMIUM", font=self._font(9, "bold"), fg_color=ACCENT,
                             text_color=ON_ACCENT, corner_radius=6, height=16, width=62).pack(
                    side="left", padx=(8, 0))
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=1, sticky="e", padx=10, pady=8)
            role_text = "Zum Nutzer" if user.get("role") == "admin" else "Zum Admin"
            self._btn(btns, role_text, lambda k=key: self.toggle_role(k), "ghost", width=104, height=28,
                      font=self._font(11)).pack(side="left", padx=2)
            if user.get("role") != "admin":  # Admins sind immer Premium
                self._btn(btns, "Kein Premium" if user.get("premium") else "Premium",
                          lambda k=key: self.toggle_premium(k), "ghost", width=104, height=28,
                          font=self._font(11)).pack(side="left", padx=2)
            self._btn(btns, "Passwort", lambda k=key: self.reset_user_password(k), "ghost", width=88,
                      height=28, font=self._font(11)).pack(side="left", padx=2)
            self._btn(btns, "Löschen", lambda k=key: self.remove_user(k), "danger", width=84, height=28,
                      font=self._font(11)).pack(side="left", padx=2)

    # -- Konten auf allen PCs
    def refresh_cloud(self):
        if not self.is_admin:
            return
        token = self.cfg.get("cloud_token") or ""
        if not token:
            self._cloud_unlock.grid(row=0, column=2, sticky="e", padx=(8, 0))
            self._cloud_status.configure(text="Noch nicht freigeschaltet: einmal das Passwort dieses "
                                              "Administratorkontos eingeben, danach bleibt die Übersicht offen.")
            return
        self._cloud_unlock.grid_remove()
        self._cloud_status.configure(text="Lade Konten …")

        def work():
            try:
                accounts = fetch_cloud_accounts(token)
            except Exception as e:
                msg = cloud_error_text(e, "Kontenliste nicht abrufbar")
                self.ui(lambda: self._cloud_status.configure(text=msg))
                return
            self.ui(lambda: self._render_cloud(accounts))

        threading.Thread(target=work, daemon=True).start()

    def unlock_cloud(self):
        """Übersicht einmalig mit dem Passwort des Administratorkontos freischalten."""
        if not self._require_admin():
            return
        name = self.user.get("name", GAST)

        def check(values):
            user = find_account(load_accounts(), name)
            if not user or not _password_ok(values.get("pw", ""), user.get("pw")):
                return "Das Passwort ist falsch. Bitte noch einmal eingeben."
            return None

        dlg = PasswordDialog(self, "Konten-Übersicht freischalten",
                             "Nur der Administrator sieht die Konten aller PCs. Das Passwort wird nur "
                             "auf diesem PC geprüft und nicht gespeichert.",
                             [{"key": "pw", "label": f"Passwort von „{name}“"}],
                             "Freischalten", check)
        dlg.wait_window()
        res = dlg.result
        if res is None:
            return
        token = secrets.token_urlsafe(32)
        ok, err = claim_cloud(token)
        if not ok:
            self.set_status(err, True)
            self._cloud_status.configure(text=err)
            return
        self.cfg["cloud_token"] = token
        save_config(self.cfg)
        self.set_status("Konten-Übersicht freigeschaltet.")
        self.toast("Konten-Übersicht freigeschaltet")
        self.refresh_cloud()

    def _render_cloud(self, accounts):
        for w in self._cloud_rows.winfo_children():
            w.destroy()
        if not accounts:
            self._cloud_status.configure(text="Noch keine Konten gemeldet.")
            return
        self._cloud_unlock.grid_remove()
        self._cloud_status.configure(text=f"{len(accounts)} Konto/Konten gemeldet "
                                           "(zuletzt aktive zuerst).")
        for acc in accounts:
            row = ctk.CTkFrame(self._cloud_rows, fg_color=SURFACE2, corner_radius=12,
                               border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=3)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(fill="x", padx=14, pady=8)
            ctk.CTkLabel(info, text=str(acc.get("name") or "?"), font=self._font(13, "bold"),
                         text_color=TEXT, anchor="w").pack(anchor="w")
            parts = [str(acc.get("platform") or ""), str(acc.get("device") or "")]
            try:
                parts.append("zuletzt " + time.strftime("%d.%m.%Y %H:%M",
                                                         time.localtime(int(acc.get("last_seen") or 0))))
            except (TypeError, ValueError, OSError):
                pass
            ctk.CTkLabel(info, text="  ·  ".join(p for p in parts if p), font=self._font(11),
                         text_color=MUTED, anchor="w").pack(anchor="w")

    # -- Tray
    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Wallura öffnen", lambda: self.ui(self.show_window), default=True),
            pystray.MenuItem(lambda item: "Anmelden" if self.guest else "Abmelden",
                             lambda: self.ui(self.login if self.guest else self.logout)),
            pystray.MenuItem(lambda item: "Fortsetzen" if self.player.paused_manual else "Pause",
                             lambda: self.ui(self.toggle_pause)),
            pystray.MenuItem(lambda item: f"Update v{(self.update_info or {}).get('version', '')} installieren",
                             lambda: self.ui(self.install_update),
                             visible=lambda item: bool(self.update_file)),
            pystray.MenuItem("Nächstes Wallpaper", lambda: self.ui(self.next_wallpaper)),
            pystray.MenuItem("★ Nächstes Favorit", lambda: self.ui(self.rotate_favorite)),
            pystray.MenuItem("🎲 Zufälliges Wallpaper", lambda: self.ui(self.random_wallpaper)),
            pystray.MenuItem("Wallpaper stoppen", lambda: self.ui(self.stop_wallpaper)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", lambda: self.ui(self.quit_app)),
        )
        self.tray = pystray.Icon(APP_NAME, make_icon(), "Wallura", menu)
        self.tray.run_detached()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_to_tray(self):
        if self.tray is None:
            self.quit_app()  # kein Tray-Symbol -> sonst wäre das Fenster nicht mehr erreichbar
        else:
            self.withdraw()

    def quit_app(self):
        if self._closing:
            return
        self._closing = True
        self.player.shutdown()
        try:
            self.tray.stop()
        except Exception:
            pass
        self.destroy()


def main():
    mutex = win32event.CreateMutex(None, False, "Local\\Wallura_SingleInstance")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    migrate_autostart()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    start_hidden = "--minimized" in sys.argv
    # Kein Pflicht-Login mehr: gemerkte Sitzung („Angemeldet bleiben“) oder Gastmodus mit „Anmelden“-Button.
    app = App(session=load_session(), start_hidden=start_hidden)
    app.mainloop()
    del mutex


if __name__ == "__main__":
    main()