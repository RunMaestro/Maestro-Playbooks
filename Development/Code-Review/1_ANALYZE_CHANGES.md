# Document 1: Analyze PR Changes

## Context

- **Playbook**: Code Review
- **Agent**: {{AGENT_NAME}}
- **Project**: {{AGENT_PATH}}
- **Date**: {{DATE}}
- **Working Folder**: {{AUTORUN_FOLDER}}

## Purpose

Understand the scope and context of the pull request before diving into detailed review.

## Pull Request Information

**Pull Request**: `[PR_URL]`

**Base Branch**: `[BASE_BRANCH]`

NOTE: *(Both values are set in the Auto Run prompt. Configure them there before running this playbook.)*

## Tasks

### Task 1: Fetch PR Context

- [ ] **Read configured values and validate the PR URL**: Read the agent prompt for [PR_URL] and [BASE_BRANCH]. Use these for the rest of this playbook. If [PR_URL] is missing or still the placeholder `https://github.com/OWNER/REPO/pull/XXX`, stop and instruct the user to set it in the Auto Run prompt before re-running. Do not proceed with any subsequent tasks. If [BASE_BRANCH] is missing, use `main`.

- [ ] **Read the PR description**: If a PR URL is provided above, understand what the PR claims to do. Note the stated goals and any linked issues.

- [ ] **Confirm the base branch**: Check that the PR targets [BASE_BRANCH] (for example with `gh pr view [PR_URL] --json baseRefName`). If it targets a different branch, use that branch for the diff below and note the mismatch in `REVIEW_SCOPE.md`.

### Task 2: Analyze Changed Files

- [ ] **Get the diff summary**: Run `git diff --stat origin/[BASE_BRANCH]...HEAD` (or the base branch confirmed above) to see all changed files and their modification sizes. If the diff output is empty (no changed files), record "No changed files detected" as the scope, skip Tasks 3 and the file-level sections of Task 4, and produce a minimal `REVIEW_SCOPE.md` noting the empty diff so downstream documents can short-circuit cleanly.

- [ ] **Categorize changes**: Group files by type:
  - Source code files
  - Test files
  - Configuration files
  - Documentation files
  - Build/CI files

### Task 3: Understand the Scope

- [ ] **Assess PR size**: Evaluate if this is a small (< 100 lines), medium (100-500 lines), or large (> 500 lines) PR.

- [ ] **Identify high-risk areas**: Note files that:
  - Handle authentication/authorization
  - Process user input
  - Interact with databases
  - Handle financial/sensitive data
  - Modify core business logic

### Task 4: Create Scope Document

- [ ] **Write REVIEW_SCOPE.md**: Create `{{AUTORUN_FOLDER}}/REVIEW_SCOPE.md` with:

```markdown
# PR Review Scope

## PR Information
- **URL**: [PR URL]
- **Title**: [PR Title if available]
- **Base Branch**: [target branch]
- **Size**: [small/medium/large]

## Changed Files Summary
[List of changed files grouped by category]

## High-Risk Areas
[Files requiring extra scrutiny]

## Review Focus
[Key areas to examine based on the changes]
```

## Success Criteria

- ✅ PR context understood
- ✅ All changed files identified
- ✅ Files categorized by type
- ✅ High-risk areas flagged
- ✅ REVIEW_SCOPE.md created

## Status

Mark complete when scope document is created.

---

**Next**: Document 2 will perform deep code review for correctness and best practices.
