import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  buildStateMessage,
  deriveSnapshotView,
  formatUsd,
  parseSnapshotFile,
} from './data';

describe('snapshot data helpers', () => {
  it('parses the repository latest.json snapshot', () => {
    const raw = readFileSync(resolve(process.cwd(), '../data/latest.json'), 'utf8');
    const snapshot = parseSnapshotFile(JSON.parse(raw));

    expect(snapshot.item_count).toBe(13);
    expect(snapshot.items).toHaveLength(13);
    expect(snapshot.source_categories).toContain('Black Friday 2025');
  });

  it('derives dc support flags and display fields', () => {
    const raw = readFileSync(resolve(process.cwd(), '../data/latest.json'), 'utf8');
    const snapshot = parseSnapshotFile(JSON.parse(raw));
    const view = deriveSnapshotView(snapshot);

    expect(view.summary.dc02Count).toBe(2);
    expect(view.summary.dc03Count).toBe(13);
    expect(view.rows[0]?.display_memory).toContain('RAM');
    expect(view.rows[0]?.display_disk).toContain('Storage');
  });

  it('formats prices and ui states', () => {
    expect(formatUsd(69.59)).toBe('$69.59');
    expect(buildStateMessage('empty').title).toContain('没有可展示');
    expect(buildStateMessage('error', 'boom').description).toContain('boom');
  });
});
