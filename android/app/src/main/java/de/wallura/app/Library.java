package de.wallura.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Ablage der importierten Videos und die Einstellungen des Wallpapers. */
final class Library {

    static final String KEY_ACTIVE = "active";
    static final String KEY_VOLUME = "volume";
    static final String KEY_FIT = "fit";
    static final String KEY_FAV = "favorites";
    static final String KEY_ROTATE = "rotate_min";
    static final String KEY_SORT = "sort";
    static final String KEY_FAV_ONLY = "favorites_only";
    static final String KEY_FAV_PLAYLIST = "fav_playlist";
    static final String KEY_QUIET = "quiet_hours";
    static final String KEY_SHUFFLE = "shuffle";
    static final String KEY_ROTATE_TOAST = "notify_rotate";
    static final String KEY_RANDOM_START = "random_start";
    static final String KEY_BATTERY = "pause_battery";
    static final String KEY_SPEED = "speed";
    static final String KEY_NIGHT = "night_video";

    static final String SORT_NEW = "new";
    static final String SORT_AZ = "az";
    static final String SORT_PLAYS = "plays";
    static final String SORT_FAV = "fav";

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

    /** Ordner für das Nacht-Wallpaper (getrennt von der normalen Bibliothek). */
    static File nightDir(Context c) {
        File d = new File(c.getFilesDir(), "night");
        if (!d.isDirectory()) {
            d.mkdirs();
        }
        return d;
    }

