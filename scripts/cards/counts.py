"""The stars and forks on the profile README's project cards, set without fonts.

Every project card (assets/tool-*.svg) ends in the same footer as a pinned repository on GitHub: a star and
the repository's star count, a fork and its fork count. An SVG shown through <img> can't load fonts, so the
numbers are outlined glyphs, built from glyphs.json: the figures 0-9, "," "." and "k" of the cards' font,
cut once from the font with their advances and kerning, and the footer's measures.

In a card the numbers are two groups with stable ids:

  <g id="stars" transform="translate(x y) scale(s)">...</g>     the star count, right after the star
  <g id="fork" transform="translate(dx 0)">...                  the fork and its count, moved along by the
      <g id="forks" transform="translate(x y) scale(s)">...</g>   width of the star count
  </g>

Numbers are written as GitHub writes them on its cards: up to 999 as they are, then 1k, 1.3k, 12.3k, 123k
(rounded: 1,250 is 1.3k).

    python3 counts.py --stars 58 --forks 2 --repo efim0v/brow
    python3 counts.py --stars 58 --forks 2 FILE.svg [FILE.svg ...]

sets the counts in a repository's cards (the README links each card to its repository, so --repo finds its
files there, a card and its -gap variant alike) or in the given files, rewrites a file only when a number in
it changed, and prints the files it changed. update_counts.py, next to it, reads the counts from GitHub and
sets them on every card; the daily workflow runs it.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # the repository: scripts/cards/ is two levels down
TABLE = json.load(open(os.path.join(HERE, 'glyphs.json'), encoding='utf-8'))
GLYPHS = TABLE['glyphs']
KERN = TABLE['kerning']
FOOT = TABLE['footer']


def fmt(v):
    s = ('%.3f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def count_text(n):
    """A count as a pinned repository's card on GitHub writes it: up to 999 as it is, then in thousands, rounded
    half up, to one decimal under 100k and to a whole number from there, without a trailing .0. As GitHub's
    cards showed them on 2026-10-18: 1,022 is 1k, 2,250 is 2.3k, 3,293 is 3.3k, 23,962 is 24k, 108,712 is 109k."""
    n = int(n)
    if n < 1000:
        return str(n)
    tenths = (n + 50) // 100
    if tenths < 1000:
        whole, tenth = divmod(tenths, 10)
        return '%d%sk' % (whole, '.%d' % tenth if tenth else '')
    return '%dk' % ((n + 500) // 1000)


def advances(text):
    """Pen positions of each glyph and the run's width, in font units, kerning included."""
    xs, x = [], 0
    for i, ch in enumerate(text):
        if ch not in GLYPHS:
            raise ValueError('no glyph for %r in glyphs.json' % ch)
        if i:
            x += KERN.get(text[i - 1] + ch, 0)
        xs.append(x)
        x += GLYPHS[ch]['advance']
    return xs, x


def width(text):
    """The run's advance width in card units at the footer's size."""
    return advances(text)[1] * FOOT['size'] / TABLE['unitsPerEm']


def glyph_run(text):
    """The glyphs of text as paths in font units, the first at the origin, the baseline on y = 0."""
    xs, _ = advances(text)
    return ''.join('<path%s d="%s"/>' % ((' transform="translate(%s)"' % fmt(x)) if x else '', GLYPHS[ch]['d'])
                   for ch, x in zip(text, xs))


def number_group(gid, text, x, fill=None):
    """A count as a group with a stable id, its first glyph at x on the footer's baseline."""
    return '<g id="%s" transform="translate(%s %s) scale(%s)"%s>%s</g>' % (
        gid, fmt(x), fmt(FOOT['baseline']), fmt(FOOT['size'] / TABLE['unitsPerEm']),
        (' fill="%s"' % fill) if fill else '', glyph_run(text))


def places(stars_text):
    """Where the footer's pieces go, in card units: the star count's x, how far the fork group moves (its icon is
    drawn at x = 0 inside the group and its count at forks_x), so that the gaps stay the same for any number."""
    stars_x = FOOT['x'] + FOOT['icon_ink_right']['star'] + FOOT['icon_gap']
    fork_dx = stars_x + width(stars_text) + FOOT['item_gap'] - FOOT['icon_ink_left']['fork']
    forks_x = FOOT['icon_ink_right']['fork'] + FOOT['icon_gap']
    return dict(stars_x=stars_x, fork_dx=fork_dx, forks_x=forks_x)


def set_counts(svg, stars, forks):
    """The card's SVG with its counts set to stars and forks; the rest of the file stays byte for byte."""
    st, ft = count_text(stars), count_text(forks)
    p = places(st)

    def regroup(gid, text, x, src):
        pat = re.compile(r'<g id="%s" transform="translate\([^)]*\) scale\([^)]*\)"( fill="[^"]*")?>(?:<path[^>]*/>)*</g>'
                         % gid)
        m = list(pat.finditer(src))
        if len(m) != 1:
            raise ValueError('expected one <g id="%s"> number group, found %d' % (gid, len(m)))
        fill = re.search(r'fill="([^"]*)"', m[0].group(1)).group(1) if m[0].group(1) else None
        return src[:m[0].start()] + number_group(gid, text, x, fill) + src[m[0].end():]

    out = regroup('stars', st, p['stars_x'], svg)
    out = regroup('forks', ft, p['forks_x'], out)
    out, n = re.subn(r'<g id="fork" transform="translate\([^)]*\)"', '<g id="fork" transform="translate(%s 0)"'
                     % fmt(p['fork_dx']), out)
    if n != 1:
        raise ValueError('expected one <g id="fork"> group, found %d' % n)
    return out


def card_files(repo, readme=None):
    """The images of the card the README links to github.com/<repo>: every src and srcset in its <picture>."""
    md = open(readme or os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    files = []
    for m in re.finditer(r'<a href="https://github\.com/%s"><picture>(.*?)</picture></a>' % re.escape(repo), md, re.S):
        for f in re.findall(r'(?:srcset|src)="(assets/[^"]+\.svg)"', m.group(1)):
            if f not in files:
                files.append(f)
    return [os.path.join(ROOT, f) for f in files]


def main():
    ap = argparse.ArgumentParser(description='Set the star and fork counts on project cards.')
    ap.add_argument('--stars', type=int, required=True)
    ap.add_argument('--forks', type=int, required=True)
    ap.add_argument('--repo', help='owner/name: the cards the README links to that repository')
    ap.add_argument('files', nargs='*')
    a = ap.parse_args()
    files = a.files + (card_files(a.repo) if a.repo else [])
    if not files:
        ap.error('no cards: give --repo or files' + (' (the README links no card to %s)' % a.repo if a.repo else ''))
    for path in files:
        src = open(path, encoding='utf-8').read()
        out = set_counts(src, a.stars, a.forks)
        if out != src:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(out)
            print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
