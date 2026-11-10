# Code Review Playbook

A Maestro Auto Run playbook for comprehensive pull request code reviews.

## What This Playbook Does

Performs a thorough, multi-pass code review of a pull request, examining correctness, security, performance, testing, and documentation.

### Review Areas

1. **Code Correctness** - Logic errors, edge cases, null handling
2. **Security** - OWASP vulnerabilities, injection risks, auth issues
3. **Performance** - N+1 queries, memory leaks, inefficient algorithms
4. **Test Coverage** - Missing tests, edge case coverage, mocking issues
5. **Documentation** - Updated docs, clear comments, API changes documented

## Playbook Structure

This playbook follows a **linear 5-document pattern** (no looping):

```
1_ANALYZE_CHANGES.md  - Understand the PR scope and changed files
2_REVIEW_CODE.md      - Deep review for correctness and best practices
3_CHECK_SECURITY.md   - Security-focused analysis
4_VERIFY_TESTS.md     - Test coverage and quality assessment
5_SUMMARIZE.md        - Compile findings and generate feedback
```

## Prerequisites

- Maestro installed and configured
- Git repository with the PR branch checked out
- Agent with access to the codebase

## Setup in Maestro

1. Place this folder in your Maestro Auto Run directory
2. Check out the PR branch you want to review
3. Update Document 1's PR URL to point to your pull request
4. Configure Auto Run settings:
   - **Loop Mode**: OFF (sequential execution)
   - **Max Loops**: N/A (no looping)
5. Run the playbook

## Execution Flow

1. **Document 1** → Analyzes PR diff, identifies changed files and scope
2. **Document 2** → Reviews code for correctness, patterns, best practices
3. **Document 3** → Scans for security vulnerabilities and risks
4. **Document 4** → Evaluates test coverage and test quality
5. **Document 5** → Summarizes all findings into actionable feedback

## Working Files Generated

| File | Purpose |
|------|---------|
| `REVIEW_SCOPE.md` | List of changed files and PR context |
| `CODE_ISSUES.md` | Code correctness and best practice issues |
| `SECURITY_ISSUES.md` | Security vulnerabilities found |
| `TEST_GAPS.md` | Missing or inadequate test coverage |
| `REVIEW_SUMMARY.md` | Final consolidated review feedback |

## Customization

Set the pull request in the Auto Run prompt before running (or answer the Launch form, in Maestro versions that have one):

```markdown
**PR_URL:** `https://github.com/OWNER/REPO/pull/123`
**BASE_BRANCH:** `main`
```

Check out the PR branch in the agent's working directory first; the diff is taken against `origin/<BASE_BRANCH>`.

## Exit Conditions

Playbook completes when all 5 documents report `COMPLETED` status.

## Support

For issues or questions, refer to the Maestro documentation at <https://github.com/pedramamini/Maestro>.
