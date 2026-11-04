"""Answer native fixture dialogs after UIKit presentation and dismissal retire."""
import asyncio
from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.keyboard import native_value

TEST_STAGE = TestStage.REGRESSION


async def _wait(predicate, deadline, message):
    loop = asyncio.get_running_loop()
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(.01)

async def _presented(get_controller, deadline):
    def ready():
        controller = get_controller()
        return (controller is not None
            and native_value(controller.presentingViewController) is not None
            and native_value(controller.view.window) is not None
            and not native_value(controller.isBeingPresented))
    await _wait(ready, deadline, 'Native dialog presentation did not finish')
    return get_controller()

async def presented_ios_dialog(dialog, *, timeout=5):
    """Return the real controller only after its presentation has completed."""
    return await _presented(lambda: getattr(dialog._impl, 'native', None),
        asyncio.get_running_loop().time() + timeout)

async def _dismiss(controller, deadline):
    from rubicon.objc import Block
    loop = asyncio.get_running_loop()
    view = controller.view
    done = loop.create_future()
    def completed():
        if not done.done():
            done.set_result(None)
    completion = Block(completed, None)
    controller.dismissViewControllerAnimated(False, completion=completion)
    try:
        await asyncio.wait_for(done, max(0, deadline - loop.time()))
    except asyncio.TimeoutError:
        raise AssertionError('Native dialog dismissal completion did not arrive') from None
    await _wait(lambda: native_value(controller.presentingViewController) is None
        and native_value(view.window) is None, deadline, 'Native dialog overlay did not detach')

async def dismiss_ios_controller(controller, *, timeout=5):
    """Retire an actual fixture presentation before dropping its references."""
    deadline = asyncio.get_running_loop().time() + timeout
    await _presented(lambda: controller, deadline)
    await _dismiss(controller, deadline)

async def respond_ios_dialog(dialog, answer, *, timeout=5):
    """Preserve the real modal lifecycle before resolving Toga's response future."""
    deadline = asyncio.get_running_loop().time() + timeout
    controller = await _presented(lambda: getattr(dialog._impl, 'native', None), deadline)
    await _dismiss(controller, deadline)
    dialog._impl.response(answer)
