package de.wallura.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Bitmap;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Random;

/** Bibliothek, Einstellungen und Wiedergabe – Aufbau und Farben wie am PC. */
public class MainActivity extends Activity {

    private static final int REQ_PICK = 1001;
    private static final int REQ_EXPORT = 1002;
    private static final int REQ_NIGHT = 1003;

    private TextView status;
    private TextView count;
    private EditText search;
    private LinearLayout list;
    private LinearLayout settings;
    private LinearLayout filterRow;
    private LinearLayout sortRow;
    private TextView activeName;
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
        sortRow = findViewById(R.id.lib_sort);
        favoritesOnly = Library.favoritesOnly(this);
        settings = findViewById(R.id.settings_container);
        activeName = findViewById(R.id.active_name);
        volume = findViewById(R.id.volume);
        volumeLabel = findViewById(R.id.volume_lbl);
        navLibrary = findViewById(R.id.nav_library);
        navSettings = findViewById(R.id.nav_settings);
        btnPause = findViewById(R.id.btn_pause);
        pageLibrary = findViewById(R.id.page_library);
        pageSettings = findViewById(R.id.page_settings);

        ((TextView) findViewById(R.id.header_version)).setText("Version " + version);

        navLibrary.setOnClickListener(v -> showPage("library"));
        navSettings.setOnClickListener(v -> showPage("settings"));
        findViewById(R.id.btn_set).setOnClickListener(v -> setAsWallpaper());
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
        buildSort();
        buildSettings();
        showPage("library");
        refresh();
        maybeRandomStart();
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
        activeName.setText(active == null ? "Keins gewählt" : Library.displayName(this, active));

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

