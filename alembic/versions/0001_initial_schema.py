"""Initial PostgreSQL foundation schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-24 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.create_table(
        "membership_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_membership_plans_id"), "membership_plans", ["id"], unique=False)

    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("joined_at", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_members_id"), "members", ["id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("receiver_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=150), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["receiver_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_id"), "messages", ["id"], unique=False)
    op.create_index(op.f("ix_messages_receiver_id"), "messages", ["receiver_id"], unique=False)
    op.create_index(op.f("ix_messages_sender_id"), "messages", ["sender_id"], unique=False)

    op.create_table(
        "membership_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["membership_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_membership_subscriptions_id"), "membership_subscriptions", ["id"], unique=False)
    op.create_index(op.f("ix_membership_subscriptions_member_id"), "membership_subscriptions", ["member_id"], unique=False)
    op.create_index(op.f("ix_membership_subscriptions_plan_id"), "membership_subscriptions", ["plan_id"], unique=False)

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_id"), "feedback", ["id"], unique=False)
    op.create_index(op.f("ix_feedback_member_id"), "feedback", ["member_id"], unique=False)

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["membership_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoices_id"), "invoices", ["id"], unique=False)
    op.create_index(op.f("ix_invoices_member_id"), "invoices", ["member_id"], unique=False)
    op.create_index(op.f("ix_invoices_subscription_id"), "invoices", ["subscription_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoices_subscription_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_member_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_id"), table_name="invoices")
    op.drop_table("invoices")

    op.drop_index(op.f("ix_feedback_member_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_id"), table_name="feedback")
    op.drop_table("feedback")

    op.drop_index(op.f("ix_membership_subscriptions_plan_id"), table_name="membership_subscriptions")
    op.drop_index(op.f("ix_membership_subscriptions_member_id"), table_name="membership_subscriptions")
    op.drop_index(op.f("ix_membership_subscriptions_id"), table_name="membership_subscriptions")
    op.drop_table("membership_subscriptions")

    op.drop_index(op.f("ix_messages_sender_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_receiver_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_members_id"), table_name="members")
    op.drop_table("members")

    op.drop_index(op.f("ix_membership_plans_id"), table_name="membership_plans")
    op.drop_table("membership_plans")

    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
