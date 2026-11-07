import type { Pool } from 'pg';
import { PostgresTutorQuestionStore } from './postgres-tutor-question.store.js';

describe('PostgresTutorQuestionStore', () => {
  it('inserts only submitted question text for the fixed demo student and matching catalog model', async () => {
    const query = vi.fn().mockResolvedValue({ rowCount: 1, rows: [] });
    const store = new PostgresTutorQuestionStore({ query } as unknown as Pool);
    await store.recordQuestion('guitarra-acustica', '¿Qué hace el puente?');
    expect(query).toHaveBeenCalledOnce();
    const [sql, params] = query.mock.calls[0] as [string, unknown[]];
    expect(sql).toContain("u.demo_key = $1 and u.role = 'student'");
    expect(sql).toContain("m.catalog_key = $2 or ($2 = 'local' and m.demo_key = 'demo-model-local-upload')");
    expect(params.slice(0, 3)).toEqual(['demo-student-01', 'guitarra-acustica', '¿Qué hace el puente?']);
    expect(params[3]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(sql).not.toContain('answer');
  });
});
