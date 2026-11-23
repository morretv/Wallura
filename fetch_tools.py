# Lädt yt-dlp.exe und mpv.exe nach .\tools, damit der Installer sie direkt mitliefert.
# Wird von build_installer.bat und vom GitHub-Workflow aufgerufen. Bereits vorhandene Dateien
# werden übersprungen (neu laden: python fetch_tools.py --force).
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "tools"
FORCE = "--force" in sys.argv

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
MPV_API = "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
SEVENZR_URL = "https://www.7-zip.org/a/7zr.exe"


def get(url, timeout=600, api=False):
    headers = {"User-Agent": "Wallura-Build"}
    token = os.environ.get("GITHUB_TOKEN")
    if api and token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_ytdlp():
    target = OUT / "yt-dlp.exe"
    if target.exists() and not FORCE:
        print("yt-dlp.exe vorhanden - übersprungen")
        return
    print("Lade yt-dlp.exe ...")
    tmp = OUT / "yt-dlp.exe.tmp"
    tmp.write_bytes(get(YTDLP_URL))
    tmp.replace(target)


def fetch_mpv():
    target = OUT / "mpv.exe"
    if target.exists() and not FORCE:
        print("mpv.exe vorhanden - übersprungen")
        return
    print("Suche aktuelles mpv-Build ...")
    release = json.loads(get(MPV_API, api=True).decode("utf-8"))
    asset = next((a for a in release["assets"]
                  if re.fullmatch(r"mpv-x86_64-\d{8}-git-[0-9a-f]+\.7z", a["name"])), None)
    if not asset:
        raise RuntimeError("Kein passendes mpv-Archiv im neuesten Release gefunden.")
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        print(f"Lade {asset['name']} ...")
        archive = td / "mpv.7z"
        archive.write_bytes(get(asset["browser_download_url"]))
        sevenzr = td / "7zr.exe"
        sevenzr.write_bytes(get(SEVENZR_URL))
        extracted = td / "x"
        subprocess.run([str(sevenzr), "x", str(archive), f"-o{extracted}", "-y"],
                       check=True, stdout=subprocess.DEVNULL)
        mpv = next(extracted.rglob("mpv.exe"), None)
        if not mpv:
            raise RuntimeError("mpv.exe nicht im Archiv gefunden.")
        shutil.copy2(mpv, target)
        for dll in mpv.parent.glob("*.dll"):  # falls das Build zusätzliche DLLs mitbringt
            shutil.copy2(dll, OUT / dll.name)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    fetch_ytdlp()
    fetch_mpv()
    for name in ("yt-dlp.exe", "mpv.exe"):
        if not (OUT / name).exists():
            sys.exit(f"FEHLER: {name} fehlt in {OUT}")
    print("Tools bereit:", ", ".join(sorted(p.name for p in OUT.iterdir())))
