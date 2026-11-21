"""Parse third-party addon metadata without executing its source."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import ast
import warnings


def parse_addon_source(source, filename):
    # Legacy addons commonly contain regex literals such as '\\.' without an
    # r prefix. They remain valid Python strings; metadata inspection should not
    # print their compiler warnings as if Logistics itself had emitted them.
    # Keep syntax errors and other warning classes intact, with source context.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message=r'invalid escape sequence', category=SyntaxWarning)
        return ast.parse(source, filename=str(filename))
