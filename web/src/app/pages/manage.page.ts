import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errMsg } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { runAction } from '../core/action';
import { Tone } from '../core/models';
import { StatusStore } from '../core/status.store';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

@Component({
  selector: 'app-manage',
  imports: [PageHead, Icon, FormsModule],
  styles: `
    ol{margin:8px 0 0;padding-left:20px;color:var(--mute);font-size:14px;display:flex;flex-direction:column;gap:6px}
    ol b{color:var(--ink)}`,
  template: `
    <app-page-head title="Gestão da VM" subtitle="Alertas e atualização do código, sempre com teste e backup" />
    <div class="grid cols-2">
      <section class="card">
        <div class="card-h">
          <div class="row"><app-icon name="bell" /><h2>Alertas</h2></div>
          <span class="pill" [class]="alertas().length ? 'ok' : 'warn'">{{ alertas().length ? alertas().join(' + ') : 'sem canal' }}</span>
        </div>
        <p class="note">Avisam por Telegram ou e-mail quando o runner cai ou volta, a trava de risco dispara, o kill-switch é acionado, a
          autoverificação falha ou um trade fecha.</p>
        <p class="sub mt">{{ alertSub() }}</p>
        <div class="row mt"><button class="btn" [disabled]="busy()" (click)="testAlert()">Enviar alerta de teste</button></div>
        <p class="note mt">Os segredos ficam em <code>/etc/quant/alert.env</code>, que você grava na VM (passo a passo em <code>deploy/README.md</code>).</p>
      </section>

      <section class="card">
        <div class="card-h">
          <div class="row"><app-icon name="package" /><h2>Atualização do código</h2></div>
          <span class="pill" [class]="deployTone()">{{ deployLabel() }}</span>
        </div>
        <p class="sub">{{ deploySub() }}</p>
        <ol>
          <li>No seu computador, rode <code>deploy/enviar-pacote.sh</code>: monta o painel, empacota o repo e coloca na caixa de entrada da VM por SSH.</li>
          <li>Clique em <b>Atualizar código</b>. A VM roda os testes numa cópia, faz backup e só então aplica.</li>
          <li>Reinicie o runner em <b>Operar</b> para usar o código novo.</li>
        </ol>
        <div class="row mt">
          <button class="btn primary" [disabled]="busy()" (click)="deploy()"><app-icon name="package" [size]="15" /> Atualizar código</button>
          <button class="btn" [disabled]="busy()" (click)="rollback()"><app-icon name="undo" [size]="15" /> Reverter</button>
        </div>
        <p class="note mt">O painel não recebe código pela web: só aplica o pacote que você colocou por SSH.</p>
      </section>
    </div>

    <section class="card mt">
      <div class="card-h">
        <div class="row"><app-icon name="shield" /><h2>Segurança</h2></div>
        <span class="pill ok">sessão de {{ auth.user() }}</span>
      </div>
      <form class="grid cols-3" (submit)="$event.preventDefault(); changePassword()">
        <label class="field"><span>Senha atual</span>
          <input type="password" name="atual" autocomplete="current-password" [ngModel]="atual()" (ngModelChange)="atual.set($event)"></label>
        <label class="field"><span>Nova senha</span>
          <input type="password" name="nova" autocomplete="new-password" [ngModel]="nova()" (ngModelChange)="nova.set($event)">
          <span class="hint">mínimo 10 caracteres</span></label>
        <label class="field"><span>Repita a nova senha</span>
          <input type="password" name="repete" autocomplete="new-password" [ngModel]="repete()" (ngModelChange)="repete.set($event)"></label>
        <div class="row"><button class="btn primary" type="submit" [disabled]="busy() || !atual() || !nova() || nova() !== repete()">Trocar senha</button>
          @if (repete() && nova() !== repete()) { <span class="sub bad">as senhas não conferem</span> }</div>
      </form>
      <p class="note mt">Trocar a senha encerra todas as sessões abertas, inclusive esta: você entra de novo com a nova.</p>
    </section>`,
})
export class ManagePage {
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);
  protected readonly busy = signal(false);
  protected readonly auth = inject(AuthService);
  protected readonly atual = signal('');
  protected readonly nova = signal('');
  protected readonly repete = signal('');

  protected readonly alertas = computed(() => this.store.data()?.alerts?.canais ?? []);
  protected readonly alertSub = computed(() => {
    const a = this.store.data()?.alerts;
    if (!a) return '';
    if (!a.canais.length) return 'Nenhum canal configurado: grave o token em /etc/quant/alert.env.';
    return a.ultima_checagem ? `Última checagem às ${new Date(a.ultima_checagem * 1000).toLocaleTimeString('pt-BR')} (a cada minuto).` : 'Aguardando a primeira checagem.';
  });
  private readonly last = computed(() => this.store.data()?.deploy?.last ?? null);
  protected readonly deployLabel = computed(() => {
    const l = this.last();
    return !l ? 'nenhuma ainda' : l.state === 'ok' ? 'aplicada' : l.state === 'erro' ? 'falhou' : 'em andamento';
  });
  protected readonly deployTone = computed<Tone>(() => (this.last()?.state === 'ok' ? 'ok' : this.last()?.state === 'erro' ? 'bad' : ''));
  protected readonly deploySub = computed(() => {
    const l = this.last(), pk = this.store.data()?.deploy?.pacote;
    return (l ? `Última: ${l.msg} (${l.at}). ` : '') + (pk ? 'Há um pacote esperando na caixa de entrada.' : 'Caixa de entrada vazia.');
  });

  private go(call: ReturnType<ApiService['testAlert']>, ok: (r: { canais?: string[] }) => string): void {
    this.busy.set(true);
    runAction(this.toast, call, ok, () => { this.busy.set(false); this.store.refresh(); });
  }

  protected changePassword(): void {
    this.busy.set(true);
    this.auth.changePassword(this.atual(), this.nova()).subscribe({
      next: () => { this.busy.set(false); this.atual.set(''); this.nova.set(''); this.repete.set(''); this.toast.ok('Senha trocada: entre de novo com a nova'); },
      error: e => { this.busy.set(false); this.toast.error(`Falhou: ${errMsg(e)}`); },
    });
  }

  protected testAlert(): void { this.go(this.api.testAlert(), r => `Alerta de teste enviado: ${(r.canais ?? []).join(', ')}`); }

  protected async deploy(): Promise<void> {
    if (!(await this.confirmSvc.ask({ title: 'Atualizar o código?', confirmLabel: 'Atualizar',
        body: 'A VM testa o pacote da caixa de entrada, faz backup e aplica. O runner não é reiniciado.' }))) return;
    this.go(this.api.runDeploy(), () => 'Atualização em execução; o resultado aparece em ~1 min');
  }

  protected async rollback(): Promise<void> {
    if (!(await this.confirmSvc.ask({ title: 'Reverter o código?', confirmLabel: 'Reverter', danger: true,
        body: 'Volta ao último backup feito antes de uma atualização.' }))) return;
    this.go(this.api.rollback(), () => 'Reversão em execução');
  }
}
