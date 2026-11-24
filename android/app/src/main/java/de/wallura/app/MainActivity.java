package de.wallura.app;

import android.app.Activity;
import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;
import java.util.Locale;

/** Videobibliothek und Einrichtung des Live-Wallpapers. */
public class MainActivity extends Activity {

    private static final int REQ_PICK = 1001;

    private TextView status;
    private LinearLayout list;
    private CheckBox mute;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        status = findViewById(R.id.status);
        list = findViewById(R.id.list);
        mute = findViewById(R.id.mute);
        mute.setChecked(Library.muted(this));
        mute.setOnCheckedChangeListener((v, checked) -> {
            Library.setMuted(this, checked);
            broadcastRefresh();
        });

        findViewById(R.id.add).setOnClickListener(v -> pickVideo());
        findViewById(R.id.set).setOnClickListener(v -> setAsWallpaper());

        TextView version = findViewById(R.id.version);
        version.setText("Version " + versionName());

        refresh();
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "";
        }
    }

    private void pickVideo() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("video/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(intent, REQ_PICK);
        } catch (Exception e) {
            status.setText("Keine App zum Auswählen gefunden: " + e.getMessage());
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_PICK && resultCode == RESULT_OK && data != null && data.getData() != null) {
            importVideo(data.getData());
        }
    }

    /** Kopiert das gewählte Video in den App-Ordner – so bleibt es auch ohne Dateizugriff nutzbar. */
    private void importVideo(final Uri uri) {
        status.setText("Video wird übernommen …");
        new Thread(() -> {
            File dest = new File(Library.dir(this), System.currentTimeMillis() + ".mp4");
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
                runOnUiThread(() -> status.setText("Import fehlgeschlagen: " + e.getMessage()));
                return;
            }
            runOnUiThread(() -> {
                Library.setActive(this, dest.getAbsolutePath());
                broadcastRefresh();
                refresh();
                status.setText("Video übernommen – oben auf „Als Live-Wallpaper setzen“ tippen.");
            });
        }).start();
    }

    private void setAsWallpaper() {
        if (Library.videos(this).isEmpty()) {
            status.setText("Erst ein Video hinzufügen.");
            return;
        }
        broadcastRefresh();
        ComponentName service = new ComponentName(this, VideoWallpaperService.class);
        Intent direct = new Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER);
        direct.putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, service);
        try {
            startActivity(direct);
        } catch (Exception e) {
            try {
                startActivity(new Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER));
            } catch (Exception e2) {
                status.setText("Live-Wallpaper-Auswahl nicht verfügbar: " + e2.getMessage());
            }
        }
    }

    private void broadcastRefresh() {
        sendBroadcast(new Intent(VideoWallpaperService.ACTION_REFRESH).setPackage(getPackageName()));
    }

    private void refresh() {
        list.removeAllViews();
        List<File> videos = Library.videos(this);
        if (videos.isEmpty()) {
            addHint("Noch keine Videos. Tippe auf „Video hinzufügen“ und wähle ein Video von deinem Handy.");
            return;
        }
        String active = Library.active(this);
        LayoutInflater inflater = LayoutInflater.from(this);
        for (final File file : videos) {
            final String path = file.getAbsolutePath();
            final boolean isActive = path.equals(active);
            View row = inflater.inflate(R.layout.item_video, list, false);

            TextView name = row.findViewById(R.id.video_name);
            name.setText(file.getName());
            TextView meta = row.findViewById(R.id.video_meta);
            meta.setText(String.format(Locale.GERMANY, "%.1f MB", file.length() / (1024.0 * 1024.0))
                    + (isActive ? "  ·  aktiv" : ""));

            Button pick = row.findViewById(R.id.video_pick);
            pick.setText(isActive ? "Aktiv" : "Auswählen");
            pick.setEnabled(!isActive);
            pick.setOnClickListener(v -> {
                Library.setActive(this, path);
                broadcastRefresh();
                refresh();
                status.setText("Video ausgewählt – oben auf „Als Live-Wallpaper setzen“ tippen.");
            });

            row.findViewById(R.id.video_delete).setOnClickListener(v -> {
                if (!file.delete()) {
                    status.setText("Video ließ sich nicht löschen.");
                    return;
                }
                if (path.equals(Library.active(this))) {
                    Library.setActive(this, null);
                }
                broadcastRefresh();
                refresh();
                status.setText("Video gelöscht.");
            });

            list.addView(row);
        }
    }

    private void addHint(String text) {
        TextView hint = new TextView(this);
        hint.setText(text);
        hint.setTextColor(0xFF9AA7B2);
        hint.setTextSize(14);
        hint.setPadding(0, 12, 0, 12);
        list.addView(hint);
    }
}
