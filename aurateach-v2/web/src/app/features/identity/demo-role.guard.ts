import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { DemoProfileSession } from './demo-profile-session';
import type { DemoRole } from './demo-profile-session';

const homeForRole: Record<DemoRole, string> = {
  teacher: '/docente/dashboard',
  student: '/alumno',
};

export function requireDemoRole(requiredRole: DemoRole): CanActivateFn {
  return () => {
    const session = inject(DemoProfileSession);
    const router = inject(Router);
    const profile = session.current();

    if (!profile) return router.parseUrl('/');
    if (profile.role !== requiredRole) return router.parseUrl(homeForRole[profile.role]);
    return true;
  };
}
