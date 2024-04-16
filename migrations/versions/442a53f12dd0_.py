"""empty message

Revision ID: 442a53f12dd0
Revises: f353221143ae
Create Date: 2024-03-01 02:17:39.885063

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '442a53f12dd0'
down_revision = 'f353221143ae'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Acc_Group', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.Numeric(precision=1), nullable=True))
        batch_op.drop_column('valid')

    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notification', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    with op.batch_alter_table('Dataset_Group', schema=None) as batch_op:
        batch_op.drop_column('editable')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Dataset_Group', schema=None) as batch_op:
        batch_op.add_column(sa.Column('editable', sa.BOOLEAN(), autoincrement=False, nullable=True))

    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.drop_column('notification')

    with op.batch_alter_table('Acc_Group', schema=None) as batch_op:
        batch_op.add_column(sa.Column('valid', sa.BOOLEAN(), autoincrement=False, nullable=True))
        batch_op.drop_column('status')

    # ### end Alembic commands ###
