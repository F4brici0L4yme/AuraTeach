import {
  BadGatewayException,
  BadRequestException,
  Body,
  Controller,
  HttpException,
  Inject,
  Post,
  ServiceUnavailableException,
} from '@nestjs/common';
import type { AskTutorCommand, AskTutorPort, TutorSceneNode, TutorScenePart } from '../../../application/ports/inbound/ask-tutor.port.js';
import { TutorProviderUnavailableError } from '../../../application/ports/outbound/tutor-provider.port.js';
import { MAX_NODES } from '../../../application/use-cases/ask-tutor.use-case.js';
import { ASK_TUTOR } from '../../nest/tutoring.tokens.js';

const MAX_SCREENSHOT_BYTES = 3 * 1024 * 1024;
const DATA_URL_PATTERN = /^data:image\/(png|jpeg|webp);base64,([a-zA-Z0-9+/]+={0,2})$/;

@Controller('tutor')
export class TutorController {
  constructor(@Inject(ASK_TUTOR) private readonly askTutor: AskTutorPort) {}

  @Post('ask')
  async ask(@Body() body: unknown) {
    const command = parseCommand(body);
    try {
      return await this.askTutor.execute(command);
    } catch (error) {
      if (error instanceof HttpException) throw error;
      if (error instanceof TutorProviderUnavailableError) {
        throw new ServiceUnavailableException('El tutor no está disponible en este momento.');
      }
      throw new BadGatewayException('No se pudo procesar la pregunta del tutor.');
    }
  }
}

function parseCommand(value: unknown): AskTutorCommand {
  if (!isRecord(value)) throw new BadRequestException('Request body must be an object.');
  const question = requiredString(value['question'], 'question', 1, 1000);
  const modelId = requiredString(value['modelId'], 'modelId', 1, 120);
  const topic = requiredString(value['topic'], 'topic', 1, 160);
  const selectedNodePath = optionalString(value['selectedNodePath'], 'selectedNodePath', 500);
  const screenshotDataUrl = optionalString(value['screenshotDataUrl'], 'screenshotDataUrl', MAX_SCREENSHOT_BYTES * 2);
  if (screenshotDataUrl) validateScreenshot(screenshotDataUrl);
  const sceneNodes = parseSceneNodes(value['sceneNodes']);
  const sceneParts = parseSceneParts(value['sceneParts']);
  if (selectedNodePath && sceneNodes && !sceneNodes.some((node) => node.nodePath === selectedNodePath)) {
    throw new BadRequestException('selectedNodePath must exist in sceneNodes.');
  }
  return {
    question,
    modelId,
    topic,
    ...(selectedNodePath ? { selectedNodePath } : {}),
    ...(sceneNodes ? { sceneNodes } : {}),
    ...(sceneParts ? { sceneParts } : {}),
    ...(screenshotDataUrl ? { screenshotDataUrl } : {}),
  };
}

function parseSceneParts(value: unknown): TutorScenePart[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length > 100) throw new BadRequestException('sceneParts must be an array with at most 100 entries.');
  const ids = new Set<string>();
  return value.map((part, index) => {
    if (!isRecord(part)) throw new BadRequestException(`sceneParts[${index}] must be an object.`);
    const partId = requiredString(part['partId'], `sceneParts[${index}].partId`, 1, 80);
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(partId) || ids.has(partId)) {
      throw new BadRequestException(`sceneParts[${index}].partId must be a unique safe identifier.`);
    }
    ids.add(partId);
    return { partId, label: requiredString(part['label'], `sceneParts[${index}].label`, 1, 120) };
  });
}

function parseSceneNodes(value: unknown): TutorSceneNode[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length > MAX_NODES) throw new BadRequestException(`sceneNodes must be an array with at most ${MAX_NODES} entries.`);
  return value.map((node, index) => {
    if (!isRecord(node)) throw new BadRequestException(`sceneNodes[${index}] must be an object.`);
    return {
      nodePath: requiredString(node['nodePath'], `sceneNodes[${index}].nodePath`, 1, 500),
      name: requiredString(node['name'], `sceneNodes[${index}].name`, 1, 160),
      type: requiredString(node['type'], `sceneNodes[${index}].type`, 1, 80),
    };
  });
}

function validateScreenshot(value: string): void {
  const match = DATA_URL_PATTERN.exec(value);
  if (!match) throw new BadRequestException('screenshotDataUrl must be a PNG, JPEG, or WebP base64 data URL.');
  const base64 = match[2] ?? '';
  if (Buffer.byteLength(base64, 'base64') > MAX_SCREENSHOT_BYTES) {
    throw new BadRequestException('Screenshot must be 3 MiB or smaller.');
  }
}

function requiredString(value: unknown, name: string, min: number, max: number): string {
  if (typeof value !== 'string' || value.trim().length < min || value.length > max) {
    throw new BadRequestException(`${name} must be a string between ${min} and ${max} characters.`);
  }
  return value.trim();
}

function optionalString(value: unknown, name: string, max: number): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== 'string' || value.length > max) throw new BadRequestException(`${name} is invalid.`);
  const normalized = value.trim();
  return normalized || undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
