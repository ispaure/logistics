"""Folder identity and actions share UIKit's safe navigation bar."""


def mount_actions(header, controller):
    """Native symbol items adapt independently, including on iPhone Duo."""
    from .ios_toolbar import mount_actions as mount, mount_leading, vertical_edge
    for button in header.title_actions:
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = header.app, header.window
    # Leading groups follow UIKit's Back item on vertical bars. Keeping Search
    # here places it directly below Back, outside the trailing tools/overflow.
    search = [button for button in header.title_actions
              if getattr(button, 'control_icon', None) == 'find'] if vertical_edge(controller) else []
    mount(controller, header, [button for button in header.title_actions if button not in search])
    mount_leading(controller, search)


def mount(header, controller, title):
    if not type(header._impl).__module__.startswith('toga_iOS.'):
        return
    header.use_native_title()
    mount_actions(header, controller)
    width = max(44, min(220, float(header.window._impl.native.bounds.size.width) - 216))
    header.status.style.font_size = 17 * .75
    identity = next(child for child in header.storage_identity.children if hasattr(child, 'text'))
    controller.navigationItem.titleView = storage_title(title, identity.text, header._storage_kinds, width)
    header._native_title_mounted = True
    header.refresh_status()


def storage_title(title, text, kinds, width):
    """One centered title/subtitle proportion for folders and open documents."""
    from rubicon.objc import ObjCClass, CGRect
    from .appearance import apple_color
    from .hub_icons import icon
    title_size = 17
    from commonUtils.ui.readers.layout import READER_LAYOUT
    subtitle_size = READER_LAYOUT.caption_size
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
    leading.widthAnchor.constraintEqualToAnchor(trailing.widthAnchor).active = True
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
