"""Logistics native acceptance budgets; generic polling defaults are shared.

Keep deliberate soak/delayed-callback durations beside their scenario. These
defaults describe the common animation boundary, not a way to hide slow tests.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

ROTATION_SETTLE = .6
# A hosted iOS poll can be delayed for over 14 seconds under simulator load.
# Keep native acknowledgement bounded and verify layout separately afterward.
IOS_ROTATION_ACK_TIMEOUT = 20
PROBE_ROTATION_SETTLE = 1
MARKDOWN_ROTATION_SETTLE = 3
CONTROL_SETTLE_TIMEOUT = 2
READER_READY_TIMEOUT = 15
