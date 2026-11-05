export async function deepSeekChatCompletion({ apiKey, endpoint, model, instructions, question, image = '', tools, fetchImpl = fetch }) {
  const userContent = [{ type: 'text', text: question }];
  if (image) userContent.push({ type: 'image_url', image_url: { url: image, detail: 'low' } });
  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages: [{ role: 'system', content: instructions }, { role: 'user', content: userContent }],
      tools,
      tool_choice: 'auto',
      temperature: 0.4
    })
  });
  const result = await response.json();
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
  if (!isOwnModel && model?.disassemblable && raw.action === 'set_exploded' && typeof raw.value === 'boolean') {
    return { type: 'set_exploded', value: raw.value };
  }
  return null;
}