    /** Alle Videos in der eingestellten Reihenfolge. */
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
        final String mode = sortMode(c);
        final SharedPreferences p = prefs(c);
        final Set<String> favs = favorites(c);
        out.sort((a, b) -> {
            if (SORT_AZ.equals(mode)) {
                return displayName(c, a).compareToIgnoreCase(displayName(c, b));
            }
            if (SORT_PLAYS.equals(mode)) {
                int pa = p.getInt("plays_" + a.getName(), 0);
                int pb = p.getInt("plays_" + b.getName(), 0);
                if (pa != pb) {
                    return pb - pa;
                }
                return displayName(c, a).compareToIgnoreCase(displayName(c, b));
            }
            if (SORT_FAV.equals(mode)) {
                boolean fa = favs.contains(a.getName());
                boolean fb = favs.contains(b.getName());
                if (fa != fb) {
                    return fa ? -1 : 1;
                }
                return displayName(c, a).compareToIgnoreCase(displayName(c, b));
            }
            return Long.compare(b.lastModified(), a.lastModified());
        });
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
            if (displayName(c, f).toLowerCase().contains(q) || f.getName().toLowerCase().contains(q)) {
                out.add(f);
            }
        }
        return out;
    }

    /** Nur die Favoriten aus einer (ggf. gefilterten) Liste. */
    static List<File> videos(Context c, String query, boolean favoritesOnly) {
        List<File> all = videos(c, query);
        if (!favoritesOnly) {
            return all;
        }
        Set<String> favs = favorites(c);
        List<File> out = new ArrayList<>();
        for (File f : all) {
            if (favs.contains(f.getName())) {
                out.add(f);
            }
        }
        return out;
    }

    /** Playlist für den automatischen Wechsel (optional nur Favoriten). */
    static List<File> rotationList(Context c) {
        List<File> all = videos(c);
        if (!favPlaylist(c)) {
            return all;
        }
        Set<String> favs = favorites(c);
        List<File> out = new ArrayList<>();
        for (File f : all) {
            if (favs.contains(f.getName())) {
                out.add(f);
            }
        }
        return out.isEmpty() ? all : out;
    }

    // ---------------------------------------------------------------- Titel und Statistik

    /** Anzeigename: eigener Titel, sonst der Dateiname. */
    static String displayName(Context c, File file) {
        return prefs(c).getString("title_" + file.getName(), file.getName());
    }

    static void setTitle(Context c, File file, String title) {
        SharedPreferences.Editor e = prefs(c).edit();
        String value = title == null ? "" : title.trim();
        if (value.isEmpty() || value.equals(file.getName())) {
            e.remove("title_" + file.getName());
        } else {
            e.putString("title_" + file.getName(), value);
        }
        e.apply();
    }

    static int plays(Context c, File file) {
        return prefs(c).getInt("plays_" + file.getName(), 0);
    }

    /** Zählt eine Wiedergabe und merkt sich den Zeitpunkt. */
    static void markPlayed(Context c, String path) {
        if (path == null) {
            return;
        }
        File file = new File(path);
        if (!file.isFile()) {
            return;
        }
        SharedPreferences p = prefs(c);
        p.edit().putInt("plays_" + file.getName(), p.getInt("plays_" + file.getName(), 0) + 1)
                .putLong("last_" + file.getName(), System.currentTimeMillis()).apply();
    }

    static void resetStats(Context c) {
        SharedPreferences p = prefs(c);
        SharedPreferences.Editor e = p.edit();
        for (String key : new HashSet<>(p.getAll().keySet())) {
            if (key.startsWith("plays_") || key.startsWith("last_")) {
                e.remove(key);
            }
        }
        e.apply();
    }

    static int totalPlays(Context c) {
        int total = 0;
        for (File f : videos(c)) {
            total += plays(c, f);
        }
        return total;
    }

    /** Titel des meistgespielten Videos oder null. */
    static String topPlayed(Context c) {
        File best = null;
        int bestPlays = 0;
        for (File f : videos(c)) {
            int p = plays(c, f);
            if (p > bestPlays) {
                bestPlays = p;
                best = f;
            }
        }
        return best == null ? null : displayName(c, best) + " (" + bestPlays + "×)";
    }

    // ---------------------------------------------------------------- Favoriten

    static Set<String> favorites(Context c) {
        Set<String> out = new HashSet<>();
        Set<String> raw = prefs(c).getStringSet(KEY_FAV, null);
        if (raw != null) {
            out.addAll(raw);
        }
        return out;
    }

    static boolean isFavorite(Context c, File file) {
        return favorites(c).contains(file.getName());
    }

    /** Schaltet den Favoriten-Stern um. -> true, wenn das Video jetzt Favorit ist. */
    static boolean toggleFavorite(Context c, File file) {
        Set<String> favs = favorites(c);
        boolean on;
        if (favs.remove(file.getName())) {
            on = false;
        } else {
            favs.add(file.getName());
            on = true;
        }
        prefs(c).edit().putStringSet(KEY_FAV, favs).apply();
        return on;
    }

    static int clearFavorites(Context c) {
        int count = favorites(c).size();
        prefs(c).edit().remove(KEY_FAV).apply();
        return count;
    }

    // ---------------------------------------------------------------- Einstellungen

    /** Automatischer Wechsel in Minuten (0 = aus). */
    static int rotateMinutes(Context c) {
        return Math.max(0, prefs(c).getInt(KEY_ROTATE, 0));
    }

    static void setRotateMinutes(Context c, int minutes) {
        prefs(c).edit().putInt(KEY_ROTATE, Math.max(0, minutes)).apply();
    }

    static List<File> duplicates(Context c) {
        List<File> all = videos(c);
        Set<Long> seen = new HashSet<>();
        List<File> out = new ArrayList<>();
        for (File f : all) {
            long key = f.length();
            if (key <= 0) {
                continue;
            }
            if (!seen.add(key)) {
                out.add(f);
            }
        }
        return out;
    }

    static int removeDuplicates(Context c) {
        List<File> dupes = duplicates(c);
        for (File f : dupes) {
            Thumbs.remove(c, f);
            f.delete();
        }
        return dupes.size();
    }

    /** Bibliotheksliste als JSON (ohne Videodateien) für Export/Teilen. */
    static String exportJson(Context c) {
        JSONArray arr = new JSONArray();
        for (File f : videos(c)) {
            try {
                JSONObject o = new JSONObject();
                o.put("name", f.getName());
                o.put("title", displayName(c, f));
                o.put("size", f.length());
                o.put("favorite", isFavorite(c, f));
                o.put("plays", plays(c, f));
                arr.put(o);
            } catch (Exception ignored) {
            }
        }
        return arr.toString();
    }

    static String sortMode(Context c) {
        String mode = prefs(c).getString(KEY_SORT, SORT_NEW);
        if (SORT_AZ.equals(mode) || SORT_PLAYS.equals(mode) || SORT_FAV.equals(mode)) {
            return mode;
        }
        return SORT_NEW;
    }

    static void setSortMode(Context c, String mode) {
        prefs(c).edit().putString(KEY_SORT, mode == null ? SORT_NEW : mode).apply();
    }

    static boolean favoritesOnly(Context c) {
        return prefs(c).getBoolean(KEY_FAV_ONLY, false);
    }

    static void setFavoritesOnly(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_FAV_ONLY, on).apply();
    }

    static boolean favPlaylist(Context c) {
        return prefs(c).getBoolean(KEY_FAV_PLAYLIST, false);
    }

    static void setFavPlaylist(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_FAV_PLAYLIST, on).apply();
    }

    static boolean quietHours(Context c) {
        return prefs(c).getBoolean(KEY_QUIET, false);
    }

    static void setQuietHours(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_QUIET, on).apply();
    }

    static boolean shuffle(Context c) {
        return prefs(c).getBoolean(KEY_SHUFFLE, false);
    }

    static void setShuffle(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_SHUFFLE, on).apply();
    }

    static boolean notifyRotate(Context c) {
        return prefs(c).getBoolean(KEY_ROTATE_TOAST, true);
    }

    static void setNotifyRotate(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_ROTATE_TOAST, on).apply();
    }

    static boolean randomStart(Context c) {
        return prefs(c).getBoolean(KEY_RANDOM_START, false);
    }

    static void setRandomStart(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_RANDOM_START, on).apply();
    }

    static boolean pauseBattery(Context c) {
        return prefs(c).getBoolean(KEY_BATTERY, false);
    }

    static void setPauseBattery(Context c, boolean on) {
        prefs(c).edit().putBoolean(KEY_BATTERY, on).apply();
    }

    static float speed(Context c) {
        float value = prefs(c).getFloat(KEY_SPEED, 1f);
        return value <= 0f ? 1f : value;
    }

    static void setSpeed(Context c, float speed) {
        prefs(c).edit().putFloat(KEY_SPEED, speed <= 0f ? 1f : speed).apply();
    }

    static int quietFrom(Context c) {
        return 22;
    }

    static int quietTo(Context c) {
        return 7;
    }

    /** Ruhezeit: nachts wird nicht automatisch gewechselt. */
    static boolean isQuietNow(Context c) {
        if (!quietHours(c)) {
            return false;
        }
        int hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY);
        return hour >= quietFrom(c) || hour < quietTo(c);
    }

    // ---------------------------------------------------------------- Tag/Nacht

    static String nightVideo(Context c) {
        return prefs(c).getString(KEY_NIGHT, null);
    }

    static void setNightVideo(Context c, String path) {
        prefs(c).edit().putString(KEY_NIGHT, path).apply();
    }

    static void clearNightVideo(Context c) {
        String path = nightVideo(c);
        if (path != null) {
            new File(path).delete();
        }
        prefs(c).edit().remove(KEY_NIGHT).apply();
    }

    static boolean isNightNow() {
        int hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY);
        return hour >= 20 || hour < 7;
    }

    /** True, wenn gerade das Nacht-Wallpaper laufen soll. */
    static boolean nightActive(Context c) {
        String path = nightVideo(c);
        return path != null && new File(path).isFile() && isNightNow();
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
        clearNightVideo(c);
        prefs(c).edit().remove(KEY_FAV).apply();
        resetStats(c);
        File[] thumbs = new File(c.getCacheDir(), "thumbs").listFiles();
        if (thumbs != null) {
            for (File f : thumbs) {
                f.delete();
            }
        }
    }
}
