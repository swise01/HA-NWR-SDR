#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  publish.sh — Create + push HA-NWR-SDR to your GitHub account
#
#  Usage:
#    chmod +x publish.sh
#    ./publish.sh YOUR_GITHUB_USERNAME YOUR_GITHUB_TOKEN
#
#  Create a token at: https://github.com/settings/tokens
#  Scopes needed: repo (full)
# ══════════════════════════════════════════════════════════════════

set -e

GITHUB_USER="${1:?Usage: ./publish.sh YOUR_GITHUB_USERNAME YOUR_GITHUB_TOKEN}"
GITHUB_TOKEN="${2:?Usage: ./publish.sh YOUR_GITHUB_USERNAME YOUR_GITHUB_TOKEN}"
REPO_NAME="HA-NWR-SDR"
REPO_DESCRIPTION="NOAA Weather Radio integration for Home Assistant — RTL-SDR SAME decode + NWS API, tiered alerts, any audio player"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Publishing $REPO_NAME to github.com/$GITHUB_USER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Create repo via API (public)
echo "→ Creating GitHub repository..."
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user/repos \
  -d "{
    \"name\": \"$REPO_NAME\",
    \"description\": \"$REPO_DESCRIPTION\",
    \"private\": false,
    \"has_issues\": true,
    \"has_projects\": false,
    \"has_wiki\": false,
    \"auto_init\": false
  }" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if 'html_url' in r:
    print('✓ Repo created:', r['html_url'])
elif r.get('errors', [{}])[0].get('message', '') == 'name already exists on this account':
    print('✓ Repo already exists — will push to existing repo')
else:
    print('Error:', json.dumps(r, indent=2))
    sys.exit(1)
"

# 2. Set remote and push
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "→ Initializing git repo..."
cd "$SCRIPT_DIR"
git init -b main
git config user.email "nwr-bot@localhost"
git config user.name "NWR Publisher"

# Replace placeholder username in all files
echo "→ Updating YOUR_GITHUB_USERNAME references..."
find . -type f \( -name "*.md" -o -name "*.yaml" -o -name "*.py" -o -name "*.service" \) | while read f; do
  sed -i "s/YOUR_GITHUB_USERNAME/$GITHUB_USER/g" "$f"
done

git add -A
git commit -m "Initial release — HA-NWR-SDR community integration"

echo "→ Pushing to GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin "https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"
git push -u origin main --force

# 3. Set topics
echo "→ Setting repo topics..."
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.mercy-preview+json" \
  "https://api.github.com/repos/$GITHUB_USER/$REPO_NAME/topics" \
  -d '{"names":["home-assistant","rtl-sdr","noaa","weather-radio","same-eas","raspberry-pi","mqtt","lovelace","hacs","weather-alerts"]}' \
  > /dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Done!"
echo "  → https://github.com/$GITHUB_USER/$REPO_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
