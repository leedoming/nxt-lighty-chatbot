# Final Answer Evaluation v1 — Thread vs DM Historical Samples

## Scope

This retrospective evaluation contains **29 historical Lighty response cases** recovered from screenshots and user-provided transcripts.

- **Thread samples: 20** — all previously preserved Slack screenshot/transcript examples.
- **DM samples: 9** — newly added examples from direct-message conversations.
- Retrieval benchmark and final-answer review remain separate: retrieval metrics come from the reconstructed 2025-03-25 corpus; this file reviews **actual historical answer behavior**.
- The samples are manually preserved convenience examples, **not a random production sample**. Counts below are for failure analysis only and must not be presented as production-wide accuracy rates.

## Why thread and DM must be separated

The application code reconstructs context differently by conversation mode:

- `get_thread_history(...)` reads replies from one Slack thread.
- `get_dm_history(...)` reads recent DM history, rebuilds adjacent user→assistant pairs, and keeps up to the latest three pairs.

Therefore a retrieval failure, a generation failure, and a conversation-context failure should not be collapsed into one label.

## New DM findings

### 1. Elliptical follow-ups lose their referent

Two separate DM trials started with **“강의실 대여할래”** and then used an abbreviated follow-up meaning “what if students rent it?”

- `FA-025`: the bot changed the referent from **classroom** to **dormitory room**.
- `FA-029`: the bot changed the referent from **classroom** to **personal item lending**.

The recovered campus source explicitly states that **student use of facilities requires approval from 학생지원처**. These are therefore not simple source-missing cases: they are clear **context/reference-resolution failures**.

### 2. User correction does not guarantee safe recovery

`FA-021` first shows a **role reversal**: instead of answering how to handle a locked classroom, the bot asks the same question back to the user.

After the user explicitly says “you should tell me; if you do not know, say you do not know,” `FA-022` produces a detailed key/door-opening procedure. The department phone numbers exist in the corpus, but the **specific classroom-unlock procedure is not supported by the recovered source**. This is a useful example of hallucination after conversational repair.

### 3. Correct context can still end in answer omission

`FA-027` correctly routes a name-change/certificate follow-up to the academic-records department, but renders only the department card. The corpus contains a direct procedure — resident-registration extract, change form/consent, and next-day certificate issuance after correction — so this is best classified as **follow-up answer omission**, not retrieval absence.

### 4. Single-turn grounding and multi-turn continuity are different axes

The repeated single-turn classroom-rental question (`FA-024`, `FA-028`) is substantially grounded in the campus source. The failures occur **after** the shortened follow-up. This supports evaluating:

1. retrieval/source grounding,
2. final-answer factuality/completeness,
3. conversation continuity/reference resolution,

as independent dimensions.

## Selected thread findings retained from v0

- Strong grounded examples exist for certificate issuance, library contacts, and shuttle facts.
- Department routing can fail even when the substantive answer is grounded.
- OOD questions can trigger unsupported generation (`FA-006`).
- Some responses expose intermediate formatting or produce visible send/render errors (`FA-020`, others).

## Recommended evaluation dimensions

Use separate labels rather than one aggregate score:

1. **Correctness** — supported factual claims are correct.
2. **Completeness** — the answer covers the user's required information.
3. **Groundedness** — claims are supported by recovered evidence.
4. **Abstention** — the bot declines or narrows the answer when evidence is absent.
5. **Department routing** — the responsible office is appropriate.
6. **Format / delivery** — internal scaffolding is hidden and Slack rendering succeeds.
7. **Context retention** — a follow-up preserves the active subject.
8. **Reference resolution** — omitted nouns/pronouns correctly resolve to the prior turn.
9. **Role adherence** — the assistant answers rather than delegating the question back to the user.

## Interpretation guardrails

- Do **not** report “11/18 = production accuracy” or any similar percentage from these historical captures.
- Thread-vs-DM counts are descriptive only because the evidence was selected, not sampled.
- When a claim cannot be verified from recovered source material, use `UNVERIFIED` rather than marking it factually false.
- A real department phone number does not make an unsupported procedure grounded; evaluate routing and procedural claims separately.
