"""Shared PostgreSQL table snapshots for migration-preservation tests."""

from sqlalchemy import Connection, Table, select

from app.models import (
    AIBriefBudget,
    AIBriefControl,
    AIBriefJob,
    AppUser,
    Article,
    ArticleReadState,
    Category,
    CollectionRun,
    ReaderInvitation,
    Source,
    SourceProposal,
    Subscription,
)

TABLES = tuple(
    model.__table__
    for model in (
        AppUser,
        Category,
        Source,
        Article,
        CollectionRun,
        Subscription,
        ArticleReadState,
        ReaderInvitation,
        SourceProposal,
        AIBriefBudget,
        AIBriefControl,
        AIBriefJob,
    )
)


def read_rows(connection: Connection, table: Table) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(select(table).order_by(*table.primary_key)).mappings()
    ]
