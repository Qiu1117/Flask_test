"""empty message

Revision ID: 8fd9bf362d83
Revises: 
Create Date: 2024-02-28 23:57:39.816043

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8fd9bf362d83'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('account')
    op.drop_table('archive')
    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.drop_index('fki_archive_contains_dataset_fk')

    op.drop_table('dataset')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('dataset',
    sa.Column('id', sa.INTEGER(), server_default=sa.text('nextval(\'"Dataset_id_seq"\'::regclass)'), autoincrement=True, nullable=False),
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('research_focus', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('authors', postgresql.ARRAY(sa.VARCHAR(length=100)), autoincrement=False, nullable=True),
    sa.Column('root_link', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('paper_link', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
    sa.Column('achive_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['achive_id'], ['archive.id'], name='archive_contains_dataset_fk'),
    sa.PrimaryKeyConstraint('id', name='Dataset_pkey')
    )
    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.create_index('fki_archive_contains_dataset_fk', ['achive_id'], unique=False)

    op.create_table('archive',
    sa.Column('id', sa.INTEGER(), server_default=sa.text('nextval(\'"Archive_id_seq"\'::regclass)'), autoincrement=True, nullable=False),
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('research_focus', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('root_link', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('paper_link', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('creation_time', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('modification_time', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('total_case_amount', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('recorded_amount', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('crawlable', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('upload_features', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('download_features', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='Archive_pkey')
    )
    op.create_table('account',
    sa.Column('id', sa.INTEGER(), server_default=sa.text('nextval(\'"Account_id_seq"\'::regclass)'), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('role', postgresql.ENUM('admin', 'member', name='role'), autoincrement=False, nullable=False),
    sa.Column('group', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('password', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('creation_time', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('expiration_time', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='Account_pkey')
    )
    # ### end Alembic commands ###