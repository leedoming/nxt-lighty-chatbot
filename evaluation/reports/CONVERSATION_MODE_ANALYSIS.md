# Conversation Context Analysis — Slack Thread vs DM

## Application behavior

The historical code uses two separate history paths:

- **Thread:** `conversations_replies` → thread-local history.
- **DM:** `conversations_history(limit=10)` → adjacent user/assistant pairs → latest 3 pairs.

The DM implementation therefore reconstructs conversational context from a wider channel history rather than a thread-scoped branch. This does **not by itself prove causality**, but it gives a concrete implementation-level hypothesis for testing the observed DM reference-resolution failures.

## Observed DM failure pattern

The clearest pair is the repeated classroom-rental scenario:

1. User: `강의실 대여할래`
2. Bot: answers about classroom/facility rental from the correct campus source.
3. User: `학생들끼리 대여하면?` / `학생끼리 대여하는 거면 괜찮은거지?`
4. Bot loses the antecedent `강의실` and switches topic to either dormitory-room transfer or personal-item lending.

The failure occurs even though the prior single-turn answer was mostly grounded, so the appropriate label is **conversation-context/reference-resolution failure**, not merely “RAG retrieval failed.”

## Testable remediation ideas

- Persist an explicit `active_topic` / `resolved_subject` for elliptical follow-ups.
- Build DM history as role-structured messages instead of concatenated text pairs.
- Exclude irrelevant earlier turns using similarity or turn-window selection.
- Add a clarification rule when the referent is ambiguous rather than silently switching domains.
- Add regression cases for `강의실 대여 → 학생들끼리 대여하면?` and similar pronoun/ellipsis sequences.
