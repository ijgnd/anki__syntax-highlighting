import os
import sys
import re
import shutil

addon_path = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(addon_path, "libs"))

from bs4 import BeautifulSoup
from pygments import highlight
from pygments.lexers import get_lexer_by_name, get_all_lexers
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from pygments.styles import get_all_styles

import aqt
from aqt.qt import *
from aqt import mw
from aqt.editor import Editor
from aqt.utils import showWarning, showInfo
from anki.utils import json
from anki.hooks import addHook, wrap

from .config import gc
from .fuzzy_panel import FilterDialog
from .settings import MyConfigWindow
from .supplementary import wrap_in_tags


############################################
########## gui config and auto loading #####

def set_some_paths():
    global addon_path
    global addonfoldername
    global addonname
    global css_templates_folder
    global mediafolder
    global css_file_in_media
    addon_path = os.path.dirname(__file__)
    addonfoldername = os.path.basename(addon_path)
    addonname = mw.addonManager.addonName(addonfoldername)
    css_templates_folder = os.path.join(addon_path, "css")
    mediafolder = os.path.join(mw.pm.profileFolder(), "collection.media")
    css_file_in_media = os.path.join(mediafolder, "_styles_for_syntax_highlighting.css")
addHook("profileLoaded", set_some_paths)


insertscript = """<script>
function MyInsertHtml(content) {
    var s = window.getSelection();
    var r = s.getRangeAt(0);
    r.collapse(true);
    var mydiv = document.createElement("div");
    mydiv.innerHTML = content;
    r.insertNode(mydiv);
    // Move the caret
    r.setStartAfter(mydiv);
    r.collapse(true);
    s.removeAllRanges();
    s.addRange(r);
}
</script>
"""

def profileLoaded():
    editor_style = ""
    if os.path.isfile(css_file_in_media):
        with open(css_file_in_media, "r") as css_file:
            css = css_file.read()
            editor_style = "<style>\n{}\n</style>".format(css.replace("%", "%%"))
    aqt.editor._html = editor_style + insertscript + aqt.editor._html
addHook("profileLoaded", profileLoaded)


def update_templates(templatenames):
    for m in mw.col.models.all():
        if m['name'] in templatenames:
            # https://github.com/trgkanki/cloze_hide_all/issues/43
            lines = [
                """@import url("_styles_for_syntax_highlighting.css");""",
                """@import url(_styles_for_syntax_highlighting.css);""",
            ]
            for l in lines:
                if l in m['css']:
                    break
            else:
                model = mw.col.models.get(m['id'])
                model['css'] = line + "\n\n" + model['css']
                mw.col.models.save(model, templates=True)


def styles_that_need_css():
    styles_to_set = []
    for s in get_all_styles():
        if mw.col.find_cards(f"shf__{s}__highlight"):
            styles_to_set.append(s)
    return styles_to_set


# font_for_line_numbers
css_to_set_font_for_line_numbers = """
.shf__{style}__highlighttable tbody tr td.linenos div.linenodiv pre span {{
    font-family: {font};
}}

.shf__{style}__highlighttable tbody tr td.linenos div.linenodiv pre {{
    font-family: {font};
}}
"""


def css_for_style(style, also_default_highlight_class=False):
    template_file = os.path.join(css_templates_folder, style + ".css")
    with open(template_file) as f:
        css = f.read()
    font = gc("font", "Droid Sans Mono")
    withfonts = css % (font, font, font)
    withstyles = withfonts.replace(".highlight", f".shf__{style}__highlight")
    line_number_fix = css_to_set_font_for_line_numbers.format(style=style, font=font)
    final = withstyles + "\n\n\n" + line_number_fix 
    if also_default_highlight_class:
        final += "\n\n\n" + withfonts
    return final


def update_cssfile_in_mediafolder(style):
    css = css_for_style(style, True)
    also_include = styles_that_need_css()
    if style in also_include:
        also_include.remove(style)
    for s in also_include:
        css += "\n\n\n\n\n" + css_for_style(s)
    with open(css_file_in_media, "w") as f:
        f.write(css)


def onMySettings():
    dialog = MyConfigWindow(mw, mw.addonManager.getConfig(__name__))
    dialog.activateWindow()
    dialog.raise_()
    if dialog.exec_():
        mw.addonManager.writeConfig(__name__, dialog.config)
        if hasattr(dialog, "templates_to_update"):
            update_templates(dialog.templates_to_update)
        update_cssfile_in_mediafolder(dialog.config["style"])
        showInfo("You need to restart Anki so that all changes take effect.")
