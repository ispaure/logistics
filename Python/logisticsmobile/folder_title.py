"""Folder identity and actions share UIKit's safe navigation bar."""


def action_group_type():
    global _action_group_type
    if '_action_group_type' not in globals():
        from rubicon.objc import ObjCClass, UIEdgeInsets, objc_method, objc_property, send_super

        class LogisticsFolderActions(ObjCClass('UIStackView')):
            actionWidth = objc_property(object)
            actionBaseWidth = objc_property(object)

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(__class__, self, 'layoutSubviews')
                window = self.window
                window = window() if callable(window) else window
                if window is None or self.actionWidth is None:
                    return
                rect = self.convertRect(self.bounds, toView=window)
                edge = float(window.bounds.size.width) - float(window.safeAreaInsets.right)
                inset = max(0, float(rect.origin.x + rect.size.width) - edge)
                if abs(float(self.layoutMargins.right) - inset) > .5:
                    self.layoutMargins = UIEdgeInsets(0, 0, 0, inset)
                    self.actionWidth.constant = float(self.actionBaseWidth) + inset

        _action_group_type = LogisticsFolderActions
    return _action_group_type


def mount_actions(header, controller):
    """Keep the existing buttons and their native menus in the trailing bar."""
    from rubicon.objc import ObjCClass, CGRect, UIEdgeInsets
    from .ios_reader_chrome import bar_control
    buttons = header.title_actions
    # Use one group so iPad does not collapse separate custom items into More.
    group = action_group_type().alloc().initWithFrame(CGRect((0, 0), (48 * len(buttons), 48)))
    group.translatesAutoresizingMaskIntoConstraints = False
    group.axis, group.distribution, group.alignment, group.spacing = 0, 1, 0, 0
    group.layoutMargins = UIEdgeInsets(0, 0, 0, 0)
    group.layoutMarginsRelativeArrangement = True
    group.actionBaseWidth = 48 * len(buttons)
    group.actionWidth = group.widthAnchor.constraintEqualToConstant(48 * len(buttons))
    group.actionWidth.active = True
    group.heightAnchor.constraintEqualToConstant(48).active = True
    item = ObjCClass('UIBarButtonItem').alloc().initWithCustomView(group)
    for button in buttons:
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = header.app, header.window
        native = bar_control(button)
        native.translatesAutoresizingMaskIntoConstraints = False
        group.addArrangedSubview(native)
    controller.navigationItem.rightBarButtonItems = [item] if buttons else []
    header._native_action_group = group
    header._native_action_item = item


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
