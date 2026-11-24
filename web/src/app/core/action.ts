import { WritableSignal } from '@angular/core';
import { Observable } from 'rxjs';
import { errMsg } from './api.service';
import { ActionResult, Tone } from './models';

export interface Msg { text: string; tone: Tone }
export const NO_MSG: Msg = { text: '', tone: '' };

/** Executa uma acao do painel e reporta o resultado num sinal de mensagem; `done` roda em sucesso e em falha. */
export function runAction(msg: WritableSignal<Msg>, call: Observable<ActionResult>, okText: (r: ActionResult) => string,
                          done?: () => void): void {
  msg.set({ text: 'executando…', tone: '' });
  call.subscribe({
    next: r => { msg.set({ text: okText(r), tone: 'ok' }); done?.(); },
    error: e => { msg.set({ text: `falhou: ${errMsg(e)}`, tone: 'bad' }); done?.(); },
  });
}
