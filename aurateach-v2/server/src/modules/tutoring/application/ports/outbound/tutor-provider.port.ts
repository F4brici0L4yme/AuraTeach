import type { AskTutorCommand } from '../inbound/ask-tutor.port.js';

export interface TutorProviderResult {
  answer: string;
  locator: unknown;
  sceneAction?: unknown;
}

export interface TutorProviderPort {
  ask(command: AskTutorCommand): Promise<TutorProviderResult>;
}

export class TutorProviderUnavailableError extends Error {
  constructor(message = 'The tutoring provider is unavailable.') {
    super(message);
    this.name = 'TutorProviderUnavailableError';
  }
}
