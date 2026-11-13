"""Replace only two embedded PNGs; preserve all text, styles and image extents."""
import argparse
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import posixpath

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--lang', choices=['ru', 'en'], required=True)
args = parser.parse_args()
assets = Path(__file__).resolve().parents[1] / 'assets'
ns = {'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
with ZipFile(args.source) as src:
    root = etree.fromstring(src.read('word/document.xml'))
    rels = {e.get('Id'): posixpath.normpath('word/' + e.get('Target'))
            for e in etree.fromstring(src.read('word/_rels/document.xml.rels'))}
    replacements = {}
    for inline in root.findall('.//wp:inline', ns):
        props = inline.find('wp:docPr', ns)
        name = props.get('title', '')
        if name in [f'architecture_{args.lang}.png', f'state_machine_{args.lang}.png']:
            rid = inline.find('.//a:blip', ns).get('{'+ns['r']+'}embed')
            replacements[rels[rid]] = (assets / name).read_bytes()
    if len(replacements) != 2:
        raise RuntimeError(f'Expected two drawings; found {list(replacements)}')
    with ZipFile(args.output, 'w') as out:
        for entry in src.infolist():
            out.writestr(entry, replacements.get(entry.filename, src.read(entry.filename)))
with ZipFile(args.source) as src, ZipFile(args.output) as out:
    changed = [n for n in src.namelist() if src.read(n) != out.read(n)]
    assert set(changed) == set(replacements), changed
print(f'{args.output}: changed only {changed}')
