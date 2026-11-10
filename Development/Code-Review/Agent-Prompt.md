# Code Review Agent Prompt

**IMPORTANT: Configure the placeholders below before running this playbook.**

---

## Configuration

### Pull Request

<!-- CONFIGURE: Full GitHub URL of the pull request to review. Required - the playbook stops if this is still the placeholder. -->
**PR_URL:** `https://github.com/OWNER/REPO/pull/XXX`

<!-- CONFIGURE: Branch the pull request merges into. The diff is taken against origin/<BASE_BRANCH>. -->
**BASE_BRANCH:** `main`

<!-- Examples / valid values:
- `main` - recommended default
- `develop` - for git-flow repositories
- `rc` - for release-candidate branches
-->

---

## Agent Instructions

Review the pull request at `[PR_URL]` with the PR branch checked out in the agent's working directory. The numbered task documents reference these variables by name. Where you see `[PR_URL]` or `[BASE_BRANCH]` in those docs, use the value configured above.
