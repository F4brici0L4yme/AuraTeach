export function parseWakeUtterance(transcript) {
  const normalized = normalizeTranscript(transcript);
  const match = normalized.match(/^pregunta(?:\s*[,;:.!?¿¡—-]\s*|\s+)?(.*)$/i);
  return match ? { activated: true, question: match[1].trim() } : { activated: false, question: '' };
}

export function normalizeTranscript(transcript) {
  return String(transcript || '').trim().replace(/\s+/g, ' ');
}

export function isCancelUtterance(transcript) {
  return /^cancelar[.!?。]*$/i.test(normalizeTranscript(transcript));
}

// Small, deterministic state machine for the browser recognition callbacks.
// A recognition result ID prevents duplicate final events from appending twice;
// claimSubmission() makes a completed utterance sendable only once.
export function createVoiceQuestionSession() {
  let armed = true;
  let transcript = '';
  let pendingSubmission = false;
  const seenFinalResultIds = new Set();

  function clearCapture() {
    transcript = '';
    pendingSubmission = false;
  }

  function appendFinal(text) {
    const clean = normalizeTranscript(text);
    if (!clean) return;
    transcript = [transcript, clean].filter(Boolean).join(' ');
    pendingSubmission = Boolean(transcript);
  }

  return {
    get armed() { return armed; },
    get transcript() { return transcript; },
    get pendingSubmission() { return pendingSubmission; },
    acceptFinal(text, resultId) {
      const clean = normalizeTranscript(text);
      if (!clean) return { type: 'ignored' };
      if (resultId !== undefined && resultId !== null) {
        const id = String(resultId);
        if (seenFinalResultIds.has(id)) return { type: 'duplicate' };
        seenFinalResultIds.add(id);
      }

      if (armed) {
        const wake = parseWakeUtterance(clean);
        if (!wake.activated) return { type: 'ignored' };
        armed = false;
        clearCapture();
        appendFinal(wake.question);
        return { type: 'activated', question: transcript };
      }

      if (isCancelUtterance(clean)) {
        clearCapture();
        armed = true;
        return { type: 'cancelled' };
      }

      appendFinal(clean);
      return { type: 'question', question: transcript };
    },
    claimSubmission() {
      if (!pendingSubmission || !transcript) return null;
      const question = transcript;
      clearCapture();
      armed = true;
      return question;
    },
    cancel() {
      clearCapture();
      armed = true;
    }
  };
}

export function chooseSpanishVoice(voices = []) {
  const language = voice => String(voice?.lang || '').replace('_', '-').toLowerCase();
  return voices.find(voice => language(voice) === 'es-pe')
    || voices.find(voice => language(voice).startsWith('es-') || language(voice) === 'es')
    || null;
}

export const shouldSpeakResponse = source => source === 'voice';

export function shouldResumeVoiceRecognition({ voiceActive, resumeRequested }) {
  return Boolean(voiceActive && resumeRequested);
}

export function resolveAgentReply(answer, action, actionApplied) {
  if (action && !actionApplied) {
    return 'No pude aplicar la indicación al modelo. Puedes seleccionar una pieza o preguntarme sobre lo que se ve.';
  }
  const text = String(answer || '').trim();
  if (text) return text;
  return action
    ? 'Listo, revisa el modelo. ¿Qué detalle observas ahora?'
    : 'Observa el modelo: ¿qué detalle te da una pista para responder?';
}
