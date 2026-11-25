package de.wallura.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.service.wallpaper.WallpaperService;
import android.view.SurfaceHolder;
import android.widget.Toast;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/** Spielt das gewählte Video als Live-Wallpaper – Anpassung, Tempo und Wechsel wie am PC. */
public class VideoWallpaperService extends WallpaperService {

    static final String ACTION_COMMAND = "de.wallura.app.COMMAND";
    static final String EXTRA_CMD = "cmd";

    static final String CMD_RELOAD = "reload";
    static final String CMD_PAUSE = "pause";
    static final String CMD_RESUME = "resume";
    static final String CMD_STOP = "stop";
    static final String CMD_VOLUME = "volume";

    @Override
    public Engine onCreateEngine() {
        return new VideoEngine();
    }

    private class VideoEngine extends Engine {

        private final Context ctx = VideoWallpaperService.this;

        private MediaPlayer player;
        private SurfaceHolder holder;
        private String shownPath;
        private int shownVolume = -1;
        private String shownFit;
        private float shownSpeed = -1f;
        private String lastMarked;
        private boolean paused;
        private boolean stopped;
        private boolean listening;

        private final Handler rotateHandler = new Handler(Looper.getMainLooper());

        /** Automatischer Wechsel: nach der eingestellten Zeit das nächste Video zeigen. */
        private final Runnable rotate = new Runnable() {
            @Override
            public void run() {
                int minutes = Library.rotateMinutes(ctx);
                if (minutes <= 0 || stopped) {
                    return;
                }
                if (!paused && holder != null && !Library.nightActive(ctx) && !Library.isQuietNow(ctx)) {
                    File next = nextVideo();
                    if (next != null) {
                        Library.setActive(ctx, next.getAbsolutePath());
                        stop();
                        start();
                        if (Library.notifyRotate(ctx)) {
                            Toast.makeText(ctx, "Wallpaper gewechselt: " + Library.displayName(ctx, next),
                                    Toast.LENGTH_SHORT).show();
                        }
                    }
                }
                rotateHandler.postDelayed(this, minutes * 60_000L);
            }
        };

        /** Im Energiesparmodus pausieren, sobald die Option aktiv ist. */
        private final Runnable powerCheck = new Runnable() {
            @Override
            public void run() {
                if (Library.pauseBattery(ctx)) {
                    if (isPowerSave() && player != null) {
                        stop();
                    } else if (!isPowerSave() && player == null && !paused && !stopped) {
                        start();
                    }
                }
                rotateHandler.postDelayed(this, 30_000L);
            }
        };

        private File nextVideo() {
            List<File> videos = Library.rotationList(ctx);
            if (videos.size() < 2) {
                return null;
            }
            File active = Library.activeFile(ctx);
            String activePath = active == null ? null : active.getAbsolutePath();
            if (Library.shuffle(ctx)) {
                List<File> pool = new ArrayList<>();
                for (File f : videos) {
                    if (!f.getAbsolutePath().equals(activePath)) {
                        pool.add(f);
                    }
                }
                return pool.isEmpty() ? null : pool.get(new Random().nextInt(pool.size()));
            }
            for (int i = 0; i < videos.size(); i++) {
                if (videos.get(i).getAbsolutePath().equals(activePath)) {
                    return videos.get((i + 1) % videos.size());
                }
            }
            return videos.get(0);
        }

        private void scheduleRotation() {
            rotateHandler.removeCallbacks(rotate);
            if (stopped || paused) {
                return;
            }
            int minutes = Library.rotateMinutes(ctx);
            if (minutes > 0) {
                rotateHandler.postDelayed(rotate, minutes * 60_000L);
            }
        }

        private boolean isPowerSave() {
            try {
                PowerManager pm = (PowerManager) VideoWallpaperService.this
                        .getSystemService(Context.POWER_SERVICE);
                return pm != null && pm.isPowerSaveMode();
            } catch (Exception e) {
                return false;
            }
        }

