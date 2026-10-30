"""Construct Qt's audio output without a Python virtual-method trampoline."""


def audio_output(parent):
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    # PySide's QAudioOutputWrapper::disconnectNotify takes the GIL on the
    # FFmpeg audio worker. Track setters keep the GIL while acquiring Qt's
    # connection mutex, producing a lock inversion during renderer retirement.
    # The fixed QML declaration constructs a native C++ QAudioOutput instead.
    engine = QQmlEngine(parent)
    component = QQmlComponent(engine)
    component.setData(b'import QtMultimedia\nAudioOutput {}', QUrl())
    output = component.create()
    if not isinstance(output, QAudioOutput):
        details = '; '.join(error.toString() for error in component.errors())
        engine.deleteLater()
        raise RuntimeError('Cannot construct native video audio output: ' + details)
    QQmlEngine.setObjectOwnership(output, QQmlEngine.ObjectOwnership.CppOwnership)
    output.setParent(parent)
    # Keep the declaration's engine alive exactly as long as its audio output.
    engine.setParent(output)
    return output
