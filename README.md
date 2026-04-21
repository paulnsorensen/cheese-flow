# cheese-flow

Opinionated scaffolding for portable agents and skills that can be compiled into harness-specific markdown bundles.

## Stack choices

- **CLI framework:** Commander.js, the most practical general-purpose TypeScript CLI choice for April 2026
- **Object safety:** Zod
- **Template engine:** Eta for portable template-to-markdown compilation
- **Skill format:** Agent Skills compatible `SKILL.md`

## Repository layout

- `src/` — TypeScript CLI and compiler
- `agents/` — harness-agnostic Eta markdown templates
- `skills/` — portable Agent Skills definitions
- `.claude/` / `.codex/` — generated install outputs

## Getting started

```bash
npm install
npm run build
npm run install:claude
npm run install:codex
```

Or target specific harnesses directly:

```bash
npx tsx src/index.ts install --harness claude-code
npx tsx src/index.ts install --harness codex
npx tsx src/index.ts install --harness claude-code,codex
```

## What `install` does

- Validates Agent Skills frontmatter with Zod
- Validates agent template metadata with Zod
- Compiles `agents/*.md.eta` into plain markdown for the selected harness
- Copies `skills/*/SKILL.md` into the harness bundle
- Writes a small manifest for the generated bundle

## Example output

- Claude Code bundle: `.claude/`
- Codex bundle: `.codex/`

Each bundle contains:

- `agents/*.md`
- `skills/*/SKILL.md`
- `manifest.json`