mw.addonManager.setConfigAction(__name__, onMySettings)


#######END gui config and auto loading #####
############################################




# This code sets a correspondence between:
#  The "language names": long, descriptive names we want
#                        to show the user AND
#  The "language aliases": short, cryptic names for internal
#                          use by HtmlFormatter
LANG_MAP = {lex[0]: lex[1][0] for lex in get_all_lexers()}

ERR_LEXER = ("<b>Error</b>: Selected language not found.<br>"
             "A common source of errors: When you update the add-on Anki keeps your user settings"
             "but an update of the add-on might include a new version of the Pygments library"
             "which sometimes renames languages. This means a setting that used to work no longer"
             "works with newer versions of this add-on.")

ERR_STYLE = ("<b>Error</b>: Selected style not found.<br>"
             "A common source of errors: When you update the add-on Anki keeps your user settings"
             "but an update of the add-on might include a new version of the Pygments library"
             "which sometimes renames languages. This means a setting that used to work no longer"
             "works with newer versions of this add-on.")

LASTUSED = ""


def showError(msg, parent):
    showWarning(msg, title="Code Formatter Error", parent=parent)


def get_deck_name(editor):
    if isinstance(editor.parentWindow, aqt.addcards.AddCards):
        return editor.parentWindow.deckChooser.deckName()
    elif isinstance(editor.parentWindow, (aqt.browser.Browser, aqt.editcurrent.EditCurrent)):
        return mw.col.decks.name(editor.card.did)
    else:
        return None  # Error


def get_default_lang(editor):
    lang = gc('defaultlang')
    if gc('defaultlangperdeck'):
        deck_name = get_deck_name(editor)
        if deck_name and deck_name in gc('deckdefaultlang'):
            lang = gc('deckdefaultlang')[deck_name]
    return lang


def process_html(html):
    for pattern, replacement in ((r"{{", r"{<!---->{"),
                                 (r"}}", r"}<!---->}"),
                                 (r"::", r":<!---->:")):
        html = re.sub(pattern, replacement, html)
    return html


