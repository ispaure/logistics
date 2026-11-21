package io.github.ispaure.logisticsmobile;

import android.content.Context;
import android.content.res.Resources;
import android.graphics.Rect;
import android.view.ActionMode;
import android.view.KeyEvent;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.widget.EditText;

import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import java.util.Collections;

public final class SessionClipboard {
    private static volatile boolean blocked;

    private SessionClipboard() {}

    public static void setBlocked(boolean value) {
        blocked = value;
    }

    private static boolean clipboardItem(int id) {
        return id == android.R.id.copy || id == android.R.id.cut
                || id == android.R.id.paste || id == android.R.id.pasteAsPlainText;
    }

    public static final class Text extends EditText {
        public Text(Context context) {
            super(context);
        }

        @Override
        public boolean onTextContextMenuItem(int id) {
            return (blocked && clipboardItem(id)) || super.onTextContextMenuItem(id);
        }
    }

    public static final class Web extends WebView {
        public Web(Context context) {
            super(context);
            if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                addJavascriptInterface(new State(), "logisticsClipboardPolicy");
                WebViewCompat.addDocumentStartJavaScript(this,
                    "for (const type of ['cut','copy','paste']) {" +
                    "window.addEventListener(type, event => {" +
                    "if (window.logisticsClipboardPolicy.isBlocked()) {" +
                    "event.preventDefault(); event.stopImmediatePropagation();" +
                    "}}, true); }", Collections.singleton("*"));
            }
        }

        @Override
        public boolean dispatchKeyEvent(KeyEvent event) {
            return (blocked && clipboardKey(event)) || super.dispatchKeyEvent(event);
        }

        @Override
        public boolean onKeyShortcut(int keyCode, KeyEvent event) {
            return (blocked && clipboardKey(event)) || super.onKeyShortcut(keyCode, event);
        }

        @Override
        public ActionMode startActionMode(ActionMode.Callback callback, int type) {
            return super.startActionMode(new SelectionActions(callback, getResources()), type);
        }

        @Override
        public ActionMode startActionMode(ActionMode.Callback callback) {
            return super.startActionMode(new SelectionActions(callback, getResources()), ActionMode.TYPE_PRIMARY);
        }
    }

    public static final class State {
        @JavascriptInterface
        public boolean isBlocked() {
            return blocked;
        }
    }

    private static boolean clipboardKey(KeyEvent event) {
        int key = event.getKeyCode();
        if (key == KeyEvent.KEYCODE_COPY || key == KeyEvent.KEYCODE_CUT || key == KeyEvent.KEYCODE_PASTE) {
            return true;
        }
        if (event.isCtrlPressed() || event.isMetaPressed()) {
            return key == KeyEvent.KEYCODE_C || key == KeyEvent.KEYCODE_X || key == KeyEvent.KEYCODE_V
                    || key == KeyEvent.KEYCODE_INSERT;
        }
        return event.isShiftPressed() && (key == KeyEvent.KEYCODE_INSERT || key == KeyEvent.KEYCODE_FORWARD_DEL);
    }

    private static final class SelectionActions extends ActionMode.Callback2 {
        private final ActionMode.Callback delegate;
        private final Resources resources;

        SelectionActions(ActionMode.Callback delegate, Resources resources) {
            this.delegate = delegate;
            this.resources = resources;
        }

        @Override
        public boolean onCreateActionMode(ActionMode mode, Menu menu) {
            return delegate.onCreateActionMode(mode, menu);
        }

        @Override
        public boolean onPrepareActionMode(ActionMode mode, Menu menu) {
            return delegate.onPrepareActionMode(mode, menu);
        }

        @Override
        public boolean onActionItemClicked(ActionMode mode, MenuItem item) {
            return (blocked && isClipboardItem(item.getItemId()))
                    || delegate.onActionItemClicked(mode, item);
        }

        private boolean isClipboardItem(int id) {
            if (clipboardItem(id)) {
                return true;
            }
            try {
                String name = resources.getResourceEntryName(id);
                return name.equals("select_action_menu_copy") || name.equals("select_action_menu_cut");
            } catch (Resources.NotFoundException error) {
                return false;
            }
        }

        @Override
        public void onDestroyActionMode(ActionMode mode) {
            delegate.onDestroyActionMode(mode);
        }

        @Override
        public void onGetContentRect(ActionMode mode, View view, Rect rect) {
            if (delegate instanceof ActionMode.Callback2) {
                ((ActionMode.Callback2) delegate).onGetContentRect(mode, view, rect);
            } else {
                super.onGetContentRect(mode, view, rect);
            }
        }
    }
}
