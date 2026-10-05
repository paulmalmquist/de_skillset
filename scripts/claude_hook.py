"""Local lint feedback plus an optional, explicitly configured read-only MCP adapter."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    try:
        from flightcheck.sql_audit import audit_sql, parse_query
        from flightcheck.policy import load_policy
        policy = load_policy(ROOT / "config/policy.yml")
        tool_input = event.get("tool_input", {})
        if name == "PreToolUse":
            sql = tool_input.get("sql") or tool_input.get("query")
            if not isinstance(sql, str) or not sql.strip():
                raise ValueError("Unrecognized query input. Map this adapter to the real tool schema before use.")
            parse_query(sql, policy.dialect)
            return 0
        path = tool_input.get("file_path")
        if not path or not path.endswith(".sql"):
            return 0
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            return 0
        if path.stat().st_size > 200000:
            raise ValueError("SQL file exceeds hook limit; run the CLI audit explicitly.")
        layer = "consumer"
        for folder, candidate in [("staging", "staging"), ("intermediate", "intermediate"), ("marts", "mart"), ("mart", "mart"), ("serving", "serving")]:
            if folder in path.relative_to(ROOT).parts:
                layer = candidate
                break
        result = audit_sql(path.read_text(), layer, policy, str(path.relative_to(ROOT)))
        context = f"Flightcheck SQL audit: {result['status']}. " + "; ".join(f"{f['rule']}: {f['message']}" for f in result["findings"][:8])
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context + " This is post-edit feedback, not a release approval. Uncompiled dbt SQL must be compiled before auditing."}}))
        return 0
    except Exception as exc:
        if name == "PreToolUse":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Flightcheck cannot verify this read-only request: {exc}"}}))
        else:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Flightcheck could not complete its audit: {exc}. Treat the SQL as unchecked."}}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
