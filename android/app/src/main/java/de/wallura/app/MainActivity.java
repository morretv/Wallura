package de.wallura.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;
import java.util.Locale;
import java.util.Random;

/** Bibliothek, Einstellungen und Wiedergabe – Aufbau und Farben wie am PC. */
public class MainActivity extends Activity {

    private static final int REQ_PICK = 1001;

    private TextView status;
    private TextView count;
    private EditText search;
    private LinearLayout list;
    private LinearLayout settings;
    private LinearLayout filterRow;
    private TextView sideActive;
    private SeekBar volume;
    private TextView volumeLabel;
    private TextView navLibrary;
    private TextView navSettings;
    private TextView btnPause;
    private TextView storageDesc;
    private View pageLibrary;
    private View pageSettings;

    private String version = "";
    private boolean paused;
    private boolean favoritesOnly;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        version = versionName();

        status = findViewById(R.id.status);
        count = findViewById(R.id.lib_count);
        search = findViewById(R.id.lib_search);
        list = findViewById(R.id.lib_list);
        filterRow = findViewById(R.id.lib_filter);
        settings = findViewById(R.id.settings_container);
        sideActive = findViewById(R.id.side_active);
        volume = findViewById(R.id.volume);
        volumeLabel = findViewById(R.id.volume_lbl);
        navLibrary = findViewById(R.id.nav_library);
        navSettings = findViewById(R.id.nav_settings);
        btnPause = findViewById(R.id.btn_pause);
        pageLibrary = findViewById(R.id.page_library);
        pageSettings = findViewById(R.id.page_settings);

        ((TextView) findViewById(R.id.side_version)).setText("Version " + version);

        navLibrary.setOnClickListener(v -> showPage("library"));
        navSettings.setOnClickListener(v -> showPage("settings"));
        findViewById(R.id.side_set).setOnClickListener(v -> setAsWallpaper());
        findViewById(R.id.btn_add).setOnClickListener(v -> pickVideo());
        findViewById(R.id.btn_next).setOnClickListener(v -> nextWallpaper());
        findViewById(R.id.btn_stop).setOnClickListener(v -> {
            paused = false;
            btnPause.setText("Pause");
            sendCommand(VideoWallpaperService.CMD_STOP);
            refresh();
            setStatus("Gestoppt – „Nächstes“ oder ein Video wählen, um weiterzuspielen.");
        });
        btnPause.setOnClickListener(v -> {
            paused = !paused;
            sendCommand(paused ? VideoWallpaperService.CMD_PAUSE : VideoWallpaperService.CMD_RESUME);
            btnPause.setText(paused ? "Fortsetzen" : "Pause");
            setStatus(paused ? "Pausiert." : "Wallpaper läuft.");
        });

