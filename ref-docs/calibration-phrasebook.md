# Calibration phrasebook

Shared vocabulary for telling Claude that a score came out wrong.

Doran does not work in numbers. The scores are an internal mechanism, not a
language he is expected to speak. This file exists so he can say what he actually
means in plain English, and Claude can map it onto the right dimension without
asking him to guess a value.

**Claude: display the table below verbatim whenever Doran gives result-quality
feedback, and never ask him for a numeric score.** Ask him what was wrong with
the judgement, in his words. Translating that into a dimension and a direction is
your job, not his.

---

## The ten levers

Every scoring complaint lands on one of these. The weight is how much that lever
moves the final number, so a complaint about dimension 1 matters roughly seven
times more than one about dimension 10.

| # | Weight | The question it answers | Something Doran might say |
|---|---|---|---|
| 1 | **22** | Is this the job he invented at Cloudflare? | *"This isn't really the same kind of job."* |
| 4 | **14** | Does the money work? | *"The money doesn't clear my floor."* |
| 2 | 12 | Is he building things, or being an engineer? | *"This is more coding than I want."* |
| 5 | 12 | How far is it, realistically? | *"That commute is worse than it looks."* |
| 7 | 9 | Does he multiply other people, or just do the work himself? | *"Nobody here is asking me to teach anyone."* |
| 8 | 9 | Who does he serve — marketing, sales, IT, the whole company? | *"This serves Sales, and that matters more than you scored it."* |
| 3 | 8 | Is the seniority and scope band right? | *"That title is a step down."* |
| 6 | 6 | Remote, hybrid, or in-office? | *"Five days in-office should hurt more."* |
| 9 | 5 | Does the company actually mean it about AI? | *"They say AI but it's one bullet."* |
| 10 | 3 | Does he get to pick his tools and keep a human in the loop? | *"No latitude here — it's someone else's stack."* |

Weights mirror `config/scoring.yml`. If they are edited there, update them here in
the same change or this table starts lying.

Two things worth knowing about the shape of the rubric:

- **Dimension 1 alone is 22%** — nearly a quarter of the score. "This isn't the
  right kind of job" is the most powerful sentence Doran can say, and also the
  vaguest-sounding. Take it seriously and ask which part is off.
- **Dimensions 1, 8 and 10 sit in Block A**, where a score above 3.0 requires a
  quoted line from the posting. That is where inflated scoring hides, so a
  complaint about any of them is worth checking against the stored `block_notes`.

---

## The three shapes feedback arrives in

**A judgement was wrong.** *"GitLab shouldn't be my top result — it's a sales
enablement job wearing marketing clothes."* → a learned rule, narrowed to one
dimension and one direction. This is the common case.

**A structural rule is missing.** *"When comp tops out below my floor with no
equity, that should cap the whole thing, not just score one dimension low."*
→ this is not a rule, it is a change to `config/scoring.yml` (a cap, a modifier,
or a weight). Show Doran the diff and wait for approval. Never edit it silently.

**A posting should be pinned forever.** *"This is exactly a 4.0 — if anything
scores below it that I'd want, the rubric is broken."* → a new calibration anchor
in `config/scoring.yml` plus an anchor document under `ref-docs/golden/` or
`ref-docs/anti-examples/`. Stronger than a rule: it fails the test suite on drift.

---

## Writing the rule back

Always show Doran the proposed wording before writing it. A rule should name the
dimension, the direction, and the reason:

> *Down-weight dim 8 when the AI enablement mandate serves a Sales or CS org
> rather than Marketing: Doran's proof points become analogies rather than direct
> evidence, and the credibility cost is real. Not a disqualifier.*

Bad rule: *"Doran didn't like GitLab."* — teaches nothing and generalizes nowhere.

Keep rules narrow. A rule broad enough to reshape every score will break
calibration, so run `python cli.py calibrate --check` after any rule lands and
report which anchor moved if one does.
