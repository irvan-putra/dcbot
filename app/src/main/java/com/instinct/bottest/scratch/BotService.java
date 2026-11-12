package com.instinct.bottest.scratch;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.io.FileWriter;

public class BotService extends Service {
    private Thread worker;

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel("bot", "Bot validation", NotificationManager.IMPORTANCE_LOW));
        }
        Notification.Builder nb = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, "bot") : new Notification.Builder(this);
        Notification n = nb.setContentTitle("SCRATCH bot validation")
                .setContentText("offline checks running")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MANIFEST);
        } else {
            startForeground(1, n);
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (worker == null || !worker.isAlive()) {
            worker = new Thread(() -> {
                try {
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                    Python.getInstance().getModule("bot_validation")
                            .callAttr("run", getApplicationInfo().nativeLibraryDir, getFilesDir().getAbsolutePath());
                } catch (Exception e) {
                    try {
                        FileWriter w = new FileWriter(new File(getFilesDir(), "validation.log"), true);
                        w.write("java-side error: " + e + "\n"); w.close();
                    } catch (Exception ignored) {}
                }
            }, "bot-validation");
            worker.start();
        }
        return START_STICKY;
    }

    @Override public void onDestroy() {
        stopForeground(true);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent i) { return null; }
}
