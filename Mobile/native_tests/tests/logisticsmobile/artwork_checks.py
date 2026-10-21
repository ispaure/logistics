"""Native background rectangles and pixel ownership; never mock safe insets."""


async def accessibility_round_trip(app, canvas):
    """Exercise the real observer callback with a forced policy, not OS settings."""
    import asyncio
    from logisticsmobile import ios_content_background as artwork
    kind = bool(getattr(app.body.children[0], '_image_preview_surface', False))
    checked = getattr(app, '_artwork_accessibility_checks', set())
    if kind in checked:
        return
    original = artwork.reduce_transparency
    image = canvas._impl.picture.image
    zoom = float(canvas._impl.native.zoomScale)
    canvas._impl.native.setZoomScale(2, animated=False)
    try:
        artwork.reduce_transparency = lambda: True
        app.screen_privacy.artwork_accessibility_changed()
        await asyncio.sleep(.1)
        assert getattr(app, '_ios_artwork_extension', None) is None
        root = app.body.children[0]._impl.container.native
        frame = canvas._impl.native.convertRect(canvas._impl.native.bounds, toView=root)
        assert frame.origin.x >= root.safeAreaInsets.left - 1, frame
        assert frame.origin.x + frame.size.width <= root.bounds.size.width - root.safeAreaInsets.right + 1, frame
    finally:
        artwork.reduce_transparency = original
        app.screen_privacy.artwork_accessibility_changed()
        await asyncio.sleep(.1)
    assert abs(float(canvas._impl.native.zoomScale) - 2) < .01, 'Relayout lost zoom'
    canvas._impl.native.setZoomScale(zoom, animated=False)
    artwork.sync(app)
    assert canvas._impl.picture.image == image, 'Accessibility relayout replaced the image'
    checked.add(kind)
    app._artwork_accessibility_checks = checked


async def snapshot(app):
    from logisticsmobile.ios_content_background import candidates
    canvases = list(candidates(app.body.children[0]))
    if canvases:
        await accessibility_round_trip(app, canvases[-1])
    state = getattr(app, '_ios_artwork_extension', None)
    if state is None:
        from logisticsmobile.ios_content_background import preview_edge, candidates
        view = app.body.children[0]
        container = view._impl.container
        edge = preview_edge(app, container)
        if edge not in (1, 2):
            return dict(mode='none')
        canvas = next(candidates(view))
        root = container.native
        frame = canvas._impl.native.convertRect(canvas._impl.native.bounds, toView=root)
        safe = root.safeAreaInsets
        if edge == 2:
            assert abs(frame.origin.x + frame.size.width - root.bounds.size.width) < 1, frame
            assert frame.origin.x >= safe.left - 1, frame
        else:
            assert abs(frame.origin.x) < 1, frame
            assert frame.origin.x + frame.size.width <= root.bounds.size.width - safe.right + 1, frame
        assert frame.origin.y >= safe.top - 1, frame
        return dict(mode='image-preview', canvas_x=float(frame.origin.x),
                    canvas_width=float(frame.size.width), root_width=float(root.bounds.size.width),
                    safe_left=float(safe.left), safe_right=float(safe.right))
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
    assert abs(extension.size.height - frame.size.height) < 1, (extension, frame, root.bounds, canvas._impl.native.zoomScale)
    return dict(mode='background', canvas_x=float(frame.origin.x), canvas_width=float(frame.size.width),
                background_x=float(extension.origin.x), background_width=float(extension.size.width),
                safe_left=float(safe.left), safe_right=float(safe.right),
                source_image_reused=True, decorative_interaction=False)