def hilcd(ed, code, langAlias):
    global LASTUSED
    linenos = gc('linenos')
    centerfragments = gc('centerfragments')
    noclasses = not gc('cssclasses')
    if (ed.mw.app.keyboardModifiers() & Qt.ShiftModifier):
        linenos ^= True
    if (ed.mw.app.keyboardModifiers() & Qt.ControlModifier):
        centerfragments ^= True
    mystyle = gc("style")
    if (ed.mw.app.keyboardModifiers() & Qt.AltModifier):
        d = FilterDialog(parent=None, values=list(get_all_styles()))
        if d.exec():
            mystyle = d.selkey
        noclasses = True
    inline = False
    if (ed.mw.app.keyboardModifiers() & Qt.MetaModifier):
        inline = True
    if inline:
        linenos = False

    try:
        if gc("remove leading spaces if possible", True):
            my_lexer = get_lexer_by_name(langAlias, stripall=False)
        else:
            my_lexer = get_lexer_by_name(langAlias, stripall=True)
    except ClassNotFound as e:
        print(e)
        print(ERR_LEXER)
        showError(ERR_LEXER, parent=ed.parentWindow)
        return False

    try:
        # http://pygments.org/docs/formatters/#HtmlFormatter
        """
nowrap
    If set to True, don’t wrap the tokens at all, not even inside a <pre> tag. This disables most other options (default: False).

full
    Tells the formatter to output a “full” document, i.e. a complete self-contained document (default: False).

title
    If full is true, the title that should be used to caption the document (default: '').

style
    The style to use, can be a string or a Style subclass (default: 'default'). This option has no effect if the cssfile and noclobber_cssfile option are given and the file specified in cssfile exists.

noclasses
    If set to true, token <span> tags (as well as line number elements) will not use CSS classes, but inline styles. This is not recommended for larger pieces of code since it increases output size by quite a bit (default: False).

classprefix
    Since the token types use relatively short class names, they may clash with some of your own class names. In this case you can use the classprefix option to give a string to prepend to all Pygments-generated CSS class names for token types. Note that this option also affects the output of get_style_defs().

cssclass
    CSS class for the wrapping <div> tag (default: 'highlight'). If you set this option, the default selector for get_style_defs() will be this class.
    If you select the 'table' line numbers, the wrapping table will have a CSS class of this string plus 'table', the default is accordingly 'highlighttable'.

cssstyles
    Inline CSS styles for the wrapping <div> tag (default: '').

prestyles
    Inline CSS styles for the <pre> tag (default: '').

cssfile
    If the full option is true and this option is given, it must be the name of an external file. If the filename does not include an absolute path, the file’s path will be assumed to be relative to the main output file’s path, if the latter can be found. The stylesheet is then written to this file instead of the HTML file.

noclobber_cssfile
    If cssfile is given and the specified file exists, the css file will not be overwritten. This allows the use of the full option in combination with a user specified css file. Default is False.

linenos
    If set to 'table', output line numbers as a table with two cells, one containing the line numbers, the other the whole code. This is copy-and-paste-friendly, but may cause alignment problems with some browsers or fonts. If set to 'inline', the line numbers will be integrated in the <pre> tag that contains the code
    The default value is False, which means no line numbers at all.
    For compatibility with Pygments 0.7 and earlier, every true value  except 'inline' means the same as 'table' (in particular, that means also True).

hl_lines
    Specify a list of lines to be highlighted.

linenostart
    The line number for the first line (default: 1).

linenostep
    If set to a number n > 1, only every nth line number is printed.

linenospecial
    If set to a number n > 0, every nth line number is given the CSS class "special" (default: 0).

nobackground
    If set to True, the formatter won’t output the background color for the wrapping element (this automatically defaults to False when there is no wrapping element [eg: no argument for the get_syntax_defs method given]) (default: False).

lineseparator
    This string is output between lines of code. It defaults to "\n", which is enough to break a line inside <pre> tags, but you can e.g. set it to "<br>" to get HTML line breaks.

lineanchors
    If set to a nonempty string, e.g. foo, the formatter will wrap each output line in an anchor tag with a name of foo-linenumber. This allows easy linking to certain lines.

linespans
    If set to a nonempty string, e.g. foo, the formatter will wrap each output line in a span tag with an id of foo-linenumber. This allows easy access to lines via javascript.

anchorlinenos
    If set to True, will wrap line numbers in <a> tags. Used in combination with linenos and lineanchors.

tagsfile
    If set to the path of a ctags file, wrap names in anchor tags that link to their definitions. lineanchors should be used, and the tags file should specify line numbers (see the -n option to ctags).

tagurlformat
    A string formatting pattern used to generate links to ctags definitions. Available variables are %(path)s, %(fname)s and %(fext)s. Defaults to an empty string, resulting in just #prefix-number links.

filename
    A string used to generate a filename when rendering <pre> blocks, for example if displaying source code.

wrapcode
    Wrap the code inside <pre> blocks using <code>, as recommended by the HTML5 specification.
        """
        tablestyling = ""
        if noclasses:
            tablestyling += "text-align: left;"
        if gc("cssclasses") and not gc("css_custom_class_per_style"):
            css_class = "highlight"  # the default for pygments
        else:
            css_class = f"shf__{mystyle}__highlight"
        my_formatter = HtmlFormatter(
            cssclass=css_class,
            cssstyles=tablestyling,
            font_size=16,
            linenos=linenos, 
            lineseparator="<br>",
            nobackground=False,  # True would solve night mode problem without any config (as long as no line numbers are used)
            noclasses=noclasses,
            style=mystyle,
            wrapcode=True)
    except ClassNotFound as e:
        print(e)
        print(ERR_STYLE)
        showError(ERR_STYLE, parent=ed.parentWindow)
        return False

    pygmntd = highlight(code, my_lexer, my_formatter).rstrip()
    # when using noclasses/inline styling pygments adds line-height 125%, see
    # see https://github.com/pygments/pygments/blob/2fe2152377e317fd215776b6d7467bda3e8cda28/pygments/formatters/html.py#L269
    # It's seems to be only relevant for IE and makes the line numbers misaligned on my PC. So I remove it.
    if noclasses:
        pygmntd = pygmntd.replace('line-height: 125%;', '')
    if inline:
        pretty_code = "".join([pygmntd, "<br>"])
        replacements = {
            '<div class=': '<span class=',
            "<pre": "<code",
            "</pre></div>": "</code></span>",
            "<br>": "",
            "</br>": "",
            "</ br>": "",
            "<br />": "",
            'style="line-height: 125%"': '',
        }
        for k, v in replacements.items():
            pretty_code = pretty_code.replace(k, v)
    else:
        if linenos:
            pretty_code = "".join([pygmntd, "<br>"])
        # to show line numbers pygments uses a table. The background color for the code
        # highlighting is limited to this table
        # If pygments doesn't use linenumbers it doesn't use a table. This means
        # that the background color covers the whole width of the card.
        # I don't like this. I didn't find an easier way than reusing the existing
        # solution.
        # Glutanimate removed the table in the commit
        # https://github.com/glutanimate/syntax-highlighting/commit/afbf5b3792611ecd2207b9975309d05de3610d45
        # which hasn't been published on Ankiweb in 2019-10-02.
        else:
            pretty_code = "".join([f'<table class="{css_class}"><tbody><tr><td>',
                                    pygmntd,
                                    "</td></tr></tbody></table><br>"])
        """
        I can't solely rely on the pygments-HTMLFormatter
        A lot of the stuff I did before 2020-11 with bs4 can indeed be done by adjusting
        the HTMLFormatter options:
        - I can override the ".card {text-align: center}" by using the option "cssstyles"
          (Inline CSS styles for the wrapping <div> tag).
        - I can set a custom class by adjusting the option "cssclass" which defaults to "highlight"
          Besides this there are the classes linenos and linenodiv. BUT I don't need to customize 
          the latter classes. I can also work with longer css rules: 
             /*syntax highlighting fork add-on: dark background*/
             .night_mode .shf__default__highlight{
             background-color: #222222 !important;
             }
             /*syntax highlighting fork add-on: line numbers: white on black: sometimes a span is used, sometimes not*/
             .night_mode .shf__default__highlighttable tr td.linenos div.linenodiv pre span {
             background-color: #222222 !important;
             color: #f0f0f0 !important;
             }
             .night_mode .shf__default__highlighttable tr td.linenos div.linenodiv pre {
             background-color: #222222 !important;
             color: #f0f0f0 !important;
             }
        BUT as far as I see I can't set inline styling for the surrounding table. But to center the
        table I need to add something like "margin: 0 auto;". If you rely on css it's easy because
        the "the wrapping table will have a CSS class of [the cssclass] string plus 'table', the 
        default is accordingly 'highlighttable'.". But my option should work without the user
        adjusting each template and the editor.
        I also need to set the font.
        """
        if centerfragments or (noclasses and gc('font')):
            soup = BeautifulSoup(pretty_code, 'html.parser')
            if centerfragments:
                tablestyling = "margin: 0 auto;"
                for t in soup.findAll("table"):
                    if t.has_attr('style'):
                        t['style'] = tablestyling + t['style']
                    else:
                        t['style'] = tablestyling
            if noclasses and gc('font'):
                for t in soup.findAll("code"):
                    t['style'] = "font-family: %s;" % gc('font')
            pretty_code = str(soup)
    if noclasses:
        out = json.dumps(pretty_code).replace('\n', ' ').replace('\r', '')
        # In 2020-05 I don't remember why I used backticks/template literals 
        # here in commit 6ea0fe8 from 2019-11.
        # Maybe for multi-line strings(?) but json.dumps shouldn't include newlines, because
        # json.dumps does "Serialize obj to a JSON formatted str using this conversion table." 
        # for the conversion table see https://docs.python.org/3/library/json.html#py-to-json-table
        # which includes JSONEncoder(.. indent=None, separators=None,..) and 
        #   If indent ... None (the default) selects the most compact representation.
        # out = "`" + json.dumps(pretty_code)[1:-1] + "`"
        ed.web.eval("MyInsertHtml(%s);" % out)
    else:
        # setFormat is a thin wrapper in Anki around document.execCommand
        ed.web.eval("setFormat('inserthtml', %s);" % json.dumps(pretty_code))
    LASTUSED = langAlias


