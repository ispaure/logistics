"""Folder identity and actions share UIKit's safe navigation bar."""


def mount_actions(header, controller):
    """Native symbol items adapt independently, including on iPhone Duo."""
    from .ios_toolbar import mount_actions as mount
    for button in header.title_actions:
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = header.app, header.window
    mount(controller, header, header.title_actions)


def mount(header, controller, title):
    if not type(header._impl).__module__.startswith('toga_iOS.'):
        return
    header.use_native_title()
    mount_actions(header, controller)
    from rubicon.objc import ObjCClass, CGRect, CGSize
    from .appearance import apple_color
    from .hub_icons import icon
    # Leave symmetric room for Back and both 48-point actions on a narrow phone.
    # A newly pushed controller may still have zero bounds before its first
    # layout. The owning window already has the actual phone/iPad viewport.
    width = max(44, min(220, float(header.window._impl.native.bounds.size.width) - 216))
    title_size = 17
    subtitle_size = title_size * .75
    header.status.style.font_size = subtitle_size
    view = ObjCClass('UIView').alloc().initWithFrame(CGRect((0, 0), (width, 37)))
    label = ObjCClass('UILabel').alloc().initWithFrame(CGRect((0, 0), (width, 21)))
    label.text = title
    label.font = ObjCClass('UIFont').systemFontOfSize(title_size)
    label.textAlignment = 1
    label.lineBreakMode = 5
    label.textColor = apple_color('text')
    label.autoresizingMask = 2
    view.addSubview(label)
    scroll = ObjCClass('UIScrollView').alloc().initWithFrame(CGRect((0, 22), (width, 15)))
    scroll.autoresizingMask = 2
    scroll.showsHorizontalScrollIndicator = False
    scroll.showsVerticalScrollIndicator = False
    scroll.directionalLockEnabled = True
    row = ObjCClass('UIStackView').alloc().initWithFrame(CGRect((0, 0), (width, 15)))
    row.axis, row.alignment, row.spacing = 0, 1, 4
    leading, trailing = [ObjCClass('UIView').alloc().init() for _ in range(2)]
    row.addArrangedSubview(leading)
    for name, _ in header._storage_kinds:
        image = icon(name)._impl.native.imageWithRenderingMode(2)
        indicator = ObjCClass('UIImageView').alloc().initWithImage(image)
        indicator.contentMode = 1
        indicator.tintColor = apple_color(name if name.startswith('folder_') else 'accent')
        indicator.widthAnchor.constraintEqualToConstant(12).active = True
        indicator.heightAnchor.constraintEqualToConstant(12).active = True
        row.addArrangedSubview(indicator)
    identity = next(child for child in header.storage_identity.children if hasattr(child, 'text'))
    subtitle = ObjCClass('UILabel').alloc().init()
    subtitle.text = identity.text
    subtitle.font = ObjCClass('UIFont').systemFontOfSize(subtitle_size)
    subtitle.textColor = apple_color('muted')
    subtitle.numberOfLines = 1
    subtitle.accessibilityLabel = identity.text
    row.addArrangedSubview(subtitle)
    row.addArrangedSubview(trailing)
    leading.widthAnchor.constraintEqualToAnchor(trailing.widthAnchor).active = True
    # Give the description its full measured width so a horizontal swipe can
    # reveal every word while short descriptions remain centered.
    text_width = float(subtitle.sizeThatFits(CGSize(100000, 15)).width)
    content_width = max(width, text_width + 16 * len(header._storage_kinds) + 8)
    row.frame = CGRect((0, 0), (content_width, 15))
    scroll.contentSize = CGSize(content_width, 15)
    scroll.accessibilityLabel = identity.text
    scroll.addSubview(row)
    view.addSubview(scroll)
    controller.navigationItem.titleView = view
    header._native_title_mounted = True
    header.refresh_status()
