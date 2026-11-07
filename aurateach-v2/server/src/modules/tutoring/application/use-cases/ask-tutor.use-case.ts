import type {
  AskTutorCommand,
  AskTutorPort,
  AskTutorResult,
  TutorLocator,
  TutorSceneAction,
} from '../ports/inbound/ask-tutor.port.js';
import type { TutorProviderPort } from '../ports/outbound/tutor-provider.port.js';
import type { TutorQuestionStorePort } from '../ports/outbound/tutor-question-store.port.js';

const MAX_NODES = 300;
const MAX_TEXT_LENGTH = 12_000;

export class AskTutorUseCase implements AskTutorPort {
  constructor(
    private readonly provider: TutorProviderPort,
    private readonly questions?: TutorQuestionStorePort,
  ) {}

  async execute(command: AskTutorCommand): Promise<AskTutorResult> {
    await this.questions?.recordQuestion(command.modelId, command.question);
    const result = await this.provider.ask(command);
    const answer = typeof result.answer === 'string' ? result.answer.trim() : '';
    if (!answer || answer.length > MAX_TEXT_LENGTH) {
      throw new Error('Tutor provider returned an invalid answer.');
    }
    const locator = this.validateLocator(result.locator, command);
    return {
      answer,
      locator,
      sceneAction: validateSceneAction(result.sceneAction, command),
      speechText: stripMarkup(answer),
    };
  }

  private validateLocator(candidate: unknown, command: AskTutorCommand): TutorLocator {
    if (!isRecord(candidate) || typeof candidate['kind'] !== 'string') return { kind: 'none' };
    if (candidate['kind'] === 'none') {
      const reason = candidate['reason'];
      return typeof reason === 'string' ? { kind: 'none', reason: reason.slice(0, 240) } : { kind: 'none' };
    }
    const label = candidate['label'];
    const confidence = candidate['confidence'];
    if (typeof label !== 'string' || !label.trim() || label.length > 120 ||
      typeof confidence !== 'number' || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
      return { kind: 'none' };
    }
    if (candidate['kind'] === 'semantic-node') {
      const nodePath = candidate['nodePath'];
      const allowed = command.sceneNodes?.some((node) => node.nodePath === nodePath) ?? false;
      if (typeof nodePath !== 'string' || !allowed) return { kind: 'none' };
      return { kind: 'semantic-node', nodePath, label: label.trim(), confidence };
    }
    if (candidate['kind'] === 'image-point') {
      const uv = candidate['uv'];
      // Only the current rendered view is accepted: the request carries one screenshot,
      // not a set of camera-identified views.
      if (candidate['viewId'] !== 'current' || !command.screenshotDataUrl ||
        !Array.isArray(uv) || uv.length !== 2 ||
        !uv.every((value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1)) {
        return { kind: 'none' };
      }
      return { kind: 'image-point', viewId: 'current', uv: [uv[0] as number, uv[1] as number], label: label.trim(), confidence };
    }
    return { kind: 'none' };
  }
}

function validateSceneAction(candidate: unknown, command: AskTutorCommand): TutorSceneAction {
  if (!isRecord(candidate) || typeof candidate['kind'] !== 'string') return { kind: 'none' };
  if (candidate['kind'] === 'assemble') {
    return command.sceneParts?.length ? { kind: 'assemble' } : { kind: 'none' };
  }
  const partId = candidate['partId'];
  const allowedPart = typeof partId === 'string' &&
    command.sceneParts?.some((part) => part.partId === partId);
  if (candidate['kind'] === 'explode-part' && typeof partId === 'string' && allowedPart) {
    return { kind: 'explode-part', partId };
  }
  return { kind: 'none' };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stripMarkup(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_>#~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export { MAX_NODES };
