"""Seed de demonstração: de onde vem a senha e o que é impresso.

No servidor público, a senha é gerada pelo Terraform. A senha fixa do
repositório só vale em desenvolvimento, e a gerada nunca vai para o log.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from scripts.semear import SENHA_PADRAO, linha_da_senha, senha_de_demonstracao


def test_sem_variavel_usa_a_senha_de_desenvolvimento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEMEAR_SENHA", raising=False)

    senha, do_ambiente = senha_de_demonstracao()

    assert senha.get_secret_value() == SENHA_PADRAO
    assert do_ambiente is False


def test_com_variavel_usa_a_senha_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEMEAR_SENHA", "GeradaPeloTerraform2026")

    senha, do_ambiente = senha_de_demonstracao()

    assert senha.get_secret_value() == "GeradaPeloTerraform2026"
    assert do_ambiente is True


@pytest.mark.parametrize("valor", ["", "curta123"])
def test_senha_fora_da_politica_do_realm_e_recusada(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("SEMEAR_SENHA", valor)

    with pytest.raises(ValueError, match="SEMEAR_SENHA"):
        senha_de_demonstracao()


def test_senha_do_ambiente_nunca_e_impressa() -> None:
    linha = linha_da_senha(SecretStr("GeradaPeloTerraform2026"), do_ambiente=True)

    assert "GeradaPeloTerraform2026" not in linha
    assert "SEMEAR_SENHA" in linha


def test_senha_de_desenvolvimento_e_impressa() -> None:
    assert SENHA_PADRAO in linha_da_senha(SecretStr(SENHA_PADRAO), do_ambiente=False)
