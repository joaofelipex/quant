import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { CONTROL_HEADERS } from './api.service';
import { AuthService, Role } from './auth.service';

export interface UserRow { id: string; user: string; role: Role; disabled: boolean; totp: boolean; created: number | null; last_login: number | null }
export interface SessionRow { id: string; criada: number; expira: number; ip: string; agent: string; ultimo_uso: number; atual: boolean }
export interface AuditRow { t: number; evento: string; user: string; ip: string; detalhe: string }
export interface Ok { ok?: boolean; erro?: string }

/** Chamadas de conta: usuarios (admin), auditoria (admin), sessoes e 2FA do proprio usuario. */
@Injectable({ providedIn: 'root' })
export class AccountsService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private post<T = Ok>(path: string, body: unknown = {}): Observable<T> {
    return this.http.post<T>(path, body, { headers: CONTROL_HEADERS });
  }

  users() { return this.http.get<{ users: UserRow[]; roles: Role[] }>('api/users'); }
  audit() { return this.http.get<{ eventos: AuditRow[] }>('api/audit'); }
  sessions() { return this.http.get<{ sessions: SessionRow[] }>('api/sessions'); }

  createUser(user: string, password: string, role: Role) { return this.post('api/users', { user, password, role }); }
  updateUser(id: string, patch: { role?: Role; disabled?: boolean; reset_2fa?: boolean }) { return this.post(`api/users/${id}/update`, patch); }
  setUserPassword(id: string, password: string) { return this.post(`api/users/${id}/password`, { password }); }
  deleteUser(id: string) { return this.post(`api/users/${id}/delete`); }

  changePassword(atual: string, nova: string) { return this.post('api/password', { atual, nova }).pipe(tap(() => this.auth.expire())); }
  revokeSession(id: string) { return this.post('api/sessions/revoke', { id }); }
  revokeOthers() { return this.post<Ok & { encerradas: number }>('api/sessions/revoke-others'); }
  twoFaStart() { return this.post<Ok & { secret: string; uri: string }>('api/2fa/start'); }
  twoFaEnable(code: string) { return this.post('api/2fa/enable', { code }); }
  twoFaDisable(password: string) { return this.post('api/2fa/disable', { password }); }
}
