import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { AccountsService, AuditRow, UserRow } from '../core/accounts.service';
import { errMsg } from '../core/api.service';
import { AuthService, Role, ROLE_LABEL } from '../core/auth.service';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

const ROLES: Role[] = ['leitor', 'operador', 'admin'];
const EVENT_LABEL: Record<string, string> = {
  login: 'entrou', 'login-falhou': 'login recusado', logout: 'saiu', acao: 'ação', 'primeiro-acesso': 'primeiro acesso',
  'senha-trocada': 'senha trocada', 'senha-redefinida': 'senha redefinida', 'usuario-criado': 'usuário criado',
  'usuario-alterado': 'usuário alterado', 'usuario-apagado': 'usuário apagado', '2fa-ativado': '2FA ativado',
  '2fa-desativado': '2FA desligado', '2fa-falhou': '2FA recusado', 'sessoes-encerradas': 'sessões encerradas',
};

/** Administracao: quem tem acesso, com que papel, e o que cada um fez (trilha de auditoria). So admin. */
@Component({
  selector: 'app-users',
  imports: [FormsModule, PageHead, Icon, DatePipe],
  template: `
    <app-page-head title="Usuários e auditoria" subtitle="Quem pode entrar, o que pode fazer e o que foi feito" />

    <section class="card">
      <div class="card-h"><div><h2>Usuários</h2>
        <div class="sub"><b>leitor</b> só vê · <b>operador</b> liga/para o robô, boleta e kill-switch · <b>administrador</b> também atualiza o código e gere usuários</div></div></div>
      <div class="scroll-x"><table>
        <thead><tr><th>Usuário</th><th>Papel</th><th>2FA</th><th>Último acesso</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          @for (u of users(); track u.id) {
            <tr [class.opacity-50]="u.disabled">
              <td><b>{{ u.user }}</b> @if (u.id === auth.me()?.id) { <span class="pill accent">você</span> }</td>
              <td><select class="!w-auto !py-1" [ngModel]="u.role" [disabled]="busy() || u.id === auth.me()?.id" (ngModelChange)="setRole(u, $event)" [name]="'r' + u.id">
                @for (r of roles; track r) { <option [value]="r">{{ label[r] }}</option> }</select></td>
              <td>@if (u.totp) { <span class="pill ok">ativo</span> } @else { <span class="sub">—</span> }</td>
              <td class="num">{{ u.last_login ? (u.last_login * 1000 | date: 'dd/MM HH:mm') : 'nunca' }}</td>
              <td><span class="pill" [class]="u.disabled ? 'bad' : 'ok'">{{ u.disabled ? 'desativado' : 'ativo' }}</span></td>
              <td class="r">
                @if (u.id !== auth.me()?.id) {
                  <div class="flex flex-wrap justify-end gap-1">
                  <button class="btn ghost sm" [disabled]="busy()" (click)="toggle(u)">{{ u.disabled ? 'Reativar' : 'Desativar' }}</button>
                  <button class="btn ghost sm" [disabled]="busy()" (click)="resetPassword(u)">Nova senha</button>
                  @if (u.totp) { <button class="btn ghost sm" [disabled]="busy()" (click)="reset2fa(u)">Remover 2FA</button> }
                  <button class="btn ghost sm !text-bad" [disabled]="busy()" (click)="remove(u)">Apagar</button>
                  </div>
                }
              </td>
            </tr>
          } @empty { <tr><td colspan="6" class="sub">carregando…</td></tr> }
        </tbody>
      </table></div>
    </section>

    @if (resetFor(); as r) {
      <section class="card mt">
        <div class="card-h"><h2>Nova senha para {{ r.user }}</h2></div>
        <form class="row" (submit)="$event.preventDefault(); applyReset()">
          <input class="!w-64" type="password" name="rp" autocomplete="new-password" placeholder="mínimo 10 caracteres" [ngModel]="resetPw()" (ngModelChange)="resetPw.set($event)">
          <button class="btn primary" type="submit" [disabled]="busy() || resetPw().length < 10">Redefinir</button>
          <button class="btn ghost" type="button" (click)="resetFor.set(null)">Cancelar</button>
        </form>
        <p class="note mt">As sessões abertas de {{ r.user }} são encerradas. Combine a senha por um canal seguro.</p>
      </section>
    }

    <section class="card mt">
      <div class="card-h"><div class="row"><app-icon name="shield" /><h2>Novo usuário</h2></div></div>
      <form class="grid cols-4" (submit)="$event.preventDefault(); create()">
        <label class="field"><span>Usuário</span><input name="nu" autocomplete="off" [ngModel]="nUser()" (ngModelChange)="nUser.set($event)"></label>
        <label class="field"><span>Senha inicial</span><input name="np" type="password" autocomplete="new-password" [ngModel]="nPass()" (ngModelChange)="nPass.set($event)"><span class="hint">mínimo 10 caracteres; a pessoa pode trocar depois</span></label>
        <label class="field"><span>Papel</span><select name="nr" [ngModel]="nRole()" (ngModelChange)="nRole.set($event)">
          @for (r of roles; track r) { <option [value]="r">{{ label[r] }}</option> }</select></label>
        <div class="flex items-end"><button class="btn primary" type="submit" [disabled]="busy() || !nUser() || nPass().length < 10">Criar usuário</button></div>
      </form>
    </section>

    <section class="card mt">
      <div class="card-h"><div><h2>Auditoria</h2><div class="sub">logins, falhas e ações de operação (últimos {{ events().length }})</div></div>
        <button class="btn" [disabled]="busy()" (click)="loadAudit()"><app-icon name="refresh" [size]="15" /> Atualizar</button></div>
      <div class="scroll-x"><table>
        <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Detalhe</th><th>IP</th></tr></thead>
        <tbody>
          @for (e of events(); track $index) {
            <tr>
              <td class="num whitespace-nowrap">{{ e.t * 1000 | date: 'dd/MM HH:mm:ss' }}</td>
              <td>{{ e.user || '—' }}</td>
              <td><span class="pill" [class]="tone(e.evento)">{{ evLabel(e.evento) }}</span></td>
              <td class="mono">{{ e.detalhe }}</td>
              <td class="num">{{ e.ip }}</td>
            </tr>
          } @empty { <tr><td colspan="5" class="sub">sem eventos</td></tr> }
        </tbody>
      </table></div>
    </section>`,
})
export class UsersPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(AccountsService);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);

  protected readonly roles = ROLES;
  protected readonly label = ROLE_LABEL;
  protected readonly users = signal<UserRow[]>([]);
  protected readonly events = signal<AuditRow[]>([]);
  protected readonly busy = signal(false);
  protected readonly resetFor = signal<UserRow | null>(null);
  protected readonly resetPw = signal('');
  protected readonly nUser = signal('');
  protected readonly nPass = signal('');
  protected readonly nRole = signal<Role>('leitor');
  protected readonly admins = computed(() => this.users().filter(u => u.role === 'admin' && !u.disabled).length);

  constructor() { this.load(); this.loadAudit(); }

  protected evLabel(e: string): string { return EVENT_LABEL[e] ?? e; }
  protected tone(e: string): string { return /falhou|recusado/.test(e) ? 'bad' : /apagado|desativ|removido/.test(e) ? 'warn' : e === 'login' ? 'ok' : ''; }

  private load(): void { this.api.users().subscribe({ next: r => this.users.set(r.users), error: e => this.toast.error(errMsg(e)) }); }
  protected loadAudit(): void { this.api.audit().subscribe({ next: r => this.events.set(r.eventos), error: () => {} }); }

  private go<T>(call: Observable<T>, ok: string, then?: () => void): void {
    this.busy.set(true);
    call.subscribe({
      next: () => { this.busy.set(false); this.toast.ok(ok); then?.(); this.load(); this.loadAudit(); },
      error: e => { this.busy.set(false); this.toast.error(errMsg(e)); this.load(); },
    });
  }

  protected create(): void {
    this.go(this.api.createUser(this.nUser().trim(), this.nPass(), this.nRole()), `Usuário ${this.nUser().trim()} criado`,
            () => { this.nUser.set(''); this.nPass.set(''); this.nRole.set('leitor'); });
  }
  protected setRole(u: UserRow, role: Role): void { this.go(this.api.updateUser(u.id, { role }), `${u.user} agora é ${role}`); }
  protected toggle(u: UserRow): void { this.go(this.api.updateUser(u.id, { disabled: !u.disabled }), u.disabled ? `${u.user} reativado` : `${u.user} desativado`); }
  protected async reset2fa(u: UserRow): Promise<void> {
    if (await this.confirmSvc.ask({ title: `Remover o 2FA de ${u.user}?`, confirmLabel: 'Remover', danger: true, body: 'A pessoa volta a entrar só com a senha.' })) {
      this.go(this.api.updateUser(u.id, { reset_2fa: true }), `2FA de ${u.user} removido`);
    }
  }
  protected resetPassword(u: UserRow): void { this.resetFor.set(u); this.resetPw.set(''); }
  protected applyReset(): void {
    const u = this.resetFor();
    if (u) this.go(this.api.setUserPassword(u.id, this.resetPw()), `Senha de ${u.user} redefinida; as sessões dele foram encerradas`,
                   () => { this.resetFor.set(null); this.resetPw.set(''); });
  }
  protected async remove(u: UserRow): Promise<void> {
    if (await this.confirmSvc.ask({ title: `Apagar ${u.user}?`, confirmLabel: 'Apagar', danger: true, requireText: u.user,
        body: 'A conta e as sessões dela são removidas. Não dá para desfazer.' })) {
      this.go(this.api.deleteUser(u.id), `${u.user} apagado`);
    }
  }
}
