"""Add embedding column to Recipe model

Revision ID: 310c35736b74
Revises: 
Create Date: 2024-09-26 21:44:57.280167

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '310c35736b74'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('recipe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding', sa.PickleType(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('recipe', schema=None) as batch_op:
        batch_op.drop_column('embedding')

    # ### end Alembic commands ###
