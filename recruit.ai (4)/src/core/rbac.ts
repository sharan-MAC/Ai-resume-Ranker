export type Role = 'admin' | 'recruiter' | 'hiring_manager';

export type Permission = 
  | 'view_dashboard'
  | 'manage_candidates'
  | 'view_candidates'
  | 'manage_jobs'
  | 'view_jobs'
  | 'manage_settings'
  | 'view_rankings'
  | 'manage_users';

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
    'view_dashboard',
    'manage_candidates',
    'view_candidates',
    'manage_jobs',
    'view_jobs',
    'manage_settings',
    'view_rankings',
    'manage_users'
  ],
  recruiter: [
    'view_dashboard',
    'manage_candidates',
    'view_candidates',
    'manage_jobs',
    'view_jobs',
    'view_rankings'
  ],
  hiring_manager: [
    'view_dashboard',
    'view_candidates',
    'view_jobs',
    'view_rankings'
  ]
};

export function hasPermission(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.includes(permission) || false;
}
