import { Routes } from '@angular/router';
import { ProfileAccess } from './features/identity/profile-access';
import { requireDemoRole } from './features/identity/demo-role.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: ProfileAccess },
  { path: 'acceso', pathMatch: 'full', redirectTo: '' },
  {
    path: 'docente/dashboard',
    loadComponent: () =>
      import('./features/analytics/teacher-dashboard').then((module) => module.TeacherDashboard),
    canActivate: [requireDemoRole('teacher')],
    data: { title: 'Dashboard docente' },
  },
  {
    path: 'alumno',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/model-catalog/model-catalog-page').then((module) => module.ModelCatalogPage),
    canActivate: [requireDemoRole('student')],
  },
  {
    path: 'alumno/exploracion/:modelId',
    loadComponent: () =>
      import('./features/exploration/exploration-page').then((module) => module.ExplorationPage),
    canActivate: [requireDemoRole('student')],
  },
  { path: '**', redirectTo: '' },
];
