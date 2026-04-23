import { describe, expect, it } from "vitest";
import { parseFrontmatter } from "../src/lib/frontmatter.js";

describe("parseFrontmatter", () => {
  it("parses valid frontmatter and body", () => {
    const content = "---\nname: cheddar\nage: 12\n---\nbody text\n";
    const { data, body } = parseFrontmatter<{ name: string; age: number }>(
      content,
    );

    expect(data).toEqual({ name: "cheddar", age: 12 });
    expect(body).toBe("body text\n");
  });

  it("handles Windows CRLF line endings", () => {
    const content = "---\r\nname: gouda\r\n---\r\nbody\r\n";
    const { data, body } = parseFrontmatter<{ name: string }>(content);

    expect(data).toEqual({ name: "gouda" });
    expect(body).toBe("body\r\n");
  });

  it("returns an empty object when frontmatter is empty", () => {
    const content = "---\n\n---\nbody only\n";
    const { data, body } = parseFrontmatter(content);

    expect(data).toEqual({});
    expect(body).toBe("body only\n");
  });

  it("throws when frontmatter delimiters are missing", () => {
    expect(() => parseFrontmatter("no markers here")).toThrow(
      /Expected YAML frontmatter/,
    );
  });

  it("throws when YAML inside frontmatter is invalid", () => {
    const content = "---\nname: : broken\n---\nbody\n";

    expect(() => parseFrontmatter(content)).toThrow();
  });
});