        search.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                refresh();
            }

            @Override
            public void afterTextChanged(Editable s) {
            }
        });

        volume.setMax(100);
        volume.setProgress(Library.volume(this));
        volumeLabel.setText(Library.volume(this) + " %");
        volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                volumeLabel.setText(value + " %");
                if (!fromUser) {
                    return;
                }
                Library.setVolume(MainActivity.this, value);
                sendCommand(VideoWallpaperService.CMD_VOLUME);
            }

            @Override
            public void onStartTrackingTouch(SeekBar bar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar bar) {
            }
        });

        buildFilters();
        buildSettings();
        showPage("library");
        refresh();
        setStatus(Library.videos(this).isEmpty()
                ? "Noch keine Videos – tippe auf „＋ Datei“." : "Bereit.");
    }

    // ---------------------------------------------------------------- Bibliothek

    private void refresh() {
        String query = search.getText().toString();
        List<File> filtered = Library.videos(this, query, favoritesOnly);
        int total = Library.videos(this).size();
        count.setText(favoritesOnly || !query.trim().isEmpty()
                ? filtered.size() + " von " + total + " Wallpaper"
                : (total == 1 ? "1 Wallpaper" : total + " Wallpaper"));

        File active = Library.activeFile(this);
        String activePath = active == null ? null : active.getAbsolutePath();
        sideActive.setText(active == null ? "Keins gewählt" : active.getName());

        updateStorageText();

        list.removeAllViews();
        if (filtered.isEmpty()) {
            String hint = total == 0
                    ? "Noch keine Videos. Tippe auf „＋ Datei“ und wähle ein Video von deinem Handy."
                    : favoritesOnly ? "Noch keine Favoriten – tippe in der Liste auf ☆."
                    : "Kein Treffer für „" + query.trim() + "“.";
            TextView empty = Ui.text(this, hint, 11, Ui.col(this, R.color.muted), false);
            empty.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 12));
            list.addView(empty);
            return;
        }

        LayoutInflater inflater = LayoutInflater.from(this);
        for (final File file : filtered) {
            final String path = file.getAbsolutePath();
            final boolean isActive = path.equals(activePath);
            View row = inflater.inflate(R.layout.item_video, list, false);

            ((TextView) row.findViewById(R.id.video_name)).setText(file.getName());
            ((TextView) row.findViewById(R.id.video_meta)).setText(
                    String.format(Locale.GERMANY, "%.1f MB", file.length() / (1024.0 * 1024.0))
                            + (isActive ? "  ·  aktiv" : ""));
            Thumbs.load(this, file, (ImageView) row.findViewById(R.id.video_thumb));

            final boolean favorite = Library.isFavorite(this, file);
            final TextView star = row.findViewById(R.id.video_fav);
            star.setText(favorite ? "★" : "☆");
            star.setTextColor(Ui.col(this, favorite ? R.color.accent : R.color.muted));
            star.setOnClickListener(v -> {
                boolean now = Library.toggleFavorite(this, file);
                refresh();
                setStatus(now ? "Zu Favoriten hinzugefügt." : "Aus Favoriten entfernt.");
            });

            final TextView pick = row.findViewById(R.id.video_pick);
            pick.setText(isActive ? "Aktiv" : "Auswählen");
            pick.setTextColor(Ui.col(this, isActive ? R.color.muted : R.color.on_accent));
            pick.setBackgroundResource(isActive ? R.drawable.bg_btn_ghost : R.drawable.bg_btn_primary);
            pick.setOnClickListener(v -> {
                Library.setActive(this, path);
                paused = false;
                btnPause.setText("Pause");
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                refresh();
                setStatus("Wallpaper: " + file.getName());
            });

            row.findViewById(R.id.video_delete).setOnClickListener(v -> {
                if (!file.delete()) {
                    setStatus("Video ließ sich nicht löschen.", true);
                    return;
                }
                Thumbs.remove(this, file);
                if (path.equals(Library.active(this))) {
                    Library.setActive(this, null);
                }
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                refresh();
                setStatus("Video gelöscht.");
            });

            list.addView(row);
        }
    }

    /** Filter-Chips (Alle / Favoriten) und Zufalls-Button über der Liste. */
    private void buildFilters() {
        filterRow.removeAllViews();

        TextView all = Ui.pill(this, "Alle", favoritesOnly ? Ui.CHIP_OFF : Ui.CHIP_ON);
        all.setOnClickListener(v -> {
            favoritesOnly = false;
            buildFilters();
            refresh();
        });
        filterRow.addView(all);

        TextView favs = Ui.pill(this, "★ Favoriten", favoritesOnly ? Ui.CHIP_ON : Ui.CHIP_OFF);
        favs.setOnClickListener(v -> {
            favoritesOnly = true;
            buildFilters();
            refresh();
        });
        LinearLayout.LayoutParams favParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        favParams.leftMargin = Ui.dp(this, 5);
        filterRow.addView(favs, favParams);

        View spacer = new View(this);
        filterRow.addView(spacer, new LinearLayout.LayoutParams(0, 1, 1f));

        TextView shuffle = Ui.pill(this, "🎲 Zufällig", Ui.SECONDARY);
        shuffle.setOnClickListener(v -> randomWallpaper());
        filterRow.addView(shuffle);
    }

    private void randomWallpaper() {
        List<File> videos = Library.videos(this, search.getText().toString(), favoritesOnly);
        if (videos.isEmpty()) {
            setStatus("Keine Wallpaper in der aktuellen Auswahl.", true);
            return;
        }
        File pick = videos.get(new Random().nextInt(videos.size()));
        Library.setActive(this, pick.getAbsolutePath());
        paused = false;
        btnPause.setText("Pause");
        sendCommand(VideoWallpaperService.CMD_RELOAD);
        refresh();
        setStatus("Zufällig gewählt: " + pick.getName());
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Das Wallpaper kann sich (automatischer Wechsel) auch ohne die App geändert haben.
        refresh();
    }

    private void pickVideo() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("video/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(intent, REQ_PICK);
        } catch (Exception e) {
            setStatus("Keine App zum Auswählen gefunden: " + e.getMessage(), true);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_PICK && resultCode == RESULT_OK && data != null && data.getData() != null) {
            importVideo(data.getData());
        }
    }

    /** Kopiert das gewählte Video in den App-Ordner – so bleibt es dauerhaft nutzbar. */
    private void importVideo(final Uri uri) {
        setStatus("Video wird übernommen …");
        new Thread(() -> {
            final File dest = new File(Library.dir(this), System.currentTimeMillis() + ".mp4");
            try (InputStream in = getContentResolver().openInputStream(uri);
                 OutputStream out = new FileOutputStream(dest)) {
                if (in == null) {
                    throw new IllegalStateException("Quelle nicht lesbar");
                }
                byte[] buffer = new byte[1 << 16];
                int read;
                while ((read = in.read(buffer)) > 0) {
                    out.write(buffer, 0, read);
                }
            } catch (Exception e) {
                dest.delete();
                runOnUiThread(() -> setStatus("Import fehlgeschlagen: " + e.getMessage(), true));
                return;
            }
            runOnUiThread(() -> {
                Library.setActive(this, dest.getAbsolutePath());
                paused = false;
                btnPause.setText("Pause");
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                refresh();
                setStatus("Video übernommen – jetzt „Als Live-Wallpaper setzen“.");
            });
        }).start();
    }

    private void nextWallpaper() {
        List<File> videos = Library.videos(this);
        if (videos.isEmpty()) {
            setStatus("Erst ein Video hinzufügen.");
            return;
        }
        File active = Library.activeFile(this);
        int index = 0;
        if (active != null) {
            for (int i = 0; i < videos.size(); i++) {
                if (videos.get(i).getAbsolutePath().equals(active.getAbsolutePath())) {
                    index = (i + 1) % videos.size();
                    break;
                }
            }
        }
        File next = videos.get(index);
        Library.setActive(this, next.getAbsolutePath());
        paused = false;
        btnPause.setText("Pause");
        sendCommand(VideoWallpaperService.CMD_RELOAD);
        refresh();
        setStatus("Wallpaper läuft: " + next.getName());
    }

    private void setAsWallpaper() {
        if (Library.videos(this).isEmpty()) {
            setStatus("Erst ein Video hinzufügen.");
            return;
        }
        sendCommand(VideoWallpaperService.CMD_RESUME);
        ComponentName service = new ComponentName(this, VideoWallpaperService.class);
        Intent direct = new Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER);
        direct.putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, service);
        try {
            startActivity(direct);
        } catch (Exception e) {
            try {
                startActivity(new Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER));
            } catch (Exception e2) {
                setStatus("Live-Wallpaper-Auswahl nicht verfügbar: " + e2.getMessage(), true);
            }
        }
    }

    // ---------------------------------------------------------------- Einstellungen

    private void buildSettings() {
        settings.removeAllViews();

        LinearLayout play = Ui.section(this, settings, "Wiedergabe");
        Ui.block(this, play, "Anpassung",
                "Füllen schneidet zu, Einpassen zeigt Balken, Strecken verzerrt.");
        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        String[] labels = {"Füllen", "Einpassen", "Strecken"};
        String[] values = {Library.FIT_COVER, Library.FIT_CONTAIN, Library.FIT_STRETCH};
        String current = Library.fit(this);
        for (int i = 0; i < labels.length; i++) {
            final String value = values[i];
            TextView chip = Ui.pill(this, labels[i],
                    value.equals(current) ? Ui.CHIP_ON : Ui.CHIP_OFF);
            chip.setOnClickListener(v -> {
                Library.setFit(this, value);
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                buildSettings();
                setStatus("Anpassung: " + value);
            });
            LinearLayout.LayoutParams chipParams = new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            if (i > 0) {
                chipParams.leftMargin = Ui.dp(this, 5);
            }
            chips.addView(chip, chipParams);
        }
        LinearLayout.LayoutParams chipsParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        chipsParams.bottomMargin = Ui.dp(this, 6);
        play.addView(chips, chipsParams);

        Ui.block(this, play, "Automatisch wechseln",
                "Wechselt das Wallpaper in festem Abstand – auch auf dem Homescreen.");
        LinearLayout rotChips = new LinearLayout(this);
        rotChips.setOrientation(LinearLayout.HORIZONTAL);
        int[] minutes = {0, 5, 15, 30, 60};
        String[] rotLabels = {"Aus", "5 Min", "15 Min", "30 Min", "1 Std"};
        int currentRotate = Library.rotateMinutes(this);
        for (int i = 0; i < minutes.length; i++) {
            final int value = minutes[i];
            TextView chip = Ui.pill(this, rotLabels[i],
                    value == currentRotate ? Ui.CHIP_ON : Ui.CHIP_OFF);
            chip.setOnClickListener(v -> {
                Library.setRotateMinutes(this, value);
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                buildSettings();
                setStatus(value == 0 ? "Automatischer Wechsel aus."
                        : "Automatischer Wechsel alle " + value + " Minuten.");
            });
            LinearLayout.LayoutParams chipParams = new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            if (i > 0) {
                chipParams.leftMargin = Ui.dp(this, 5);
            }
            rotChips.addView(chip, chipParams);
        }
        LinearLayout.LayoutParams rotParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        rotParams.bottomMargin = Ui.dp(this, 6);
        play.addView(rotChips, rotParams);

        Ui.block(this, play, "Lautstärke", "Ton des Wallpapers – 0 % ist stumm (unten in der Leiste).");

        LinearLayout wall = Ui.section(this, settings, "Wallpaper");
        LinearLayout wallRow = Ui.block(this, wall, "Live-Wallpaper",
                "Wallura als Live-Wallpaper im System einrichten.");
        TextView set = Ui.pill(this, "Setzen", Ui.PRIMARY);
        set.setOnClickListener(v -> setAsWallpaper());
        wallRow.addView(set);

        LinearLayout updates = Ui.section(this, settings, "Updates");
        LinearLayout updateRow = Ui.block(this, updates, "Wallura " + version,
                "Sucht bei GitHub nach einer neuen Version.");
        TextView check = Ui.pill(this, "Nach Updates suchen", Ui.SECONDARY);
        check.setOnClickListener(v -> checkUpdates());
        updateRow.addView(check);

        LinearLayout storage = Ui.section(this, settings, "Speicher");
        LinearLayout storageRow = Ui.block(this, storage, "Videos", "…");
        storageDesc = (TextView) storageRow.getTag();
        TextView clear = Ui.pill(this, "Alle löschen", Ui.DANGER);
        clear.setOnClickListener(v -> confirmDeleteAll());
        storageRow.addView(clear);

        LinearLayout about = Ui.section(this, settings, "Über");
        Ui.block(this, about, "Wallura " + version,
                "Video-Live-Wallpaper für Android. © 2026 MorreTv. Open Source (MIT).");

        updateStorageText();
    }

    private void updateStorageText() {
        if (storageDesc == null) {
            return;
        }
        int total = Library.videos(this).size();
        float mb = Library.totalBytes(this) / (1024f * 1024f);
        String size = String.format(Locale.GERMANY, "%.1f MB", mb);
        storageDesc.setText((total == 1 ? "1 Video · " : total + " Videos · ") + size);
    }

    private void confirmDeleteAll() {
        new AlertDialog.Builder(this)
                .setTitle("Alle Videos löschen?")
                .setMessage("Die importierten Videos werden aus Wallura entfernt. "
                        + "Die Originale auf dem Handy bleiben erhalten.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Löschen", (dialog, which) -> {
                    Library.deleteAll(this);
                    sendCommand(VideoWallpaperService.CMD_STOP);
                    paused = false;
                    btnPause.setText("Pause");
                    refresh();
                    setStatus("Alle Videos gelöscht.");
                })
                .show();
    }

    private void checkUpdates() {
        setStatus("Suche nach Updates …");
        Updater.check((tag, apkUrl, error) -> {
            if (error != null) {
                setStatus("Update-Suche fehlgeschlagen: " + error, true);
                return;
            }
            if (tag == null || tag.isEmpty()) {
                setStatus("Keine Release-Information gefunden.", true);
                return;
            }
            if (!Updater.isNewer(tag, version)) {
                setStatus("Wallura " + version + " ist aktuell.");
                return;
            }
            setStatus("Update " + tag + " ist verfügbar – Download startet im Browser.");
            openUrl(apkUrl == null || apkUrl.isEmpty()
                    ? "https://github.com/morretv/Wallura/releases/latest" : apkUrl);
        });
    }

    private void openUrl(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            setStatus("Link ließ sich nicht öffnen: " + e.getMessage(), true);
        }
    }

    // ---------------------------------------------------------------- Hilfen

    private void showPage(String name) {
        boolean library = "library".equals(name);
        pageLibrary.setVisibility(library ? View.VISIBLE : View.GONE);
        pageSettings.setVisibility(library ? View.GONE : View.VISIBLE);
        navLibrary.setBackgroundResource(library ? R.drawable.bg_nav_on : R.drawable.bg_nav_off);
        navSettings.setBackgroundResource(library ? R.drawable.bg_nav_off : R.drawable.bg_nav_on);
        navLibrary.setTextColor(Ui.col(this, library ? R.color.text : R.color.muted));
        navSettings.setTextColor(Ui.col(this, library ? R.color.muted : R.color.text));
    }

    private void sendCommand(String cmd) {
        Intent intent = new Intent(VideoWallpaperService.ACTION_COMMAND).setPackage(getPackageName());
        intent.putExtra(VideoWallpaperService.EXTRA_CMD, cmd);
        sendBroadcast(intent);
    }

    private void setStatus(String text) {
        setStatus(text, false);
    }

    private void setStatus(String text, boolean error) {
        status.setText(text);
        status.setTextColor(Ui.col(this, error ? R.color.status_err : R.color.status_ok));
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "";
        }
    }
}
