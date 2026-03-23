"""Git integration utilities for Clawdia code review."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ChangedFile:
    """A file changed in a diff."""

    path: str
    additions: int
    deletions: int
    status: str  # "A" added, "M" modified, "D" deleted, "R" renamed


@dataclass
class DiffHunk:
    """A single @@ hunk from a unified diff."""

    header: str  # the @@ line
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)  # all lines in the hunk including header


@dataclass
class FileDiff:
    """Parsed diff for a single file."""

    path: str
    old_path: str | None  # for renames
    hunks: list[DiffHunk] = field(default_factory=list)
    raw: str = ""  # the raw unified diff text for this file

    @property
    def additions(self) -> int:
        return sum(
            1
            for h in self.hunks
            for line in h.lines
            if line.startswith("+") and not line.startswith("+++")
        )

    @property
    def deletions(self) -> int:
        return sum(
            1
            for h in self.hunks
            for line in h.lines
            if line.startswith("-") and not line.startswith("---")
        )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _run_git(args: list[str], cwd: str) -> str:
    """Run a git/gh command and return stdout. Raises RuntimeError on failure."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{stderr.decode()}")
    return stdout.decode()


# ---------------------------------------------------------------------------
# Diff retrieval
# ---------------------------------------------------------------------------

async def git_diff(cwd: str, staged: bool | None = False) -> str:
    """Return raw unified diff.

    If *staged* is ``True``, returns ``git diff --cached`` (staged only).
    If *staged* is ``False``, returns ``git diff`` (unstaged only).
    If *staged* is ``None``, returns all changes vs HEAD (staged + unstaged).
    """
    if staged is None:
        # All changes — compare working tree against HEAD
        return await _run_git(["git", "diff", "HEAD"], cwd)
    if staged:
        return await _run_git(["git", "diff", "--cached"], cwd)
    return await _run_git(["git", "diff"], cwd)


async def git_diff_branch(base: str, head: str = "HEAD", cwd: str = ".") -> str:
    """Return ``git diff base...head``."""
    return await _run_git(["git", "diff", f"{base}...{head}"], cwd)


async def git_diff_pr(pr_number: int, cwd: str = ".") -> str:
    """Return the patch-format diff for a PR via ``gh pr diff``.

    Raises ``RuntimeError`` if ``gh`` is not available or the command fails.
    """
    return await _run_git(["gh", "pr", "diff", str(pr_number), "--patch"], cwd)


# ---------------------------------------------------------------------------
# PR helpers (gh CLI)
# ---------------------------------------------------------------------------

async def git_pr_info(pr_number: int, cwd: str = ".") -> dict:
    """Return structured PR metadata via ``gh pr view --json``."""
    import json

    fields = (
        "title,body,state,headRefName,baseRefName,"
        "files,additions,deletions,author"
    )
    raw = await _run_git(
        ["gh", "pr", "view", str(pr_number), "--json", fields],
        cwd,
    )
    return json.loads(raw)


async def post_pr_review(
    pr_number: int,
    body: str,
    event: str = "COMMENT",
    cwd: str = ".",
) -> None:
    """Post a review on a PR via ``gh pr review``.

    *event* should be one of ``"approve"``, ``"request-changes"``, or
    ``"comment"`` (case-insensitive).
    """
    flag = f"--{event.lower()}"
    await _run_git(
        ["gh", "pr", "review", str(pr_number), "--body", body, flag],
        cwd,
    )


