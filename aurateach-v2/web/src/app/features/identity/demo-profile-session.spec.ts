import { TestBed } from '@angular/core/testing';
import { DemoProfileSession } from './demo-profile-session';

describe('DemoProfileSession', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({});
  });

  afterEach(() => sessionStorage.clear());

  it('stores the selected demo profile for the current browser tab', () => {
    const session = TestBed.inject(DemoProfileSession);

    session.enterAs('teacher');

    expect(session.current()?.role).toBe('teacher');
    expect(JSON.parse(sessionStorage.getItem('aurateach.demo-profile') ?? '{}')).toEqual({
      role: 'teacher',
      displayName: 'Docente demo',
    });
  });

  it('restores a valid demo profile after the service is recreated', () => {
    sessionStorage.setItem(
      'aurateach.demo-profile',
      JSON.stringify({ role: 'student', displayName: 'Alumno demo' }),
    );

    const session = TestBed.inject(DemoProfileSession);

    expect(session.current()).toEqual({ role: 'student', displayName: 'Alumno demo' });
  });

  it('clears the demo profile when the user leaves', () => {
    const session = TestBed.inject(DemoProfileSession);
    session.enterAs('student');

    session.leave();

    expect(session.current()).toBeNull();
    expect(sessionStorage.getItem('aurateach.demo-profile')).toBeNull();
  });
});
