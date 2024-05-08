"""empty message

Revision ID: ea0f94518956
Revises: 80de5581b32a
Create Date: 2024-02-29 14:25:05.139384

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ea0f94518956'
down_revision = '80de5581b32a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uploaded_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('download_times', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('size', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('modalities', postgresql.ARRAY(sa.String(length=30)), nullable=True))
        batch_op.add_column(sa.Column('participants', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('files', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('others', postgresql.JSON(astext_type=sa.Text()), nullable=True))
        batch_op.drop_column('upload_features')
        batch_op.drop_column('crawlable')
        batch_op.drop_column('recorded_amount')
        batch_op.drop_column('total_case_amount')
        batch_op.drop_column('download_features')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('download_features', sa.TEXT(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('total_case_amount', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('recorded_amount', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('crawlable', sa.BOOLEAN(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('upload_features', sa.TEXT(), autoincrement=False, nullable=True))
        batch_op.drop_column('others')
        batch_op.drop_column('files')
        batch_op.drop_column('participants')
        batch_op.drop_column('modalities')
        batch_op.drop_column('size')
        batch_op.drop_column('download_times')
        batch_op.drop_column('uploaded_date')

    # ### end Alembic commands ###