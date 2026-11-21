"""Focused native encrypted-copy acceptance in an owned disposable QA app."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from .document_workspace_probe import DocumentWorkspaceProbe
from .localcrypt_checks import exercise_localcrypt


class LocalCryptProbe(DocumentWorkspaceProbe):
    result_name = 'localcrypt-result.json'

    async def run_checks(self, app, report):
        await exercise_localcrypt(app, report['cases'])


def main():
    return LocalCryptProbe('LocalCrypt QA', 'io.github.ispaure.logisticsnotebookqa')
