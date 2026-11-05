import test from 'node:test';
import assert from 'node:assert/strict';
import {
  chooseSpanishVoice,
  createVoiceQuestionSession,
  isCancelUtterance,
  parseWakeUtterance,
  resolveAgentReply,
  shouldResumeVoiceRecognition,
  shouldSpeakResponse
} from './voice-agent.mjs';

test('wake command activates only when pregunta begins the utterance', () => {
  assert.deepEqual(parseWakeUtterance('pregunta'), { activated: true, question: '' });
  assert.deepEqual(parseWakeUtterance('Pregunta, ¿qué une los ladrillos?'), { activated: true, question: '¿qué une los ladrillos?' });
  assert.deepEqual(parseWakeUtterance('  pregunta: ¿Qué ves aquí?  '), { activated: true, question: '¿Qué ves aquí?' });
  assert.deepEqual(parseWakeUtterance('pregunta ¿qué es esto?'), { activated: true, question: '¿qué es esto?' });
  assert.deepEqual(parseWakeUtterance('quiero hacer una pregunta'), { activated: false, question: '' });
});

test('wake phrase by itself arms the tutor without submitting an empty question', () => {
  const session = createVoiceQuestionSession();
  assert.deepEqual(session.acceptFinal('pregunta', 1), { type: 'activated', question: '' });
  assert.equal(session.armed, false);
  assert.equal(session.pendingSubmission, false);
  assert.equal(session.claimSubmission(), null);
});

test('complete wake phrase question is captured and can be submitted exactly once', () => {
  const session = createVoiceQuestionSession();
  assert.deepEqual(session.acceptFinal('pregunta, ¿qué ves aquí?', 1), { type: 'activated', question: '¿qué ves aquí?' });
  assert.equal(session.pendingSubmission, true);
  assert.equal(session.claimSubmission(), '¿qué ves aquí?');
  assert.equal(session.claimSubmission(), null);
  assert.equal(session.armed, true);
});

test('empty and duplicate final recognition results never create duplicate submits', () => {
  const session = createVoiceQuestionSession();
  assert.deepEqual(session.acceptFinal('   ', 1), { type: 'ignored' });
  session.acceptFinal('pregunta', 2);
  assert.deepEqual(session.acceptFinal('¿qué une los ladrillos?', 3), { type: 'question', question: '¿qué une los ladrillos?' });
  assert.deepEqual(session.acceptFinal('¿qué une los ladrillos?', 3), { type: 'duplicate' });
  assert.equal(session.claimSubmission(), '¿qué une los ladrillos?');
  assert.equal(session.claimSubmission(), null);
});

test('cancel clears a partial dictation and re-arms the wake phrase', () => {
  const session = createVoiceQuestionSession();
  session.acceptFinal('pregunta', 1);
  session.acceptFinal('¿qué ves?', 2);
  assert.equal(isCancelUtterance(' Cancelar. '), true);
  assert.deepEqual(session.acceptFinal('cancelar', 3), { type: 'cancelled' });
  assert.equal(session.transcript, '');
  assert.equal(session.pendingSubmission, false);
  assert.equal(session.armed, true);
  assert.equal(session.claimSubmission(), null);
});

test('voice is synthesized only for a voice-originated question', () => {
  assert.equal(shouldSpeakResponse('voice'), true);
  assert.equal(shouldSpeakResponse('text'), false);
});

test('recognition resumes after TTS only when it was requested and voice mode remains active', () => {
  assert.equal(shouldResumeVoiceRecognition({ voiceActive: true, resumeRequested: true }), true);
  assert.equal(shouldResumeVoiceRecognition({ voiceActive: false, resumeRequested: true }), false);
  assert.equal(shouldResumeVoiceRecognition({ voiceActive: true, resumeRequested: false }), false);
});

test('Spanish voice selection prefers es-PE, then another Spanish voice', () => {
  const pe = { name: 'Peruana', lang: 'es-PE' };
  const es = { name: 'Española', lang: 'es-ES' };
  assert.equal(chooseSpanishVoice([es, pe]), pe);
  assert.equal(chooseSpanishVoice([es]), es);
  assert.equal(chooseSpanishVoice([{ lang: 'en-US' }]), null);
});

test('agent response is gated on the local canvas action result', () => {
  const action = { type: 'focus_part', partId: 'clip-1' };
  assert.equal(resolveAgentReply('Mira la relación entre sus partes.', action, true), 'Mira la relación entre sus partes.');
  assert.match(resolveAgentReply('Ya señalé el clip.', action, false), /^No pude aplicar/);
  assert.match(resolveAgentReply('', action, true), /^Listo, revisa el modelo/);
  assert.match(resolveAgentReply('', null, true), /^Observa el modelo/);
});
