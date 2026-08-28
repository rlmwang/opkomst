# Rich text in the details field

The description of an event, questionnaire, date poll or roster is rich
text: bold, italic, underline, strikethrough, links and lists.

The editor is Tiptap. What it produces is stored as HTML and sanitised
on the way in, on the server, against a small allowlist of tags and
attributes: no styles, no classes, no scripts, and every link forced to
`rel="noopener"`. `services/sanitize.py` is the whole rule, and the
public pages render what it returned.

Plain text stays plain. A description somebody typed without touching a
button is stored as the paragraph it is, so nothing that never used the
editor carries markup it did not ask for.
