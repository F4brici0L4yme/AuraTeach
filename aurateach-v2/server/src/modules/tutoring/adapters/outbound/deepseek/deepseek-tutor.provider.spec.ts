import { DeepSeekTutorProvider } from './deepseek-tutor.provider.js';
import { TutorProviderUnavailableError } from '../../../application/ports/outbound/tutor-provider.port.js';

describe('DeepSeekTutorProvider', () => {
  const originalKey = process.env['DEEPSEEK_API_KEY'];
  const originalLegacyKey = process.env['LLM_API_KEY'];
  const originalLegacyUrl = process.env['LLM_API_URL'];
  const originalLegacyModel = process.env['LLM_MODEL'];
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    if (originalKey === undefined) delete process.env['DEEPSEEK_API_KEY'];
    else process.env['DEEPSEEK_API_KEY'] = originalKey;
    if (originalLegacyKey === undefined) delete process.env['LLM_API_KEY'];
    else process.env['LLM_API_KEY'] = originalLegacyKey;
    if (originalLegacyUrl === undefined) delete process.env['LLM_API_URL'];
    else process.env['LLM_API_URL'] = originalLegacyUrl;
    if (originalLegacyModel === undefined) delete process.env['LLM_MODEL'];
    else process.env['LLM_MODEL'] = originalLegacyModel;
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('keeps the key in the server request and sends a structured tutor prompt', async () => {
    process.env['DEEPSEEK_API_KEY'] = 'server-only-test-key';
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      choices: [{ message: { content: JSON.stringify({ answer: 'Observa las cuerdas. ¿Qué cambia?', locator: { kind: 'none' } }) } }],
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;
    const provider = new DeepSeekTutorProvider();
    await expect(provider.ask({ question: '¿Qué pasa?', modelId: 'guitar', topic: 'Sonido' })).resolves.toEqual({
      answer: 'Observa las cuerdas. ¿Qué cambia?', locator: { kind: 'none' },
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://api.deepseek.com/chat/completions');
    expect((init.headers as Record<string, string>).authorization).toBe('Bearer server-only-test-key');
    const requestBody = JSON.parse(init.body as string) as { messages: Array<{ content: unknown }> };
    expect(JSON.stringify(requestBody)).toContain('Todo lo que nos rodea es un laboratorio');
  });

  it('fails closed when no key is configured and does not issue a network call', async () => {
    delete process.env['DEEPSEEK_API_KEY'];
    delete process.env['LLM_API_KEY'];
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    await expect(new DeepSeekTutorProvider().ask({ question: 'Q', modelId: 'm', topic: 't' })).rejects.toBeInstanceOf(TutorProviderUnavailableError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reuses the existing V1 DeepSeek endpoint, key, and model from LLM_* settings', async () => {
    delete process.env['DEEPSEEK_API_KEY'];
    process.env['LLM_API_KEY'] = 'legacy-server-key';
    process.env['LLM_API_URL'] = 'https://api.deepseek.com/chat/completions';
    process.env['LLM_MODEL'] = 'deepseek-flash';
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      choices: [{ message: { content: JSON.stringify({ answer: 'Mira las cuerdas.', locator: { kind: 'none' }, sceneAction: { kind: 'none' } }) } }],
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;

    await new DeepSeekTutorProvider().ask({ question: '¿Qué vibra?', modelId: 'guitar', topic: 'Sonido' });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://api.deepseek.com/chat/completions');
    expect((init.headers as Record<string, string>).authorization).toBe('Bearer legacy-server-key');
    expect(JSON.parse(init.body as string).model).toBe('deepseek-flash');
  });

  it('hides provider failures behind a generic provider error', async () => {
    process.env['DEEPSEEK_API_KEY'] = 'server-only-test-key';
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('secret provider diagnostic', { status: 401 }));
    await expect(new DeepSeekTutorProvider().ask({ question: 'Q', modelId: 'm', topic: 't' })).rejects.toBeInstanceOf(TutorProviderUnavailableError);
  });
});
