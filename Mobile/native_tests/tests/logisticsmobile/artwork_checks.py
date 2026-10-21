"""Native background rectangles and pixel ownership; never mock safe insets."""


def snapshot(app):
    state = getattr(app, '_ios_artwork_extension', None)
    if state is None:
        return dict(mode='none')
    canvas = state.owner()
    assert canvas is not None and canvas.image is not None
    assert not state.native.isUserInteractionEnabled()
    assert bool(state.native.accessibilityElementsHidden)
    assert state.picture.image == canvas._impl.picture.image
    root = state.root
    frame = canvas._impl.native.convertRect(canvas._impl.native.bounds, toView=root)
    extension = state.native.frame
    safe = root.safeAreaInsets
    # The image-only surface may overlap a bar; the actual page stays readable.
    assert frame.origin.x >= safe.left - 1, (frame, safe)
    assert frame.origin.x + frame.size.width <= root.bounds.size.width - safe.right + 1, (frame, safe)
    assert extension.size.width > frame.size.width, (frame, extension)
    assert abs(extension.origin.y - frame.origin.y) < 1
    assert abs(extension.size.height - frame.size.height) < 1
    return dict(mode='background', canvas_x=float(frame.origin.x), canvas_width=float(frame.size.width),
                background_x=float(extension.origin.x), background_width=float(extension.size.width),
                safe_left=float(safe.left), safe_right=float(safe.right),
                source_image_reused=True, decorative_interaction=False)
