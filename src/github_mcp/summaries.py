"""Response shaping.

Each helper trims a GitHub API payload to the fields worth showing a
model and drops the rest. Pure functions: no I/O, no configuration.
"""

from __future__ import annotations

from typing import Any


def _summarize_repo(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "description": repo.get("description"),
        "private": repo.get("private"),
        "fork": repo.get("fork"),
        "default_branch": repo.get("default_branch"),
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues": repo.get("open_issues_count"),
        "html_url": repo.get("html_url"),
        "updated_at": repo.get("updated_at"),
    }


def _summarize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "user": (issue.get("user") or {}).get("login"),
        "labels": [label.get("name") for label in issue.get("labels", [])],
        "comments": issue.get("comments"),
        "is_pull_request": "pull_request" in issue,
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "html_url": issue.get("html_url"),
    }


def _summarize_pull(pull: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pull.get("number"),
        "title": pull.get("title"),
        "state": pull.get("state"),
        "draft": pull.get("draft"),
        "user": (pull.get("user") or {}).get("login"),
        "head": (pull.get("head") or {}).get("ref"),
        "base": (pull.get("base") or {}).get("ref"),
        "merged": pull.get("merged"),
        "mergeable": pull.get("mergeable"),
        "comments": pull.get("comments"),
        "review_comments": pull.get("review_comments"),
        "changed_files": pull.get("changed_files"),
        "additions": pull.get("additions"),
        "deletions": pull.get("deletions"),
        "created_at": pull.get("created_at"),
        "html_url": pull.get("html_url"),
    }


def _summarize_commit(commit: dict[str, Any]) -> dict[str, Any]:
    detail = commit.get("commit", {})
    author = detail.get("author", {})
    return {
        "sha": commit.get("sha"),
        "message": detail.get("message"),
        "author": author.get("name"),
        "date": author.get("date"),
        "html_url": commit.get("html_url"),
    }


def _summarize_file(file: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": file.get("filename"),
        "status": file.get("status"),
        "additions": file.get("additions"),
        "deletions": file.get("deletions"),
        "changes": file.get("changes"),
        "previous_filename": file.get("previous_filename"),
    }


def _summarize_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "display_title": run.get("display_title"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "run_number": run.get("run_number"),
        "created_at": run.get("created_at"),
        "html_url": run.get("html_url"),
    }


def _summarize_release(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_name": release.get("tag_name"),
        "name": release.get("name"),
        "draft": release.get("draft"),
        "prerelease": release.get("prerelease"),
        "published_at": release.get("published_at"),
        "author": (release.get("author") or {}).get("login"),
        "html_url": release.get("html_url"),
    }


def _summarize_job(job: dict[str, Any]) -> dict[str, Any]:
    steps = job.get("steps") or []
    failed_steps = [
        s.get("name") for s in steps if s.get("conclusion") == "failure"
    ]
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "status": job.get("status"),
        "conclusion": job.get("conclusion"),
        "failed_steps": failed_steps,
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "html_url": job.get("html_url"),
    }


def _summarize_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": review.get("id"),
        "user": (review.get("user") or {}).get("login"),
        "state": review.get("state"),
        "body": review.get("body"),
        "submitted_at": review.get("submitted_at"),
        "html_url": review.get("html_url"),
    }


def _summarize_secret_alert(alert: dict[str, Any]) -> dict[str, Any]:
    # Deliberately omit the raw `secret` value GitHub may include.
    return {
        "number": alert.get("number"),
        "state": alert.get("state"),
        "secret_type": alert.get("secret_type"),
        "secret_type_display_name": alert.get("secret_type_display_name"),
        "resolution": alert.get("resolution"),
        "created_at": alert.get("created_at"),
        "html_url": alert.get("html_url"),
    }


def _summarize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    # Works for issue/PR conversation comments and inline review comments
    # (the latter add path/line).
    out = {
        "id": comment.get("id"),
        "user": (comment.get("user") or {}).get("login"),
        "body": comment.get("body"),
        "created_at": comment.get("created_at"),
        "html_url": comment.get("html_url"),
    }
    if "path" in comment:
        out["path"] = comment.get("path")
        out["line"] = comment.get("line")
    return out


def _summarize_notification(n: dict[str, Any]) -> dict[str, Any]:
    subject = n.get("subject") or {}
    return {
        "id": n.get("id"),
        "reason": n.get("reason"),
        "unread": n.get("unread"),
        "title": subject.get("title"),
        "type": subject.get("type"),
        "url": subject.get("url"),
        "repository": (n.get("repository") or {}).get("full_name"),
        "updated_at": n.get("updated_at"),
    }


def _summarize_check_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "html_url": run.get("html_url"),
    }


def _summarize_code_scanning_alert(alert: dict[str, Any]) -> dict[str, Any]:
    rule = alert.get("rule") or {}
    tool = alert.get("tool") or {}
    return {
        "number": alert.get("number"),
        "state": alert.get("state"),
        "rule_id": rule.get("id"),
        "severity": rule.get("security_severity_level") or rule.get("severity"),
        "description": rule.get("description"),
        "tool": tool.get("name"),
        "created_at": alert.get("created_at"),
        "html_url": alert.get("html_url"),
    }


def _summarize_dependabot_alert(alert: dict[str, Any]) -> dict[str, Any]:
    advisory = alert.get("security_advisory") or {}
    dep = (alert.get("dependency") or {}).get("package") or {}
    return {
        "number": alert.get("number"),
        "state": alert.get("state"),
        "package": dep.get("name"),
        "ecosystem": dep.get("ecosystem"),
        "severity": advisory.get("severity"),
        "summary": advisory.get("summary"),
        "created_at": alert.get("created_at"),
        "html_url": alert.get("html_url"),
    }


def _summarize_gist(gist: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": gist.get("id"),
        "description": gist.get("description"),
        "public": gist.get("public"),
        "files": list((gist.get("files") or {}).keys()),
        "html_url": gist.get("html_url"),
    }
