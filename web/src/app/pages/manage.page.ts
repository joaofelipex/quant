import { Component, computed, inject, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
import { Msg, NO_MSG, runAction } from '../core/action';
import { StatusStore } from '../core/status.store';
import { Tone } from '../core/models';
import { StatCard } from '../shared/stat-card';

@Component({
  selector: 'app-manage',
  imports: [StatCard],
  template: `
    <h2>Gestão da VM</h2>
    <div class="grid">
      <app-stat label="alertas" [value]="alertas().length ? alertas().join(' + ') : 'sem canal'" [tone]="alertas().length ? 'ok' : 'bad'"
                [sub]="alertSub()" />
      <app-stat label="atualização do código" [value]="deployLabel()" [tone]="deployTone()" [sub]="deploySub()" />
    </div>
    <div class="row mt">
      <button class="act" [disabled]="busy()" (click)="testAlert()">Enviar alerta de teste</button>
      <button class="act" [disabled]="busy()" (click)="deploy()">Atualizar código</button>
      <button class="act" [disabled]="busy()" (click)="rollback()">Reverter</button>
      <span class="sub" [class]="msg().tone">{{ msg().text }}</span>
    </div>
    <p class="note"><b>Alertas:</b> avisam por Telegram/e-mail quando o runner cai ou volta, a trava de risco dispara, o kill-switch é acionado,
      a autoverificação falha ou um trade fecha. Os segredos ficam em <code>/etc/quant/alert.env</code> (você grava na VM).</p>
    <p class="note"><b>Atualizar:</b> no seu computador rode <code>deploy/enviar-pacote.sh</code> (monta o painel Angular, empacota o repo e coloca
      na caixa de entrada da VM por SSH) e clique em Atualizar. A VM testa o pacote, faz backup e só então aplica; reinicie o runner depois.
      <b>Reverter</b> volta ao último backup. O painel não recebe código pela web.</p>`,
})
export class ManagePage {
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);
  protected readonly busy = signal(false);
  protected readonly msg = signal<Msg>(NO_MSG);

  protected readonly alertas = computed(() => this.store.data()?.alerts?.canais ?? []);
  protected readonly alertSub = computed(() => {
    const a = this.store.data()?.alerts;
    if (!a) return '';
    if (!a.canais.length) return 'grave o token em /etc/quant/alert.env na VM (ver deploy/README.md)';
    return a.ultima_checagem ? `última checagem ${new Date(a.ultima_checagem * 1000).toLocaleTimeString('pt-BR')}` : 'aguardando a 1ª checagem';
  });
  private readonly last = computed(() => this.store.data()?.deploy?.last ?? null);
  protected readonly deployLabel = computed(() => {
    const l = this.last();
    return !l ? 'nenhuma ainda' : l.state === 'ok' ? 'aplicado' : l.state === 'erro' ? 'FALHOU' : 'em andamento';
  });
  protected readonly deployTone = computed<Tone>(() => (this.last()?.state === 'ok' ? 'ok' : this.last()?.state === 'erro' ? 'bad' : ''));
  protected readonly deploySub = computed(() => {
    const l = this.last(), pk = this.store.data()?.deploy?.pacote;
    return (l ? `${l.msg} (${l.at})` : '') + (pk ? ' · pacote esperando na caixa de entrada' : ' · caixa de entrada vazia');
  });

  private go(call: ReturnType<ApiService['testAlert']>, ok: (r: { canais?: string[] }) => string, ask?: string): void {
    if (ask && !window.confirm(ask)) return;
    this.busy.set(true);
    runAction(this.msg, call, ok, () => { this.busy.set(false); this.store.refresh(); });
  }

  protected testAlert(): void { this.go(this.api.testAlert(), r => `alerta enviado: ${(r.canais ?? []).join(', ')}`); }
  protected deploy(): void {
    this.go(this.api.runDeploy(), () => 'atualização em execução; atualiza em ~1 min', 'Testar o pacote da caixa de entrada e aplicar o código novo?');
  }
  protected rollback(): void {
    this.go(this.api.rollback(), () => 'reversão em execução', 'Voltar o código ao último backup?');
  }
}
