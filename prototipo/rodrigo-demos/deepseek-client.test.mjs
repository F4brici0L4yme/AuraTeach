import test from 'node:test';
import assert from 'node:assert/strict';
import { deepSeekChatCompletion, validateCanvasAction } from './deepseek-client.mjs';

test('DeepSeek request keeps the key in authorization header and sends master prompt, question and image', async () => {
  const apiKey = 'test-secret-key'; let request;
  await deepSeekChatCompletion({
    apiKey, endpoint: 'https://api.deepseek.com/chat/completions', model: 'deepseek-flash',
    instructions: 'Prompt maestro · modelo: lapicero', question: '¿Qué parte estoy viendo?',
    image: 'data:image/jpeg;base64,ZmFrZQ==', tools: [],
    fetchImpl: async (url, options) => {
      request = { url, ...options };
      return { json: async () => ({ choices: [{ message: { content: 'Respuesta' } }] }) };
    }
  });
  const payload = JSON.parse(request.body);
  assert.equal(request.headers.authorization, `Bearer ${apiKey}`);
  assert.equal(request.url, 'https://api.deepseek.com/chat/completions');
  assert.equal(payload.messages[0].content, 'Prompt maestro · modelo: lapicero');
  assert.equal(payload.messages[1].content[0].text, '¿Qué parte estoy viendo?');
  assert.equal(payload.messages[1].content[1].image_url.url, 'data:image/jpeg;base64,ZmFrZQ==');
  assert.equal(request.body.includes(apiKey), false, 'key is never placed in request JSON');
});

test('canvas tool validation only accepts verified pieces on the prepared model', () => {
  const model = { id: 'lapicero', disassemblable: true };
  const parts = [{ id: 'clip-1', label: 'Clip' }];
  assert.deepEqual(validateCanvasAction({ action: 'focus_part', partId: 'clip-1' }, { model, isOwnModel: false, parts }), { type: 'focus_part', partId: 'clip-1', message: 'Clip' });
  assert.equal(validateCanvasAction({ action: 'focus_part', partId: 'inventada' }, { model, isOwnModel: false, parts }), null);
  assert.equal(validateCanvasAction({ action: 'set_exploded', value: true }, { model, isOwnModel: true, parts }), null);
  assert.equal(validateCanvasAction({ action: 'run_python' }, { model, isOwnModel: false, parts }), null);
});

test('general arrows and camera actions work without a verified part manifest', () => {
  assert.deepEqual(validateCanvasAction({ action: 'arrow', message: 'Observa esta zona' }, { model: null, isOwnModel: true, parts: [] }), { type: 'arrow', message: 'Observa esta zona' });
  assert.deepEqual(validateCanvasAction({ action: 'zoom' }, { model: null, isOwnModel: true, parts: [] }), { type: 'zoom' });
  assert.deepEqual(validateCanvasAction({ action: 'reset' }, { model: null, isOwnModel: true, parts: [] }), { type: 'reset' });
  assert.equal(validateCanvasAction({ action: 'focus_part', partId: 'inventada' }, { model: null, isOwnModel: true, parts: [] }), null);
});

test('prepared model only accepts the true exploded state when parts are verified', () => {
  const context = { model: { id: 'lapicero', disassemblable: true }, isOwnModel: false, parts: [{ id: 'part-1' }] };
  assert.deepEqual(validateCanvasAction({ action: 'set_exploded', value: true }, context), { type: 'set_exploded', value: true });
  assert.deepEqual(validateCanvasAction({ action: 'set_exploded', value: false }, context), { type: 'set_exploded', value: false });
  assert.equal(validateCanvasAction({ action: 'set_exploded', value: 'true' }, context), null);
  assert.equal(validateCanvasAction({ action: 'set_exploded', value: true }, { ...context, parts: [] }), null);
});
