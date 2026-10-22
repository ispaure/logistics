"""Present the native iOS burst camera without retaining a second camera owner."""


def available(app):
    return type(app.main_window._impl).__module__.startswith('toga_iOS.')


def present(app):
    from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
    from ctypes import c_bool, c_double
    controller = ObjCClass('LGBurstCameraController').alloc().init()
    controller.cameraKey = app.preferences.values['burst_camera']
    controller.framesPerSecond = float(app.preferences.values['burst_photos_per_second'])
    def save(camera, rate):
        try:
            save_camera_preferences(app, str(ObjCInstance(camera)), str(int(rate)))
            return True
        except (OSError, ValueError):
            return False
    # Retain the Python callback for the lifetime of the modal viewer.
    app._burst_camera_callback = Block(save, c_bool, objc_id, c_double)
    controller.savePreferences = app._burst_camera_callback
    controller.modalPresentationStyle = 0  # Full screen; Done controls capture teardown.
    host = app.main_window._impl.native.rootViewController
    while host.presentedViewController:
        host = host.presentedViewController
    host.presentViewController(controller, animated=True, completion=None)


CAMERAS = {
    'rear_wide': 'Rear main (1×)',
    'rear_ultra_wide': 'Rear ultra wide (0.5×)',
    'rear_telephoto': 'Rear telephoto',
    'front': 'Front',
}
RATES = tuple(str(rate) for rate in range(1, 31))
DEFAULTS = {'burst_camera': 'rear_wide', 'burst_photos_per_second': '8'}


def validate_preferences(values):
    if values['burst_camera'] not in CAMERAS:
        raise ValueError('Choose a supported burst camera.')
    if values['burst_photos_per_second'] not in RATES:
        raise ValueError('Choose 1–30 pictures per second.')


def available_cameras():
    from rubicon.objc import ObjCClass
    return [str(key) for key in ObjCClass('LGBurstCameraController').availableCameraKeys()]


def save_camera_preferences(app, camera, rate):
    app.preferences.save(burst_camera=camera, burst_photos_per_second=rate)
    controls = getattr(app, '_burst_preference_controls', None)
    if controls is None:
        return
    choice, speed, labels, status = controls
    app._burst_preference_refresh = True
    try:
        if camera not in labels:
            labels[camera] = CAMERAS[camera]
            choice.items = list(labels.values())
        choice.value = labels[camera]
        speed.value = rate
    finally:
        app._burst_preference_refresh = False
    status.text = 'Camera preferences saved.'


def settings_controls(app, box):
    import toga
    from toga.style import Pack
    from commonUtils.ui.native.forms import FittedLabel as SettingsLabel
    keys = [key for key in available_cameras() if key in CAMERAS]
    saved = app.preferences.values['burst_camera']
    labels = {key: CAMERAS[key] for key in keys}
    if saved not in labels:
        labels[saved] = CAMERAS[saved] + ' (unavailable)'
    camera = toga.Selection(items=list(labels.values()), value=labels[saved], style=Pack(height=48))
    rate = toga.Selection(items=RATES, value=app.preferences.values['burst_photos_per_second'], style=Pack(height=48))
    status = SettingsLabel('Saved automatically. Shared with the controls in Burst camera.', style=Pack(font_size=12))
    box.add(toga.Label('Camera'))
    box.add(camera)
    box.add(toga.Label('Pictures per second'))
    box.add(rate)
    box.add(SettingsLabel('The first photo starts on press. This is the requested rate; camera processing and Photos saving may limit the actual rate.', style=Pack(font_size=12)))
    box.add(status)

    def save(widget, **kwargs):
        if getattr(app, '_burst_preference_refresh', False):
            return
        try:
            save_camera_preferences(app, next(key for key, label in labels.items() if label == camera.value), rate.value)
            status.text = 'Camera preferences saved.'
        except (OSError, ValueError) as error:
            status.text = str(error)

    app._burst_preference_controls = camera, rate, labels, status
    camera.on_change = rate.on_change = save
    return camera, rate, status
