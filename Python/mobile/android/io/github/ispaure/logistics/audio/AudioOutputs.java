package io.github.ispaure.logistics.audio;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Arrays;
import java.util.List;

/** Query anticipated media outputs, never the list of paired/nearby devices. */
public final class AudioOutputs {
    public interface Listener { void changed(); void lost(); }
    private final AudioManager audio;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Listener listener;
    private String previous;
    private final AudioDeviceCallback devices = new AudioDeviceCallback() {
        @Override public void onAudioDevicesAdded(AudioDeviceInfo[] values) { notifyChange(); }
        @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] values) {
            for (AudioDeviceInfo device : values) {
                if (device.isSink()) {
                    Listener value = listener;
                    if (value != null) value.lost();
                    break;
                }
            }
            notifyChange();
        }
    };
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (listener == null) return;
            notifyChange();
            handler.postDelayed(this, 100);
        }
    };
    public AudioOutputs(Context context, Listener value) {
        audio = (AudioManager)context.getSystemService(Context.AUDIO_SERVICE);
        listener = value;
        previous = outputs();
        audio.registerAudioDeviceCallback(devices, handler);
        handler.postDelayed(poll, 100);
    }
    private void notifyChange() {
        String next = outputs();
        if (!next.equals(previous)) {
            previous = next;
            Listener value = listener;
            if (value != null) value.changed();
        }
    }
    public boolean inCall() {
        int mode = audio.getMode();
        return mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_IN_COMMUNICATION || mode == AudioManager.MODE_RINGTONE;
    }
    public String outputs() {
        try {
            List<AudioDeviceInfo> selected;
            if (Build.VERSION.SDK_INT >= 33) {
                selected = audio.getAudioDevicesForAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build());
            } else {
                // Older APIs enumerate connected, not selected, devices. Do not guess.
                selected = Arrays.asList(audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS));
                if (selected.size() != 1) return "null";
            }
            if (selected.isEmpty()) return "null";
            JSONArray rows = new JSONArray();
            for (AudioDeviceInfo device : selected) {
                int type = device.getType();
                boolean bluetooth = type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP || type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    (Build.VERSION.SDK_INT >= 31 && (type == AudioDeviceInfo.TYPE_BLE_HEADSET || type == AudioDeviceInfo.TYPE_BLE_SPEAKER)) ||
                    (Build.VERSION.SDK_INT >= 33 && type == AudioDeviceInfo.TYPE_BLE_BROADCAST);
                String id = bluetooth ? device.getAddress() : Integer.toString(device.getId());
                if (bluetooth && (id == null || id.isEmpty() || "02:00:00:00:00:00".equals(id))) return "null";
                rows.put(new JSONObject().put("id", id).put("type", type).put("bluetooth", bluetooth)
                    .put("name", device.getProductName().toString()));
            }
            return rows.toString();
        } catch (Exception error) {
            return "null"; // Missing permission/identity is never an approved speaker.
        }
    }
    public void close() {
        listener = null;
        handler.removeCallbacks(poll);
        audio.unregisterAudioDeviceCallback(devices);
    }
}
