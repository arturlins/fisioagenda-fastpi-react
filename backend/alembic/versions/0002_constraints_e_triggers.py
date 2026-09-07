"""constraints e triggers que o ORM nao expressa

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

Três garantias que precisam viver no banco, não na aplicação:

1. Sobreposição de agenda do profissional — validar em código falha sob
   concorrência: duas requisições simultâneas checam, ambas veem o horário
   livre, ambas inserem. A constraint de exclusão elimina a corrida.
2. Capacidade do atendimento — mesma corrida, mesma solução: a trigger trava a
   linha do agendamento antes de contar.
3. Total pago da cobrança — materializado por trigger a partir de `pagamentos`,
   para que listagem de inadimplência não precise de agregado.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # btree_gist permite combinar igualdade (profissional_id) com sobreposição
    # de intervalo no mesmo índice GiST.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE agendamentos ADD CONSTRAINT agendamentos_sem_sobreposicao
        EXCLUDE USING gist (
            profissional_id WITH =,
            tstzrange(inicio_em, fim_em, '[)') WITH &&
        ) WHERE (status IN ('agendado', 'confirmado', 'realizado'))
        """
    )

    # --- capacidade do atendimento -------------------------------------------
    # Cancelado e remarcado não ocupam vaga; falta do paciente ocupa — a vaga
    # foi consumida ainda que ninguém tenha aparecido.
    op.execute(
        """
        CREATE FUNCTION verificar_capacidade_agendamento() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            vagas smallint;
            ocupadas integer;
        BEGIN
            SELECT a.capacidade INTO vagas
            FROM agendamentos a
            WHERE a.id = NEW.agendamento_id
            FOR UPDATE;

            SELECT count(*) INTO ocupadas
            FROM agendamento_pacientes ap
            WHERE ap.agendamento_id = NEW.agendamento_id
              AND ap.status IN ('agendado', 'confirmado', 'presente', 'falta_paciente');

            IF ocupadas > vagas THEN
                RAISE EXCEPTION
                    'capacidade excedida no agendamento %: % vaga(s), % participante(s)',
                    NEW.agendamento_id, vagas, ocupadas
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER agendamento_pacientes_respeitam_capacidade
        AFTER INSERT OR UPDATE OF status, agendamento_id ON agendamento_pacientes
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION verificar_capacidade_agendamento()
        """
    )

    # --- total pago da cobrança ----------------------------------------------
    # Pagamento estornado não conta: a linha permanece, o valor sai do total.
    # Cobrança cancelada não volta a ser 'aberta' ou 'paga' por causa de
    # pagamento — cancelamento é decisão de quem opera, não do somatório.
    op.execute(
        """
        CREATE FUNCTION recalcular_total_da_cobranca() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            alvo bigint := COALESCE(NEW.cobranca_id, OLD.cobranca_id);
            pago integer;
            devido integer;
            situacao status_cobranca;
        BEGIN
            SELECT c.valor_centavos - c.desconto_centavos + c.acrescimo_centavos, c.status
              INTO devido, situacao
            FROM cobrancas c
            WHERE c.id = alvo
            FOR UPDATE;

            SELECT COALESCE(sum(p.valor_centavos), 0) INTO pago
            FROM pagamentos p
            WHERE p.cobranca_id = alvo
              AND p.estornado_em IS NULL;

            UPDATE cobrancas SET
                valor_pago_centavos = pago,
                status = CASE
                    WHEN situacao = 'cancelada' THEN 'cancelada'
                    WHEN pago <= 0 THEN 'aberta'
                    WHEN pago >= devido THEN 'paga'
                    ELSE 'parcial'
                END::status_cobranca,
                quitada_em = CASE
                    WHEN situacao <> 'cancelada' AND pago >= devido THEN now()
                    ELSE NULL
                END,
                atualizado_em = now()
            WHERE id = alvo;

            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER pagamentos_recalculam_cobranca
        AFTER INSERT OR UPDATE OR DELETE ON pagamentos
        FOR EACH ROW EXECUTE FUNCTION recalcular_total_da_cobranca()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS pagamentos_recalculam_cobranca ON pagamentos")
    op.execute("DROP FUNCTION IF EXISTS recalcular_total_da_cobranca()")
    op.execute(
        "DROP TRIGGER IF EXISTS agendamento_pacientes_respeitam_capacidade ON agendamento_pacientes"
    )
    op.execute("DROP FUNCTION IF EXISTS verificar_capacidade_agendamento()")
    op.execute("ALTER TABLE agendamentos DROP CONSTRAINT IF EXISTS agendamentos_sem_sobreposicao")
    # A extensão fica: outros objetos podem depender dela, e removê-la num
    # downgrade parcial quebraria mais do que conserta.