            ((TextView) row.findViewById(R.id.video_name)).setText(Library.displayName(this, file));
            int plays = Library.plays(this, file);
            ((TextView) row.findViewById(R.id.video_meta)).setText(
                    String.format(Locale.GERMANY, "%.1f MB", file.length() / (1024.0 * 1024.0))
                            + (plays > 0 ? "  ·  " + plays + "×" : "")
                            + (isActive ? "  ·  aktiv" : ""));
            row.setOnLongClickListener(v -> {
                fileMenu(file);
                return true;
            });
            row.findViewById(R.id.video_edit).setOnClickListener(v -> rename(file));
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
            Library.setFavoritesOnly(this, false);
            buildFilters();
            refresh();
        });
        filterRow.addView(all);

        TextView favs = Ui.pill(this, "★ Favoriten", favoritesOnly ? Ui.CHIP_ON : Ui.CHIP_OFF);
        favs.setOnClickListener(v -> {
            favoritesOnly = true;
            Library.setFavoritesOnly(this, true);
            buildFilters();
            refresh();
        });
        LinearLayout.LayoutParams favParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        favParams.leftMargin = Ui.dp(this, 5);
        filterRow.addView(favs, favParams);

        TextView randomFav = Ui.pill(this, "★🎲", Ui.SECONDARY);
        randomFav.setOnClickListener(v -> randomFavorite());
        LinearLayout.LayoutParams randomFavParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        randomFavParams.leftMargin = Ui.dp(this, 10);
        filterRow.addView(randomFav, randomFavParams);

        TextView shuffle = Ui.pill(this, "🎲 Zufällig", Ui.SECONDARY);
        shuffle.setOnClickListener(v -> randomWallpaper());
        LinearLayout.LayoutParams shuffleParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        shuffleParams.leftMargin = Ui.dp(this, 6);
        filterRow.addView(shuffle, shuffleParams);
    }

    /** Sortier-Chips über der Liste (Neu / A–Z / Meistgesehen / Favoriten zuerst). */
    private void buildSort() {
        sortRow.removeAllViews();
        String[][] modes = {{"Neu", Library.SORT_NEW}, {"A–Z", Library.SORT_AZ},
                {"Meistgesehen", Library.SORT_PLAYS}, {"★ zuerst", Library.SORT_FAV}};
        String current = Library.sortMode(this);
        for (int i = 0; i < modes.length; i++) {
            final String value = modes[i][1];
            TextView chip = Ui.pill(this, modes[i][0], value.equals(current) ? Ui.CHIP_ON : Ui.CHIP_OFF);
            chip.setOnClickListener(v -> {
                Library.setSortMode(this, value);
                buildSort();
                refresh();
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            if (i > 0) {
                params.leftMargin = Ui.dp(this, 6);
            }
            sortRow.addView(chip, params);
        }
    }

    /** Spielt ein Video ab und aktualisiert die Oberfläche. */
    private void playPick(File pick, String prefix) {
        Library.setActive(this, pick.getAbsolutePath());
        paused = false;
        btnPause.setText("Pause");
        sendCommand(VideoWallpaperService.CMD_RELOAD);
        refresh();
        setStatus(prefix + Library.displayName(this, pick));
    }

    private void randomWallpaper() {
        List<File> videos = Library.videos(this, search.getText().toString(), favoritesOnly);
        if (Library.favPlaylist(this)) {
            List<File> favs = new ArrayList<>();
            for (File f : videos) {
                if (Library.isFavorite(this, f)) {
                    favs.add(f);
                }
            }
            if (!favs.isEmpty()) {
                videos = favs;
            }
        }
        if (videos.isEmpty()) {
            setStatus("Keine Wallpaper in der aktuellen Auswahl.", true);
            return;
        }
        File active = Library.activeFile(this);
        List<File> pool = new ArrayList<>();
        for (File f : videos) {
            if (active == null || !f.getAbsolutePath().equals(active.getAbsolutePath())) {
                pool.add(f);
            }
        }
        if (pool.isEmpty()) {
            pool = videos;
        }
        playPick(pool.get(new Random().nextInt(pool.size())), "Zufällig gewählt: ");
    }

    /** Zufällig ein Favorit – ohne den gerade laufenden zu wiederholen. */
    private void randomFavorite() {
        List<File> favs = new ArrayList<>();
        for (File f : Library.videos(this, search.getText().toString(), favoritesOnly)) {
            if (Library.isFavorite(this, f)) {
                favs.add(f);
            }
        }
        if (favs.isEmpty()) {
            setStatus("Keine Favoriten in der Auswahl.", true);
            return;
        }
        File active = Library.activeFile(this);
        File pick = favs.get(new Random().nextInt(favs.size()));
        if (favs.size() > 1 && active != null) {
            for (int i = 0; i < 8 && pick.getAbsolutePath().equals(active.getAbsolutePath()); i++) {
                pick = favs.get(new Random().nextInt(favs.size()));
            }
        }
        playPick(pick, "Favorit: ");
    }

    /** "Zufällig beim Start": beim Öffnen der App ein zufälliges Wallpaper wählen. */
    private void maybeRandomStart() {
        if (!Library.randomStart(this)) {
            return;
        }
        List<File> videos = Library.videos(this);
        if (videos.isEmpty()) {
            return;
        }
        File pick = videos.get(new Random().nextInt(videos.size()));
        Library.setActive(this, pick.getAbsolutePath());
        sendCommand(VideoWallpaperService.CMD_RELOAD);
        refresh();
        setStatus("Zufällig beim Start: " + Library.displayName(this, pick));
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
        if (requestCode == REQ_EXPORT && resultCode == RESULT_OK && data != null && data.getData() != null) {
            try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                if (out != null) {
                    out.write(Library.exportJson(this).getBytes("UTF-8"));
                }
                setStatus("Bibliotheksliste exportiert.");
            } catch (Exception e) {
                setStatus("Export fehlgeschlagen: " + e.getMessage(), true);
            }
        }
        if (requestCode == REQ_NIGHT && resultCode == RESULT_OK && data != null && data.getData() != null) {
            importNight(data.getData());
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
        List<File> videos = Library.videos(this, search.getText().toString(), favoritesOnly);
        if (Library.favPlaylist(this)) {
            List<File> favs = new ArrayList<>();
            for (File f : videos) {
                if (Library.isFavorite(this, f)) {
                    favs.add(f);
                }
            }
            if (!favs.isEmpty()) {
                videos = favs;
            }
        }
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
        playPick(videos.get(index), "Wallpaper läuft: ");
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
        LinearLayout chips = Ui.chipScroll(this, play);
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
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            if (i > 0) {
                chipParams.leftMargin = Ui.dp(this, 6);
            }
            chips.addView(chip, chipParams);
        }

        Ui.block(this, play, "Automatisch wechseln",
                "Wechselt das Wallpaper in festem Abstand – auch auf dem Homescreen.");
        LinearLayout rotChips = Ui.chipScroll(this, play);
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
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            if (i > 0) {
                chipParams.leftMargin = Ui.dp(this, 6);
            }
            rotChips.addView(chip, chipParams);
        }

        Ui.block(this, play, "Geschwindigkeit", "Wiedergabe schneller oder langsamer.");
        LinearLayout speedRow = Ui.chipScroll(this, play);
        float[] speeds = {1f, 1.25f, 1.5f, 2f};
        String[] speedLabels = {"1×", "1,25×", "1,5×", "2×"};
        for (int i = 0; i < speeds.length; i++) {
            final float value = speeds[i];
            TextView chip = Ui.pill(this, speedLabels[i],
                    Math.abs(Library.speed(this) - value) < 0.01f ? Ui.CHIP_ON : Ui.CHIP_OFF);
            chip.setOnClickListener(v -> {
                Library.setSpeed(this, value);
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                buildSettings();
                setStatus("Geschwindigkeit: " + value + "×");
            });
            LinearLayout.LayoutParams chipParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            if (i > 0) {
                chipParams.leftMargin = Ui.dp(this, 6);
            }
            speedRow.addView(chip, chipParams);
        }

        Ui.block(this, play, "Lautstärke", "Ton des Wallpapers – 0 % ist stumm (unten in der Leiste).");

        LinearLayout wall = Ui.section(this, settings, "Wallpaper");
        LinearLayout wallRow = Ui.block(this, wall, "Live-Wallpaper",
                "Wallura als Live-Wallpaper im System einrichten.");
        TextView set = Ui.pill(this, "Setzen", Ui.PRIMARY);
        set.setOnClickListener(v -> setAsWallpaper());
        Ui.wide(Ui.controls(this, wallRow), set);

        LinearLayout updates = Ui.section(this, settings, "Updates");
        LinearLayout updateRow = Ui.block(this, updates, "Wallura " + version,
                "Sucht bei GitHub nach einer neuen Version.");
        TextView check = Ui.pill(this, "Nach Updates suchen", Ui.SECONDARY);
        check.setOnClickListener(v -> checkUpdates());
        Ui.controls(this, updateRow).addView(check);

        LinearLayout storage = Ui.section(this, settings, "Speicher");
        LinearLayout storageRow = Ui.block(this, storage, "Videos", "…");
        storageDesc = (TextView) storageRow.getTag();
        TextView clear = Ui.pill(this, "Alle löschen", Ui.DANGER);
        clear.setOnClickListener(v -> confirmDeleteAll());
        Ui.wide(Ui.controls(this, storageRow), clear);

        LinearLayout change = Ui.section(this, settings, "Wechsel");
        Ui.block(this, change, "Ruhezeiten und Reihenfolge",
                "Nachts pausieren, nur Favoriten wechseln oder zufällig mischen.");
        LinearLayout changeRow = Ui.chipScroll(this, change);
        toggleChip(changeRow, "Nur Favoriten", Library.favPlaylist(this),
                () -> Library.setFavPlaylist(this, !Library.favPlaylist(this)));
        toggleChip(changeRow, "Ruhezeiten 22–7", Library.quietHours(this),
                () -> Library.setQuietHours(this, !Library.quietHours(this)));
        LinearLayout changeRow2 = Ui.chipScroll(this, change);
        toggleChip(changeRow2, "Zufällige Reihenfolge", Library.shuffle(this),
                () -> Library.setShuffle(this, !Library.shuffle(this)));
        toggleChip(changeRow2, "Hinweis", Library.notifyRotate(this),
                () -> Library.setNotifyRotate(this, !Library.notifyRotate(this)));

        LinearLayout power = Ui.section(this, settings, "Akku & Start");
        Ui.block(this, power, "Energiesparmodus",
                "Pausiert das Wallpaper, sobald Android Strom spart.");
        LinearLayout powerRow = Ui.chipScroll(this, power);
        toggleChip(powerRow, "Bei Energiesparen pausieren", Library.pauseBattery(this),
                () -> Library.setPauseBattery(this, !Library.pauseBattery(this)));
        toggleChip(powerRow, "Zufällig beim Start", Library.randomStart(this),
                () -> Library.setRandomStart(this, !Library.randomStart(this)));

        LinearLayout libBox = Ui.section(this, settings, "Bibliothek");
        LinearLayout statsRow = Ui.block(this, libBox, "Statistik", statsText());
        TextView reset = Ui.pill(this, "Zurücksetzen", Ui.GHOST);
        reset.setOnClickListener(v -> {
            Library.resetStats(this);
            buildSettings();
            refresh();
            setStatus("Wiedergabe-Statistik zurückgesetzt.");
        });
        Ui.controls(this, statsRow).addView(reset);
        LinearLayout cleanRow = Ui.block(this, libBox, "Aufräumen",
                "Doppelte Videos, Favoriten und Vorschaubilder.");
        LinearLayout cleanBtns = new LinearLayout(this);
        cleanBtns.setOrientation(LinearLayout.HORIZONTAL);
        TextView dupes = Ui.pill(this, "Duplikate", Ui.SECONDARY);
        dupes.setOnClickListener(v -> {
            int removed = Library.removeDuplicates(this);
            refresh();
            buildSettings();
            setStatus(removed == 0 ? "Keine doppelten Videos gefunden."
                    : removed + " doppelte Videos entfernt.");
        });
        cleanBtns.addView(dupes);
        TextView clearFavs = Ui.pill(this, "Favoriten", Ui.GHOST);
        clearFavs.setOnClickListener(v -> {
            int count = Library.clearFavorites(this);
            refresh();
            buildSettings();
            setStatus(count == 0 ? "Keine Favoriten vorhanden."
                    : count + " Favoriten entfernt.");
        });
        LinearLayout.LayoutParams btnGap = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        btnGap.leftMargin = Ui.dp(this, 5);
        cleanBtns.addView(clearFavs, btnGap);
        TextView thumbsBtn = Ui.pill(this, "Vorschauen", Ui.GHOST);
        thumbsBtn.setOnClickListener(v -> {
            Thumbs.clear(this);
            refresh();
            setStatus("Vorschaubilder werden neu erzeugt.");
        });
        LinearLayout.LayoutParams thumbsGap = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        thumbsGap.leftMargin = Ui.dp(this, 5);
        cleanBtns.addView(thumbsBtn, thumbsGap);
        HorizontalScrollView cleanScroll = new HorizontalScrollView(this);
        cleanScroll.setHorizontalScrollBarEnabled(false);
        cleanScroll.addView(cleanBtns);
        Ui.controls(this, cleanRow).addView(cleanScroll);
        LinearLayout exportRow = Ui.block(this, libBox, "Export",
                "Bibliotheksliste als JSON sichern (ohne Videodateien).");
        TextView export = Ui.pill(this, "Exportieren", Ui.SECONDARY);
        export.setOnClickListener(v -> exportLibrary());
        Ui.wide(Ui.controls(this, exportRow), export);

        LinearLayout night = Ui.section(this, settings, "Tag/Nacht");
        LinearLayout nightRow = Ui.block(this, night, "Nacht-Wallpaper",
                "Zwischen 20 und 7 Uhr läuft automatisch ein eigenes Video.");
        TextView chooseNight = Ui.pill(this, Library.nightVideo(this) == null ? "Wählen" : "Ändern",
                Ui.SECONDARY);
        chooseNight.setOnClickListener(v -> pickNight());
        LinearLayout nightActs = Ui.controls(this, nightRow);
        nightActs.addView(chooseNight);
        if (Library.nightVideo(this) != null) {
            TextView removeNight = Ui.pill(this, "Entfernen", Ui.GHOST);
            removeNight.setOnClickListener(v -> {
                Library.clearNightVideo(this);
                buildSettings();
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                setStatus("Nacht-Wallpaper entfernt.");
            });
            LinearLayout.LayoutParams removeParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            removeParams.leftMargin = Ui.dp(this, 6);
            nightActs.addView(removeNight, removeParams);
        }

        LinearLayout lock = Ui.section(this, settings, "Sperrbildschirm");
        LinearLayout lockRow = Ui.block(this, lock, "Standbild setzen",
                "Aktuelles Video als Bild auf dem Sperrbildschirm.");
        TextView lockBtn = Ui.pill(this, "Setzen", Ui.PRIMARY);
        lockBtn.setOnClickListener(v -> setLockscreen());
        Ui.wide(Ui.controls(this, lockRow), lockBtn);

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

    // ---------------------------------------------------------------- Neue Funktionen

    /** Sortier-/Umschalt-Chip für die Einstellungen. */
    private void toggleChip(LinearLayout row, String label, boolean on, Runnable action) {
        TextView chip = Ui.pill(this, label, on ? Ui.CHIP_ON : Ui.CHIP_OFF);
        chip.setOnClickListener(v -> {
            action.run();
            buildSettings();
            refresh();
        });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.leftMargin = Ui.dp(this, 6);
        row.addView(chip, params);
    }

    /** Langes Drücken auf eine Karte: umbenennen oder Favorit umschalten. */
    private void fileMenu(final File file) {
        new AlertDialog.Builder(this)
                .setTitle(Library.displayName(this, file))
                .setItems(new String[]{"Umbenennen", "Favorit umschalten"}, (dialog, which) -> {
                    if (which == 0) {
                        rename(file);
                    } else {
                        boolean now = Library.toggleFavorite(this, file);
                        refresh();
                        setStatus(now ? "Zu Favoriten hinzugefügt." : "Aus Favoriten entfernt.");
                    }
                })
                .show();
    }

    /** Eigener Titel für ein Video (wird in Suche und Liste verwendet). */
    private void rename(final File file) {
        final EditText input = new EditText(this);
        input.setText(Library.displayName(this, file));
        input.setSelection(input.getText().length());
        new AlertDialog.Builder(this)
                .setTitle("Titel ändern")
                .setView(input)
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Speichern", (dialog, which) -> {
                    Library.setTitle(this, file, input.getText().toString());
                    refresh();
                    setStatus("Titel geändert.");
                })
                .show();
    }

    private String statsText() {
        int total = Library.videos(this).size();
        int favs = Library.favorites(this).size();
        float mb = Library.totalBytes(this) / (1024f * 1024f);
        String text = total + " Videos · " + favs + " Favoriten · "
                + String.format(Locale.GERMANY, "%.1f MB", mb) + " · "
                + Library.totalPlays(this) + " Wiedergaben";
        String top = Library.topPlayed(this);
        if (top != null) {
            text += " · meistgesehen: " + top;
        }
        return text;
    }

    private void exportLibrary() {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.putExtra(Intent.EXTRA_TITLE, "wallura-bibliothek.json");
        try {
            startActivityForResult(intent, REQ_EXPORT);
        } catch (Exception e) {
            setStatus("Export nicht möglich: " + e.getMessage(), true);
        }
    }

    private void pickNight() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("video/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(intent, REQ_NIGHT);
        } catch (Exception e) {
            setStatus("Keine App zum Auswählen gefunden: " + e.getMessage(), true);
        }
    }

    /** Kopiert das gewählte Nacht-Video in den App-Ordner. */
    private void importNight(final Uri uri) {
        setStatus("Nacht-Wallpaper wird übernommen …");
        new Thread(() -> {
            File dir = Library.nightDir(this);
            File[] old = dir.listFiles();
            if (old != null) {
                for (File f : old) {
                    f.delete();
                }
            }
            final File dest = new File(dir, "night.mp4");
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
                runOnUiThread(() -> setStatus("Nacht-Wallpaper fehlgeschlagen: " + e.getMessage(), true));
                return;
            }
            Library.setNightVideo(this, dest.getAbsolutePath());
            runOnUiThread(() -> {
                buildSettings();
                sendCommand(VideoWallpaperService.CMD_RELOAD);
                setStatus("Nacht-Wallpaper gesetzt (20–7 Uhr).");
            });
        }).start();
    }

    /** Standbild des aktiven Videos als Sperrbildschirm setzen. */
    private void setLockscreen() {
        final File active = Library.activeFile(this);
        if (active == null) {
            setStatus("Erst ein Video hinzufügen.", true);
            return;
        }
        setStatus("Erstelle Bild für den Sperrbildschirm …");
        new Thread(() -> {
            Bitmap frame = null;
            MediaMetadataRetriever retriever = new MediaMetadataRetriever();
            try {
                retriever.setDataSource(active.getAbsolutePath());
                frame = retriever.getFrameAtTime(1000000L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
            } catch (Exception ignored) {
            } finally {
                try {
                    retriever.release();
                } catch (Exception ignored) {
                }
            }
            if (frame == null) {
                runOnUiThread(() -> setStatus("Kein Bild im Video gefunden.", true));
                return;
            }
            try {
                ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                frame.compress(Bitmap.CompressFormat.JPEG, 90, buffer);
                try (InputStream in = new ByteArrayInputStream(buffer.toByteArray())) {
                    WallpaperManager.getInstance(this).setStream(in, null, true, WallpaperManager.FLAG_LOCK);
                }
                runOnUiThread(() -> setStatus("Sperrbildschirm gesetzt."));
            } catch (Exception e) {
                runOnUiThread(() -> setStatus("Sperrbildschirm fehlgeschlagen: " + e.getMessage(), true));
            }
        }).start();
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
