export class DeepSeekRequestError extends Error {
  constructor(message, { status = 0, code = 'network_error', publicMessage } = {}) {
    super(message);
    this.name = 'DeepSeekRequestError';
    this.status = status;
    this.code = code;
    this.publicMessage = publicMessage;
  }
}

function normalizeEndpoint(value) {
  const endpoint = String(value || 'https://api.deepseek.com/chat/completions').trim();
  let parsed;
  try { parsed = new URL(endpoint); } catch { throw new DeepSeekRequestError('Invalid DeepSeek endpoint', { code: 'invalid_endpoint', publicMessage: 'La URL de DeepSeek no es válida. Revisa LLM_API_URL en .env.' }); }
  if (!['https:', 'http:'].includes(parsed.protocol)) throw new DeepSeekRequestError('Unsupported DeepSeek endpoint protocol', { code: 'invalid_endpoint', publicMessage: 'La URL de DeepSeek debe comenzar con https://.' });
  // Accept the common base URL as well as the full Chat Completions URL.
  if (/\/v1\/?$/.test(parsed.pathname)) parsed.pathname = `${parsed.pathname.replace(/\/$/, '')}/chat/completions`;
  else if (parsed.pathname === '/' || parsed.pathname === '') parsed.pathname = '/chat/completions';
  return parsed.toString();
}

function apiError(response, payload) {
  const status = response.status;
  const providerMessage = String(payload?.error?.message || payload?.message || '').slice(0, 500);
  let code = 'provider_error';
  let publicMessage = 'DeepSeek rechazó la solicitud. Revisa el endpoint y el modelo configurados.';
  if (status === 401 || status === 403) {
    code = 'authentication_error';
    publicMessage = 'DeepSeek rechazó la autenticación. Revisa que LLM_API_KEY sea una clave activa y esté copiada completa en .env.';
  } else if (status === 402) {
    code = 'billing_error';
    publicMessage = 'DeepSeek no aceptó la solicitud por saldo o facturación. Revisa la cuenta de API.';
  } else if (status === 404) {
    code = 'model_or_endpoint_not_found';
    publicMessage = 'DeepSeek no encontró el endpoint o modelo configurado. Revisa LLM_API_URL y LLM_MODEL en .env.';
  } else if (status === 429) {
    code = 'rate_limited';
    publicMessage = 'DeepSeek alcanzó un límite de uso. Espera un momento y vuelve a intentar.';
  } else if (status >= 500) {
    code = 'provider_unavailable';
    publicMessage = 'DeepSeek está teniendo un problema temporal. Inténtalo de nuevo en un momento.';
  }
  return new DeepSeekRequestError(providerMessage || `DeepSeek HTTP ${status}`, { status, code, publicMessage });
}

export async function deepSeekChatCompletion({ apiKey, endpoint, model, instructions, question, image = '', tools, fetchImpl = fetch }) {
  if (!String(apiKey || '').trim()) throw new DeepSeekRequestError('Missing DeepSeek API key', { code: 'missing_key', publicMessage: 'Falta LLM_API_KEY. Añádela al .env y reinicia el servidor.' });
  const url = normalizeEndpoint(endpoint);
  const userContent = [{ type: 'text', text: question }];
  if (image) userContent.push({ type: 'image_url', image_url: { url: image, detail: 'low' } });
  let response;
  try {
    response = await fetchImpl(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${String(apiKey).trim()}` },
      body: JSON.stringify({
        model,
        messages: [{ role: 'system', content: instructions }, { role: 'user', content: userContent }],
        tools,
        tool_choice: 'auto',
        temperature: 0.4
      }),
      signal: AbortSignal.timeout(60_000)
    });
  } catch (error) {
    const timedOut = error?.name === 'TimeoutError' || error?.name === 'AbortError';
    throw new DeepSeekRequestError(timedOut ? 'DeepSeek request timed out' : 'Could not reach DeepSeek', {
      code: timedOut ? 'timeout' : 'network_error',
      publicMessage: timedOut ? 'DeepSeek tardó demasiado en responder. Inténtalo otra vez.' : 'No se pudo alcanzar DeepSeek. Verifica tu conexión y vuelve a intentar.'
    });
  }
  const raw = await response.text();
  let result = {};
  try { result = raw ? JSON.parse(raw) : {}; } catch {
    if (response.ok) throw new DeepSeekRequestError('DeepSeek returned a non-JSON response', { status: response.status, code: 'invalid_response', publicMessage: 'DeepSeek respondió con un formato inesperado. Revisa LLM_API_URL.' });
  }
  if (!response.ok) throw apiError(response, result);
  if (!result?.choices?.[0]?.message) throw new DeepSeekRequestError('DeepSeek response did not include a chat message', { status: response.status, code: 'invalid_response', publicMessage: 'DeepSeek respondió, pero no devolvió una respuesta de chat válida.' });
  return { response, result };
}

export function validateCanvasAction(raw, { model, isOwnModel, parts }) {
  if (!raw || typeof raw !== 'object') return null;
  const message = String(raw.message || '').slice(0, 100);
  if (['zoom', 'reset'].includes(raw.action)) return { type: raw.action };
  if (raw.action === 'arrow') return { type: 'arrow', message: message || 'Observa esta zona' };
  if (!isOwnModel && model?.disassemblable && raw.action === 'focus_part') {
    const part = parts.find(item => item.id === raw.partId);
    if (part) return { type: 'focus_part', partId: part.id, message: message || part.label };
  }
  if (!isOwnModel && model?.disassemblable && parts?.length && raw.action === 'set_exploded' && typeof raw.value === 'boolean') {
    return { type: 'set_exploded', value: raw.value };
  }
  return null;
}
