# Stars and forks on the project cards

The project cards in the profile README (`assets/tool-*.svg`) end in a footer like a pinned repository's: a star with the repository's star count, a fork with its fork count. An image in a README can't load fonts, so the numbers are drawn as outlined glyphs, and a daily job redraws them when they change.

- `glyphs.json`: the figures 0–9, `.`, `,` and `k` of the cards' font (Onest), with their kerning and the footer's measures.
- `counts.py`: draws a number from those glyphs into a card's `<g id="stars">` and `<g id="forks">`, and moves `<g id="fork">` (the fork and its count) along by the width of the star count.
- `update_counts.py`: reads each card's repository from GitHub's API and redraws the numbers that changed. Standard library only.
- `.github/workflows/cards.yml`: runs it every day at 03:17 UTC and, when a number changed, commits the cards as github-actions[bot] ("Update the stars and forks on the cards"). To run it now: Actions → Card counts → Run workflow.

## By hand

```sh
python3 scripts/cards/update_counts.py --dry-run                   # what would change
python3 scripts/cards/update_counts.py                             # update the cards
python3 scripts/cards/update_counts.py --set efim0v/brow 1250 3    # try a number out (then run without --set)
```

## Good to know

- The README decides which card shows which repository: the `<a href="https://github.com/OWNER/NAME">` around a card's `<picture>`. The card and its `-gap` twin both get the numbers. A new card needs the same footer; if a linked card has none, the job stops without writing anything.
- Numbers look the way GitHub's pinned cards show them: 57, 999, 1k, 1.3k for 1,250, 24k for 23,962, 109k for 108,712. A zero is shown too (GitHub hides it), so the three footers line up.
- If a run fails (GitHub down, a repository deleted or made private), nothing changes, and the next day's run tries again. A renamed repository still works, and the log says where it moved: update its link in the README.
- The job commits to `main`, so pull before you push.
- The job keeps the file names. GitHub caches an image for up to 5 minutes, so a new number can take that long to show. A new design still gets a new file name.
- GitHub turns off scheduled workflows in a public repository after 60 days without activity. If the cards stop updating, enable the workflow again in the Actions tab.
- `glyphs.json` and the footer come from the builder that drew the cards, outside this repository. If the font or the footer changes, rebuild the cards and `glyphs.json` together.
