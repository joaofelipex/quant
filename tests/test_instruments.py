import dataclasses

import pytest

from quant.instruments import WDO, WIN


def test_especificacoes_b3():
    assert (WIN.point_value, WIN.tick_size) == (0.20, 5)
    assert (WDO.point_value, WDO.tick_size) == (10.0, 0.5)
    assert WIN.currency == "BRL"


def test_instrumento_imutavel():
    with pytest.raises(dataclasses.FrozenInstanceError):
        WIN.point_value = 1.0
