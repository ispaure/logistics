"""Focused native encrypted-copy acceptance in an owned disposable QA app."""

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
