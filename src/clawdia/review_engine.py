"""AI-powered code review annotation engine.

Sends file diffs to Claude for review and returns structured per-hunk annotations.
Uses the Anthropic API directly for lightweight, focused review requests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Annotation:
    """A single review annotation on a diff hunk."""

    hunk_index: int  # 0-based index into the file's hunks
    severity: str  # "info", "warning", "error", "praise"
    comment: str  # the review comment
    suggestion: str | None = None  # optional code suggestion

    @property
    def emoji(self) -> str:
        return {"info": "\U0001f4a1", "warning": "\u26a0\ufe0f", "error": "\U0001f41b", "praise": "\u2705"}.get(
            self.severity, "\U0001f4ac"
        )


@dataclass
class FileReview:
    """Review result for a single file."""

    path: str
    annotations: list[Annotation] = field(default_factory=list)
    summary: str = ""  # 1-sentence overall assessment

    @property
    def has_issues(self) -> bool:
        return any(a.severity in ("warning", "error") for a in self.annotations)


REVIEW_SYSTEM_PROMPT = """\
You are an expert code reviewer. You will receive a unified diff for a single file \
and must review it for:

1. **Bugs** — logic errors, off-by-one errors, null/None handling, race conditions
2. **Security** — injection, unsanitized input, credential exposure, path traversal
3. **Quality** — dead code, unnecessary complexity, missing error handling
4. **Style** — naming, consistency with surrounding code patterns

For each issue or notable aspect, identify which hunk it belongs to (0-indexed).

Respond with valid JSON only — no markdown, no explanation outside the JSON:
{
  "summary": "One sentence overall assessment",
  "annotations": [
    {
      "hunk_index": 0,
      "severity": "error",
      "comment": "Explanation of the issue",
      "suggestion": "Optional corrected code or null"
    }
  ]
}

Severity levels:
- "error" — bugs, security issues, will cause problems
- "warning" — potential issues, code smells, risky patterns
- "info" — suggestions for improvement, style notes
- "praise" — good patterns worth highlighting

Be concise. Focus on substantive issues. Don't nitpick formatting. If the diff looks \
good, return an empty annotations list with a positive summary."""


async def review_file(
    file_path: str,
    diff_text: str,
    model: str = "sonnet",
    context: str | None = None,
) -> FileReview:
    """Review a single file's diff and return structured annotations.

    Args:
        file_path: Path of the file being reviewed.
        diff_text: The raw unified diff text for this file.
        model: Model tier — "haiku", "sonnet", or "opus".
        context: Optional additional context (e.g., PR description).

    Returns:
        FileReview with annotations.
    """
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed — skipping review")
        return FileReview(path=file_path, summary="Review unavailable (SDK not installed)")

    # Map tier names to model IDs
    model_map = {
        "haiku": "claude-haiku-4-20250414",
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-20250514",
    }
    model_id = model_map.get(model, model_map["sonnet"])

    user_msg = f"## File: `{file_path}`\n\n```diff\n{diff_text}\n```"
    if context:
        user_msg = f"## Context\n{context}\n\n{user_msg}"

    try:
        client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var
        response = await client.messages.create(
            model=model_id,
            max_tokens=2048,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        # Parse the JSON response
        raw = response.content[0].text.strip()
        # Handle markdown code fences if model wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        annotations = []
        for a in data.get("annotations", []):
            annotations.append(
                Annotation(
                    hunk_index=a.get("hunk_index", 0),
                    severity=a.get("severity", "info"),
                    comment=a.get("comment", ""),
                    suggestion=a.get("suggestion"),
                )
            )

        return FileReview(
            path=file_path,
            annotations=annotations,
            summary=data.get("summary", ""),
        )

    except json.JSONDecodeError as exc:
        log.warning("Failed to parse review response as JSON: %s", exc)
        return FileReview(path=file_path, summary="Review response was not valid JSON")
    except anthropic.APIError as exc:
        log.warning("Anthropic API error during review: %s", exc)
        return FileReview(path=file_path, summary=f"API error: {exc}")
    except Exception as exc:
        log.exception("Unexpected error during file review")
        return FileReview(path=file_path, summary=f"Review failed: {exc}")


async def review_diff(
    file_diffs: list,
    model: str = "sonnet",
    context: str | None = None,
    on_file_reviewed: "callable | None" = None,
) -> list[FileReview]:
    """Review multiple files from a parsed diff.

    Args:
        file_diffs: List of FileDiff objects (from git_utils.parse_unified_diff).
        model: Model tier for review.
        context: Optional context (PR description, etc).
        on_file_reviewed: Optional callback(file_path, FileReview) called after each file.

    Returns:
        List of FileReview results.
    """
    reviews = []
    for fd in file_diffs:
        review = await review_file(
            file_path=fd.path,
            diff_text=fd.raw,
            model=model,
            context=context,
        )
        reviews.append(review)
        if on_file_reviewed:
            on_file_reviewed(fd.path, review)
    return reviews


def format_review_markdown(reviews: list[FileReview], title: str = "Code Review") -> str:
    """Format review results as a GitHub-compatible markdown comment.

    Suitable for posting via ``gh pr review --body``.
    """
    lines = [f"## {title}\n"]

    total_issues = sum(len(r.annotations) for r in reviews)
    errors = sum(1 for r in reviews for a in r.annotations if a.severity == "error")
    warnings = sum(1 for r in reviews for a in r.annotations if a.severity == "warning")

    lines.append(
        f"Reviewed {len(reviews)} files — {total_issues} annotations "
        f"({errors} errors, {warnings} warnings)\n"
    )

    for review in reviews:
        if not review.annotations and not review.summary:
            continue
        lines.append(f"### `{review.path}`")
        if review.summary:
            lines.append(f"_{review.summary}_\n")
        for a in review.annotations:
            lines.append(f"- {a.emoji} **{a.severity.upper()}** (hunk {a.hunk_index + 1}): {a.comment}")
            if a.suggestion:
                lines.append(f"  ```suggestion\n  {a.suggestion}\n  ```")
        lines.append("")

    lines.append("---")
    lines.append("_\U0001f916 Reviewed by Re:Clawed AI Code Review_")

    return "\n".join(lines)
