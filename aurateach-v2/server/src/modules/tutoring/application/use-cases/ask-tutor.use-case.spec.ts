import { AskTutorUseCase } from './ask-tutor.use-case.js';
import type { TutorProviderPort } from '../ports/outbound/tutor-provider.port.js';

describe('AskTutorUseCase', () => {
  const baseCommand = {
    question: '¿Qué parte es esta?',
    modelId: 'guitarra',
    topic: 'Ingeniería y sonido',
    sceneNodes: [{ nodePath: '/Guitar/Bridge', name: 'Bridge', type: 'Mesh' }],
  };

  it('returns spoken text while accepting only a node present in the submitted scene index', async () => {
    const provider: TutorProviderPort = {
      ask: vi.fn().mockResolvedValue({
        answer: '**El puente** sostiene las cuerdas. ¿Qué notas en su forma?',
        locator: { kind: 'semantic-node', nodePath: '/Guitar/Bridge', label: 'Puente', confidence: 0.91 },
      }),
    };
    await expect(new AskTutorUseCase(provider).execute(baseCommand)).resolves.toEqual({
      answer: '**El puente** sostiene las cuerdas. ¿Qué notas en su forma?',
      speechText: 'El puente sostiene las cuerdas. ¿Qué notas en su forma?',
      locator: { kind: 'semantic-node', nodePath: '/Guitar/Bridge', label: 'Puente', confidence: 0.91 },
      sceneAction: { kind: 'none' },
    });
  });

  it('rejects invented node paths and out-of-range image points as no locator', async () => {
    const provider: TutorProviderPort = {
      ask: vi.fn()
        .mockResolvedValueOnce({ answer: 'Mira esta pieza. ¿Qué observas?', locator: { kind: 'semantic-node', nodePath: '/invented', label: 'Pieza', confidence: 1 } })
        .mockResolvedValueOnce({ answer: 'Observa esta zona. ¿Qué ves?', locator: { kind: 'image-point', viewId: 'current', uv: [2, 0.5], label: 'Zona', confidence: 0.8 } }),
    };
    const useCase = new AskTutorUseCase(provider);
    await expect(useCase.execute(baseCommand)).resolves.toMatchObject({ locator: { kind: 'none' } });
    await expect(useCase.execute({ ...baseCommand, screenshotDataUrl: 'data:image/png;base64,AA==' })).resolves.toMatchObject({ locator: { kind: 'none' } });
  });

  it('accepts a normalized point only for the supplied current screenshot', async () => {
    const provider: TutorProviderPort = {
      ask: vi.fn().mockResolvedValue({ answer: 'Mira la unión. ¿Por qué crees que está ahí?', locator: { kind: 'image-point', viewId: 'current', uv: [0.3, 0.7], label: 'Unión', confidence: 0.75 } }),
    };
    await expect(new AskTutorUseCase(provider).execute({ ...baseCommand, screenshotDataUrl: 'data:image/png;base64,AA==' })).resolves.toMatchObject({
      locator: { kind: 'image-point', uv: [0.3, 0.7], viewId: 'current' },
    });
    await expect(new AskTutorUseCase(provider).execute(baseCommand)).resolves.toMatchObject({ locator: { kind: 'none' } });
  });

  it('fails closed when provider returns an empty answer', async () => {
    const provider: TutorProviderPort = { ask: vi.fn().mockResolvedValue({ answer: ' ', locator: { kind: 'none' } }) };
    await expect(new AskTutorUseCase(provider).execute(baseCommand)).rejects.toThrow('invalid answer');
  });

  it('accepts only bounded safe scene action proposals and defaults unknown actions to none', async () => {
    const provider: TutorProviderPort = {
      ask: vi.fn()
        .mockResolvedValueOnce({ answer: 'Miremos el interior. ¿Qué cambia?', locator: { kind: 'none' }, sceneAction: { kind: 'explode-part', partId: 'soundboard-cover' } })
        .mockResolvedValueOnce({ answer: 'No se puede asegurar. ¿Qué pieza señalas?', locator: { kind: 'none' }, sceneAction: { kind: 'explode-part', partId: '../anything' } })
        .mockResolvedValueOnce({ answer: 'Volvamos a armar. ¿Qué función cumple?', locator: { kind: 'none' }, sceneAction: { kind: 'assemble' } }),
    };
    const useCase = new AskTutorUseCase(provider);
    const command = { ...baseCommand, sceneParts: [{ partId: 'soundboard-cover', label: 'Tapa armónica' }] };
    await expect(useCase.execute(command)).resolves.toMatchObject({ sceneAction: { kind: 'explode-part', partId: 'soundboard-cover' } });
    await expect(useCase.execute(command)).resolves.toMatchObject({ sceneAction: { kind: 'none' } });
    await expect(useCase.execute(command)).resolves.toMatchObject({ sceneAction: { kind: 'assemble' } });
  });
});