# ---------------------------------------------------------------------------
# Diff parsing (pure / synchronous)
# ---------------------------------------------------------------------------

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff string into a list of :class:`FileDiff` objects.

    Splits on ``diff --git`` boundaries, parses ``@@`` hunks, and handles
    renames (``rename from`` / ``rename to``).  Binary files are skipped.
    """
    if not diff_text or not diff_text.strip():
        return []

    # Split into per-file chunks. The first element before any "diff --git"
    # is empty or preamble — skip it.
    chunks = re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE)
    results: list[FileDiff] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("diff --git "):
            continue

        # Detect binary files and skip them
        if "Binary files" in chunk and "differ" in chunk:
            continue

        lines = chunk.split("\n")

        # Parse path from the diff --git line
        header_match = re.match(r"diff --git a/(.+?) b/(.+)", lines[0])
        if not header_match:
            continue
        a_path = header_match.group(1)
        b_path = header_match.group(2)

        # Detect renames
        old_path: str | None = None
        for line in lines:
            if line.startswith("rename from "):
                old_path = line[len("rename from "):]
            elif line.startswith("rename to "):
                b_path = line[len("rename to "):]

        # Parse hunks
        hunks: list[DiffHunk] = []
        current_hunk: DiffHunk | None = None
        for line in lines:
            m = _HUNK_RE.match(line)
            if m:
                current_hunk = DiffHunk(
                    header=line,
                    old_start=int(m.group(1)),
                    old_count=int(m.group(2)) if m.group(2) else 1,
                    new_start=int(m.group(3)),
                    new_count=int(m.group(4)) if m.group(4) else 1,
                    lines=[line],
                )
                hunks.append(current_hunk)
            elif current_hunk is not None:
                current_hunk.lines.append(line)

        results.append(
            FileDiff(
                path=b_path,
                old_path=old_path,
                hunks=hunks,
                raw=chunk,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Repository queries
# ---------------------------------------------------------------------------

async def git_changed_files(cwd: str, staged: bool = False) -> list[ChangedFile]:
    """Return file change stats via ``git diff --numstat``."""
    args = ["git", "diff", "--numstat"]
    if staged:
        args.append("--cached")

    raw = await _run_git(args, cwd)
    files: list[ChangedFile] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        adds_str, dels_str, path = parts
        # Binary files show "-" for additions/deletions
        adds = int(adds_str) if adds_str != "-" else 0
        dels = int(dels_str) if dels_str != "-" else 0

        # Determine status heuristically from numstat
        if adds > 0 and dels == 0 and "{" not in path and " => " not in path:
            status = "A"
        elif " => " in path or "{" in path:
            status = "R"
        elif adds == 0 and dels > 0:
            status = "D"
        else:
            status = "M"

        files.append(ChangedFile(path=path, additions=adds, deletions=dels, status=status))
    return files


async def git_log_oneline(cwd: str, n: int = 10) -> list[str]:
    """Return the last *n* commit one-liners."""
    raw = await _run_git(["git", "log", f"--oneline", f"-{n}"], cwd)
    return [line for line in raw.strip().splitlines() if line.strip()]


async def git_current_branch(cwd: str) -> str:
    """Return the current branch name."""
    raw = await _run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return raw.strip()


async def git_branches(cwd: str) -> list[str]:
    """Return a deduplicated list of local + remote branch names.

    Remote branches are included with the ``origin/`` prefix stripped so
    they're easy to type.  Local branches appear first, then any remote-
    only branches that aren't already listed.
    """
    raw_local = await _run_git(
        ["git", "branch", "--format=%(refname:short)"], cwd,
    )
    local = [b.strip() for b in raw_local.strip().splitlines() if b.strip()]

    try:
        raw_remote = await _run_git(
            ["git", "branch", "-r", "--format=%(refname:short)"], cwd,
        )
        remote = []
        for b in raw_remote.strip().splitlines():
            b = b.strip()
            if not b or "/" not in b:
                continue  # skip bare remote name (e.g. "origin" from HEAD)
            # Strip first remote prefix (e.g. "origin/main" → "main")
            short = b.split("/", 1)[1]
            remote.append(short)
    except RuntimeError:
        remote = []

    # Deduplicate preserving order: local first, then remote-only
    seen = set(local)
    for r in remote:
        if r not in seen:
            local.append(r)
            seen.add(r)
    return local


# ---------------------------------------------------------------------------
# Worktree management (Orchestrator v2)
# ---------------------------------------------------------------------------


async def is_git_repo(cwd: str) -> bool:
    """Check if the given directory is inside a git repository."""
    try:
        await _run_git(["git", "rev-parse", "--is-inside-work-tree"], cwd)
        return True
    except RuntimeError:
        return False


async def git_repo_root(cwd: str) -> str:
    """Return the root of the git repository containing *cwd*."""
    return (await _run_git(["git", "rev-parse", "--show-toplevel"], cwd)).strip()


async def git_create_branch(cwd: str, branch_name: str, start_point: str = "HEAD") -> None:
    """Create a new branch at *start_point* without checking it out."""
    await _run_git(["git", "branch", branch_name, start_point], cwd)


async def git_add_worktree(cwd: str, worktree_path: str, branch: str) -> str:
    """Create a git worktree at *worktree_path* on the given branch.

    Returns the absolute path of the created worktree.
    """
    Path(worktree_path).parent.mkdir(parents=True, exist_ok=True)
    await _run_git(["git", "worktree", "add", worktree_path, branch], cwd)
    return str(Path(worktree_path).resolve())


async def git_remove_worktree(cwd: str, worktree_path: str, force: bool = False) -> None:
    """Remove a worktree. Uses --force for dirty worktrees."""
    args = ["git", "worktree", "remove", worktree_path]
    if force:
        args.append("--force")
    await _run_git(args, cwd)


async def git_list_worktrees(cwd: str) -> list[dict]:
    """List all worktrees for the repo. Returns list of {path, branch, head}."""
    output = await _run_git(["git", "worktree", "list", "--porcelain"], cwd)
    worktrees: list[dict] = []
    current: dict = {}
    for line in output.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[9:]}
        elif line.startswith("HEAD "):
            current["head"] = line[5:]
        elif line.startswith("branch "):
            # "branch refs/heads/main" → "main"
            ref = line[7:]
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "bare":
            current["bare"] = True
    if current:
        worktrees.append(current)
    return worktrees


async def git_prune_worktrees(cwd: str) -> None:
    """Remove stale worktree administrative files."""
    await _run_git(["git", "worktree", "prune"], cwd)


async def git_delete_branch(cwd: str, branch: str, force: bool = False) -> None:
    """Delete a local branch."""
    flag = "-D" if force else "-d"
    await _run_git(["git", "branch", flag, branch], cwd)


def make_task_slug(task: str, max_len: int = 30) -> str:
    """Convert a task description into a branch-safe slug.

    Example: "Implement JWT auth system" -> "implement-jwt-auth-system"
    """
    slug = task.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug or "task"


# ---------------------------------------------------------------------------
# PR creation (Orchestrator v2)
# ---------------------------------------------------------------------------


async def git_create_pr(
    cwd: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict:
    """Stage, commit, push, and create a PR from the current branch.

    Returns ``{"number": int, "url": str, "title": str}``.
    """
    # Stage all changes
    await _run_git(["git", "add", "-A"], cwd)

    # Commit (may fail if nothing to commit — that's ok, push anyway)
    try:
        await _run_git(["git", "commit", "-m", f"Worker: {title}"], cwd)
    except RuntimeError:
        pass  # nothing to commit

    # Push the branch
    branch = (await git_current_branch(cwd)).strip()
    await _run_git(["git", "push", "-u", "origin", branch], cwd)

    # Create PR
    output = await _run_git(
        ["gh", "pr", "create", "--title", title, "--body", body, "--base", base],
        cwd,
    )

    # Parse PR URL from output (last line is typically the URL)
    pr_url = output.strip().splitlines()[-1].strip()
    pr_number = int(pr_url.rstrip("/").split("/")[-1]) if "/pull/" in pr_url else 0

    return {"number": pr_number, "url": pr_url, "title": title}


# ---------------------------------------------------------------------------
# CI status checking (Orchestrator v2)
# ---------------------------------------------------------------------------


@dataclass
class CICheck:
    """A single CI check run result."""

    name: str
    status: str  # "pass" | "fail" | "pending"
    url: str = ""


@dataclass
class CIStatus:
    """Aggregate CI status for a PR."""

    overall: str  # "pass" | "fail" | "pending"
    checks: list[CICheck] = field(default_factory=list)
    pr_number: int = 0

    @property
    def failed_checks(self) -> list[CICheck]:
        return [c for c in self.checks if c.status == "fail"]


async def git_pr_checks(pr_number: int, cwd: str = ".") -> CIStatus:
    """Get CI check status for a PR."""
    import json as _json

    try:
        output = await _run_git(
            ["gh", "pr", "checks", str(pr_number), "--json", "name,state,detailsUrl"],
            cwd,
        )
        raw = _json.loads(output)
    except (RuntimeError, _json.JSONDecodeError):
        return CIStatus(overall="pending", pr_number=pr_number)

    checks: list[CICheck] = []
    for c in raw:
        state = str(c.get("state", "")).upper()
        if state == "SUCCESS":
            status = "pass"
        elif state == "FAILURE":
            status = "fail"
        else:
            status = "pending"
        checks.append(CICheck(
            name=str(c.get("name", "")),
            status=status,
            url=str(c.get("detailsUrl", "")),
        ))

    if not checks:
        overall = "pending"
    elif any(c.status == "fail" for c in checks):
        overall = "fail"
    elif all(c.status == "pass" for c in checks):
        overall = "pass"
    else:
        overall = "pending"

    return CIStatus(overall=overall, checks=checks, pr_number=pr_number)


async def git_pr_check_logs(pr_number: int, cwd: str = ".") -> str:
    """Get failure logs for a PR's failing checks.

    Uses ``gh run view --log-failed`` on the most recent failing run.
    """
    import json as _json

    try:
        # Get the failing run ID
        output = await _run_git(
            ["gh", "pr", "checks", str(pr_number), "--json", "name,state,event,link"],
            cwd,
        )
        raw = _json.loads(output)
        # Find a failing check's run URL
        for c in raw:
            if str(c.get("state", "")).upper() == "FAILURE":
                link = str(c.get("link", ""))
                if "/runs/" in link:
                    run_id = link.split("/runs/")[-1].split("/")[0].split("?")[0]
                    try:
                        logs = await _run_git(
                            ["gh", "run", "view", run_id, "--log-failed"],
                            cwd,
                        )
                        return logs[:5000]  # truncate to reasonable size
                    except RuntimeError:
                        pass
    except (RuntimeError, _json.JSONDecodeError):
        pass

    return "(Could not retrieve CI failure logs)"


async def git_pr_review_comments(
    pr_number: int,
    cwd: str = ".",
    since: str | None = None,
) -> list[dict]:
    """Get review comments on a PR.

    Returns list of ``{"author": str, "body": str, "path": str, "created_at": str}``.
    """
    import json as _json

    try:
        output = await _run_git(
            ["gh", "pr", "view", str(pr_number), "--json", "reviewRequests,reviews,comments"],
            cwd,
        )
        raw = _json.loads(output)
    except (RuntimeError, _json.JSONDecodeError):
        return []

    comments: list[dict] = []

    # Extract review comments
    for review in raw.get("reviews", []):
        body = review.get("body", "").strip()
        if body:
            created = review.get("submittedAt", "")
            if since and created <= since:
                continue
            comments.append({
                "author": review.get("author", {}).get("login", "unknown"),
                "body": body,
                "path": "",
                "created_at": created,
            })

    # Extract inline comments
    for comment in raw.get("comments", []):
        body = comment.get("body", "").strip()
        if body:
            created = comment.get("createdAt", "")
            if since and created <= since:
                continue
            comments.append({
                "author": comment.get("author", {}).get("login", "unknown"),
                "body": body,
                "path": comment.get("path", ""),
                "created_at": created,
            })

    return comments
