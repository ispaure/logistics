package io.github.ispaure.logisticsmobile;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Own granted streams until complete private copies have been published. */
public final class ReceiveActivity extends Activity {
    private volatile boolean cancelled;
    private TextView status;
    private static final long FILE_LIMIT = 1024L * 1024 * 1024;
    private static final long QUEUE_LIMIT = 4L * FILE_LIMIT;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 24);
        status = new TextView(this);
        status.setText("Receiving files into Inbox…");
        layout.addView(status);
        Button cancel = new Button(this);
        cancel.setText("Cancel remaining files");
        cancel.setOnClickListener(v -> { cancelled = true; cancel.setEnabled(false); });
        layout.addView(cancel);
        Button open = new Button(this);
        open.setText("Open Logisticks");
        open.setEnabled(false);
        open.setOnClickListener(v -> {
            Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                startActivity(launch);
            }
            finish();
        });
        layout.addView(open);
        setContentView(layout, new ViewGroup.LayoutParams(-1, -1));
        // Configuration changes are handled in the manifest. A restored activity
        // must not replay a delivery whose streams might already be consumed.
        if (state != null) {
            status.setText("Receiving was interrupted. Complete files are waiting in Inbox; share missing files again.");
            cancel.setEnabled(false); open.setEnabled(true); return;
        }
        final Intent incoming = getIntent();
        new Thread(() -> {
            int saved = 0, failed = 0;
            try {
                List<Uri> uris = new ArrayList<>();
                if (Intent.ACTION_SEND.equals(incoming.getAction())) {
                    Uri uri = incoming.getParcelableExtra(Intent.EXTRA_STREAM);
                    if (uri != null) uris.add(uri);
                } else if (Intent.ACTION_SEND_MULTIPLE.equals(incoming.getAction())) {
                    ArrayList<Uri> values = incoming.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
                    if (values != null) uris.addAll(values);
                } else { throw new IOException("Unsupported handoff"); }
                if (uris.isEmpty() && incoming.getClipData() != null) {
                    int count = incoming.getClipData().getItemCount();
                    if (count > 100) throw new IOException("Too many files");
                    for (int i = 0; i < count; i++) uris.add(incoming.getClipData().getItemAt(i).getUri());
                }
                if (uris.isEmpty() || uris.size() > 100) throw new IOException("Invalid file count");
                long batch = 0;
                for (Uri uri : new LinkedHashSet<>(uris)) {
                    if (cancelled) break;
                    try { batch += receive(uri, 2 * FILE_LIMIT - batch); saved++; }
                    catch (Exception error) { if (!cancelled) failed++; }
                }
            } catch (Exception error) { failed++; }
            final String message = saved + " file(s) received. Open Logisticks to find them in Inbox."
                + (failed > 0 ? " Some files could not be received; share them again." : "")
                + (cancelled ? " Remaining files cancelled." : "");
            runOnUiThread(() -> { status.setText(message); cancel.setEnabled(false); open.setEnabled(true); });
        }, "Logistics incoming files").start();
    }

    private long receive(Uri uri, long remaining) throws Exception {
        if (uri == null || !"content".equals(uri.getScheme())) throw new IOException("Choose a granted file");
        String name = null;
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) name = cursor.getString(0);
        }
        if (name == null) name = "Shared file";
        if (name.isEmpty() || name.equals(".") || name.equals("..") || name.getBytes(StandardCharsets.UTF_8).length > 240
                || name.contains("/") || name.contains("\\") || name.matches("(?s).*[\\x00-\\x1f].*"))
            throw new IOException("Invalid filename");
        File queue = new File(getNoBackupFilesDir(), "Incoming");
        if (!queue.isDirectory() && !queue.mkdirs()) throw new IOException("Cannot prepare incoming storage");
        // No backup of plaintext intake. Android's rules exclude this owner.
        try (RandomAccessFile guard = new RandomAccessFile(new File(queue, ".producer.lock"), "rw");
             java.nio.channels.FileChannel channel = guard.getChannel();
             java.nio.channels.FileLock lock = channel.tryLock()) {
            if (lock == null) throw new IOException("Another delivery is receiving files");
            long queued = treeSize(queue);
            if (queued >= QUEUE_LIMIT) throw new IOException("Incoming storage is full");
            String id = UUID.randomUUID().toString();
            File partial = new File(queue, id + ".partial");
            if (!partial.mkdir()) throw new IOException("Cannot stage file");
            boolean complete = false;
            try {
                long bytes = 0;
                try (InputStream input = getContentResolver().openInputStream(uri);
                     FileOutputStream output = new FileOutputStream(new File(partial, "payload"))) {
                    if (input == null) throw new IOException("Unavailable stream");
                    byte[] buffer = new byte[256 * 1024]; int count;
                    while ((count = input.read(buffer)) != -1) {
                        if (cancelled || isFinishing()) throw new IOException("Cancelled");
                        bytes += count;
                        if (bytes > FILE_LIMIT || bytes > remaining || queued + bytes > QUEUE_LIMIT)
                            throw new IOException("Incoming size limit exceeded");
                        output.write(buffer, 0, count);
                    }
                    output.getFD().sync();
                }
                try (FileOutputStream output = new FileOutputStream(new File(partial, "metadata.json"))) {
                    output.write(new JSONObject().put("name", name).toString().getBytes(StandardCharsets.UTF_8));
                    output.getFD().sync();
                }
                if (!partial.renameTo(new File(queue, id + ".ready"))) throw new IOException("Cannot finish handoff");
                complete = true;
                return bytes;
            } finally { if (!complete) remove(partial); }
        }
    }

    private static long treeSize(File file) throws IOException {
        try {
            if (android.system.OsConstants.S_ISLNK(android.system.Os.lstat(file.getPath()).st_mode))
                throw new IOException("Linked intake storage");
        } catch (android.system.ErrnoException error) { throw new IOException("Unavailable intake storage"); }
        if (!file.isDirectory()) return file.length();
        long size = 0; File[] children = file.listFiles();
        if (children == null || children.length > 1000) throw new IOException("Incoming storage unavailable");
        for (File child : children) size += treeSize(child);
        return size;
    }
    private static void remove(File file) {
        File[] children = file.listFiles();
        if (children != null) for (File child : children) child.delete();
        file.delete();
    }
    @Override protected void onDestroy() { cancelled = true; super.onDestroy(); }
}