basic_stylesheet = """
QMenu::item {
    padding-top: 16px;
    padding-bottom: 16px;
    padding-right: 75px;
    padding-left: 20px;
    font-size: 15px;
}
QMenu::item:selected {
    background-color: #fd4332;
}
"""


class keyFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Space:
                self.parent.alternative_keys(self.parent, Qt.Key_Return)
                return True
            elif event.key() == Qt.Key_T:
                self.parent.alternative_keys(self.parent, Qt.Key_Left)
                return True
            elif event.key() == Qt.Key_B:
                self.parent.alternative_keys(self.parent, Qt.Key_Down)
                return True
            elif event.key() == Qt.Key_G:
                self.parent.alternative_keys(self.parent, Qt.Key_Up)
                return True
            # elif event.key() == :
            #     self.parent.alternative_keys(self.parent, Qt.Key_Right)
            #     return True
        return False


def alternative_keys(self, key):
    # https://stackoverflow.com/questions/56014149/mimic-a-returnpressed-signal-on-qlineedit
    keyEvent = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    QCoreApplication.postEvent(self, keyEvent)


def onAll(editor, code):
    d = FilterDialog(editor.parentWindow, LANG_MAP)
    if d.exec():
        hilcd(editor, code, d.selvalue)


def illegal_info(val):
    msg = ('Illegal value ("{}") in the config of the add-on {}.\n'
           "A common source of errors: When you update the add-on Anki keeps your "
           "user settings but an update of the add-on might include a new version of "
           "the Pygments library which sometimes renames languages. This means a "
           "setting that used to work no longer works with newer versions of this "
           "add-on.".format(val, addonname))
    showInfo(msg)


