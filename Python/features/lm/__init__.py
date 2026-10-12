"""OpenAI-compatible chat client; registration does not perform network I/O."""
FEATURE_DESCRIPTION = 'Chat with an existing LM server and keep conversations locally.'


def create_page(parent=None):
    from .page import LMPage
    return LMPage(parent)


def register():
    from pathlib import Path
    from features.contributions import Feature, PageContribution, SettingsContribution
    return Feature(id='lm', label='LM Chat', pages=[
        PageContribution('LM Chat', 'lm.chat', create_page, order=20, navigation_icon='lm'),
    ], settings=[SettingsContribution('Chat defaults', 'lm.defaults',
                                     config_files=(Path(__file__).with_name('config.ini'),),
                                     scope='personal', config_scope='application')])
