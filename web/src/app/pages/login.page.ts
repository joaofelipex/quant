import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { errMsg } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { StatusStore } from '../core/status.store';

/** Entrada do painel: primeiro acesso (cria o admin), login e, se a conta tem 2FA, o codigo do autenticador. */
@Component({
  selector: 'app-login',
  imports: [FormsModule],
  host: { class: 'grid min-h-screen place-items-center p-5 bg-bg bg-[radial-gradient(900px_500px_at_15%_-10%,var(--accent-soft),transparent)]' },
  template: `
    <main class="card flex w-full max-w-[420px] flex-col gap-[18px] px-7 py-[30px]">
      <div class="flex items-center gap-3">
        <span class="grid size-10 place-items-center rounded-xl bg-accent text-[22px] font-extrabold text-accent-ink" aria-hidden="true">q</span>
        <div><h1 class="text-[22px]">quant</h1><div class="sub">{{ first() ? 'primeiro acesso' : 'painel de controle' }}</div></div>
      </div>

      @if (first()) {
        <div class="rounded-[10px] bg-accent-soft px-3 py-2.5 text-[13.5px]">
          <b>Crie a conta de administrador.</b> Para provar que você é o dono da VM, leia o token com:
          <code class="mt-1 block break-all">sudo cat /var/lib/quant/setup-token</code>
        </div>
      }

      <form class="flex flex-col gap-3.5" (submit)="$event.preventDefault(); submit()">
        @if (first()) {
          <label class="field"><span>Token de primeiro acesso</span>
            <input name="token" autocomplete="off" required [ngModel]="token()" (ngModelChange)="token.set($event)"></label>
        }
        <label class="field"><span>Usuário</span>
          <input name="user" autocomplete="username" autocapitalize="none" required [ngModel]="user()" (ngModelChange)="user.set($event)"></label>
        <label class="field"><span>{{ first() ? 'Senha (mínimo 10 caracteres)' : 'Senha' }}</span>
          <input name="password" type="password" [attr.autocomplete]="first() ? 'new-password' : 'current-password'" required
                 [ngModel]="password()" (ngModelChange)="password.set($event)"></label>
        @if (first()) {
          <label class="field"><span>Repita a senha</span>
            <input name="again" type="password" autocomplete="new-password" required [ngModel]="again()" (ngModelChange)="again.set($event)"></label>
        }
        @if (needCode()) {
          <label class="field"><span>Código do autenticador (6 dígitos)</span>
            <input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required [ngModel]="code()" (ngModelChange)="code.set($event)"></label>
        }
        @if (!first()) {
          <label class="flex cursor-pointer items-center gap-2 text-[13.5px] text-mute"><input class="w-auto" type="checkbox" name="lembrar"
            [ngModel]="remember()" (ngModelChange)="remember.set($event)"> manter conectado por 7 dias</label>
        }
        @if (error()) { <div class="rounded-[10px] bg-bad-soft px-3 py-2.5 text-[13.5px] text-bad" role="alert">{{ error() }}</div> }
        <button class="btn primary !p-[11px] !text-[15px]" type="submit" [disabled]="!ready()">{{ label() }}</button>
      </form>
      <p class="note">Acesso restrito. Depois de várias tentativas erradas o acesso é bloqueado por alguns minutos.</p>
    </main>`,
})
export class LoginPage {
  protected readonly auth = inject(AuthService);
  private readonly store = inject(StatusStore);
  protected readonly first = computed(() => this.auth.setup());
  protected readonly token = signal('');
  protected readonly user = signal('');
  protected readonly password = signal('');
  protected readonly again = signal('');
  protected readonly code = signal('');
  protected readonly remember = signal(false);
  protected readonly needCode = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected readonly ready = computed(() => !this.busy() && !!this.user() && !!this.password()
    && (!this.first() || (!!this.token() && this.password() === this.again()))
    && (!this.needCode() || this.code().trim().length === 6));
  protected readonly label = computed(() => this.busy() ? 'Entrando…' : this.first() ? 'Criar conta e entrar' : 'Entrar');

  protected submit(): void {
    if (!this.ready()) return;
    this.busy.set(true);
    this.error.set('');
    const user = this.user().trim();
    const call = this.first()
      ? this.auth.firstAccess(this.token().trim(), user, this.password())
      : this.auth.login({ user, password: this.password(), lembrar: this.remember(), code: this.code().trim() || undefined });
    call.subscribe({
      next: () => { this.busy.set(false); this.password.set(''); this.again.set(''); this.code.set(''); this.needCode.set(false); this.store.refresh(); },
      error: e => {
        this.busy.set(false);
        this.error.set(errMsg(e));
        if (e instanceof HttpErrorResponse && (e.error as { codigo?: boolean } | null)?.codigo) { this.needCode.set(true); this.code.set(''); }
        else { this.password.set(''); this.code.set(''); }
        if (!this.first()) this.auth.check();
      },
    });
  }
}
