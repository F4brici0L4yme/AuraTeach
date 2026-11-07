import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { findArchitectureViolations } from '../scripts/architecture-rules.mjs';

describe('hexagonal architecture import rules', () => {
  let temporaryRoot: string;

  beforeEach(() => {
    temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aurateach-architecture-'));
  });

  afterEach(() => {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  });

  it('allows application code to depend on its domain', () => {
    const domain = path.join(temporaryRoot, 'modules/identity/domain/user.ts');
    const useCase = path.join(
      temporaryRoot,
      'modules/identity/application/create-user.ts',
    );
    fs.mkdirSync(path.dirname(domain), { recursive: true });
    fs.mkdirSync(path.dirname(useCase), { recursive: true });
    fs.writeFileSync(domain, 'export interface User { id: string }');
    fs.writeFileSync(useCase, "import type { User } from '../domain/user.js';\nexport type Result = User;");

    expect(findArchitectureViolations(temporaryRoot)).toEqual([]);
  });

  it('rejects framework and adapter imports from the application core', () => {
    const useCase = path.join(
      temporaryRoot,
      'modules/tutoring/application/ask-tutor.ts',
    );
    const adapter = path.join(
      temporaryRoot,
      'modules/tutoring/adapters/deepseek.adapter.ts',
    );
    fs.mkdirSync(path.dirname(useCase), { recursive: true });
    fs.mkdirSync(path.dirname(adapter), { recursive: true });
    fs.writeFileSync(adapter, 'export class DeepSeekAdapter {}');
    fs.writeFileSync(
      useCase,
      "import { Injectable } from '@nestjs/common';\nimport { DeepSeekAdapter } from '../adapters/deepseek.adapter.js';",
    );

    expect(findArchitectureViolations(temporaryRoot)).toHaveLength(2);
  });

  it('rejects external imports from the domain core', () => {
    const entity = path.join(temporaryRoot, 'modules/model-catalog/domain/model.ts');
    fs.mkdirSync(path.dirname(entity), { recursive: true });
    fs.writeFileSync(entity, "import { Injectable } from '@nestjs/common';");

    expect(findArchitectureViolations(temporaryRoot)).toHaveLength(1);
  });

  it('rejects imports into another feature module internal folders', () => {
    const controller = path.join(
      temporaryRoot,
      'modules/tutoring/adapters/inbound/http/tutor.controller.ts',
    );
    const target = path.join(temporaryRoot, 'modules/identity/domain/user.ts');
    fs.mkdirSync(path.dirname(controller), { recursive: true });
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, 'export interface User {}');
    fs.writeFileSync(
      controller,
      "import { User } from '../../../../identity/domain/user.js';",
    );

    expect(findArchitectureViolations(temporaryRoot)).toHaveLength(1);
  });
});
