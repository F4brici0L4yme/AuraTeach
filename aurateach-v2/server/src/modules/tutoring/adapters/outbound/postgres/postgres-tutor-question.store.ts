import { randomUUID } from 'node:crypto';
import type { Pool } from 'pg';
import type { TutorQuestionStorePort } from '../../../application/ports/outbound/tutor-question-store.port.js';

/** Records only final submitted question text, attributed to the fixed demo student. */
export class PostgresTutorQuestionStore implements TutorQuestionStorePort {
  constructor(private readonly pool: Pool) {}

  async recordQuestion(modelId: string, questionText: string): Promise<void> {
    await this.pool.query(
      `insert into student_questions (user_id, model_id, question_text, demo_key, asked_at)
       select u.id, m.id, $3, $4, now()
       from users u cross join models m
       where u.demo_key = $1 and u.role = 'student'
         and (m.catalog_key = $2 or ($2 = 'local' and m.demo_key = 'demo-model-local-upload'))`,
      ['demo-student-01', modelId, questionText, randomUUID()],
    );
  }
}
