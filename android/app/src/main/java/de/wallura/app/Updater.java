package de.wallura.app;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/** Fragt die neueste Wallura-Version bei GitHub ab (wie die Update-Suche am PC). */
final class Updater {

    interface Callback {
        void onResult(String tag, String apkUrl, String error);
    }

    private static final String API = "https://api.github.com/repos/morretv/Wallura/releases/latest";

    private Updater() {
    }

    static void check(final Callback callback) {
        new Thread(() -> {
            String tag = null;
            String apkUrl = null;
            String error = null;
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(API).openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(8000);
                conn.setRequestProperty("Accept", "application/vnd.github+json");
                conn.setRequestProperty("User-Agent", "Wallura-Android");
                int code = conn.getResponseCode();
                if (code != 200) {
                    throw new IllegalStateException("HTTP " + code);
                }
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(conn.getInputStream(), "UTF-8"))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        body.append(line);
                    }
                }
                JSONObject json = new JSONObject(body.toString());
                tag = json.optString("tag_name", "");
                JSONArray assets = json.optJSONArray("assets");
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject asset = assets.getJSONObject(i);
                        if ("Wallura.apk".equals(asset.optString("name"))) {
                            apkUrl = asset.optString("browser_download_url");
                        }
                    }
                }
            } catch (Exception e) {
                error = e.getMessage() == null ? e.toString() : e.getMessage();
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
            final String resultTag = tag;
            final String resultUrl = apkUrl;
            final String resultError = error;
            new Handler(Looper.getMainLooper()).post(
                    () -> callback.onResult(resultTag, resultUrl, resultError));
        }).start();
    }

    /** Ist die Version im Release neuer als die installierte? */
    static boolean isNewer(String latest, String current) {
        int[] a = parts(latest);
        int[] b = parts(current);
        for (int i = 0; i < 3; i++) {
            if (a[i] != b[i]) {
                return a[i] > b[i];
            }
        }
        return false;
    }

    private static int[] parts(String version) {
        int[] out = new int[3];
        if (version == null) {
            return out;
        }
        String value = version.trim();
        if (value.startsWith("v") || value.startsWith("V")) {
            value = value.substring(1);
        }
        String[] chunks = value.split("\\.");
        for (int i = 0; i < 3 && i < chunks.length; i++) {
            StringBuilder digits = new StringBuilder();
            for (char ch : chunks[i].toCharArray()) {
                if (Character.isDigit(ch)) {
                    digits.append(ch);
                } else {
                    break;
                }
            }
            if (digits.length() > 0) {
                try {
                    out[i] = Integer.parseInt(digits.toString());
                } catch (Exception ignored) {
                }
            }
        }
        return out;
    }
}
