import { describe, it, expect } from 'vitest';
import {
  parseSections,
  serializeSections,
  setSection,
  findSection,
  parseCriteria,
  serializeCriteria,
  unknownSections,
} from './body-sections';

const BODY = `## Summary

Add a thing.

## Acceptance Criteria

- [ ] First
- [x] Second

## Design notes

Some custom section the form does not know about.

\`\`\`
## not a heading inside a fence
\`\`\`
`;

describe('parseSections', () => {
  it('splits on ## headings in order', () => {
    const s = parseSections(BODY);
    expect(s.map((x) => x.heading)).toEqual(['Summary', 'Acceptance Criteria', 'Design notes']);
  });

  it('does not split on headings inside a fenced code block', () => {
    const s = parseSections(BODY);
    const design = findSection(s, 'Design notes')!;
    expect(design.content).toContain('## not a heading inside a fence');
  });

  it('keeps a non-empty preamble as an empty-heading section', () => {
    const s = parseSections('intro text\n\n## Summary\n\nx');
    expect(s[0].heading).toBe('');
    expect(s[0].content).toBe('intro text');
  });

  it('drops an empty leading preamble', () => {
    const s = parseSections('\n\n## Summary\n\nx');
    expect(s[0].heading).toBe('Summary');
  });
});

describe('round-trip', () => {
  it('serializeSections(parseSections(body)) preserves headings, order, and content', () => {
    const reparsed = parseSections(serializeSections(parseSections(BODY)));
    expect(reparsed.map((x) => x.heading)).toEqual([
      'Summary',
      'Acceptance Criteria',
      'Design notes',
    ]);
    expect(findSection(reparsed, 'Summary')!.content).toBe('Add a thing.');
    expect(findSection(reparsed, 'Design notes')!.content).toContain('custom section');
  });

  it('preserves an unknown section verbatim through a known-section edit', () => {
    let sections = parseSections(BODY);
    sections = setSection(sections, 'Summary', 'A new summary.');
    const out = serializeSections(sections);
    expect(out).toContain('## Summary\n\nA new summary.');
    expect(out).toContain('## not a heading inside a fence'); // unknown survived
  });

  it('is a fixed point: editing a section reads back exactly what was written', () => {
    // Mirrors the form editor's per-keystroke cycle. If the read-back differed
    // from the typed text, a controlled textarea would jump the cursor / drop chars.
    const typed = 'Line one\nLine two with **bold** and a - dash';
    const body = serializeSections(setSection(parseSections(BODY), 'Summary', typed));
    expect(findSection(parseSections(body), 'Summary')!.content).toBe(typed);
  });
});

describe('setSection', () => {
  it('inserts a new section when absent', () => {
    const s = setSection([], 'Notes', 'hello');
    expect(findSection(s, 'Notes')!.content).toBe('hello');
  });

  it('removes a section when blanked', () => {
    let s = parseSections('## Notes\n\nx');
    s = setSection(s, 'Notes', '   ');
    expect(findSection(s, 'Notes')).toBeUndefined();
  });
});

describe('acceptance criteria', () => {
  it('parses checkbox rows', () => {
    const rows = parseCriteria('- [ ] a\n- [x] b\nnot a row');
    expect(rows).toEqual([
      { checked: false, text: 'a' },
      { checked: true, text: 'b' },
    ]);
  });

  it('round-trips rows, dropping empties', () => {
    const md = serializeCriteria([
      { checked: true, text: 'done' },
      { checked: false, text: '   ' },
      { checked: false, text: 'todo' },
    ]);
    expect(md).toBe('- [x] done\n- [ ] todo');
  });
});

describe('unknownSections', () => {
  it('returns only sections the form does not know', () => {
    const u = unknownSections(parseSections(BODY));
    expect(u.map((s) => s.heading)).toEqual(['Design notes']);
  });
});
