"""Run the unchanged complete native suite in a disposable QA application."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
from .__main__ import NativeCheckApp


def main():
    return NativeCheckApp('Native suite QA', 'io.github.ispaure.logisticsnotebookqa')
