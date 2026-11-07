import { Inject, Module, OnApplicationShutdown } from '@nestjs/common';
import { Pool } from 'pg';
import { AskTutorUseCase } from '../../application/use-cases/ask-tutor.use-case.js';
import { DeepSeekTutorProvider } from '../outbound/deepseek/deepseek-tutor.provider.js';
import { PostgresTutorQuestionStore } from '../outbound/postgres/postgres-tutor-question.store.js';
import { TutorController } from '../inbound/http/tutor.controller.js';
import { ASK_TUTOR, TUTOR_PROVIDER, TUTORING_POOL, TUTOR_QUESTION_STORE } from './tutoring.tokens.js';

class CloseTutoringPool implements OnApplicationShutdown {
  constructor(@Inject(TUTORING_POOL) private readonly pool: Pool) {}

  onApplicationShutdown(): Promise<void> {
    return this.pool.end();
  }
}

@Module({
  controllers: [TutorController],
  providers: [
    { provide: TUTORING_POOL, useFactory: () => new Pool({ connectionString: process.env['DATABASE_URL'] }) },
    {
      provide: TUTOR_QUESTION_STORE,
      inject: [TUTORING_POOL],
      useFactory: (pool: Pool) => new PostgresTutorQuestionStore(pool),
    },
    { provide: TUTOR_PROVIDER, useClass: DeepSeekTutorProvider },
    {
      provide: ASK_TUTOR,
      inject: [TUTOR_PROVIDER, TUTOR_QUESTION_STORE],
      useFactory: (provider: DeepSeekTutorProvider, questions: PostgresTutorQuestionStore) =>
        new AskTutorUseCase(provider, questions),
    },
    CloseTutoringPool,
  ],
  exports: [ASK_TUTOR],
})
export class TutoringModule {}
