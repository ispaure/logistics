"""Folder identity and actions share UIKit's safe navigation bar."""


def mount_actions(header, controller):
    """Native symbol items adapt independently, including on iPhone Duo."""
    from .ios_toolbar import mount_actions as mount, vertical_edge
    for button in header.title_actions:
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = header.app, header.window
    # The shared renderer keeps supplemental Search below Back when it fits,
    # and includes it in overflow when system UI leaves too little bar space.
    search = [button for button in header.title_actions
              if getattr(button, 'control_icon', None) == 'find'] if vertical_edge(controller) else []
    mount(controller, header, [button for button in header.title_actions if button not in search],
          supplemental=search)


def mount(header, controller, title):
    if not type(header._impl).__module__.startswith('toga_iOS.'):
        return
    header.use_native_title()
    mount_actions(header, controller)
    width = max(44, min(220, float(header.window._impl.native.bounds.size.width) - 216))
    header.status.style.font_size = 17 * .75
    identity = next(child for child in header.storage_identity.children if hasattr(child, 'text'))
    kinds = tuple(header._storage_kinds)
    state = (title, identity.text, kinds, width, header.folder_location)
    if getattr(header, '_folder_title_state', None) != state:
        from .document_location import bind_apple_hold
        header._folder_title_view = storage_title(title, identity.text, kinds, width)
        bind_apple_hold(header, header._folder_title_view, lambda owner: owner.show_location(name=title))
        header._folder_title_state = state
    if getattr(controller.navigationItem, 'titleView', None) != header._folder_title_view:
        controller.navigationItem.titleView = header._folder_title_view
    header._native_title_mounted = True
    header.refresh_status()


def storage_title_height(text):
    return 37 if text else 21


def storage_title(title, text, kinds, width, *, leading=False, bold=False, title_size=17):
    """Use the same title and subtitle proportions for folders and documents."""
    from rubicon.objc import ObjCClass, CGRect
    from .appearance import apple_color
    from .hub_icons import icon
    from commonUtils.ui.readers.layout import READER_LAYOUT
    subtitle_size = READER_LAYOUT.caption_size
    from commonUtils.ui.native.panning_title import apple_title_class
    label = apple_title_class().alloc().initWithFrame(CGRect((0, 0), (width, storage_title_height(None))))
    label.text = title
    font = ObjCClass('UIFont')
    label.font = font.boldSystemFontOfSize(title_size) if bold else font.systemFontOfSize(title_size)
    label.textAlignment = 0 if leading else 1
    label.lineBreakMode = 5
    label.textColor = apple_color('text')
    label.autoresizingMask = 2
    if not text:
        return label
    view = ObjCClass('UIView').alloc().initWithFrame(CGRect((0, 0), (width, storage_title_height(text))))
    view.addSubview(label)
    scroll = ObjCClass('UIScrollView').alloc().initWithFrame(CGRect((0, 22), (width, 15)))
    scroll.autoresizingMask = 2
    scroll.showsHorizontalScrollIndicator = False
    scroll.showsVerticalScrollIndicator = False
    scroll.directionalLockEnabled = True
    row = ObjCClass('UIStackView').alloc().initWithFrame(CGRect((0, 0), (width, 15)))
    row.axis, row.alignment, row.spacing = 0, 1, 4
    trailing = ObjCClass('UIView').alloc().init()
    if not leading:
        gutter = ObjCClass('UIView').alloc().init()
        row.addArrangedSubview(gutter)
    for name, _ in kinds:
        image = icon(name)._impl.native.imageWithRenderingMode(2)
        indicator = ObjCClass('UIImageView').alloc().initWithImage(image)
        indicator.contentMode = 1
        indicator.tintColor = apple_color(name if name.startswith('folder_') else 'accent')
        indicator.widthAnchor.constraintEqualToConstant(12).active = True
        indicator.heightAnchor.constraintEqualToConstant(12).active = True
        row.addArrangedSubview(indicator)
    subtitle = ObjCClass('UILabel').alloc().init()
    subtitle.text = text
    subtitle.font = ObjCClass('UIFont').systemFontOfSize(subtitle_size)
    subtitle.textColor = apple_color('muted')
    subtitle.numberOfLines = 1
    subtitle.accessibilityLabel = text
    row.addArrangedSubview(subtitle)
    row.addArrangedSubview(trailing)
    if not leading:
        gutter.widthAnchor.constraintEqualToAnchor(trailing.widthAnchor).active = True
    scroll.accessibilityLabel = text
    scroll.addSubview(row)
    # UIKit can shrink a title view after mounting (notably beside Duo's side
    # bar). Track that actual width, with equal gutters for short captions and
    # scrollable intrinsic width for long storage/privacy descriptions.
    row.translatesAutoresizingMaskIntoConstraints = False
    for edge in ('leading', 'trailing', 'top', 'bottom'):
        getattr(row, edge + 'Anchor').constraintEqualToAnchor(
            getattr(scroll.contentLayoutGuide, edge + 'Anchor')).active = True
    row.widthAnchor.constraintGreaterThanOrEqualToAnchor(scroll.frameLayoutGuide.widthAnchor).active = True
    row.heightAnchor.constraintEqualToConstant(15).active = True
    subtitle.setContentCompressionResistancePriority(1000, forAxis=0)
    view.addSubview(scroll)
    return view
