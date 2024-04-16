"""empty message

Revision ID: ae85366de726
Revises: ea0f94518956
Create Date: 2024-02-29 17:01:29.062205

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ae85366de726'
down_revision = 'ea0f94518956'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.drop_column('group')

    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('labels', postgresql.ARRAY(sa.String(length=30)), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.drop_column('labels')

    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group', sa.VARCHAR(length=40), autoincrement=False, nullable=True))

    # ### end Alembic commands ###
