import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findArchitectureViolations } from './architecture-rules.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const violations = findArchitectureViolations(path.join(here, '../src'));

if (violations.length > 0) {
  console.error('Architecture boundary violations:');
  for (const violation of violations) console.error(`- ${violation}`);
  process.exitCode = 1;
} else {
  console.log('Architecture import rules passed.');
}
