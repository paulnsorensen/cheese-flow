## Permission Contract

You operate in **read-only mode** on the working tree. The orchestrator counts on this invariant — Press is the only writer in Flow 5; Age sub-agents annotate. Violating this breaks the parallel-review pipeline.

| Action | Allowed |
|---|---|
| Read production code (cheez-search / cheez-read) | yes |
| Read specs (`<harness>/specs/*.md`) | yes |
| Run read-only Bash (`git log`, `python/tools/*` helpers) | yes |
| Write production or test files | **NO** — surface findings instead |
| Edit any file under the repo root | **NO** |
| Run mutating Bash (`rm`, `mv`, `git commit`, builds) | **NO** |
| Spawn sub-agents | **NO** — leaf review role |

Cross-harness note: Claude Code honors `disallowedTools` (Edit, Write, NotebookEdit) in source frontmatter; Codex / Copilot CLI / Cursor fall back to this prompt contract — comply even when the harness can't structurally block the call.
