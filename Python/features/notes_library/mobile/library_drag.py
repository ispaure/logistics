"""Native, library-local icon drags; payloads contain only an opaque token."""
import posixpath
from pathlib import PurePosixPath
from uuid import uuid4

_ios_classes = None


class NativeRowDrag:
    """Attach the platform's local-only drag interactions to one row owner."""

    def bind(self, widget, path, *, source=True, target=False):
        self.unbind(widget)
        backend = type(widget._impl).__module__
        if backend.startswith('toga_android.'):
            self.bind_android(widget, path, source, target)
        elif backend.startswith('toga_iOS.'):
            self.bind_ios(widget, path, source, target)

    def bind_android(self, widget, path, source, target):
        from android.view import View, DragEvent
        from android.content import ClipData
        from java import dynamic_proxy
        owner, native = self, widget._impl.native
        bindings = []
        if source:
            class Start(dynamic_proxy(View.OnLongClickListener)):
                def onLongClick(self, view):
                    if not owner.start(path):
                        return False
                    clip = ClipData.newPlainText(owner.token, '')
                    started = view.startDragAndDrop(clip, View.DragShadowBuilder(view), None, 0)
                    if not started:
                        owner.end()
                    return started
            listener = Start()
            native.setOnLongClickListener(listener)
            bindings.append(listener)
        if target:
            class Drop(dynamic_proxy(View.OnDragListener)):
                def onDrag(self, view, event):
                    action = event.getAction()
                    if action == DragEvent.ACTION_DRAG_ENDED:
                        owner.end()
                        return True
                    description = event.getClipDescription()
                    if description is None or str(description.getLabel()) != owner.token:
                        return False
                    if action == DragEvent.ACTION_DRAG_STARTED:
                        return owner.source is not None
                    if action in (DragEvent.ACTION_DRAG_ENTERED, DragEvent.ACTION_DRAG_LOCATION):
                        owner.highlight(widget if owner.destination(path) is not None else None)
                    elif action == DragEvent.ACTION_DROP:
                        return owner.drop(path)
                    elif action == DragEvent.ACTION_DRAG_EXITED:
                        owner.highlight(None)
                    elif action == DragEvent.ACTION_DRAG_ENDED:
                        owner.end()
                    return True
            listener = Drop()
            native.setOnDragListener(listener)
            bindings.append(listener)
        self.bindings[widget] = ('android', native, bindings)

    def bind_ios(self, widget, path, source, target):
        global _ios_classes
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_id, ns_from_py
        from rubicon.objc.types import NSInteger
        if _ios_classes is None:
            class LogisticsNotesDragSource(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIDragInteractionDelegate'),)):
                @objc_method
                def dragInteraction_itemsForBeginningSession_(self, interaction, session) -> objc_id:
                    drag = self.drag
                    if drag is None or not drag.start(self.path):
                        return ns_from_py([])
                    provider = ObjCClass('NSItemProvider').alloc().initWithObject(ns_from_py(drag.token))
                    item = ObjCClass('UIDragItem').alloc().initWithItemProvider(provider)
                    item.localObject = ns_from_py(drag.token)
                    return ns_from_py([item])

                @objc_method
                def dragInteraction_sessionIsRestrictedToDraggingApplication_(self, interaction, session) -> bool:
                    return True

                @objc_method
                def dragInteraction_session_didEndWithOperation_(self, interaction, session, operation: NSInteger) -> None:
                    if self.drag is not None:
                        self.drag.end()

            class LogisticsNotesDropTarget(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIDropInteractionDelegate'),)):
                @objc_method
                def dropInteraction_canHandleSession_(self, interaction, session) -> bool:
                    return self.drag is not None and self.drag.source is not None and session.localDragSession is not None

                @objc_method
                def dropInteraction_sessionDidUpdate_(self, interaction, session) -> objc_id:
                    allowed = self.drag is not None and self.drag.destination(self.path) is not None
                    if self.drag is not None:
                        self.drag.highlight(self.widget if allowed else None)
                    return ObjCClass('UIDropProposal').alloc().initWithDropOperation(3 if allowed else 1)

                @objc_method
                def dropInteraction_performDrop_(self, interaction, session) -> None:
                    if self.drag is not None:
                        self.drag.drop(self.path)

                @objc_method
                def dropInteraction_sessionDidExit_(self, interaction, session) -> None:
                    if self.drag is not None:
                        self.drag.highlight(None)

                @objc_method
                def dropInteraction_sessionDidEnd_(self, interaction, session) -> None:
                    if self.drag is not None:
                        self.drag.end()
            _ios_classes = LogisticsNotesDragSource, LogisticsNotesDropTarget
        native, bindings = widget._impl.native, []
        native.userInteractionEnabled = True
        for enabled, name, delegate_class in ((source, 'UIDragInteraction', _ios_classes[0]),
                                               (target, 'UIDropInteraction', _ios_classes[1])):
            if enabled:
                delegate = delegate_class.alloc().init()
                delegate.drag, delegate.path, delegate.widget = self, path, widget
                interaction = ObjCClass(name).alloc().initWithDelegate(delegate)
                if source and name == 'UIDragInteraction':
                    interaction.enabled = True
                native.addInteraction(interaction)
                bindings.append((interaction, delegate))
        self.bindings[widget] = ('ios', native, bindings)

    def unbind(self, widget):
        binding = self.bindings.pop(widget, None)
        if binding is None:
            return
        if self.highlighted is widget:
            self.highlight(None)
        backend, native, bindings = binding
        if backend == 'android':
            native.setOnLongClickListener(None)
            native.setOnDragListener(None)
        else:
            for interaction, delegate in bindings:
                native.removeInteraction(interaction)
                delegate.drag = delegate.widget = None


class LibraryDrag(NativeRowDrag):
    def __init__(self, owner):
        self.owner = owner
        self.token = uuid4().hex
        self.source = None
        self.bindings = {}
        self.highlighted = None
        self.task = None

    def start(self, path):
        if (not self.owner.valid() or self.owner.file_command_busy
                or (self.task is not None and not self.task.done()) or not self.owner.library.supports('rename')):
            return False
        path = self.owner.library.contained(path)
        if path == self.owner.root:
            return False
        self.source = path
        return True

    def destination(self, target):
        if self.source is None or not self.owner.valid() or self.owner.file_command_busy:
            return None
        target = self.owner.library.contained(target)
        destination = posixpath.join(target, PurePosixPath(self.source).name)
        if destination == self.source or target == self.source or target.startswith(self.source + '/'):
            return None
        return destination

    def drop(self, target):
        destination = self.destination(target)
        source, self.source = self.source, None
        self.highlight(None)
        if destination is None:
            return False
        self.task = self.owner.host.loop.create_task(self.owner.move_entry_to(source, destination))
        return True

    def highlight(self, widget):
        if self.highlighted is widget:
            return
        if self.highlighted is not None:
            self.owner.host.highlight_entry(self.highlighted, False)
        self.highlighted = widget
        if widget is not None:
            self.owner.host.highlight_entry(widget, True)

    def end(self):
        self.source = None
        self.highlight(None)

    def dispose(self):
        self.end()
        if self.task is not None and not self.task.done():
            self.task.cancel()
        for widget in list(self.bindings):
            self.unbind(widget)
        self.token = ''
