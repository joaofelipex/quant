"""Especificacao de contrato: o motor de backtest nao conhece nenhum ativo especifico."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    name: str
    point_value: float  # moeda por ponto, 1 contrato/unidade
    tick_size: float  # menor variacao de preco, em pontos
    fee_round_trip: float = 0.0  # custo fixo por round-trip, por contrato
    currency: str = "BRL"


WIN = Instrument("WIN", point_value=0.20, tick_size=5, fee_round_trip=1.20)
WDO = Instrument("WDO", point_value=10.0, tick_size=0.5, fee_round_trip=1.20)
