"""``.. tooldoc:: <name>`` -- the header documentation of ``bin/<name>``, verbatim.

A tool's own docstring (Python) or leading comment block (bash) is its usage
text, so the documentation shows that text rather than a copy that can drift.
Tools are READ, never imported: importing one loads fleet.toml, which a docs
build does not have.
"""
import ast
import os

from docutils import nodes
from docutils.parsers.rst import Directive

BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'bin'))


def header_text(path):
    src = open(path, encoding='utf-8').read()
    first = src.splitlines()[0] if src else ''
    if 'python' in first:
        doc = ast.get_docstring(ast.parse(src))
        if not doc:
            raise ValueError(f'{path}: no module docstring')
        return doc
    lines = []
    for line in src.splitlines()[1:]:          # skip the shebang
        if not line.startswith('#'):
            break
        lines.append(line[2:] if line.startswith('# ') else line[1:])
    if not lines:
        raise ValueError(f'{path}: no leading comment block')
    return '\n'.join(lines).strip('\n')


class ToolDoc(Directive):
    required_arguments = 1

    def run(self):
        name = self.arguments[0]
        path = os.path.join(BIN, name)
        self.state.document.settings.record_dependencies.add(path)
        try:
            text = header_text(path)
        except (OSError, ValueError) as e:
            raise self.error(f'tooldoc: {e}')
        block = nodes.literal_block(text, text)
        block['language'] = 'text'
        return [block]


def setup(app):
    app.add_directive('tooldoc', ToolDoc)
    return {'parallel_read_safe': True, 'parallel_write_safe': True}
