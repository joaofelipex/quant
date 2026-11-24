import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { errMsg } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { StatusStore } from '../core/status.store';

/** Tela de entrada do painel. Ocupa a janela toda; so some quando a sessao e aceita. */
@Component({
  selector: 'app-login',
  imports: [FormsModule],
  host: { class: 'grid min-h-screen place-items-center p-5 bg-bg bg-[radial-gradient(900px_500px_at_15%_-10%,var(--accent-soft),transparent)]' },
  template: `
    <main class="card flex w-full max-w-[400px] flex-col gap-[18px] px-7 py-[30px]">
      <div class="flex items-center gap-3">
        <span class="grid size-10 place-items-center rounded-xl bg-accent text-[22px] font-extrabold text-accent-ink" aria-hidden="true">q</span>
        <div><h1 class="text-[22px]">quant</h1><div class="sub">painel de controle</div></div>
      </div>
      @if (!auth.configured()) {
        <div class="rounded-[10px] bg-warn-soft px-3 py-2.5 text-[13.5px] text-warn" role="alert"><b>Senha ainda não definida.</b> Na VM, rode
          <code>sudo /opt/quant/deploy/definir-senha.sh</code> e volte aqui.</div>
      }
      <form class="flex flex-col gap-3.5" (submit)="$event.preventDefault(); enter()">
        <label class="field"><span>Usuário</span>
          <input name="user" autocomplete="username" autocapitalize="none" required [ngModel]="user()" (ngModelChange)="user.set($event)"></label>
        <label class="field"><span>Senha</span>
          <input name="password" type="password" autocomplete="current-password" required [ngModel]="password()" (ngModelChange)="password.set($event)"></label>
        <label class="flex cursor-pointer items-center gap-2 text-[13.5px] text-mute"><input class="w-auto" type="checkbox" name="lembrar" [ngModel]="remember()" (ngModelChange)="remember.set($event)"> manter conectado por 7 dias</label>
        @if (error()) { <div class="rounded-[10px] bg-bad-soft px-3 py-2.5 text-[13.5px] text-bad" role="alert">{{ error() }}</div> }
        <button class="btn primary !p-[11px] !text-[15px]" type="submit" [disabled]="busy() || !user() || !password()">{{ busy() ? 'Entrando…' : 'Entrar' }}</button>
      </form>
      <p class="note">Acesso restrito. Depois de várias tentativas erradas o acesso é bloqueado por alguns minutos.</p>
    </main>`,
})
export class LoginPage {
  protected readonly auth = inject(AuthService);
  private readonly store = inject(StatusStore);
  protected readonly user = signal('painel');
  protected readonly password = signal('');
  protected readonly remember = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected enter(): void {
    this.busy.set(true);
    this.error.set('');
    this.auth.login({ user: this.user().trim(), password: this.password(), lembrar: this.remember() }).subscribe({
      next: () => { this.busy.set(false); this.password.set(''); this.store.refresh(); },
      error: e => {
        this.busy.set(false);
        this.password.set('');
        this.error.set(errMsg(e));
        this.auth.check();  // atualiza "senha nao definida"
      },
    });
  }
}
