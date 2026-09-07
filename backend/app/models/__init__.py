"""Models ORM — as 18 tabelas do MVP.

Importar este pacote registra tudo em `Base.metadata`. O Alembic depende disso:
model não importado é tabela que o autogenerate propõe remover.

Os models cobrem o esquema inteiro desde já (ADR-008), mesmo que as camadas de
repositório, serviço e controller ainda existam só para o módulo de acesso.
"""

from __future__ import annotations

from app.models.acesso import ClinicaUsuario, Usuario
from app.models.agenda import Agendamento, AgendamentoPaciente, Turma, TurmaAluno
from app.models.catalogo import ProfissionalServico, Servico
from app.models.disponibilidade import BloqueioAgenda, HorarioProfissional
from app.models.financeiro import Cobranca, Contrato, Pagamento
from app.models.organizacao import Clinica, Conta
from app.models.pacientes import Evolucao, Paciente, PontoAtencao

__all__ = [
    "Agendamento",
    "AgendamentoPaciente",
    "BloqueioAgenda",
    "Clinica",
    "ClinicaUsuario",
    "Cobranca",
    "Conta",
    "Contrato",
    "Evolucao",
    "HorarioProfissional",
    "Paciente",
    "Pagamento",
    "PontoAtencao",
    "ProfissionalServico",
    "Servico",
    "Turma",
    "TurmaAluno",
    "Usuario",
]
