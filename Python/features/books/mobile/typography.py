"""Portable reader appearance contracts and offline CSS; hosts persist values."""
from html import escape
import re

DEFAULTS = {'reading_font': 'system', 'line_spacing': '150', 'reading_width': '800', 'epub_justify': 'false'}
THEMES = ('system', 'light', 'dark', 'sepia', 'slate')
SPACING = tuple(str(value) for value in range(100, 221))
WIDTHS = ('auto', *(str(value) for value in range(480, 1401)))
FONT_SIZES = tuple(str(value) for value in range(12, 33))


def validate(values):
    if values.get('epub_justify', 'false') not in {'true', 'false'}:
        raise ValueError('Invalid EPUB justification preference.')
    font = values['reading_font']
    if not isinstance(font, str) or not re.fullmatch(r'[\w .+\-]{1,100}', font):
        raise ValueError('Choose an installed reading font.')
    if values['line_spacing'] not in SPACING or values['reading_width'] not in WIDTHS:
        raise ValueError('Choose supported spacing and reading width.')
    if values['reading_theme'] not in THEMES:
        raise ValueError('Choose a supported reading theme.')


def options(values):
    merged = dict(DEFAULTS, **{key: values[key] for key in DEFAULTS if key in values})
    validate(dict(merged, reading_theme=values.get('reading_theme', 'system')))
    return dict(font_family=merged['reading_font'], line_spacing=int(merged['line_spacing']),
                reading_width=merged['reading_width'], justify=merged['epub_justify'] == 'true')


def font_families():
    """Local font families only; no downloading fonts or permitting remote CSS."""
    names = {'system', 'serif', 'sans-serif', 'monospace'}
    try:
        from toga.platform import get_factory
        backend = get_factory().WebView.__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            families = ObjCClass('UIFont').familyNames
            names.update(str(value) for value in (families() if callable(families) else families))
        elif backend.startswith('toga_android.'):
            from xml.etree.ElementTree import parse
            for family in parse('/system/etc/fonts.xml').getroot().iter('family'):
                if family.get('name'):
                    names.add(family.get('name'))
    except (OSError, ValueError, AttributeError):
        pass
    return sorted((name for name in names if re.fullmatch(r'[\w .+\-]{1,100}', name)), key=str.casefold)


def css(size, margin, theme, *, font_family='system', line_spacing=150, reading_width='800', justify=False):
    validate(dict(reading_font=font_family, line_spacing=str(line_spacing),
                  reading_width=str(reading_width), reading_theme=theme))
    fonts = {'system': 'system-ui', 'serif': 'serif', 'sans-serif': 'sans-serif', 'monospace': 'monospace'}
    family = fonts.get(font_family, '"' + escape(font_family, quote=True) + '",sans-serif')
    from features.books.themes import THEMES as colors
    background, foreground = colors.get(theme, colors['light'])
    width = 'none' if reading_width == 'auto' else str(reading_width) + 'px'
    # Native title and progress controls already separate the page from chrome.
    # Keep the chosen horizontal gutter without spending it again vertically.
    result = (f'html{{background:{background};color-scheme:{"light dark" if theme == "system" else "dark" if theme in ("dark", "slate") else "light"};'
        '-webkit-text-size-adjust:100%;text-size-adjust:100%}'
        f'body{{background:{background};color:{foreground};font-family:{family};font-size:{size}px;'
        f'line-height:{line_spacing / 100};margin:0 auto;padding:0 {margin}px;max-width:{width};'
        'box-sizing:border-box;overflow-wrap:anywhere}'
        f'p,li{{text-align:var(--logistics-text-align,{"justify" if justify else "start"})}}'
        'p{margin:0 0 1em}h1,h2,h3,h4,h5,h6{line-height:1.25;margin:1.25em 0 .65em;overflow-wrap:break-word}'
        'body>:first-child,[data-logistics-pages]>:first-child{margin-top:0}'
        'blockquote{margin:1em;padding-left:1em;border-left:3px solid currentColor}'
        'img{display:block;margin:1em auto}a{color:inherit;text-decoration:underline;text-underline-offset:.15em}'
        'table{display:block;overflow-x:auto}pre{overflow-wrap:anywhere}'
        '::selection{background:#b4d5fe;color:#202124}')
    if theme == 'system':
        result += '@media(prefers-color-scheme:dark){html,body{background:#111111;color:#eeeeee}}'
    return result
