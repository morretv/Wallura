package de.wallura.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.MediaMetadataRetriever;
import android.widget.ImageView;

import java.io.File;
import java.io.FileOutputStream;

/** Vorschaubild einer Videokarte (erstes Bild, als JPEG gecacht). */
final class Thumbs {

    private Thumbs() {
    }

    private static File cacheFile(Context c, File video) {
        File dir = new File(c.getCacheDir(), "thumbs");
        if (!dir.isDirectory()) {
            dir.mkdirs();
        }
        return new File(dir, video.getName().replaceAll("[^A-Za-z0-9._-]", "_") + ".jpg");
    }

    static void load(final Context c, final File video, final ImageView target) {
        final File cached = cacheFile(c, video);
        if (cached.isFile()) {
            Bitmap bmp = BitmapFactory.decodeFile(cached.getAbsolutePath());
            if (bmp != null) {
                target.setImageBitmap(bmp);
                return;
            }
        }
        target.setImageDrawable(null);
        new Thread(() -> {
            Bitmap frame = null;
            MediaMetadataRetriever retriever = new MediaMetadataRetriever();
            try {
                retriever.setDataSource(video.getAbsolutePath());
                frame = retriever.getFrameAtTime(1000000L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
            } catch (Exception ignored) {
            } finally {
                try {
                    retriever.release();
                } catch (Exception ignored) {
                }
            }
            if (frame == null) {
                return;
            }
            final Bitmap small = Bitmap.createScaledBitmap(frame, 148, 92, true);
            try (FileOutputStream out = new FileOutputStream(cached)) {
                small.compress(Bitmap.CompressFormat.JPEG, 80, out);
            } catch (Exception ignored) {
            }
            target.post(() -> target.setImageBitmap(small));
        }).start();
    }

    static void remove(Context c, File video) {
        cacheFile(c, video).delete();
    }
}
