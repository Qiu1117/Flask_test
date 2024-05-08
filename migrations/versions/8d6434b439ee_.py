"""empty message

Revision ID: 8d6434b439ee
Revises: 8fd9bf362d83
Create Date: 2024-02-29 02:25:27.146688

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d6434b439ee'
down_revision = '8fd9bf362d83'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(length=80), nullable=False))
        batch_op.add_column(sa.Column('password_hash', sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.alter_column('group',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.String(length=40),
               existing_nullable=True)
        batch_op.drop_index('ix_Account_name')
        batch_op.create_index(batch_op.f('ix_Account_username'), ['username'], unique=True)
        batch_op.drop_column('password')
        batch_op.drop_column('name')

    with op.batch_alter_table('Archive', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archive_name', sa.String(length=40), nullable=False))
        batch_op.drop_index('ix_Archive_name')
        batch_op.create_index(batch_op.f('ix_Archive_archive_name'), ['archive_name'], unique=True)
        batch_op.drop_column('name')

    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dataset_name', sa.String(length=100), nullable=False))
        batch_op.drop_index('ix_Dataset_name')
        batch_op.create_index(batch_op.f('ix_Dataset_dataset_name'), ['dataset_name'], unique=True)
        batch_op.drop_column('name')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False))
        batch_op.drop_index(batch_op.f('ix_Dataset_dataset_name'))
        batch_op.create_index('ix_Dataset_name', ['name'], unique=True)
        batch_op.drop_column('dataset_name')

    with op.batch_alter_table('Archive', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.VARCHAR(length=40), autoincrement=False, nullable=False))
        batch_op.drop_index(batch_op.f('ix_Archive_archive_name'))
        batch_op.create_index('ix_Archive_name', ['name'], unique=True)
        batch_op.drop_column('archive_name')

    with op.batch_alter_table('Account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.VARCHAR(length=20), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('password', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.drop_index(batch_op.f('ix_Account_username'))
        batch_op.create_index('ix_Account_name', ['name'], unique=True)
        batch_op.alter_column('group',
               existing_type=sa.String(length=40),
               type_=sa.VARCHAR(length=20),
               existing_nullable=True)
        batch_op.drop_column('email')
        batch_op.drop_column('password_hash')
        batch_op.drop_column('username')

    # ### end Alembic commands ###