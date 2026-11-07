import { Injectable, signal } from '@angular/core';

export type DemoRole = 'teacher' | 'student';

export interface DemoProfile {
  role: DemoRole;
  displayName: string;
}

const STORAGE_KEY = 'aurateach.demo-profile';
const DEMO_PROFILES: Record<DemoRole, DemoProfile> = {
  teacher: { role: 'teacher', displayName: 'Docente demo' },
  student: { role: 'student', displayName: 'Alumno demo' },
};

/** A tab-scoped profile selector for the prototype; it does not authenticate a person. */
@Injectable({ providedIn: 'root' })
export class DemoProfileSession {
  private readonly profileState = signal<DemoProfile | null>(this.readStoredProfile());
  readonly profile = this.profileState.asReadonly();

  current(): DemoProfile | null {
    return this.profileState();
  }

  enterAs(role: DemoRole): void {
    const profile = DEMO_PROFILES[role];
    this.profileState.set(profile);
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
    }
  }

  leave(): void {
    this.profileState.set(null);
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  }

  private readStoredProfile(): DemoProfile | null {
    if (typeof window === 'undefined') return null;

    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    if (!stored) return null;

    try {
      const parsed: unknown = JSON.parse(stored);
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        'role' in parsed &&
        (parsed.role === 'teacher' || parsed.role === 'student')
      ) {
        return DEMO_PROFILES[parsed.role];
      }
    } catch {
      // Discard a malformed demo profile and show the selector again.
    }

    window.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}
