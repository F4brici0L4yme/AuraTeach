// Dataset reproducible para el pitch. Las filas sintéticas quedan etiquetadas
// y se insertan una sola vez en cada base de datos.
export function seedDemoActivity(db, { enabled = true, now = Date.now() } = {}) {
  if (!enabled || db.prepare("SELECT COUNT(*) n FROM events WHERE is_synthetic=1").get().n) return false;
  const students = [
    ['demo-student-01', 'Ana Demo', 'active'], ['demo-student-02', 'Bruno Demo', 'active'],
    ['demo-student-03', 'Camila Demo', 'steady'], ['demo-student-04', 'Diego Demo', 'steady'],
    ['demo-student-05', 'Elena Demo', 'quiet'], ['demo-student-06', 'Fabio Demo', 'quiet'],
    ['demo-student-07', 'Gabriela Demo', 'inactive'], ['demo-student-08', 'Hugo Demo', 'new']
  ];
  const isoDaysAgo = days => new Date(now - days * 86400000).toISOString();
  const insertUser = db.prepare("INSERT OR IGNORE INTO users(id,alias,role,created_at,is_synthetic) VALUES(?,?, 'student', ?,1)");
  const insertEvent = db.prepare(`INSERT INTO events(type,alias,role,detail,model,at,user_id,question,is_synthetic)
    VALUES(?,?,'student',?,?,?,?,?,1)`);
  const models = ['lapicero', 'maceta', 'colonia-hongos', 'lab-anatomia-cerebro', 'lab-electronica-arduino_uno'];
  const cohorts = {
    active: { days: [0, 0, 1, 2, 3, 4, 6, 8, 10], questions: ['¿Cómo llega la tinta hasta la punta?', '¿Qué parte evita que la tinta se seque?', '¿Por qué el clip puede flexionarse sin romperse?'] },
    steady: { days: [0, 2, 4, 7, 9, 12], questions: ['¿Qué diferencias observas entre estas hojas?', '¿Qué función cumple esta pieza del mecanismo?'] },
    quiet: { days: [1, 5], questions: ['¿De qué material podría estar hecha esta parte?'] },
    inactive: { days: [10, 13], questions: ['¿Qué forma tiene esta estructura?'] },
    new: { days: [0], questions: ['¿Qué puedo explorar primero en este modelo?'] }
  };
  db.exec('BEGIN IMMEDIATE');
  try {
    for (const [id, alias] of students) insertUser.run(id, alias, isoDaysAgo(14));
    for (const [id, alias, cohort] of students) {
      const sample = cohorts[cohort]; let index = 0;
      for (const day of sample.days) {
        const model = models[(index + Number(id.slice(-2))) % models.length];
        const at = isoDaysAgo(day);
        insertEvent.run('model_open', alias, 'Abrió modelo', model, new Date(new Date(at).getTime() - 8 * 60000).toISOString(), id, '');
        if (index % (cohort === 'active' ? 1 : 2) === 0) {
          const question = sample.questions[index % sample.questions.length];
          insertEvent.run('question', alias, question, model, new Date(new Date(at).getTime() - 5 * 60000).toISOString(), id, question);
        }
        if (cohort === 'active' && index % 2 === 0) insertEvent.run('part_inspect', alias, 'Exploró una pieza', 'lapicero', new Date(new Date(at).getTime() - 2 * 60000).toISOString(), id, '');
        index++;
      }
    }
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
  return true;
}
