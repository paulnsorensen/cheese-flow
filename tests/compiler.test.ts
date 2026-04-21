import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { installHarnessArtifacts, previewAgent, readSkill } from '../src/lib/compiler.js';

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await import('node:fs/promises').then(({ rm }) => rm(directory, { recursive: true, force: true }));
    })
  );
});

describe('installHarnessArtifacts', () => {
  it('compiles the basic agent template for Claude Code and Codex', async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'cheese-flow-'));
    createdDirectories.push(projectRoot);
    await import('node:fs/promises').then(async ({ cp }) => {
      await cp(path.resolve('agents'), path.join(projectRoot, 'agents'), { recursive: true });
      await cp(path.resolve('skills'), path.join(projectRoot, 'skills'), { recursive: true });
    });

    const outputs = await installHarnessArtifacts({
      projectRoot,
      harnesses: ['claude-code', 'codex']
    });

    expect(outputs).toHaveLength(2);

    const claudeAgent = await readFile(
      path.join(projectRoot, '.claude', 'agents', 'basic-agent.md'),
      'utf8'
    );
    const codexAgent = await readFile(path.join(projectRoot, '.codex', 'agents', 'basic-agent.md'), 'utf8');

    expect(claudeAgent).toContain('claude-sonnet-4-5');
    expect(codexAgent).toContain('gpt-5.1-codex');
  });

  it('validates the shipped skill metadata', async () => {
    const skill = await readSkill(path.resolve('.'), 'basic-skill');
    expect(skill.name).toBe('basic-skill');
    expect(skill.description).toContain('portable');
  });

  it('renders a preview from the template source', async () => {
    const output = await previewAgent(path.resolve('.'), 'basic-agent.md.eta', 'claude-code');
    expect(output).toContain('Harness target: Claude Code');
  });

  it('rejects skills whose folder name does not match the spec name', async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'cheese-flow-invalid-'));
    createdDirectories.push(projectRoot);
    await import('node:fs/promises').then(async ({ mkdir, cp }) => {
      await mkdir(path.join(projectRoot, 'agents'), { recursive: true });
      await mkdir(path.join(projectRoot, 'skills', 'wrong-name'), { recursive: true });
      await cp(path.resolve('agents', 'basic-agent.md.eta'), path.join(projectRoot, 'agents', 'basic-agent.md.eta'));
    });

    await writeFile(
      path.join(projectRoot, 'skills', 'wrong-name', 'SKILL.md'),
      `---\nname: basic-skill\ndescription: Portable test skill\n---\n# Wrong\n`,
      'utf8'
    );

    await expect(
      installHarnessArtifacts({
        projectRoot,
        harnesses: ['claude-code']
      })
    ).rejects.toThrow(/must match frontmatter name/u);
  });
});
