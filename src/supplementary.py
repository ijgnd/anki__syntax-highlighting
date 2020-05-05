# License AGPLv3
# slightly adjusted functions from the add-on "Mini Format Pack Supplementary"
# which aws anonymously uploaded to Ankiweb, https://ankiweb.net/shared/info/476705431

import json
import re


def escape_html_chars(s):

    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
        ">": "&gt;",
        "<": "&lt;",
        "\n":"<br>"
    }

    result = "".join(html_escape_table.get(c, c) for c in s)

    return result


def wrap_in_tags(editor, selection, tag, class_name=None):
    """
    Wrap selected text in a tag, optionally giving it a class.
    """


    selection = escape_html_chars(selection)
    # print("before1:",repr(selection))
    # selection = selection.replace("\n", "<br>")
    # print("after1:", repr(selection))

    tag_string_begin = ("<{0} class='{1}'>".format(tag, class_name) if
                        class_name else "<{0}>".format(tag))
    tag_string_end = "</{0}>".format(tag)

    html = editor.note.fields[editor.currentField]

    if "<li><br /></li>" in html:
        # an empty list means trouble, because somehow Anki will also make the
        # line in which we want to put a <code> tag a list if we continue
        replacement = tag_string_begin + selection + tag_string_end
        editor.web.eval("document.execCommand('insertHTML', false, %s);"
                        % json.dumps(replacement))

        editor.web.setFocus()
        field=editor.currentField
        editor.web.eval("focusField(%d);" % field)
        def cb():
            html_after = editor.note.fields[field]

            if html_after != html:
                # you're in luck!
                return
            else:
                # nothing happened :( this is a quirk that has to do with <code> tags following <div> tags
                return
        editor.saveNow(cb)

    # Due to a bug in Anki or BeautifulSoup, we cannot use a simple
    # wrap operation like with <a>. So this is a very hackish way of making
    # sure that a <code> tag may precede or follow a <div> and that the tag
    # won't eat the character immediately preceding or following it
    pattern = "@%*!"
    len_p = len(pattern)

    # first, wrap the selection up in a pattern that the user is unlikely
    # to use in its own cards
    editor.web.eval("wrap('{0}', '{1}')".format(pattern, pattern[::-1]))

    # focus the field, so that changes are saved
    # this causes the cursor to go to the end of the field
    editor.web.setFocus()
    field = editor.currentField
    editor.web.eval("focusField(%d);" % field)

    # print("selection:", repr(selection))
    # if tag == "blockquote":
    #     selection = selection.replace("\n", "<br>")

    def cb1():
        html = editor.note.fields[field]
        begin = html.find(pattern)
        end = html.find(pattern[::-1], begin)

        # print("before:", html)
        #原来有<pre>标签，就把它替换成有class的，即添加<pre>标签时即使重复点两次也没事
        if re.match("<pre[^<]+?@%\*!",html):
            html = re.sub("<pre[^<]+?@%\*!","<pre class='myCodeClass'>@%*!",html)
            html = html.replace("!*%@<br>", "!*%@")
            # print("before:",html)
            html = html.replace(pattern, "")
            html = html.replace(pattern[::-1], "")
            # print("after:", html)
        else:
            html = html.replace("!*%@<br>", "!*%@")
            html = (html[:begin] + tag_string_begin + selection + tag_string_end +
                    html[end + len_p:])
        # print("after:",html)
        # if tag == "blockquote":
        #     html.replace()
        # delete the current HTML and replace it by our new & improved one
        editor.note.fields[field] = html

        # reload the note: this is needed on OS X, because it will otherwise
        # falsely show that the formatting of the element at the start of
        # the HTML has spread across the entire note
        editor.loadNote()

        # focus the field, so that changes are saved
        editor.web.setFocus()
        editor.web.eval("focusField(%d);" % field)
    editor.saveNow(cb1)

    def cb2():
        editor.web.setFocus()
        editor.web.eval("focusField(%d);" % field)
    editor.saveNow(cb2) 
