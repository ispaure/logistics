package io.github.ispaure.logistics.video;

import android.graphics.Bitmap;
import android.graphics.Rect;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;

/** Volatile frame hold while VLC processes a manual Pause; never writes pixels. */
final class PausePresentation {
    private final VideoPlayer owner;
    private ImageView image;
    private Bitmap bitmap;
    private TextureView source;
    PausePresentation(VideoPlayer owner) {
        this.owner = owner;
        owner.root.addOnLayoutChangeListener((view,l,t,r,b,ol,ot,or,ob) -> arrange());
    }
    private void arrange() {
        if (image == null || source == null) return;
        Rect rect = new Rect(0,0,source.getWidth(),source.getHeight());
        owner.root.offsetDescendantRectToMyCoords(source,rect);
        FrameLayout.LayoutParams frame = (FrameLayout.LayoutParams) image.getLayoutParams();
        if (frame.width == rect.width() && frame.height == rect.height() && frame.leftMargin == rect.left && frame.topMargin == rect.top) return;
        frame.width=rect.width(); frame.height=rect.height(); frame.leftMargin=rect.left; frame.topMargin=rect.top;
        image.setLayoutParams(frame);
    }
    private TextureView texture(View view) {
        if (view instanceof TextureView) return (TextureView) view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i=0;i<group.getChildCount();i++) { TextureView found=texture(group.getChildAt(i)); if (found!=null) return found; }
        }
        return null;
    }
    void hold() {
        if (image != null || !owner.player.isPlaying() || !owner.allowed(false)) return;
        TextureView texture = texture(owner.video);
        if (texture == null || !texture.isAvailable() || texture.getWidth() == 0 || texture.getHeight() == 0) return;
        source = texture;
        bitmap = texture.getBitmap();
        if (bitmap == null) return;
        image = new ImageView(owner.activity); image.setImageBitmap(bitmap);
        image.setScaleType(ImageView.ScaleType.FIT_XY);
        image.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        Rect rect = new Rect(0,0,texture.getWidth(),texture.getHeight());
        owner.root.offsetDescendantRectToMyCoords(texture,rect);
        FrameLayout.LayoutParams frame = new FrameLayout.LayoutParams(rect.width(),rect.height());
        frame.leftMargin=rect.left; frame.topMargin=rect.top;
        owner.root.addView(image,1,frame);
    }
    void clear() {
        if (image != null) { owner.root.removeView(image); image.setImageDrawable(null); image=null; }
        if (bitmap != null) { bitmap.recycle(); bitmap=null; }
        source = null;
    }
}
