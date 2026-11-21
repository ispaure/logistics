package io.github.ispaure.logisticsoutgoingreceiver;

// TEST_STAGE = TestStage.REGRESSION

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;

import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class OutgoingReceiver extends Activity {
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        Uri uri = getIntent().getParcelableExtra(Intent.EXTRA_STREAM);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        Button verify = new Button(this);
        verify.setText("Read again");
        verify.setOnClickListener(view -> read(uri, "reopen"));
        content.addView(verify);
        setContentView(content);
        read(uri, "receive");
    }

    private void receipt(String name, String value) {
        try (FileOutputStream output = openFileOutput(name, MODE_PRIVATE)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private void read(Uri uri, String operation) {
        if (uri == null || !"content".equals(uri.getScheme())) {
            receipt(operation, "Expected content URI");
            return;
        }
        try (InputStream input = getContentResolver().openInputStream(uri);
                FileOutputStream output = openFileOutput(operation + ".bin", MODE_PRIVATE)) {
            byte[] buffer = new byte[4096];
            for (int length; (length = input.read(buffer)) != -1;) {
                output.write(buffer, 0, length);
            }
            receipt(operation, uri.toString());
        } catch (Exception error) {
            receipt(operation, error.getClass().getName());
        }
    }
}