def remove_leading_spaces(code):
    #https://github.com/hakakou/syntax-highlighting/commit/f5678c0e7dfeb926a5d7f0b780d8dce6ffeaa9d9
    
    # Search in each line for the first non-whitespace character,
    # and calculate minimum padding shared between all lines.
    lines = code.splitlines()
    starting_space = sys.maxsize

    for l in lines:
        # only interested in non-empty lines
        if len(l.strip()) > 0:
            # get the index of the first non whitespace character
            s = len(l) - len(l.lstrip())
            # is it smaller than anything found?
            if s < starting_space:
                starting_space = s

    # if we found a minimum number of chars we can strip off each line, do it.
    if (starting_space < sys.maxsize):
        code = '';    
        for l in lines:
            code = code + l[starting_space:] + '\n'
    return code



'''
Notes about wrapping with pre or code

pre is supposed to be "preformatted text which is to be presented exactly as written 
in the HTML file.", https://developer.mozilla.org/en-US/docs/Web/HTML/Element/pre, 


there are some differences: pre is a block element, see https://www.w3schools.com/html/html_blocks.asp
so code is an inline element, then I could use the "Custom Styles" add-on,
https://ankiweb.net/shared/info/1899278645 to apply the code tag?


### "Mini Format Pack supplementary" approach, https://ankiweb.net/shared/info/476705431?
# wrap_in_tags(editor, code, "pre")) 
# wrap_in_tags(editor, code, "code"))
# My custom version depends on deleting the selection first



### combine execCommands delete and insertHTML
# I remove the selection when opening the helper menu
#     editor.web.evalWithCallback("document.execCommand('delete');", lambda 
#                                 _, e=editor, c=code: _openHelperMenu(e, c, True))
# then in theory this should work:
#   editor.web.eval(f"""document.execCommand('insertHTML', false, %s);""" % json.dumps(code))
# but it often doesn't work in Chrome
# e.g.
#      code = f"<table><tbody><tr><td><pre>{code}</pre></td></tr></tbody></table>"  # works
#      code = f"<p><pre>{code}</pre></p>"  # doesn't work
#      code = f'<pre id="{uuid.uuid4().hex}">{code}</pre>'  # doesn't work
#      code = f'<pre style="" id="{uuid.uuid4().hex}">{code}</pre>'  # doesn't work
#      code = '<pre class="shf_pre">' + code + "</pre>"  # doesn't work
#      code = '<div class="city">' + code + "</div>"     # doesn't work
#      code = """<span style=" font-weight: bold;">code </span>"""  # works
#      code = """<div style=" font-weight: bold;">code </div>"""  # partially: transformed into span?
# That's a known problem, see https://stackoverflow.com/questions/25941559/is-there-a-way-to-keep-execcommandinserthtml-from-removing-attributes-in-chr
# The top answer is to use a custom js inserter function


### MiniFormatPack approach
#     editor.web.eval("setFormat('formatBlock', 'pre')")
# setFormat is a thin Anki wrapper around document.execCommand
# but this formats the whole paragraph and not just the selection


### idea: move the selection to a separate block first. Drawback: in effect there's no undo
# undo in contenteditable is hard, works best if I just use document.execCommand, i.e.
# setFormat. So I have to decide what's more important for me, I think undo is more important


At the moment my version of the MiniFormatSupplementary mostly works so I keep it.
'''


