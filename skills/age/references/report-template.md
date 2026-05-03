# /age Report Template

The orchestrator's Phase 3 fills in every `<!-- placeholder -->` comment.
Do NOT include numeric scores anywhere in the rendered output.

---

## Review: <!-- placeholder: slug, e.g. "my-feature-abc123" -->

<!-- placeholder: orientation paragraph -- 2-4 factual sentences built by the
orchestrator from the correctness and precedent agents' summaries. State what
changed, what patterns are present, and any prior-art signals. Not evaluative.
Example: "This diff adds a new cache layer to the payments module (3 files,
+187/-42). The correctness agent found one null-dereference path in the happy
route. Precedent shows the same pattern was reverted in commit a1b2c3 six
months ago." -->

Ran <!-- placeholder: N --> dims; <!-- placeholder: N --> had findings
(`<!-- placeholder: dim-names with findings, comma-separated -->`).
<!-- placeholder: dims with scope_match: false, if any -->

---

## High-stakes findings

<!-- placeholder: one section per high-stake dim (correctness, security,
encapsulation, spec) with observations. Omit dim section entirely if empty --
it is counted in the tally above. -->

### <!-- placeholder: dim name, e.g. "correctness" -->

<!-- placeholder: per-observation block -- repeat for each observation.

<narrative text>

bucket: low|med|high

**Evidence**
- <evidence[0]>
- <evidence[1]>

**Consideration** (omit if fix is set)
<consideration text>

**Fix available** (omit if fix is absent)
Category: <fix.category>

-->

---

## Medium-stakes findings

<!-- placeholder: one section per medium-stake dim (complexity, deslop,
assertions) with observations. Same per-observation format as above. -->

### <!-- placeholder: dim name -->

<!-- placeholder: per-observation blocks -->

---

## Advisory findings

<!-- placeholder: one section for the precedent dim if it has observations.
Same per-observation format. -->

### precedent

<!-- placeholder: per-observation blocks -->

---

## Cross-dimension callouts

<!-- placeholder: panel appears only when group_by_locus() finds observations
from >= 2 dims within a 3-line window. Omit entirely if no cross-dim overlap.

Format per callout:

**<file>:<approx-line>** -- agreement across: <dim1>, <dim2>
- <dim1>: <observation narrative, one line>
- <dim2>: <observation narrative, one line>

-->

---

*Report written to `.cheese/age/<slug>.md`. Fixes: <!-- placeholder: N -->. Suggestions: <!-- placeholder: N -->.*
*Next step: `/cure <slug>` — applies fixes, routes suggestions, and re-ages the touched paths.*
