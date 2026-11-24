package de.wallura.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.MediaPlayer;
import android.os.Build;
import android.service.wallpaper.WallpaperService;
import android.view.SurfaceHolder;

import java.io.File;
import java.util.List;

/** Spielt das ausgewählte Video als Live-Wallpaper (zentriert, bildfüllend, in Schleife). */
public class VideoWallpaperService extends WallpaperService {

    /** Wird von der App gesendet, wenn Video oder Ton geändert wurden. */
    static final String ACTION_REFRESH = "de.wallura.app.REFRESH";

    @Override
    public Engine onCreateEngine() {
        return new VideoEngine();
    }

    private class VideoEngine extends Engine {

        private MediaPlayer player;
        private SurfaceHolder holder;
        private String shownPath;
        private boolean shownMuted;
        private boolean listening;

        private final BroadcastReceiver refresh = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                stop();
                start();
            }
        };

        @Override
        public void onCreate(SurfaceHolder surfaceHolder) {
            super.onCreate(surfaceHolder);
            holder = surfaceHolder;
            IntentFilter filter = new IntentFilter(ACTION_REFRESH);
            try {
                if (Build.VERSION.SDK_INT >= 33) {
                    VideoWallpaperService.this.registerReceiver(refresh, filter,
                            Context.RECEIVER_NOT_EXPORTED);
                } else {
                    VideoWallpaperService.this.registerReceiver(refresh, filter);
                }
                listening = true;
            } catch (Exception ignored) {
                listening = false;
            }
        }

        @Override
        public void onDestroy() {
            if (listening) {
                try {
                    VideoWallpaperService.this.unregisterReceiver(refresh);
                } catch (Exception ignored) {
                }
                listening = false;
            }
            stop();
            super.onDestroy();
        }

        @Override
        public void onSurfaceCreated(SurfaceHolder surfaceHolder) {
            super.onSurfaceCreated(surfaceHolder);
            holder = surfaceHolder;
            start();
        }

        @Override
        public void onSurfaceDestroyed(SurfaceHolder surfaceHolder) {
            super.onSurfaceDestroyed(surfaceHolder);
            holder = null;
            stop();
        }

        @Override
        public void onVisibilityChanged(boolean visible) {
            super.onVisibilityChanged(visible);
            if (visible) {
                start();
            } else {
                stop();
            }
        }

        private String pickPath() {
            String active = Library.active(VideoWallpaperService.this);
            if (active != null && new File(active).isFile()) {
                return active;
            }
            List<File> videos = Library.videos(VideoWallpaperService.this);
            return videos.isEmpty() ? null : videos.get(0).getAbsolutePath();
        }

        private void start() {
            if (holder == null || !holder.getSurface().isValid()) {
                return;
            }
            String path = pickPath();
            if (path == null) {
                stop();
                return;
            }
            boolean muted = Library.muted(VideoWallpaperService.this);
            if (player != null && path.equals(shownPath) && muted == shownMuted) {
                try {
                    if (!player.isPlaying()) {
                        player.start();
                    }
                } catch (Exception ignored) {
                }
                return;
            }
            stop();
            try {
                MediaPlayer mp = new MediaPlayer();
                mp.setDataSource(path);
                mp.setSurface(holder.getSurface());
                mp.setLooping(true);
                mp.setVolume(muted ? 0f : 1f, muted ? 0f : 1f);
                mp.setOnPreparedListener(p -> {
                    try {
                        // Bildfüllend ohne Verzerrung
                        p.setVideoScalingMode(MediaPlayer.VIDEO_SCALING_MODE_SCALE_TO_FIT_WITH_CROPPING);
                        p.start();
                    } catch (Exception ignored) {
                    }
                });
                mp.setOnErrorListener((p, what, extra) -> {
                    stop();
                    return true;
                });
                mp.prepareAsync();
                player = mp;
                shownPath = path;
                shownMuted = muted;
            } catch (Exception e) {
                stop();
            }
        }

        private void stop() {
            MediaPlayer mp = player;
            player = null;
            shownPath = null;
            if (mp != null) {
                try {
                    mp.setSurface(null);
                } catch (Exception ignored) {
                }
                try {
                    mp.release();
                } catch (Exception ignored) {
                }
            }
        }
    }
}
