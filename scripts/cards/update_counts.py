"""Set the stars and forks on the README's project cards to their repositories' counts on GitHub.

Each project card (assets/tool-*.svg) ends in a footer like a pinned repository's: a star and the repository's
star count, a fork and its fork count. This reads the counts from GitHub's REST API and redraws the numbers with
counts.py, from the outlined figures in glyphs.json and with the alignment the cards were built with. Nothing
else in a card changes, and a card is written only when one of its numbers changed. The workflow
.github/workflows/cards.yml runs it once a day and commits what changed.

The README says which card belongs to which repository: every <a href="https://github.com/OWNER/NAME"> around a
<picture> is a project card, and every image in that <picture> (a card and its -gap twin) gets those counts.

    python3 scripts/cards/update_counts.py              read the counts and update the cards
    python3 scripts/cards/update_counts.py --dry-run    only say what would change
    python3 scripts/cards/update_counts.py --set efim0v/brow 1250 3
                                                        these counts for that repository instead of GitHub's
                                                        (to try a number out); the others still come from GitHub

GITHUB_TOKEN, when set (the workflow sets it), authenticates the requests, which lifts the limit of 60 an hour.
Standard library only. On any error (a request failed, a card has no number groups) it exits with 1 and writes
nothing.
"""
import argparse
import http.client
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # the repository: scripts/cards/ is two levels down
API = 'https://api.github.com/repos/'
CARD = re.compile(r'<a href="https://github\.com/([\w.-]+/[\w.-]+)"><picture>')
# what redrawing a card may change: the two number groups and how far the fork and its count move along
NUMBERS = re.compile(r'<g id="(?:stars|forks)" [^>]*>(?:<path[^>]*/>)*</g>'
                     r'|<g id="fork" transform="translate\([^)]*\)"')


def load_counts():
    """counts.py, loaded by its path, so this runs from any directory (and under python3 -I)."""
    spec = importlib.util.spec_from_file_location('cards_counts', os.path.join(HERE, 'counts.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = load_counts()
GLYPH_OF = {g['d']: ch for ch, g in C.GLYPHS.items()}


class Failure(Exception):
    pass


def cards(readme):
    """{repository: [its card files]} in the README's order: the images of each card's <picture>, and the -gap
    twin of each one when it exists."""
    found = {}
    for repo in CARD.findall(open(readme, encoding='utf-8').read()):
        files = found.setdefault(repo, [])
        for path in C.card_files(repo, readme):
            for p in (path, path[:-len('.svg')] + '-gap.svg'):
                if p not in files and (p == path or os.path.exists(p)):
                    files.append(p)
    return found


def get(url, token):
    """The JSON at url. Tries three times when the network or GitHub fails, once when the answer is a plain no."""
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'efim0v-cards',
                                               'X-GitHub-Api-Version': '2022-11-28'})
    if token:
        req.add_unredirected_header('Authorization', 'Bearer ' + token)    # never sent on to a redirect
    problem = None
    for wait in (0, 10, 30):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            problem = 'HTTP %d %s' % (e.code, e.reason)
            if e.code == 404:
                problem += ' (renamed, deleted or private?)'
            if e.headers.get('X-RateLimit-Remaining') == '0':
                problem += ' (rate limit reached%s)' % ('' if token else '; GITHUB_TOKEN lifts it')
            if e.code < 500 and e.code != 429:
                break
        except (OSError, ValueError, http.client.HTTPException) as e:   # no network, a cut-off or garbled reply
            problem = str(e) or type(e).__name__
    raise Failure('%s: %s' % (url, problem))


def repo_counts(repo, token):
    """(stars, forks) of repo on GitHub."""
    data = get(API + repo, token)
    if not isinstance(data, dict):
        data = {}
    stars, forks = data.get('stargazers_count'), data.get('forks_count')
    if not all(type(v) is int and v >= 0 for v in (stars, forks)):
        raise Failure('%s: no star and fork counts in the reply' % repo)
    if str(data.get('full_name', repo)).lower() != repo.lower():
        print('%s is now %s: point its card in the README there' % (repo, data['full_name']))
    return stars, forks


