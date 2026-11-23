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
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import winreg
from pathlib import Path
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
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ----------------------------------------------------------------------------- Pfade
APP_NAME = "Wallura"
COPYRIGHT = "© 2026 MorreTv. Open Source (MIT)"
APP_VERSION = "1.1.0"   # wird vom Build / GitHub-Workflow aus dem Release-Tag gesetzt
# GitHub-Repo für automatische Updates ("benutzername/repo"). Dort muss pro Version ein Release
# mit der Datei Wallura-Setup.exe liegen (Repo bzw. Releases müssen öffentlich sein).
GITHUB_REPO = "MorreTv/Wallura"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
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
TOOLS_USER = DATA_DIR / "tools"
TOOLS_APP = APP_DIR / "tools"
UPDATE_DIR = DATA_DIR / "update"
CONFIG_FILE = DATA_DIR / "config.json"
for _d in (DATA_DIR, LIB_DIR, THUMB_DIR, TOOLS_USER, UPDATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CREATE_NO_WINDOW = 0x08000000
ACCENT = "#4cc2ff"
ACCENT_HOVER = "#79d2ff"
ACCENT_DIM = "#2d7fa8"
ON_ACCENT = "#06202e"
BG = "#0d0f13"
SURFACE = "#15181e"
SURFACE2 = "#1c2028"
BORDER = "#2a303a"
TEXT = "#e9edf2"
MUTED = "#8a93a2"
DANGER_TEXT = "#ff8a8e"
FONT = "Segoe UI"
STATUS_OK = "#c3cad5"
STATUS_ERR = "#ff7b7b"
SIDEBAR_W = 300
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Wallura"}

VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".gif")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MEDIA_EXT = VIDEO_EXT + IMAGE_EXT
YT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.I)
YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")

FIT_MAP = {"Füllen (zuschneiden)": "cover", "Einpassen (Balken)": "contain", "Strecken": "stretch"}
QUALITIES = ["720", "1080", "1440", "2160"]
FPS_MAP = {"Original": 0, "60 FPS": 60, "30 FPS": 30}
BELOW_NORMAL_PRIORITY = 0x00004000
KIND_LABEL = {"local": "Lokal", "youtube": "YouTube", "web": "Web"}

DEFAULTS = {
    "items": [],
    "current": None,      # alt (vor 1.1) – wird zu "assign" migriert
    "assign": {},         # Monitor-Index (als Text) -> Wallpaper-ID
    "volume": 0,
    "fit": "cover",
    "monitor": "all",
    "quality": "1080",
    "fps_limit": 30,
    "pause_fullscreen": True,
    "autostart": False,
    "auto_update": True,
    "update_repo": "",    # optional: überschreibt GITHUB_REPO
}


# ----------------------------------------------------------------------------- Config
def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    if DATA_DIR.exists() and not _OLD_DIR.exists():  # Pfade heruntergeladener Dateien auf den neuen Ordner umbiegen
        old = str(_OLD_DIR)
        for it in cfg.get("items", []):
            if isinstance(it.get("src"), str) and it["src"].startswith(old):
                it["src"] = str(DATA_DIR) + it["src"][len(old):]
    return cfg


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


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
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r, open(tmp, "wb") as f:
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
        return dest

    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp fehlt – bitte links auf „Tools installieren“ klicken.")
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
        raise RuntimeError(last or "Download fehlgeschlagen")
    return max(files, key=lambda p: p.stat().st_mtime)


