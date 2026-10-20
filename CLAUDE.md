# awardinsights-build

Private source for awardinsights.org. **Read `docs/SPEC.md` first** — it holds the data rules, wording rules, design system and open items. Update it when a decision changes.

- Build + check everything: `./deploy.sh --dry-run` (needs `npm install` once and trimmed USAspending files in `inputs/trimmed/`, which are not in git).
- Publish: `./deploy.sh` (force-pushes the built site to `paintthedog/awardinsights` gh-pages). Only on the owner's go-ahead.
- Never hand-edit the public repo. Never commit `inputs/trimmed/`, `inputs/subawards/` or `build/`.
- The four original pages must stay byte-identical to live unless a change is intended: `COMPARE_LIVE=<public checkout> ./deploy.sh --dry-run`.
- Data checks (`scripts/verify*.py`) must pass; if a rule changes, change the check the same way.
- Wording: describe the data, never judge an institution.
