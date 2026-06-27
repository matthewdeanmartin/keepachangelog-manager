// Parse a task fragment's free body into ordered `## `-delimited sections, and
// serialize them back losslessly. This is what lets the form-first editor expose
// Summary / Acceptance Criteria / Notes as structured fields while preserving
// every other ("unknown") section verbatim. See spec/web_remaining_phases.md §5 (W2).
//
// Round-trip invariant: serializeSections(parseSections(body)) preserves heading
// text, body content, ordering, and any preamble before the first heading
// (modulo trailing-whitespace normalization).

export interface BodySection {
  /** Heading text without the leading `## `; empty string for a preamble block. */
  heading: string;
  /** Raw markdown under the heading (between this heading and the next). */
  content: string;
}

const HEADING_RE = /^(#{1,6})\s+(.*)$/;

/** Split a body into ordered sections. Content before the first heading is a
 * section with an empty heading (preamble), kept only when non-empty. */
export function parseSections(body: string): BodySection[] {
  const lines = body.split('\n');
  const sections: BodySection[] = [];
  let current: BodySection | null = null;
  let inFence = false;
  let fenceMarker = '';

  const flush = () => {
    if (current) {
      current.content = current.content.replace(/\n+$/, '');
      sections.push(current);
    }
  };

  for (const line of lines) {
    const fence = line.match(/^(```+|~~~+)/);
    if (fence) {
      if (!inFence) {
        inFence = true;
        fenceMarker = fence[1][0];
      } else if (line.startsWith(fenceMarker)) {
        inFence = false;
      }
    }
    const headingMatch = !inFence ? line.match(HEADING_RE) : null;
    if (headingMatch) {
      flush();
      current = { heading: headingMatch[2].trim(), content: '' };
    } else {
      if (!current) current = { heading: '', content: '' };
      current.content += (current.content ? '\n' : '') + line;
    }
  }
  flush();

  // Drop an empty leading preamble.
  return sections.filter((s, i) => !(i === 0 && s.heading === '' && s.content.trim() === ''));
}

/** Serialize ordered sections back to a markdown body. */
export function serializeSections(sections: BodySection[]): string {
  const blocks: string[] = [];
  for (const s of sections) {
    const content = s.content.replace(/\n+$/, '');
    if (s.heading === '') {
      if (content.trim()) blocks.push(content);
      continue;
    }
    blocks.push(`## ${s.heading}${content ? '\n\n' + content : ''}`);
  }
  return blocks.join('\n\n').replace(/\n+$/, '');
}

/** Find a section by case-insensitive heading match. */
export function findSection(sections: BodySection[], heading: string): BodySection | undefined {
  const h = heading.toLowerCase();
  return sections.find((s) => s.heading.toLowerCase() === h);
}

/** Set (or insert) a section's content, keeping order; removes it when blank. */
export function setSection(
  sections: BodySection[],
  heading: string,
  content: string,
): BodySection[] {
  const next = sections.map((s) => ({ ...s }));
  const existing = findSection(next, heading);
  if (existing) {
    existing.content = content;
    return next.filter((s) => s.heading === '' || s.content.trim() !== '' || isKnownEmptyKeep(s));
  }
  if (content.trim()) next.push({ heading, content });
  return next;
}

// Known sections are allowed to persist empty so the form always shows them.
const ALWAYS_KEEP = new Set<string>();
function isKnownEmptyKeep(s: BodySection): boolean {
  return ALWAYS_KEEP.has(s.heading.toLowerCase());
}

// --- Acceptance-criteria checkbox rows ---

export interface CriterionRow {
  checked: boolean;
  text: string;
}

/** Parse `- [ ] text` / `- [x] text` lines from a section's content. */
export function parseCriteria(content: string): CriterionRow[] {
  const rows: CriterionRow[] = [];
  for (const line of content.split('\n')) {
    const m = line.match(/^\s*[-*]\s+\[([ xX])\]\s+(.*)$/);
    if (m) rows.push({ checked: m[1].toLowerCase() === 'x', text: m[2].trim() });
  }
  return rows;
}

/** Render checkbox rows back to markdown task-list lines. */
export function serializeCriteria(rows: CriterionRow[]): string {
  return rows
    .filter((r) => r.text.trim())
    .map((r) => `- [${r.checked ? 'x' : ' '}] ${r.text.trim()}`)
    .join('\n');
}

/** Section headings the form understands; everything else is "unknown". */
export const KNOWN_SECTIONS = {
  summary: 'Summary',
  acceptance: 'Acceptance Criteria',
  notes: 'Notes',
} as const;

/** Sections not recognized by the form, preserved verbatim and shown read-mostly. */
export function unknownSections(sections: BodySection[]): BodySection[] {
  const known = new Set(Object.values(KNOWN_SECTIONS).map((h) => h.toLowerCase()));
  return sections.filter((s) => s.heading !== '' && !known.has(s.heading.toLowerCase()));
}
