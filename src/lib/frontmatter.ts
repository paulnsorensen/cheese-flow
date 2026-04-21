import { parseDocument } from 'yaml';

const frontmatterPattern = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/u;

export function parseFrontmatter<T>(content: string): { data: T; body: string } {
  const match = content.match(frontmatterPattern);

  if (!match) {
    throw new Error('Expected YAML frontmatter bounded by --- markers.');
  }

  const [, rawFrontmatter, body] = match;
  const document = parseDocument(rawFrontmatter);

  if (document.errors.length > 0) {
    throw new Error(document.errors.map((error) => error.message).join('\n'));
  }

  return {
    data: (document.toJS() ?? {}) as T,
    body
  };
}
