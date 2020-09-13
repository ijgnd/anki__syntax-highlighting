import os

from aqt import mw



user_files_folder = os.path.join(os.path.dirname(__file__), "user_files")


def gc(arg, fail=False):
    conf = mw.addonManager.getConfig(__name__)
    if conf:
        return conf.get(arg, fail)
    else:
        return fail


# Syntax Highlighting (Enhanced Fork) has the id 1972239816 which 
# is loaded after "extended html editor for fields and card templates (with some versioning)"
# with the id 1043915942
try:
    ex_html_edi = __import__("1043915942").dialog_cm.CmDialogBase
except:
    ex_html_edi = False