def shown(svg, gid):
    """The number a card's <g id="gid"> shows, read back from its glyphs; None if they aren't glyphs.json's."""
    m = re.search(r'<g id="%s" [^>]*>((?:<path[^>]*/>)*)</g>' % gid, svg)
    chars = [GLYPH_OF.get(d) for d in re.findall(r' d="([^"]*)"', m.group(1))] if m else []
    return ''.join(chars) if chars and None not in chars else None


def redraw(path, stars, forks):
    """(the card at path with these counts, or None when it shows them already; the numbers it shows now)."""
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding='utf-8', newline='') as fh:
        src = fh.read()
    new = (C.count_text(stars), C.count_text(forks))
    old = (shown(src, 'stars'), shown(src, 'forks'))
    try:
        out = C.set_counts(src, stars, forks)
    except ValueError as e:                         # the card has no footer, or not the one counts.py draws
        raise Failure('%s: %s' % (rel, e))
    if old == new:
        if out != src:
            print('  %s shows %s and %s already, though not quite as glyphs.json draws them: left as it is'
                  % (rel, new[0], new[1]))
        return None, old
    try:
        ET.fromstring(out)
    except ET.ParseError as e:
        raise Failure('%s: the redrawn card is not well-formed XML (%s)' % (rel, e))
    if NUMBERS.sub('', out) != NUMBERS.sub('', src):
        raise Failure('%s: redrawing the numbers would change more than the numbers' % rel)
    if (shown(out, 'stars'), shown(out, 'forks')) != new:
        raise Failure('%s: the redrawn card does not read %s and %s' % (rel, new[0], new[1]))
    return out, old


def count_arg(repo, value):
    if not re.fullmatch(r'[0-9]+', value):
        raise Failure('--set %s: %r is not a count' % (repo, value))
    return int(value)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Set the project cards' stars and forks to their repositories' counts.")
    ap.add_argument('--dry-run', action='store_true', help='say what would change, write nothing')
    ap.add_argument('--set', nargs=3, action='append', default=[], metavar=('OWNER/NAME', 'STARS', 'FORKS'),
                    help="these counts for that repository's cards instead of GitHub's")
    a = ap.parse_args(argv)
    done = []
    try:
        given = {repo.lower(): (count_arg(repo, s), count_arg(repo, f)) for repo, s, f in a.set}
        found = cards(os.path.join(ROOT, 'README.md'))
        if not found:
            raise Failure('the README links no project card to a GitHub repository')
        unknown = sorted(set(given) - {r.lower() for r in found})
        if unknown:
            raise Failure('no card in the README links to %s' % ', '.join(unknown))
        token = os.environ.get('GITHUB_TOKEN', '').strip() or None
        writes, report = [], []
        for repo, files in found.items():
            stars, forks = given.get(repo.lower()) or repo_counts(repo, token)
            said = ['%s' % n if C.count_text(n) == str(n) else '%s (%s)' % (format(n, ','), C.count_text(n))
                    for n in (stars, forks)]
            lines = []
            for path in files:
                out, old = redraw(path, stars, forks)
                if out is not None:
                    writes.append((path, out))
                    lines.append('  %s: was stars %s, forks %s' % (os.path.relpath(path, ROOT), old[0] or '?',
                                                                  old[1] or '?'))
            report.append('%s: stars %s, forks %s%s%s' % (repo, said[0], said[1],
                                                         ' (given)' if repo.lower() in given else '',
                                                         '' if lines else ', no change'))
            report.extend(lines)
        if not a.dry_run:
            for path, out in writes:
                with open(path, 'w', encoding='utf-8', newline='') as fh:
                    fh.write(out)
                done.append(os.path.relpath(path, ROOT))
        print('\n'.join(report))
        print('%d card file%s %s.' % (len(writes), '' if len(writes) == 1 else 's',
                                      'would change (dry run)' if a.dry_run else 'written'))
    except (Failure, ValueError, OSError) as e:
        print('update_counts: %s' % e, file=sys.stderr)
        print('update_counts: %s.' % ('written before the error: ' + ', '.join(done) if done else 'nothing written'),
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
