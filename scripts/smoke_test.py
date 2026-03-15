#!/usr/bin/env python3
"""
End-to-end smoke test — drives the full Strategist → Scraper → QuestionSetter
→ Evaluator pipeline via the mock webhook endpoint.

Usage:
    python scripts/smoke_test.py [--base-url http://localhost:8000]

Requires the server to be running (`make dev` or `make up-full`).
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ✗ HTTP {e.code}: {body[:300]}")
        sys.exit(1)


def get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ✗ HTTP {e.code}: {body[:300]}")
        sys.exit(1)


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print("\n" + "="*60)
    print("  SDE-3 Mentor Agent — Smoke Test")
    print("="*60)

    # ── 1. Health check ───────────────────────────────────────────────────────
    section("1/5  Health check")
    health = get(f"{base}/health")
    print(f"  Status     : {health.get('status')}")
    print(f"  Checkpointer: {health.get('checkpointer')}")
    assert health.get("status") == "ok", "Health check failed"
    print("  ✓ Server is up")

    # ── 2. Mock WhatsApp: start session ───────────────────────────────────────
    section("2/5  POST /webhook/mock  →  'start'")
    print("  Triggering Strategist → Scraper → QuestionSetter …")
    t0 = time.time()
    resp = post(f"{base}/webhook/mock", {"from": "+10000000001", "body": "start"})
    elapsed = time.time() - t0

    print(f"  user_id    : {resp.get('user_id')}")
    print(f"  thread_id  : {resp.get('thread_id')}")
    print(f"  stage_after: {resp.get('stage_after')}")
    print(f"  elapsed    : {elapsed:.1f}s")
    print()
    reply = resp.get("reply", "")
    print("  QUESTION PREVIEW (first 500 chars):")
    print("  " + reply[:500].replace("\n", "\n  "))
    assert resp.get("stage_after") == "testing", f"Expected stage 'testing', got {resp.get('stage_after')}"
    print("\n  ✓ Question generated and delivered")

    thread_id = resp["thread_id"]
    user_id   = resp["user_id"]

    # ── 3. REST: check session state ──────────────────────────────────────────
    section("3/5  GET /session/{thread_id}")
    state = get(f"{base}/session/{thread_id}?user_id={user_id}")
    print(f"  interview_stage   : {state.get('interview_stage')}")
    print(f"  current_topic     : {state.get('current_topic')}")
    print(f"  current_subtopic  : {state.get('current_subtopic')}")
    print(f"  knowledge_gap_score: {state.get('knowledge_gap_score')}")
    print("  ✓ State retrieved from checkpointer")

    # ── 4. Mock WhatsApp: submit a (deliberately weak) answer ─────────────────
    section("4/5  POST /webhook/mock  →  code submission")
    weak_answer = (
        "def solve(nums):\n"
        "    result = []\n"
        "    for i in range(len(nums)):\n"
        "        for j in range(i+1, len(nums)):\n"
        "            result.append(nums[i] + nums[j])\n"
        "    return result\n"
        "\n"
        "# I think this is O(n^2) but should work fine for the given constraints.\n"
        "# Thread safety is handled by the GIL in Python."
    )
    print("  Submitting a deliberately weak O(n²) answer with GIL hand-wave …")
    t0 = time.time()
    eval_resp = post(f"{base}/webhook/mock", {"from": "+10000000001", "body": weak_answer})
    elapsed = time.time() - t0

    print(f"  stage_after: {eval_resp.get('stage_after')}")
    print(f"  elapsed    : {elapsed:.1f}s")
    reply = eval_resp.get("reply", "")
    # Extract verdict line
    for line in reply.split("\n"):
        if "VERDICT" in line.upper() or "SCORE DELTA" in line.upper():
            print(f"  {line.strip()}")
    print()
    print("  FEEDBACK PREVIEW (first 600 chars):")
    print("  " + reply[:600].replace("\n", "\n  "))
    print("\n  ✓ Evaluation complete")

    # ── 5. History check ──────────────────────────────────────────────────────
    section("5/5  GET /session/{thread_id}/history")
    history = get(f"{base}/session/{thread_id}/history?user_id={user_id}")
    fb_count = len(history.get("feedback_history", []))
    msg_count = len(history.get("messages", []))
    print(f"  feedback_history entries : {fb_count}")
    print(f"  messages in thread       : {msg_count}")
    assert fb_count >= 1, "Expected at least 1 feedback_history entry"
    print("  ✓ History persisted in checkpointer")

    print("\n" + "="*60)
    print("  ALL TESTS PASSED ✓")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
