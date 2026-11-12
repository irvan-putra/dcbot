package com.instinct.bottest.scratch;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;

public class MainActivity extends Activity {
    private TextView logView;
    private final Handler handler = new Handler();

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        Button start = new Button(this); start.setText("Start bot service (offline validation)");
        Button stop = new Button(this); stop.setText("Stop service");
        logView = new TextView(this);
        ScrollView sv = new ScrollView(this); sv.addView(logView);
        root.addView(start); root.addView(stop); root.addView(sv);
        setContentView(root);

        start.setOnClickListener(v -> {
            if (Build.VERSION.SDK_INT >= 33
                    && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 1);
            }
            startForegroundService(new Intent(this, BotService.class));
        });
        stop.setOnClickListener(v -> stopService(new Intent(this, BotService.class)));

        Runnable tick = new Runnable() { public void run() {
            logView.setText(readLog());
            handler.postDelayed(this, 1000);
        }};
        handler.post(tick);
    }

    private String readLog() {
        try {
            File f = new File(getFilesDir(), "validation.log");
            if (!f.exists()) return "(no validation.log yet)";
            byte[] buf = new byte[(int) f.length()];
            FileInputStream in = new FileInputStream(f);
            int n = in.read(buf); in.close();
            return n > 0 ? new String(buf, 0, n) : "(log empty)";
        } catch (Exception e) { return "log read error: " + e; }
    }
}
