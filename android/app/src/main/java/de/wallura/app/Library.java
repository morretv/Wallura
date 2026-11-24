package de.wallura.app;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** Ablage der importierten Videos und der aktuellen Auswahl. */
final class Library {

    static final String KEY_ACTIVE = "active";
    static final String KEY_MUTED = "muted";

    private static final String PREFS = "wallura";

    private Library() {
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /** Ordner, in dem die Videos liegen (bleibt beim Deinstallieren nicht erhalten). */
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
            String n = f.getName().toLowerCase();
            if (!f.isFile()) {
                continue;
            }
            if (n.endsWith(".mp4") || n.endsWith(".webm") || n.endsWith(".mkv")
                    || n.endsWith(".3gp") || n.endsWith(".m4v") || n.endsWith(".mov")) {
                out.add(f);
            }
        }
        out.sort((a, b) -> Long.compare(b.lastModified(), a.lastModified()));
        return out;
    }

    static String active(Context c) {
        return prefs(c).getString(KEY_ACTIVE, null);
    }

    static void setActive(Context c, String path) {
        prefs(c).edit().putString(KEY_ACTIVE, path).apply();
    }

    static boolean muted(Context c) {
        return prefs(c).getBoolean(KEY_MUTED, true);
    }

    static void setMuted(Context c, boolean muted) {
        prefs(c).edit().putBoolean(KEY_MUTED, muted).apply();
    }
}
