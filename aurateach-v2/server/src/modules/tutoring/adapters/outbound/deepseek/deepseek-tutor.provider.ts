import type { AskTutorCommand } from '../../../application/ports/inbound/ask-tutor.port.js';
import type {
  TutorProviderPort,
  TutorProviderResult,
} from '../../../application/ports/outbound/tutor-provider.port.js';
import { TutorProviderUnavailableError } from '../../../application/ports/outbound/tutor-provider.port.js';
import { MASTER_TUTOR_PROMPT } from './master-tutor-prompt.js';

const REQUEST_TIMEOUT_MS = 45_000;
const MAX_RESPONSE_LENGTH = 12_000;

export class DeepSeekTutorProvider implements TutorProviderPort {
  // Accept the V1 LLM_* names so the existing local DeepSeek credentials can be
  // reused without exposing them to Angular or maintaining duplicate secrets.
  private readonly apiKey = process.env['DEEPSEEK_API_KEY'] ?? process.env['LLM_API_KEY'];
  private readonly endpoint = (process.env['DEEPSEEK_CHAT_COMPLETIONS_URL']
    ?? process.env['LLM_API_URL']
    ?? `${(process.env['DEEPSEEK_BASE_URL'] ?? 'https://api.deepseek.com').replace(/\/+$/, '')}/chat/completions`)
    .replace(/\/+$/, '');
  private readonly model = process.env['DEEPSEEK_MODEL'] ?? process.env['LLM_MODEL'] ?? 'deepseek-flash';

  async ask(command: AskTutorCommand): Promise<TutorProviderResult> {
    if (!this.apiKey) throw new TutorProviderUnavailableError('DEEPSEEK_API_KEY is not configured.');
    const userContent: Array<Record<string, unknown>> = [
      {
        type: 'text',
        text: JSON.stringify({
          question: command.question,
          modelId: command.modelId,
          topic: command.topic,
          selectedNodePath: command.selectedNodePath ?? null,
          sceneNodes: command.sceneNodes ?? [],
          sceneParts: command.sceneParts ?? [],
        }),
      },
    ];
    if (command.screenshotDataUrl) {
      userContent.push({ type: 'image_url', image_url: { url: command.screenshotDataUrl } });
    }

    let response: Response;
    try {
      response = await fetch(this.endpoint, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${this.apiKey}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model: this.model,
          temperature: 0.4,
          max_tokens: 700,
          response_format: { type: 'json_object' },
          messages: [
            { role: 'system', content: MASTER_TUTOR_PROMPT },
            { role: 'user', content: userContent },
          ],
        }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch {
      throw new TutorProviderUnavailableError('Could not reach DeepSeek.');
    }
    if (!response.ok) {
      // Do not expose provider error bodies; they can contain request metadata.
      throw new TutorProviderUnavailableError(`DeepSeek returned HTTP ${response.status}.`);
    }
    const payload: unknown = await response.json().catch(() => null);
    const content = readAssistantContent(payload);
    if (!content || content.length > MAX_RESPONSE_LENGTH) {
      throw new TutorProviderUnavailableError('DeepSeek returned an invalid response.');
    }
    try {
      const parsed: unknown = JSON.parse(content);
      if (!isRecord(parsed) || typeof parsed['answer'] !== 'string') {
        throw new Error('Invalid response shape.');
      }
      return { answer: parsed['answer'], locator: parsed['locator'], sceneAction: parsed['sceneAction'] };
    } catch {
      throw new TutorProviderUnavailableError('DeepSeek returned malformed tutor JSON.');
    }
  }
}

function readAssistantContent(payload: unknown): string | undefined {
  if (!isRecord(payload) || !Array.isArray(payload['choices'])) return undefined;
  const choice = payload['choices'][0];
  if (!isRecord(choice) || !isRecord(choice['message'])) return undefined;
  const content = choice['message']['content'];
  return typeof content === 'string' ? content : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
