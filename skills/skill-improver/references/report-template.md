# /skill-improver Report Template

The orchestrator's Phase 3 fills in every `<!-- placeholder -->` comment.
Do NOT include numeric scores anywhere in the rendered output.

The shape mirrors `skills/age/references/report-template.md` so /age and
/skill-improver readers do not have to learn two layouts.

---

## Skill-Improver Review: <!-- placeholder: slug, e.g. "agents-foo-md-eta-2026-04-29" -->

<!-- placeholder: orientation paragraph — 2-4 factual sentences built by the
orchestrator from the target's frontmatter. State the target kind (agent vs
skill), declared model tier, tool surface (read-only / write-scoped / focused),
and prompt body line count. Not evaluative.

Example: "Target: agents/foo.md.eta — a Claude Code review agent declared at
haiku tier with 6 tools (read-only) and a 92-line body. Activation dim found
no trigger phrases; tool-scoping dim found Edit reachable despite a 'read-only'
prose claim." -->

Ran <!-- placeholder: 5 --> dims; <!-- placeholder: N --> had findings
(`<!-- placeholder: dim-names with findings -->`).
<!-- placeholder: dims with scope_match: false, if any -->

---

## High-stakes findings

<!-- placeholder: one section per high-stake dim (activation, tool-scoping)
with observations. Omit dim section entirely if empty — it is counted in the
tally above. -->

### <!-- placeholder: dim name, e.g. "activation" -->

<!-- placeholder: per-observation block, repeat for each observation:

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

<!-- placeholder: one section per medium-stake dim (context, prompt-quality,
output-format) with observations. Same per-observation format as above. -->

### <!-- placeholder: dim name -->

<!-- placeholder: per-observation blocks -->

---

## Cross-dimension callouts

<!-- placeholder: panel appears only when group_by_locus() finds observations
from ≥ 2 dims within a 3-line window. Omit entirely if no cross-dim overlap.

Format per callout:

**<file>:<approx-line>** — agreement across: <dim1>, <dim2>
- <dim1>: <observation narrative, one line>
- <dim2>: <observation narrative, one line>

-->

---

*Report written to `.cheese/skill-improver/<slug>.md`. Fixes: <!-- placeholder: N -->. Suggestions: <!-- placeholder: N -->.*
*To apply fixes: `/cleanup <slug>` — to act on suggestions: `/fromage cook --suggestions <slug>`*
