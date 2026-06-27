// Scaffolds for new tickets so non-developers start from a useful skeleton
// rather than a blank file. See spec/web_remaining_phases.md §5 (W2).

export interface TicketTemplate {
  id: string;
  label: string;
  category: string;
  status: string;
  body: string;
}

const FEATURE_BODY = `## Summary

_What should this do, and why?_

## Acceptance Criteria

- [ ]
- [ ]

## Notes

`;

const BUG_BODY = `## Summary

_What is broken? Steps to reproduce, expected vs. actual._

## Acceptance Criteria

- [ ] The bug no longer reproduces.

## Notes

`;

const CHORE_BODY = `## Summary

_What maintenance work is this? (deps, CI, build, docs.)_

## Notes

`;

export const TICKET_TEMPLATES: TicketTemplate[] = [
  {
    id: 'feature',
    label: 'New feature',
    category: 'added',
    status: 'proposed',
    body: FEATURE_BODY,
  },
  { id: 'bug', label: 'Bug fix', category: 'fixed', status: 'proposed', body: BUG_BODY },
  { id: 'chore', label: 'Chore', category: 'chore', status: 'proposed', body: CHORE_BODY },
];

export function templateById(id: string): TicketTemplate | undefined {
  return TICKET_TEMPLATES.find((t) => t.id === id);
}
