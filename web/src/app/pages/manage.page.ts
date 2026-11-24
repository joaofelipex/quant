import { Component, computed, inject, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
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
  imports: [PageHead, Icon],
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
        <div class="row mt"><button class="btn" [disabled]="!auth.canOperate() || busy()" (click)="testAlert()">Enviar alerta de teste</button></div>
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
          <button class="btn primary" [disabled]="!auth.isAdmin() || busy()" (click)="deploy()"><app-icon name="package" [size]="15" /> Atualizar código</button>
          <button class="btn" [disabled]="!auth.isAdmin() || busy()" (click)="rollback()"><app-icon name="undo" [size]="15" /> Reverter</button>
        </div>
        <p class="note mt">O painel não recebe código pela web: só aplica o pacote que você colocou por SSH.</p>
      </section>
    </div>
`,
})
export class ManagePage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);
  protected readonly busy = signal(false);

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
