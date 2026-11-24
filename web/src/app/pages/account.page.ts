import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { AccountsService, SessionRow } from '../core/accounts.service';
import { errMsg } from '../core/api.service';
import { AuthService, ROLE_LABEL } from '../core/auth.service';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

/** Conta de quem esta logado: senha, 2FA (autenticador) e sessoes abertas. */
@Component({
  selector: 'app-account',
  imports: [FormsModule, PageHead, Icon, DatePipe, RouterLink],
  template: `
    <app-page-head title="Minha conta" [subtitle]="'Entrou como ' + auth.user() + ' · ' + role()">
      @if (auth.isAdmin()) { <a class="btn" routerLink="/usuarios"><app-icon name="shield" [size]="15" /> Usuários e auditoria</a> }
    </app-page-head>

    <div class="grid cols-2">
      <section class="card">
        <div class="card-h"><div class="row"><app-icon name="shield" /><h2>Trocar senha</h2></div></div>
        <form class="stack" (submit)="$event.preventDefault(); changePassword()">
          <label class="field"><span>Senha atual</span><input type="password" name="atual" autocomplete="current-password" [ngModel]="atual()" (ngModelChange)="atual.set($event)"></label>
          <label class="field"><span>Nova senha</span><input type="password" name="nova" autocomplete="new-password" [ngModel]="nova()" (ngModelChange)="nova.set($event)"><span class="hint">mínimo 10 caracteres</span></label>
          <label class="field"><span>Repita a nova senha</span><input type="password" name="repete" autocomplete="new-password" [ngModel]="repete()" (ngModelChange)="repete.set($event)"></label>
          <div class="row"><button class="btn primary" type="submit" [disabled]="busy() || !atual() || !nova() || nova() !== repete()">Trocar senha</button>
            @if (repete() && nova() !== repete()) { <span class="sub bad">as senhas não conferem</span> }</div>
        </form>
        <p class="note mt">Trocar a senha encerra todas as suas sessões, inclusive esta: você entra de novo com a nova.</p>
      </section>

      <section class="card">
        <div class="card-h">
          <div class="row"><app-icon name="bell" /><h2>Verificação em duas etapas</h2></div>
          <span class="pill" [class]="auth.me()?.totp ? 'ok' : 'warn'">{{ auth.me()?.totp ? 'ativa' : 'desligada' }}</span>
        </div>
        @if (auth.me()?.totp) {
          <p class="note">Ao entrar, além da senha, o painel pede o código de 6 dígitos do seu aplicativo autenticador.</p>
          <form class="stack mt" (submit)="$event.preventDefault(); disable2fa()">
            <label class="field"><span>Senha para desligar</span><input type="password" name="pw2" autocomplete="current-password" [ngModel]="pw2()" (ngModelChange)="pw2.set($event)"></label>
            <div><button class="btn danger" type="submit" [disabled]="busy() || !pw2()">Desligar 2FA</button></div>
          </form>
        } @else if (secret()) {
          <p class="note">1. No app autenticador (Google Authenticator, Authy, 1Password…), adicione uma conta <b>manualmente</b> com esta chave:</p>
          <code class="mt block break-all text-[15px] tracking-wider">{{ spaced() }}</code>
          <p class="note mt">Ou abra este endereço no celular: <code class="break-all">{{ uri() }}</code></p>
          <form class="stack mt" (submit)="$event.preventDefault(); enable2fa()">
            <label class="field"><span>2. Digite o código de 6 dígitos que o app mostra</span>
              <input name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" [ngModel]="code()" (ngModelChange)="code.set($event)"></label>
            <div class="row"><button class="btn primary" type="submit" [disabled]="busy() || code().length !== 6">Ativar 2FA</button>
              <button class="btn ghost" type="button" (click)="secret.set('')">Cancelar</button></div>
          </form>
        } @else {
          <p class="note">Protege a conta mesmo se a senha vazar: sem o código do celular ninguém entra. Recomendado para administradores.</p>
          <div class="mt"><button class="btn primary" [disabled]="busy()" (click)="start2fa()">Configurar 2FA</button></div>
        }
      </section>
    </div>

    <section class="card mt">
      <div class="card-h">
        <div><h2>Sessões abertas</h2><div class="sub">onde você está conectado agora</div></div>
        <button class="btn" [disabled]="busy() || sessions().length < 2" (click)="revokeOthers()">Encerrar as outras</button>
      </div>
      <div class="scroll-x"><table>
        <thead><tr><th>Dispositivo</th><th>IP</th><th>Iniciada</th><th>Expira</th><th></th></tr></thead>
        <tbody>
          @for (s of sessions(); track s.id) {
            <tr>
              <td>{{ shortAgent(s.agent) }} @if (s.atual) { <span class="pill ok">esta sessão</span> }</td>
              <td class="num">{{ s.ip || '—' }}</td>
              <td class="num">{{ s.criada * 1000 | date: 'dd/MM HH:mm' }}</td>
              <td class="num">{{ s.expira * 1000 | date: 'dd/MM HH:mm' }}</td>
              <td class="r">@if (!s.atual) { <button class="btn ghost sm" [disabled]="busy()" (click)="revoke(s)">Encerrar</button> }</td>
            </tr>
          } @empty { <tr><td colspan="5" class="sub">carregando…</td></tr> }
        </tbody>
      </table></div>
    </section>`,
})
export class AccountPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(AccountsService);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);

  protected readonly busy = signal(false);
  protected readonly atual = signal('');
  protected readonly nova = signal('');
  protected readonly repete = signal('');
  protected readonly pw2 = signal('');
  protected readonly code = signal('');
  protected readonly secret = signal('');
  protected readonly uri = signal('');
  protected readonly sessions = signal<SessionRow[]>([]);

  constructor() { this.load(); }

  protected role(): string { const r = this.auth.role(); return r ? ROLE_LABEL[r] : ''; }
  protected spaced(): string { return this.secret().replace(/(.{4})/g, '$1 ').trim(); }
  protected shortAgent(a: string): string {
    const m = /(Edg|Chrome|Firefox|Safari|OPR)\/[\d.]+/.exec(a);
    const os = /(Windows|Android|iPhone|iPad|Mac OS X|Linux)/.exec(a);
    return m || os ? `${m ? m[1].replace('Edg', 'Edge').replace('OPR', 'Opera') : 'Navegador'} · ${os ? os[1] : '?'}` : (a || 'desconhecido');
  }

  private load(): void { this.api.sessions().subscribe({ next: r => this.sessions.set(r.sessions), error: () => {} }); }

  /** Roda uma chamada: trava os botoes, avisa o resultado e recarrega as sessoes. */
  private go<T>(call: Observable<T>, ok: string, then?: (r: T) => void): void {
    this.busy.set(true);
    call.subscribe({
      next: r => { this.busy.set(false); if (ok) this.toast.ok(ok); then?.(r); this.load(); },
      error: e => { this.busy.set(false); this.toast.error(errMsg(e)); },
    });
  }

  protected changePassword(): void {
    this.go(this.api.changePassword(this.atual(), this.nova()), 'Senha trocada: entre de novo com a nova',
            () => { this.atual.set(''); this.nova.set(''); this.repete.set(''); });
  }
  protected start2fa(): void { this.go(this.api.twoFaStart(), '', r => { this.secret.set(r.secret); this.uri.set(r.uri); this.code.set(''); }); }
  protected enable2fa(): void {
    this.go(this.api.twoFaEnable(this.code()), '2FA ativado: o próximo login pedirá o código',
            () => { this.secret.set(''); this.code.set(''); this.auth.check(); });
  }
  protected disable2fa(): void { this.go(this.api.twoFaDisable(this.pw2()), '2FA desligado', () => { this.pw2.set(''); this.auth.check(); }); }
  protected revoke(s: SessionRow): void { this.go(this.api.revokeSession(s.id), 'Sessão encerrada'); }
  protected async revokeOthers(): Promise<void> {
    if (await this.confirmSvc.ask({ title: 'Encerrar as outras sessões?', confirmLabel: 'Encerrar', body: 'Todos os outros dispositivos precisarão entrar de novo.' })) {
      this.go(this.api.revokeOthers(), 'Outras sessões encerradas');
    }
  }
}