        private final BroadcastReceiver commands = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String cmd = intent.getStringExtra(EXTRA_CMD);
                if (cmd == null) {
                    cmd = CMD_RELOAD;
                }
                switch (cmd) {
                    case CMD_PAUSE:
                        paused = true;
                        if (player != null) {
                            try {
                                player.pause();
                            } catch (Exception ignored) {
                            }
                        }
                        break;
                    case CMD_RESUME:
                        paused = false;
                        stopped = false;
                        start();
                        break;
                    case CMD_STOP:
                        paused = false;
                        stopped = true;
                        stop();
                        break;
                    case CMD_VOLUME:
                        applyVolume();
                        break;
                    default:
                        paused = false;
                        stopped = false;
                        stop();
                        start();
                        break;
                }
                scheduleRotation();
            }
        };

        @Override
        public void onCreate(SurfaceHolder surfaceHolder) {
            super.onCreate(surfaceHolder);
            holder = surfaceHolder;
            IntentFilter filter = new IntentFilter(ACTION_COMMAND);
            try {
                if (Build.VERSION.SDK_INT >= 33) {
                    VideoWallpaperService.this.registerReceiver(commands, filter,
                            Context.RECEIVER_NOT_EXPORTED);
                } else {
                    VideoWallpaperService.this.registerReceiver(commands, filter);
                }
                listening = true;
            } catch (Exception ignored) {
                listening = false;
            }
            rotateHandler.postDelayed(powerCheck, 30_000L);
        }

        @Override
        public void onDestroy() {
            rotateHandler.removeCallbacks(rotate);
            rotateHandler.removeCallbacks(powerCheck);
            if (listening) {
                try {
                    VideoWallpaperService.this.unregisterReceiver(commands);
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
            scheduleRotation();
            rotateHandler.removeCallbacks(powerCheck);
            rotateHandler.postDelayed(powerCheck, 30_000L);
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
                scheduleRotation();
                rotateHandler.removeCallbacks(powerCheck);
                rotateHandler.postDelayed(powerCheck, 30_000L);
            } else {
                stop();
                rotateHandler.removeCallbacks(rotate);
                rotateHandler.removeCallbacks(powerCheck);
            }
        }

        private void applyVolume() {
            if (player == null) {
                return;
            }
            int volume = Library.volume(ctx);
            float value = volume / 100f;
            try {
                player.setVolume(value, value);
                shownVolume = volume;
            } catch (Exception ignored) {
            }
        }

        private void applySpeed(MediaPlayer mp) {
            if (mp == null) {
                return;
            }
            try {
                mp.setPlaybackParams(new android.media.PlaybackParams().setSpeed(Library.speed(ctx)));
                shownSpeed = Library.speed(ctx);
            } catch (Exception ignored) {
            }
        }

        /** Nacht-Wallpaper zwischen 20 und 7 Uhr, sonst das aktive Video. */
        private String pickPath() {
            if (Library.nightActive(ctx)) {
                return Library.nightVideo(ctx);
            }
            File active = Library.activeFile(ctx);
            return active == null ? null : active.getAbsolutePath();
        }

        private void start() {
            if (stopped || paused) {
                return;
            }
            if (holder == null || !holder.getSurface().isValid()) {
                return;
            }
            if (Library.pauseBattery(ctx) && isPowerSave()) {
                stop();
                return;
            }
            String path = pickPath();
            if (path == null) {
                stop();
                return;
            }
            int volume = Library.volume(ctx);
            String fit = Library.fit(ctx);
            float speed = Library.speed(ctx);
            if (player != null && path.equals(shownPath) && volume == shownVolume
                    && fit.equals(shownFit) && speed == shownSpeed) {
                try {
                    if (!player.isPlaying()) {
                        player.start();
                        applySpeed(player);
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
                float value = volume / 100f;
                mp.setVolume(value, value);
                mp.setOnPreparedListener(p -> {
                    try {
                        String mode = Library.fit(ctx);
                        if (Library.FIT_CONTAIN.equals(mode)) {
                            p.setVideoScalingMode(MediaPlayer.VIDEO_SCALING_MODE_SCALE_TO_FIT);
                        } else if (Library.FIT_COVER.equals(mode)) {
                            p.setVideoScalingMode(
                                    MediaPlayer.VIDEO_SCALING_MODE_SCALE_TO_FIT_WITH_CROPPING);
                        }
                        applySpeed(p);
                        if (!paused && !stopped) {
                            p.start();
                        }
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
                shownVolume = volume;
                shownFit = fit;
                shownSpeed = speed;
                if (!path.equals(lastMarked)) {
                    lastMarked = path;
                    Library.markPlayed(ctx, path);
                }
            } catch (Exception e) {
                stop();
            }
        }

        private void stop() {
            MediaPlayer mp = player;
            player = null;
            shownPath = null;
            shownVolume = -1;
            shownFit = null;
            shownSpeed = -1f;
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
