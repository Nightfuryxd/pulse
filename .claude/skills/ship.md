---
name: ship
description: Test, commit, and push all PULSE changes to GitHub
user_invocable: true
---

Ship the current PULSE changes to GitHub:

1. **Syntax check** all Python files in api/:
   `for f in /Users/aniketgupta/Desktop/Claude/pulse/api/*.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "✓ $f" || echo "✗ $f"; done`

2. **Quick API health check** (if containers running):
   `curl -s http://localhost:8001/api/stats`

3. **Show git diff summary** — what changed

4. **Create a descriptive commit** with all changes. Use conventional commit format:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `refactor:` for refactoring
   Add `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

5. **Push to origin main**

6. Report: what was committed and pushed, the commit hash, and GitHub URL
