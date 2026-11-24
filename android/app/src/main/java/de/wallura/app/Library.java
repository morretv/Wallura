package de.wallura.app;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** Ablage der importierten Videos und die Einstellungen des Wallpapers. */
final class Library {

    static final String KEY_ACTIVE = "active";
    static final String KEY_VOLUME = "volume";
    static final String KEY_FIT = "fit";

    static final String FIT_COVER = "cover";
    static final String FIT_CONTAIN = "contain";
    static final String FIT_STRETCH = "stretch";

    private static final String PREFS = "wallura";
    private static final String[] EXT = {".mp4", ".webm", ".mkv", ".3gp", ".m4v", ".mov"};

    private Library() {
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /** Ordner mit den importierten Videos (im App-Speicher, damit keine Rechte verloren gehen). */
    static File dir(Context c) {
        File d = new File(c.getFilesDir(), "videos");
        if (!d.isDirectory()) {
            d.mkdirs();
        }
        return d;
    }

    static List<File> videos(Context c) {
        List<File> out = new ArrayList<>();
        File[] files = dir(c).listFiles();
        if (files == null) {
            return out;
        }
        for (File f : files) {
            if (!f.isFile()) {
                continue;
            }
            String n = f.getName().toLowerCase();
            for (String ext : EXT) {
                if (n.endsWith(ext)) {
                    out.add(f);
                    break;
                }
            }
        }
        out.sort((a, b) -> Long.compare(b.lastModified(), a.lastModified()));
        return out;
    }

    static List<File> videos(Context c, String query) {
        List<File> all = videos(c);
        String q = query == null ? "" : query.trim().toLowerCase();
        if (q.isEmpty()) {
            return all;
        }
        List<File> out = new ArrayList<>();
        for (File f : all) {
            if (f.getName().toLowerCase().contains(q)) {
                out.add(f);
            }
        }
        return out;
    }

    static long totalBytes(Context c) {
        long total = 0;
        for (File f : videos(c)) {
            total += f.length();
        }
        return total;
    }

    static String active(Context c) {
        return prefs(c).getString(KEY_ACTIVE, null);
    }

    static void setActive(Context c, String path) {
        prefs(c).edit().putString(KEY_ACTIVE, path).apply();
    }

    /** Das gesetzte Video – oder das erste in der Bibliothek, wenn keins (mehr) existiert. */
    static File activeFile(Context c) {
        String path = active(c);
        if (path != null && new File(path).isFile()) {
            return new File(path);
        }
        List<File> list = videos(c);
        return list.isEmpty() ? null : list.get(0);
    }

    static int volume(Context c) {
        return Math.max(0, Math.min(100, prefs(c).getInt(KEY_VOLUME, 0)));
    }

    static void setVolume(Context c, int value) {
        prefs(c).edit().putInt(KEY_VOLUME, Math.max(0, Math.min(100, value))).apply();
    }

    static String fit(Context c) {
        String fit = prefs(c).getString(KEY_FIT, FIT_COVER);
        return fit == null ? FIT_COVER : fit;
    }

    static void setFit(Context c, String fit) {
        prefs(c).edit().putString(KEY_FIT, fit).apply();
    }

    static void deleteAll(Context c) {
        File[] files = dir(c).listFiles();
        if (files != null) {
            for (File f : files) {
                f.delete();
            }
        }
        setActive(c, null);
        File[] thumbs = new File(c.getCacheDir(), "thumbs").listFiles();
        if (thumbs != null) {
            for (File f : thumbs) {
                f.delete();
            }
        }
    }
}
