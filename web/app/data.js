import fs from 'node:fs';
import path from 'node:path';

/**
 * Reads the exported eval run at build time.
 *
 * The file is produced by `python -m evals.export_web` and is NOT written by
 * this app. If it is missing, the page says so in plain words rather than
 * rendering invented numbers — an eval page that fabricates its own data to
 * look complete is worse than one that is honestly empty.
 */
export function loadEvalData() {
  const file = path.join(process.cwd(), 'public', 'eval-data.json');
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}
