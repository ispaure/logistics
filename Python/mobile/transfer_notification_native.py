"""Platform presentation for generic transfer outcomes; no execution ownership."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

ANDROID_PERMISSION = 'android.permission.POST_NOTIFICATIONS'
ANDROID_CHANNEL = 'transfer-results'


def backend(app):
    return type(app._impl).__module__.split('.')[0]


def supported(app):
    return backend(app) in {'toga_iOS', 'toga_android'}


def _ios_center():
    from ctypes import CDLL
    from rubicon.objc import ObjCClass

    CDLL('/System/Library/Frameworks/UserNotifications.framework/UserNotifications')
    return ObjCClass('UNUserNotificationCenter').currentNotificationCenter()


def request(app, done):
    """Ask only from the explicit Settings control, and return on the app loop."""
    def complete(granted):
        if not app.loop.is_closed():
            app.loop.call_soon_threadsafe(done, bool(granted))

    if backend(app) == 'toga_iOS':
        from rubicon.objc import Block, objc_id
        from ctypes import c_bool

        _ios_center().requestAuthorizationWithOptions(4, completionHandler=Block(
            lambda granted, error: complete(granted), None, c_bool, objc_id))
    elif backend(app) == 'toga_android':
        from android.os import Build
        activity = app._impl.native
        manager = activity.getSystemService('notification')
        if Build.VERSION.SDK_INT >= 33 and activity.checkSelfPermission(ANDROID_PERMISSION) != 0:
            app._impl.request_permissions([ANDROID_PERMISSION], on_complete=lambda *_:
                complete(activity.checkSelfPermission(ANDROID_PERMISSION) == 0
                         and manager.areNotificationsEnabled()))
        else:
            complete(manager.areNotificationsEnabled())
    else:
        complete(False)


def post(app, notice, *, allow, done):
    if not allow():
        done(False)
    elif backend(app) == 'toga_iOS':
        _post_ios(app, notice, allow, done)
    elif backend(app) == 'toga_android':
        done(_post_android(app, notice))
    else:
        done(False)


def _post_ios(app, notice, allow, done):
    from rubicon.objc import Block, ObjCClass, objc_id

    center = _ios_center()
    loop = app.loop

    def on_loop(callback, *args):
        if not loop.is_closed():
            loop.call_soon_threadsafe(callback, *args)

    def submit(authorized):
        if not authorized or not allow():
            done(False)
            return
        try:
            if ObjCClass('UIApplication').sharedApplication.applicationState != 2:
                done(False)
                return
            content = ObjCClass('UNMutableNotificationContent').alloc().init()
            content.title, content.body = notice.title, notice.message
            request = ObjCClass('UNNotificationRequest').requestWithIdentifier(
                notice.id, content=content, trigger=None)
            center.addNotificationRequest(request, withCompletionHandler=Block(
                lambda error: on_loop(done, not bool(error)), None, objc_id))
        except Exception:
            done(False)

    def settings(value):
        # Authorization can change at any time. Alert or Notification Center
        # must be enabled before attempting delivery.
        try:
            authorized = value.authorizationStatus in (2, 3, 4) and 2 in (
                value.alertSetting, value.notificationCenterSetting, value.lockScreenSetting)
        except Exception:
            authorized = False
        on_loop(submit, authorized)

    center.getNotificationSettingsWithCompletionHandler(Block(settings, None, objc_id))


def _post_android(app, notice):
    from android.app import Notification, NotificationChannel, NotificationManager, PendingIntent
    from android.content import Intent
    from android.os import Build

    context = app._impl.native.getApplicationContext()
    manager = context.getSystemService('notification')
    if (not manager.areNotificationsEnabled()
            or (Build.VERSION.SDK_INT >= 33 and context.checkSelfPermission(ANDROID_PERMISSION) != 0)):
        return False
    if Build.VERSION.SDK_INT >= 26:
        manager.createNotificationChannel(NotificationChannel(
            ANDROID_CHANNEL, 'Transfer results', NotificationManager.IMPORTANCE_DEFAULT))
        if manager.getNotificationChannel(ANDROID_CHANNEL).getImportance() == NotificationManager.IMPORTANCE_NONE:
            return False
        builder = Notification.Builder(context, ANDROID_CHANNEL)
    else:
        builder = Notification.Builder(context)
    builder.setSmallIcon(context.getApplicationInfo().icon)
    builder.setContentTitle(notice.title).setContentText(notice.message)
    builder.setStyle(Notification.BigTextStyle().bigText(notice.message))
    builder.setAutoCancel(True).setVisibility(Notification.VISIBILITY_PUBLIC)
    launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName())
    if launch is not None:
        launch.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        builder.setContentIntent(PendingIntent.getActivity(
            context, 0, launch, PendingIntent.FLAG_IMMUTABLE))
    manager.notify(notice.id, 0, builder.build())
    return True


def banner(app, notice, details):
    text = notice.title + '\n' + notice.message
    if backend(app) == 'toga_android':
        from android.view import View
        from com.google.android.material.snackbar import Snackbar
        from java import dynamic_proxy, jclass

        class OpenDetails(dynamic_proxy(View.OnClickListener)):
            def onClick(self, view):
                details()

        root = app._impl.native.findViewById(jclass('android.R$id').content)
        bar = Snackbar.make(root, text, Snackbar.LENGTH_INDEFINITE)
        bar.setAction('Details', OpenDetails())
        bar.show()
        return bar.dismiss
    if backend(app) == 'toga_iOS':
        return _ios_banner(app, text, details)
    return None


def _ios_banner(app, text, details):
    from rubicon.objc import Block, ObjCClass, objc_id

    action = ObjCClass('UIAction').actionWithHandler(Block(lambda sender: details(), None, objc_id))
    config = ObjCClass('UIButtonConfiguration').filledButtonConfiguration()
    title, _, message = text.partition('\n')
    config.title, config.subtitle = title, message
    button = ObjCClass('UIButton').buttonWithConfiguration(config, primaryAction=action)
    button.accessibilityHint = 'Opens transfer details'
    button.translatesAutoresizingMaskIntoConstraints = False
    window = app.main_window._impl.native
    window.addSubview(button)
    safe = window.safeAreaLayoutGuide
    for constraint in (
        button.leadingAnchor.constraintEqualToAnchor(safe.leadingAnchor, constant=16),
        button.trailingAnchor.constraintEqualToAnchor(safe.trailingAnchor, constant=-16),
        button.bottomAnchor.constraintEqualToAnchor(safe.bottomAnchor, constant=-10),
        button.heightAnchor.constraintGreaterThanOrEqualToConstant(56),
    ):
        constraint.active = True
    return button.removeFromSuperview
