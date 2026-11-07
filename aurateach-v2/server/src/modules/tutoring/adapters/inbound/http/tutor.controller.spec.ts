import { BadRequestException } from '@nestjs/common';
import { TutorController } from './tutor.controller.js';
import type { AskTutorPort } from '../../../application/ports/inbound/ask-tutor.port.js';

describe('TutorController request boundary', () => {
  it('forwards a valid request to the inbound port', async () => {
    const execute = vi.fn().mockResolvedValue({ answer: 'Respuesta', locator: { kind: 'none' }, speechText: 'Respuesta' });
    const controller = new TutorController({ execute } as unknown as AskTutorPort);
    const result = await controller.ask({
      question: '¿Qué observo?',
      modelId: 'guitarra',
      topic: 'Sonido',
      sceneNodes: [{ nodePath: '/Guitar/Body', name: 'Body', type: 'Mesh' }],
      selectedNodePath: '/Guitar/Body',
    });
    expect(result.answer).toBe('Respuesta');
    expect(execute).toHaveBeenCalledWith(expect.objectContaining({ selectedNodePath: '/Guitar/Body' }));
  });

  it('rejects malformed payloads and selection paths absent from sceneNodes', async () => {
    const execute = vi.fn();
    const controller = new TutorController({ execute } as unknown as AskTutorPort);
    await expect(controller.ask({ modelId: 'guitar', topic: 'STEM' })).rejects.toBeInstanceOf(BadRequestException);
    await expect(controller.ask({
      question: 'Q', modelId: 'guitar', topic: 'STEM', selectedNodePath: '/fake',
      sceneNodes: [{ nodePath: '/real', name: 'Real', type: 'Mesh' }],
    })).rejects.toBeInstanceOf(BadRequestException);
    expect(execute).not.toHaveBeenCalled();
  });

  it('rejects unsupported, malformed, or oversized image data URLs', async () => {
    const controller = new TutorController({ execute: vi.fn() } as unknown as AskTutorPort);
    const request = { question: 'Q', modelId: 'guitar', topic: 'STEM' };
    await expect(controller.ask({ ...request, screenshotDataUrl: 'data:text/plain,hello' })).rejects.toBeInstanceOf(BadRequestException);
    await expect(controller.ask({ ...request, screenshotDataUrl: `data:image/png;base64,${'A'.repeat(5 * 1024 * 1024)}` })).rejects.toBeInstanceOf(BadRequestException);
  });
});
