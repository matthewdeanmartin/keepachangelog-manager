// Map the GitHub-style emoji short names used by changelogmanager to glyphs.
const EMOJI: Record<string, string> = {
  rocket: '🚀',
  scissors: '✂️',
  warning: '⚠️',
  no_entry_sign: '🚫',
  bug: '🐛',
  closed_lock_with_key: '🔐',
  hammer_and_wrench: '🛠️',
  broom: '🧹',
  book: '📖',
  test_tube: '🧪',
  microscope: '🔬',
};

export function emojiGlyph(shortName: string | undefined): string {
  if (!shortName) return '🏷️';
  return EMOJI[shortName] ?? '🏷️';
}

const STATUS_GLYPH: Record<string, string> = {
  proposed: '💭',
  accepted: '✅',
  'in-progress': '🚧',
  blocked: '⛔',
  done: '🎉',
  wontfix: '🚮',
};

export function statusGlyph(status: string): string {
  return STATUS_GLYPH[status] ?? '•';
}
