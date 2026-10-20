#!/usr/bin/env bash
# Award Insights: build all four tools, check them, and publish.   © 2026 Award Insights
#
#   ./deploy.sh            build + check + publish
#   ./deploy.sh --dry-run  build + check, publish nothing (look at build/site first)
#   COMPARE_LIVE=../awardinsights ./deploy.sh --dry-run   also checks the four original pages byte for byte
#                          against a checkout of the public repo (do this before the first gh-pages publish)
#
# Before the first run:  npm install   (installs the minifier)
# Each refresh:          run scripts/usaspending_pull.py and scripts/usaspending_trim.py,
#                        put the trimmed *.csv.gz files in inputs/trimmed/, then ./deploy.sh
#
# Publishing: everything the site serves is built here: the landing page, NSF Award Insights, Research
# Activity Designations and Research Portfolio Trends (legacy/build_legacy.py), and Federal Award Insights
# under /federal/. The result is force-pushed as ONE fresh commit to the public repo's gh-pages branch, so
# data never accumulates in git history. Nothing is edited by hand in the public repo.
# One-time GitHub setting: Settings → Pages → Build and deployment → Deploy from branch → gh-pages / (root).
set -euo pipefail
cd "$(dirname "$0")"

PUBLIC_REPO="${PUBLIC_REPO:-git@github.com:paintthedog/awardinsights.git}"
DOMAIN="${DOMAIN:-awardinsights.org}"
SUBDIR="${SUBDIR:-federal}"
DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1

n=$(ls inputs/trimmed/*.csv.gz 2>/dev/null | wc -l | tr -d ' ')
[[ "$n" -gt 0 ]] || { echo "No trimmed files in inputs/trimmed/. Run the pull and trim scripts first."; exit 1; }
echo "→ $n trimmed files"

rm -rf build && mkdir -p build/site
echo "→ building the landing page, NSF, Designations and Portfolio"
python3 -I legacy/build_legacy.py --out build/site ${COMPARE_LIVE:+--compare "$COMPARE_LIVE"}

echo "→ building Federal data"
python3 -I scripts/build_fai.py --core inputs/ai-1-core --nsf inputs/nsf \
  --assistance inputs/trimmed --contracts inputs/trimmed --out "build/site/$SUBDIR" --awards inst

echo "→ checking dollars against the raw files"
FAI_INPUTS=inputs FAI_SITE="build/site/$SUBDIR" python3 -I scripts/verify.py
FAI_INPUTS=inputs FAI_SITE="build/site/$SUBDIR" python3 -I scripts/verify_cliff.py 214777
FAI_INPUTS=inputs FAI_SITE="build/site/$SUBDIR" python3 -I scripts/verify_ic.py 198419 "ALLERGY|NIAID"

echo "→ building page"
python3 scripts/build_page.py --head page/head.html --body page/body.html --public "build/site/$SUBDIR" \
  --terser node_modules/.bin/terser

if [[ $DRY -eq 1 ]]; then echo "Dry run: built into build/site/. Preview with: (cd build/site && python3 -m http.server)"; exit 0; fi

echo "→ assembling the full site"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/pages" && cp -R build/site/. "$tmp/pages/"
echo "$DOMAIN" > "$tmp/pages/CNAME"
touch "$tmp/pages/.nojekyll"
grep -q "Disallow: /$SUBDIR/data/" "$tmp/pages/robots.txt" 2>/dev/null || printf 'User-agent: *\nDisallow: /%s/data/\n' "$SUBDIR" >> "$tmp/pages/robots.txt"

echo "→ publishing to gh-pages (single commit, history replaced)"
cd "$tmp/pages"
git init --quiet -b gh-pages
git add -A
git -c user.name="Award Insights" -c user.email="noreply@$DOMAIN" commit --quiet -m "Publish $(date -u +%Y-%m-%d)"
git push --quiet --force "$PUBLIC_REPO" gh-pages
echo "Published. Live at https://$DOMAIN/ (Federal at /$SUBDIR/) within a few minutes."