def install_tools(say):
    """yt-dlp direkt von GitHub laden, mpv über winget installieren (falls es fehlt)."""
    msgs = []
    try:
        say("Lade yt-dlp …")
        data = http_get("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", timeout=180)
        tmp = TOOLS_USER / "yt-dlp.exe.tmp"
        tmp.write_bytes(data)
        tmp.replace(TOOLS_USER / "yt-dlp.exe")
        msgs.append("yt-dlp aktualisiert")
    except Exception as e:
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
    try:
        for p in UPDATE_DIR.glob("*"):
            m = re.search(r"Setup-([\d.]+)\.exe$", p.name)
            if p.suffix == ".part" or (m and parse_version(m.group(1)) <= parse_version(APP_VERSION)):
                p.unlink(missing_ok=True)
    except Exception:
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
local capped = false
mp.observe_property("container-fps", "number", function(_, fps)
    if limit <= 0 or not fps then return end
    if fps > limit + 1 then
        if not capped then
            capped = true
            mp.set_property("hwdec", "auto-copy-safe")
        end
        mp.commandv("vf", "set", "fps=" .. limit)
    elseif capped then
        capped = false
        mp.commandv("vf", "clr", "")
        mp.set_property("hwdec", "auto-safe")
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

    def _add_to_job(self, proc):
        if self.job:
            try:
                win32job.AssignProcessToJobObject(self.job, int(proc._handle))
            except Exception:
                pass

    def _base_cmd(self, mpv, ytdlp):
        q = self.cfg.get("quality", "1080")
        vol = int(self.cfg.get("volume", 0))
        fit = self.cfg.get("fit", "cover")
        base = [mpv, "--no-config", "--force-window=immediate", "--no-border", "--no-osc", "--osd-level=0",
                "--no-input-default-bindings", "--window-dragging=no", "--input-cursor=no", "--loop-file=inf", "--keep-open=yes",
                "--image-display-duration=inf", "--stop-screensaver=no", "--hwdec=auto-safe",
                "--audio-display=no", "--scale=bilinear", "--cscale=bilinear", "--dscale=bilinear", "--dither=no",
                "--correct-downscaling=no", "--interpolation=no", "--deband=no", "--video-sync=audio",
                "--framedrop=vo", "--sub-auto=no", "--sid=no", "--demuxer-max-bytes=64MiB",
                "--demuxer-max-back-bytes=16MiB", f"--volume={vol}", f"--mute={'yes' if vol == 0 else 'no'}",
                "--ytdl=yes", f"--ytdl-format=bv*[height<=?{q}]+ba/b[height<=?{q}]/b",
                "--ytdl-raw-options=no-playlist=", "--no-terminal", "--msg-level=all=warn"]
        if ytdlp:
            base.append("--script-opts=ytdl_hook-ytdl_path=" + ytdlp.replace("\\", "/"))
        fps_limit = int(self.cfg.get("fps_limit", 30) or 0)
        script = fps_script() if fps_limit else None
        if script:
            base += [f"--script={script}", f"--script-opts-append=wallura-fps={fps_limit}"]
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
            self.on_error("mpv fehlt – bitte links auf „Tools installieren“ klicken.")
            return False
        ytdlp = find_tool("yt-dlp")
        if not self.instances:
            self._paused = self.paused_manual
        base = self._base_cmd(mpv, ytdlp)

        new = {}
        for idx, item in todo.items():
            src = item["src"]
            if item["kind"] == "local" and not Path(src).exists():
                self.on_error(f"Datei nicht gefunden: {src}")
                ok = False
                continue
            if item["kind"] == "youtube" and not ytdlp:
                self.on_error("yt-dlp fehlt (für YouTube nötig) – bitte „Tools installieren“ klicken.")
                ok = False
                continue
            pipe = rf"\\.\pipe\wallura_{os.getpid()}_{idx}"
            log = DATA_DIR / f"mpv_{idx}.log"
            cmd = base + [f"--title=Wallura-{os.getpid()}-{idx}", f"--input-ipc-server={pipe}",
                          f"--log-file={log}", src]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY)
            self._add_to_job(proc)
            new[idx] = {"proc": proc, "pipe": pipe, "rect": mons[idx]["rect"], "hwnd": None, "log": log, "item": item}

        deadline = time.time() + 30
        for idx, inst in new.items():
            hwnd = self._find_window(inst["proc"], deadline)
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
            want = self.paused_manual or (self.cfg.get("pause_fullscreen", True) and fullscreen_app_active())
            if want != self._paused:
                self._apply_pause(want)
            covered = covered_monitor_rects() if (self.cfg.get("pause_fullscreen", True) and not self._paused) else set()
            for inst in alive:
                should = inst["rect"] in covered
                if should != inst.get("cover_paused", False):
                    inst["cover_paused"] = should
                    self._ipc(inst, ["set_property", "pause", should])
            if self._tick % 2 == 0:
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
                        if (l, t, r - l, b - t) != (x, y, w, h):
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
class App(ctk.CTk):
    def __init__(self, start_hidden=False):
        super().__init__()
        self.title(f"Wallura {APP_VERSION}")
        self.geometry("1200x820")
        self.minsize(1020, 660)
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

        self._build_ui()
        self.refresh_library()
        self._update_tools_banner()
        self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.bind("<Configure>", self._on_resize)
        self.after(100, self._poll)
        if start_hidden:
            self.withdraw()
        if self._assign_items():
            threading.Thread(target=self._startup_worker, args=(start_hidden,), daemon=True).start()
        cleanup_old_updates()
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
    def _font(self, size=13, weight="normal"):
        return ctk.CTkFont(family=FONT, size=size, weight=weight)

    def _btn(self, parent, text, command, kind="secondary", **kw):
        styles = {
            "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT),
            "secondary": dict(fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT,
                              border_width=1, border_color=BORDER),
            "ghost": dict(fg_color="transparent", hover_color=SURFACE2, text_color=MUTED),
            "danger": dict(fg_color="transparent", hover_color="#3a1c1f", text_color=DANGER_TEXT,
                           border_width=1, border_color="#5a2a2e"),
        }[kind]
        opts = dict(height=36, corner_radius=10, command=command,
                    font=self._font(13, "bold" if kind == "primary" else "normal"))
        opts.update(styles)
        opts.update(kw)
        return ctk.CTkButton(parent, text=text, **opts)

    def _panel(self, parent, title):
        box = ctk.CTkFrame(parent, corner_radius=14, fg_color=SURFACE2, border_width=1, border_color=BORDER)
        box.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(box, text=title, font=self._font(12, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=14, pady=(12, 6))
        return box

    def _menu_style(self):
        return dict(fg_color=SURFACE, button_color=BORDER, button_hover_color="#3a4150",
                    dropdown_fg_color=SURFACE2, dropdown_hover_color=BORDER, dropdown_text_color=TEXT,
                    text_color=TEXT, corner_radius=8, height=32, font=self._font(13),
                    dropdown_font=self._font(13))

    def _switch(self, parent, text, command):
        sw = ctk.CTkSwitch(parent, text=text, command=command, progress_color=ACCENT,
                           button_color=TEXT, button_hover_color="white", fg_color=BORDER,
                           font=self._font(13), text_color=TEXT)
        sw.pack(anchor="w", padx=14, pady=5)
        return sw

    def _build_ui(self):
        self.configure(fg_color=BG)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=SIDEBAR_W, corner_radius=0, fg_color=SURFACE)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        # unten festgepinnt: Stoppen + Hilfs-Aktionen
        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(side="bottom", fill="x", padx=14, pady=(4, 14))
        ctk.CTkLabel(foot, text=COPYRIGHT, font=self._font(11), text_color=MUTED,
                     anchor="center").pack(side="bottom", fill="x", pady=(8, 0))
        self.btn_stop = self._btn(foot, "■  Wallpaper stoppen", self.stop_wallpaper, "danger")
        self.btn_stop.pack(fill="x", pady=(0, 6))
        frow = ctk.CTkFrame(foot, fg_color="transparent")
        frow.pack(fill="x")
        frow.grid_columnconfigure((0, 1), weight=1)
        self._btn(frow, "Updates suchen", lambda: self.check_updates(True), "ghost",
                  height=30, font=self._font(12)).grid(row=0, column=0, sticky="we", padx=(0, 3))
        self._btn(frow, "Tools installieren", self.on_install_tools, "ghost",
                  height=30, font=self._font(12)).grid(row=0, column=1, sticky="we", padx=(3, 0))

        body = ctk.CTkScrollableFrame(side, fg_color="transparent", scrollbar_button_color=BORDER,
                                      scrollbar_button_hover_color=MUTED)
        body.pack(side="top", fill="both", expand=True, padx=(0, 2), pady=(4, 4))

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 14))
        try:
            self._logo = ctk.CTkImage(make_icon(128), size=(42, 42))
            ctk.CTkLabel(head, image=self._logo, text="").pack(side="left", padx=(0, 12))
        except Exception:
            pass
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Wallura", font=self._font(24, "bold"), text_color=TEXT,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text=f"Version {APP_VERSION}", font=self._font(12), text_color=MUTED,
                     anchor="w").pack(anchor="w")

        self._btn(body, "＋  Datei hinzufügen", self.add_local, "primary", height=40).pack(
            fill="x", padx=18, pady=(0, 6))
        self._btn(body, "＋  Link (YouTube / Web)", self.add_link, "secondary", height=40).pack(
            fill="x", padx=18, pady=(0, 10))

        # --- Monitor
        mon = self._panel(body, "Monitor")
        self.mon_preview = ctk.CTkLabel(mon, text="", cursor="hand2")
        self.mon_preview.pack(padx=14, pady=(0, 6))
        self.mon_preview.bind("<Button-1>", self._on_preview_click)
        self.mon_hint = ctk.CTkLabel(mon, text="", anchor="w", font=self._font(13, "bold"), text_color=TEXT)
        self.mon_hint.pack(fill="x", padx=14)
        ctk.CTkLabel(mon, text="Monitor anklicken, dann ein Wallpaper wählen.", anchor="w", justify="left",
                     wraplength=SIDEBAR_W - 90, font=self._font(11), text_color=MUTED).pack(
            fill="x", padx=14, pady=(0, 8))
        self.btn_all = self._btn(mon, "Alle Monitore gleich", lambda: self.select_monitor("all"),
                                 "secondary", height=30, font=self._font(12))
        self.btn_all.pack(fill="x", padx=14, pady=(0, 14))

        # --- Wiedergabe
        play = self._panel(body, "Wiedergabe")
        vrow = ctk.CTkFrame(play, fg_color="transparent")
        vrow.pack(fill="x", padx=14)
        ctk.CTkLabel(vrow, text="Lautstärke", font=self._font(13), text_color=TEXT, anchor="w").pack(side="left")
        self.vol_lbl = ctk.CTkLabel(vrow, text=f"{int(self.cfg['volume'])} %", font=self._font(12), text_color=MUTED)
        self.vol_lbl.pack(side="right")
        self.vol = ctk.CTkSlider(play, from_=0, to=100, number_of_steps=100, command=self.on_volume,
                                 button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                 progress_color=ACCENT, fg_color=BORDER)
        self.vol.set(self.cfg["volume"])
        self.vol.pack(fill="x", padx=14, pady=(6, 12))

        ctk.CTkLabel(play, text="Anpassung", font=self._font(13), text_color=TEXT, anchor="w").pack(fill="x", padx=14)
        self.fit_menu = ctk.CTkOptionMenu(play, values=list(FIT_MAP), command=self.on_fit, **self._menu_style())
        self.fit_menu.set(next(k for k, v in FIT_MAP.items() if v == self.cfg["fit"]))
        self.fit_menu.pack(fill="x", padx=14, pady=(4, 12))

        ctk.CTkLabel(play, text="Max. FPS (spart Leistung)", font=self._font(13), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=14)
        self.fps_menu = ctk.CTkOptionMenu(play, values=list(FPS_MAP), command=self.on_fps, **self._menu_style())
        self.fps_menu.set(next((k for k, v in FPS_MAP.items() if v == self.cfg.get("fps_limit", 30)), "30 FPS"))
        self.fps_menu.pack(fill="x", padx=14, pady=(4, 12))

        ctk.CTkLabel(play, text="Max. Qualität (Streams, p)", font=self._font(13), text_color=TEXT,
                     anchor="w").pack(fill="x", padx=14)
        self.q_menu = ctk.CTkOptionMenu(play, values=QUALITIES, command=self.on_quality, **self._menu_style())
        self.q_menu.set(str(self.cfg["quality"]))
        self.q_menu.pack(fill="x", padx=14, pady=(4, 14))

        # --- System
        sysp = self._panel(body, "System")
        self.sw_pause = self._switch(sysp, "Pause wenn Desktop verdeckt", self.on_pause_fs)
        if self.cfg["pause_fullscreen"]:
            self.sw_pause.select()
        self.sw_auto = self._switch(sysp, "Mit Windows starten", self.on_autostart)
        if is_autostart():
            self.sw_auto.select()
        self.sw_upd = self._switch(sysp, "Updates automatisch laden", self.on_auto_update)
        if self.cfg.get("auto_update", True):
            self.sw_upd.select()
        ctk.CTkFrame(sysp, height=8, fg_color="transparent").pack()

        # --- Hauptbereich
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=18, pady=(16, 12))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        mhead = ctk.CTkFrame(main, fg_color="transparent")
        mhead.grid(row=0, column=0, sticky="we", padx=6)
        ctk.CTkLabel(mhead, text="Bibliothek", font=self._font(26, "bold"), text_color=TEXT).pack(side="left")
        self.count_lbl = ctk.CTkLabel(mhead, text="", font=self._font(13), text_color=MUTED)
        self.count_lbl.pack(side="left", padx=(12, 0), pady=(8, 0))
        self._search_job = None
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        ctk.CTkEntry(mhead, textvariable=self.search_var, placeholder_text="Wallpaper suchen", width=230,
                     height=34, corner_radius=10, fg_color=SURFACE, border_color=BORDER, text_color=TEXT,
                     placeholder_text_color=MUTED, font=self._font(13)).pack(side="right", pady=(6, 0))

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=1, column=0, sticky="we")
        self.banner = ctk.CTkLabel(top, text="", text_color="#ffb454", anchor="w", font=self._font(12))
        self.banner.pack(fill="x", padx=6, pady=(4, 4))
        self.upd_frame = ctk.CTkFrame(top, corner_radius=12, fg_color="#12303f",
                                      border_width=1, border_color=ACCENT_DIM)  # erst sichtbar, wenn ein Update da ist
        self.upd_label = ctk.CTkLabel(self.upd_frame, text="", anchor="w", font=self._font(13), text_color=TEXT)
        self.upd_label.pack(side="left", padx=14, pady=10)
        self.upd_btn = self._btn(self.upd_frame, "", None, "primary", width=160, height=32)
        self.upd_btn.pack(side="right", padx=10, pady=8)

        self.scroll = ctk.CTkScrollableFrame(main, corner_radius=0, fg_color="transparent",
                                             scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        self.scroll.grid(row=2, column=0, sticky="nsew")

        bar = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=10)
        bar.grid(row=3, column=0, sticky="we", pady=(10, 0))
        bar.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(bar, text="Bereit.", anchor="w", font=self._font(12), text_color=STATUS_OK)
        self.status.grid(row=0, column=0, sticky="we", padx=14, pady=8)
        self.progress = ctk.CTkProgressBar(bar, width=200, height=6, progress_color=ACCENT, fg_color=BORDER)
        self.progress.set(0)
        self.progress.grid(row=0, column=1, padx=14)

    # -- Bibliothek
    def find_item(self, item_id):
        return next((i for i in self.cfg["items"] if i["id"] == item_id), None)

    def _cols(self):
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        return max(1, int((self.winfo_width() / scale - SIDEBAR_W - 70) // 272))

    def _on_resize(self, e):
        if e.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(300, lambda: self._cols() != self._last_cols and self.refresh_library())

    def _on_search(self, *_):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.refresh_library)

    def _thumb_image(self, item):
        p = THUMB_DIR / f"{item['id']}.jpg"
        try:
            img = Image.open(p).convert("RGB") if p.exists() else placeholder()
        except Exception:
            img = placeholder()
        img = ImageOps.fit(img, (480, 270)).convert("RGBA")
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=26, fill=255)
        img.putalpha(mask)
        return ctk.CTkImage(img, size=(240, 135))

    def refresh_library(self):
        self._refresh_monitor_ui()
        for w in self.scroll.winfo_children():
            w.destroy()
        on = {}
        for idx, it in self._assign_items().items():
            on.setdefault(it["id"], []).append(idx)
        self._on_map, self._mon_count = on, len(get_monitors())
        cols = self._last_cols = self._cols()
        n_items = len(self.cfg["items"])
        q = self.search_var.get().strip().lower()
        shown = [it for it in self.cfg["items"] if q in str(it.get("title", "")).lower()] if q else self.cfg["items"]
        if not n_items:
            self.count_lbl.configure(text="")
        else:
            self.count_lbl.configure(text=f"{len(shown)} von {n_items}" if q else f"{n_items} Wallpaper")
        if n_items and not shown:
            ctk.CTkLabel(self.scroll, text=f"Keine Treffer für „{q}“.", font=self._font(14),
                         text_color=MUTED).grid(row=0, column=0, padx=20, pady=40)
            return
        if not n_items:
            box = ctk.CTkFrame(self.scroll, corner_radius=16, fg_color=SURFACE, border_width=1, border_color=BORDER)
            box.grid(row=0, column=0, padx=8, pady=24)
            ctk.CTkLabel(box, text="Noch keine Wallpaper", font=self._font(18, "bold"),
                         text_color=TEXT).pack(padx=48, pady=(28, 4))
            ctk.CTkLabel(box, text="Füge ein Video, ein Bild oder einen YouTube-Link hinzu.",
                         font=self._font(13), text_color=MUTED).pack(padx=48)
            brow = ctk.CTkFrame(box, fg_color="transparent")
            brow.pack(padx=48, pady=(16, 28))
            self._btn(brow, "＋  Datei hinzufügen", self.add_local, "primary", width=170).pack(side="left", padx=4)
            self._btn(brow, "＋  Link", self.add_link, "secondary", width=110).pack(side="left", padx=4)
            return
        for n, item in enumerate(shown):
            self._card(item, n // cols, n % cols)

    def _card(self, item, r, c):
        on = sorted(self._on_map.get(item["id"], []))
        active = bool(on) and self.player.active
        card = ctk.CTkFrame(self.scroll, corner_radius=14, fg_color="#14232c" if active else SURFACE,
                            border_width=2 if active else 1, border_color=ACCENT if active else BORDER)
        card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
        lbl = ctk.CTkLabel(card, image=self._thumb_image(item), text="", cursor="hand2")
        lbl.pack(padx=10, pady=(10, 8))
        lbl.bind("<Button-1>", lambda e, it=item: self.apply(it))
        if not active:
            lbl.bind("<Enter>", lambda e, cd=card: cd.configure(border_color=ACCENT_DIM))
            lbl.bind("<Leave>", lambda e, cd=card: cd.configure(border_color=BORDER))
        ctk.CTkLabel(card, text=shorten(item["title"], 34), font=self._font(14, "bold"), text_color=TEXT,
                     anchor="w", width=240).pack(padx=12, anchor="w")
        if on:
            if self._mon_count == 1:
                where = "Aktiv"
            elif len(on) == self._mon_count:
                where = "Aktiv auf allen Monitoren"
            else:
                where = "Aktiv auf Monitor " + ", ".join(str(i + 1) for i in on)
            ctk.CTkLabel(card, text="●  " + where, text_color=ACCENT, font=self._font(12),
                         anchor="w", width=240).pack(padx=12, anchor="w")
        else:
            ctk.CTkLabel(card, text=KIND_LABEL.get(item["kind"], "?"), text_color=MUTED, font=self._font(12),
                         anchor="w", width=240).pack(padx=12, anchor="w")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(8, 10))
        self._btn(row, "▶  Anwenden", lambda it=item: self.apply(it), "secondary" if active else "primary",
                  height=30, width=110, font=self._font(12, "bold")).pack(side="left")
        self._btn(row, "✕", lambda it=item: self.remove(it), "ghost", width=30, height=30,
                  hover_color="#3a1c1f").pack(side="right")
        if item["kind"] != "local":
            self._btn(row, "⬇", lambda it=item: self.download(it), "ghost", width=30, height=30).pack(side="right")

    # -- Hinzufügen / Entfernen
    def add_local(self):
        pats = " ".join(f"*{e}" for e in MEDIA_EXT)
        files = filedialog.askopenfilenames(title="Wallpaper auswählen",
                                            filetypes=[("Videos & Bilder", pats), ("Alle Dateien", "*.*")])
        for f in files:
            item = {"id": uuid.uuid4().hex[:10], "title": Path(f).stem, "kind": "local", "src": f}
            self.cfg["items"].append(item)
            threading.Thread(target=self._thumb_worker, args=(item,), daemon=True).start()
        if files:
            save_config(self.cfg)
            self.refresh_library()

    def add_link(self):
        dlg = ctk.CTkInputDialog(text="YouTube-, Video- oder Web-Link einfügen:", title="Link hinzufügen")
        url = (dlg.get_input() or "").strip()
        if not url:
            return
        if not re.match(r"https?://", url, re.I):
            self.set_status("Das sieht nicht nach einem Link aus (https://…).", True)
            return
        item = {"id": uuid.uuid4().hex[:10], "title": url, "kind": detect_kind(url), "src": url}
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
        save_config(self.cfg)
        if ok:
            where = "" if len(idxs) != 1 or self._mon_count == 1 else f" (Monitor {idxs[0] + 1})"
            self.ui(lambda: self.set_status(f"Aktiv: {shorten(item['title'], 60)}{where}"))
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
        self.refresh_library()

    def restart_current(self):
        if self.player.active:
            threading.Thread(target=lambda: self.player.apply(self._assign_items(), force=True), daemon=True).start()

    def next_wallpaper(self):
        items = self.cfg["items"]
        if not items:
            return
        idxs = self._target_indices()
        ids = [i["id"] for i in items]
        cur = self.cfg.get("assign", {}).get(str(idxs[0])) if idxs else None
        self.apply(items[(ids.index(cur) + 1) % len(items)] if cur in ids else items[0])

    def toggle_pause(self):
        self.player.set_manual_pause(not self.player.paused_manual)
        self.set_status("Pausiert." if self.player.paused_manual else "Läuft weiter.")

    # -- Download
    def download(self, item):
        self.set_status(f"Lade „{shorten(item['title'], 40)}“ herunter …")
        self.progress.set(0)
        threading.Thread(target=self._download_worker, args=(item,), daemon=True).start()

    def _download_worker(self, item):
        try:
            path = download_item(item, self.cfg["quality"], lambda p: self.ui(lambda: self.progress.set(p / 100)))
        except Exception as e:
            msg = f"Download fehlgeschlagen: {e}"
            self.ui(lambda: (self.set_status(msg, True), self.progress.set(0)))
            return
        item["origin"] = item["src"]
        item["kind"], item["src"] = "local", str(path)
        save_config(self.cfg)
        if not (THUMB_DIR / f"{item['id']}.jpg").exists():
            make_local_thumb(item["id"], path)
        self.ui(lambda: (self.progress.set(1), self.set_status(f"Heruntergeladen: {path.name} (offline nutzbar)"),
                         self.refresh_library()))

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
        self._mon_img = ctk.CTkImage(img, size=(244, 122))
        self.mon_preview.configure(image=self._mon_img)
        mons = get_monitors()
        sel = str(self.cfg.get("monitor", "all"))
        single = sel.isdigit() and int(sel) < len(mons)
        if single:
            i = int(sel)
            self.mon_hint.configure(text=f"Ziel: Monitor {i + 1}" + (" (Haupt)" if mons[i]["primary"] else ""))
            self.btn_stop.configure(text=f"■  Monitor {i + 1} stoppen")
            self.btn_all.configure(fg_color=SURFACE, hover_color=BORDER, text_color=TEXT, border_color=BORDER)
        else:
            self.mon_hint.configure(text="Ziel: Alle Monitore")
            self.btn_stop.configure(text="■  Wallpaper stoppen")
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
            left, top, right, bottom = win32api.GetMonitorInfo(mon)["Work"]
        except Exception:
            left, top, right, bottom = 0, 0, t.winfo_screenwidth(), t.winfo_screenheight()
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
        self.vol_lbl.configure(text=f"{int(v)} %")
        self.cfg["volume"] = int(v)
        self.player.set_volume(int(v))
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

    def _update_tools_banner(self):
        missing = [n for n in ("mpv", "yt-dlp") if not find_tool(n)]
        self.banner.configure(text=("Fehlt noch: " + ", ".join(missing) +
                                    "  →  links auf „Tools installieren“ klicken.") if missing else "")

    # -- Tray
    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Wallura öffnen", lambda: self.ui(self.show_window), default=True),
            pystray.MenuItem(lambda item: "Fortsetzen" if self.player.paused_manual else "Pause",
                             lambda: self.ui(self.toggle_pause)),
            pystray.MenuItem(lambda item: f"Update v{(self.update_info or {}).get('version', '')} installieren",
                             lambda: self.ui(self.install_update), visible=lambda item: bool(self.update_file)),
            pystray.MenuItem("Nächstes Wallpaper", lambda: self.ui(self.next_wallpaper)),
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
        self.withdraw()

    def quit_app(self):
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
    app = App(start_hidden="--minimized" in sys.argv)
    app.mainloop()
    del mutex


if __name__ == "__main__":
    main()