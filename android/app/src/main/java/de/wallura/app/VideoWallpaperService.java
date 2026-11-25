package de.wallura.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.service.wallpaper.WallpaperService;
import android.view.SurfaceHolder;

import java.io.File;
import java.util.List;

/** Spielt das gewählte Video als Live-Wallpaper – Anpassung und Lautstärke wie am PC. */
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

        private MediaPlayer player;
        private SurfaceHolder holder;
        private String shownPath;
        private int shownVolume = -1;
        private String shownFit;
        private boolean paused;
        private boolean stopped;
        private boolean listening;

        private final Handler rotateHandler = new Handler(Looper.getMainLooper());

        /** Automatischer Wechsel: nach der eingestellten Zeit das nächste Video zeigen. */
        private final Runnable rotate = new Runnable() {
            @Override
            public void run() {
                int minutes = Library.rotateMinutes(VideoWallpaperService.this);
                if (minutes <= 0 || stopped) {
                    return;
                }
                if (!paused && holder != null) {
                    List<File> videos = Library.videos(VideoWallpaperService.this);
                    if (videos.size() > 1) {
                        File active = Library.activeFile(VideoWallpaperService.this);
                        String activePath = active == null ? null : active.getAbsolutePath();
                        int next = 0;
                        for (int i = 0; i < videos.size(); i++) {
                            if (videos.get(i).getAbsolutePath().equals(activePath)) {
                                next = (i + 1) % videos.size();
                                break;
                            }
                        }
                        Library.setActive(VideoWallpaperService.this, videos.get(next).getAbsolutePath());
                        stop();
                        start();
                    }
                }
                rotateHandler.postDelayed(this, minutes * 60_000L);
            }
        };

        private void scheduleRotation() {
            rotateHandler.removeCallbacks(rotate);
            if (stopped || paused) {
                return;
            }
            int minutes = Library.rotateMinutes(VideoWallpaperService.this);
            if (minutes > 0) {
                rotateHandler.postDelayed(rotate, minutes * 60_000L);
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
                    case CMD_PAUSE:                        paused = true;
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
        }

        @Override
        public void onDestroy() {
            rotateHandler.removeCallbacks(rotate);
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
            } else {
                stop();
                rotateHandler.removeCallbacks(rotate);
            }
        }

        private void applyVolume() {
            if (player == null) {
                return;
            }
            int volume = Library.volume(VideoWallpaperService.this);
            float value = volume / 100f;
            try {
                player.setVolume(value, value);
                shownVolume = volume;
            } catch (Exception ignored) {
            }
        }

        private String pickPath() {
            File active = Library.activeFile(VideoWallpaperService.this);
            return active == null ? null : active.getAbsolutePath();
        }

        private void start() {
            if (stopped || paused) {
                return;
            }
            if (holder == null || !holder.getSurface().isValid()) {
                return;
            }
            String path = pickPath();
            if (path == null) {
                stop();
                return;
            }
            int volume = Library.volume(VideoWallpaperService.this);
            String fit = Library.fit(VideoWallpaperService.this);
            if (player != null && path.equals(shownPath) && volume == shownVolume
                    && fit.equals(shownFit)) {
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
                float value = volume / 100f;
                mp.setVolume(value, value);
                mp.setOnPreparedListener(p -> {
                    try {
                        String mode = Library.fit(VideoWallpaperService.this);
                        if (Library.FIT_CONTAIN.equals(mode)) {
                            p.setVideoScalingMode(MediaPlayer.VIDEO_SCALING_MODE_SCALE_TO_FIT);
                        } else if (Library.FIT_COVER.equals(mode)) {
                            p.setVideoScalingMode(
                                    MediaPlayer.VIDEO_SCALING_MODE_SCALE_TO_FIT_WITH_CROPPING);
                        }
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
