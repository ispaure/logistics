"""Run the unchanged complete native suite in a disposable QA application."""
from .__main__ import NativeCheckApp


def main():
    return NativeCheckApp('Native suite QA', 'io.github.ispaure.logisticsnotebookqa')
