# Wallura – Live-Wallpaper-Engine für Windows 10/11

## Starten

1. Python 3.10+ installieren (https://www.python.org, Haken bei „Add to PATH“).
2. `install_and_run.bat` doppelklicken.
3. In Wallura links auf **„Tools installieren / aktualisieren“** klicken.
   Das lädt `yt-dlp` (für YouTube) und installiert `mpv` (Player) per winget.
   Klappt winget nicht: `mpv.exe` manuell nach `%APPDATA%\Wallura\tools` kopieren.
4. Datei oder Link hinzufügen, Karte anklicken – fertig.

Optional: `ffmpeg` (`winget install Gyan.FFmpeg`) für Downloads in voller Qualität.

## Installer bauen

`build_installer.bat` ausführen → `installer\Wallura-Setup.exe`. Dabei lädt `fetch_tools.py` automatisch
`mpv.exe` und `yt-dlp.exe` nach `tools\`, und der Installer legt sie mit ins Programmverzeichnis
(`{app}\tools`). Wer Wallura per Setup installiert, muss also keine Tools mehr nachinstallieren.
„Tools installieren / aktualisieren“ in der App bleibt für yt-dlp-Updates nützlich.

## Als .exe bauen

`build_exe.bat` ausführen → `dist\Wallura.exe`.

## Funktionen

- Lokale Dateien (mp4, webm, mkv, mov, gif, Bilder), Web-Links (direkte Videos oder alles, was yt-dlp kann), YouTube
- ⬇ lädt Links in die Bibliothek, danach offline nutzbar
- Lautstärke, Anpassung (Füllen / Einpassen / Strecken), Monitor-Auswahl, Max-Qualität
- Pausiert automatisch bei Vollbild-Apps (Spiele usw.)
- Tray-Icon (Pause, Nächstes, Stoppen, Beenden), Autostart mit Windows
- Nach einem mpv-Absturz startet das Wallpaper automatisch neu

## Pro Monitor ein eigenes Wallpaper

- Links unter **Monitor** siehst du eine kleine Karte deiner Monitore mit dem jeweils laufenden Wallpaper.
- Monitor anklicken (blauer Rahmen = Ziel), dann in der Bibliothek ein Wallpaper wählen – nur dieser Monitor wechselt.
- **Alle Monitore gleich** setzt das nächste Wallpaper auf alle Monitore.
- „Stoppen“ und „Nächstes Wallpaper“ (Tray) wirken ebenfalls auf das gewählte Ziel.
- Die Lautstärke gilt für alle Monitore gleich – bei unterschiedlichen Videos am besten auf 0 lassen.

## Automatische Updates (GitHub)

1. In `wallura.py` oben `GITHUB_REPO = "name/repo"` auf dein öffentliches Repo setzen.
2. Neue Version: `APP_VERSION` erhöhen, `build_installer.bat` ausführen und `installer\Wallura-Setup.exe`
   als Datei an ein **GitHub-Release** hängen (Tag z. B. `v1.2.0`).
   Oder automatisch: Tag pushen (`git tag v1.2.0 && git push origin v1.2.0`) – `.github/workflows/release.yml`
   lädt die Tools, baut den Installer und legt das Release an (braucht `requirements.txt` und `fetch_tools.py` im Repo).
3. Wallura prüft beim Start und danach alle 6 Stunden, lädt das Update (bei aktivem Schalter
   „Updates automatisch laden“) herunter und zeigt oben **„Jetzt installieren“**. Der Installer läuft still
   und startet Wallura danach neu. „Nach Updates suchen“ prüft sofort.

Updates gibt es nur in der installierten Version (.exe), nicht beim Start aus dem Quellcode.

## Daten

`%APPDATA%\Wallura` – config.json, downloads, thumbs, tools, mpv-Logs (`mpv_0.log`)

## Fehlersuche

- Schwarzes Bild / startet nicht: `%APPDATA%\Wallura\mpv_0.log` ansehen.
- YouTube geht nicht mehr: „Tools installieren / aktualisieren“ (yt-dlp-Update).
- Wallpaper liegt über den Icons oder fehlt (Windows 11 24H2): Das Einbetten in `get_wallpaper_parent()` / `place()` in `wallura.py` ist die empfindlichste Stelle.

## Lizenz

Wallura ist kostenlos und Open Source (MIT-Lizenz), © 2026 MorreTv. Siehe [LICENSE](LICENSE).
Drittanbieter-Komponenten (customtkinter, pystray, Pillow, pywin32, mpv, yt-dlp) haben ihre eigenen Lizenzen.
