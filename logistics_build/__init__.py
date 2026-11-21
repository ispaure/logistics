"""Logistics build policy and adapters for the external build-deployment-manager."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
import sys

# This is the trusted project adapter process, not the manager GUI. Bind the
# consumer's own dependency before importing the external manager's bootstrap.
# The standalone manager keeps its foreign-working-directory protection.
_project_source = Path(__file__).resolve().parents[1] / 'Python'
sys.path.insert(0, str(_project_source))
import commonUtils as _project_commonutils  # noqa: E402,F401