def _openHelperMenu(editor, code, selected_text):
    global LASTUSED

    if gc("remove leading spaces if possible", True):
        code = remove_leading_spaces(code)

    menu = QMenu(editor.widget)
    menu.setStyleSheet(basic_stylesheet)
    # add small info if pasting
    label = QLabel("selection" if selected_text else "paste")
    action = QWidgetAction(editor.widget)
    action.setDefaultWidget(label)
    menu.addAction(action)

    menu.alternative_keys = alternative_keys
    kfilter = keyFilter(menu)
    menu.installEventFilter(kfilter)

    if gc("show pre/code", False):
        # TODO: Do I really need the custom code, couldn't I just wrap in newer versions
        # as with the mini format pack, see https://github.com/glutanimate/mini-format-pack/pull/13/commits/725bb8595631e4dbc56bf881427aeada848e43c9
        m_pre = menu.addAction("&unformatted (<pre>)")
        m_pre.triggered.connect(lambda _, a=editor, c=code: wrap_in_tags(a, c, tag="pre", class_name="shf_pre"))
        m_cod = menu.addAction("unformatted (<&code>)")
        m_cod.triggered.connect(lambda _, a=editor, c=code: wrap_in_tags(a, c, tag="code", class_name="shf_code"))

    defla = get_default_lang(editor)
    if defla in LANG_MAP:
        d = menu.addAction("&default (%s)" % defla)
        d.triggered.connect(lambda _, a=editor, c=code: hilcd(a, c, LANG_MAP[defla]))
    else:
        d = False
        illegal_info(defla)
        return
    
    if LASTUSED:
        l = menu.addAction("l&ast used")
        l.triggered.connect(lambda _, a=editor, c=code: hilcd(a, c, LASTUSED))

    favmenu = menu.addMenu('&favorites')
    favfilter = keyFilter(favmenu)
    favmenu.installEventFilter(favfilter)
    favmenu.alternative_keys = alternative_keys

    a = menu.addAction("&select from all")
    a.triggered.connect(lambda _, a=editor, c=code: onAll(a, c))
    for e in gc("favorites"):
        if e in LANG_MAP:
            a = favmenu.addAction(e)
            a.triggered.connect(lambda _, a=editor, c=code, l=LANG_MAP[e]: hilcd(a, c, l))
        else:
            illegal_info(e)
            return

    if d:
        menu.setActiveAction(d)
    menu.exec_(QCursor.pos())


def openHelperMenu(editor):
    selected_text = editor.web.selectedText()
    if selected_text:
        #  Sometimes, self.web.selectedText() contains the unicode character
        # '\u00A0' (non-breaking space). This character messes with the
        # formatter for highlighted code.
        code = selected_text.replace('\u00A0', ' ')
        editor.web.evalWithCallback("document.execCommand('delete');", lambda 
                                    _, e=editor, c=code: _openHelperMenu(e, c, True))
    else:
        clipboard = QApplication.clipboard()
        code = clipboard.text()
        _openHelperMenu(editor, code, False)


def editorContextMenu(ewv, menu):
    e = ewv.editor
    a = menu.addAction("Syntax Highlighting")
    a.triggered.connect(lambda _, ed=e: openHelperMenu(ed))
addHook('EditorWebView.contextMenuEvent', editorContextMenu)


# def SetupShortcuts(cuts, editor):
#     cuts.append((gc("hotkey"), lambda e=editor: openHelperMenu(e)))
# addHook("setupEditorShortcuts", SetupShortcuts)


def keystr(k):
    key = QKeySequence(k)
    return key.toString(QKeySequence.NativeText)


def setupEditorButtonsFilter(buttons, editor):
    b = editor.addButton(
        os.path.join(addon_path, "icons", "button.png"),
        "syhl_linkbutton",
        openHelperMenu,
        tip="Syntax Highlighting for code ({})".format(keystr(gc("hotkey", ""))),
        keys=gc("hotkey", "")
        )
    buttons.append(b)
    return buttons
addHook("setupEditorButtons", setupEditorButtonsFilter)
