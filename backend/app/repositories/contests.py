from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Contest, Entry, EntryRevision


class ContestRepository:
    """ORM persistence operations for contest aggregates; transaction ownership stays outside."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, contest: Contest) -> Contest:
        self.session.add(contest)
        self.session.flush()
        return contest

    def get(self, contest_id: int) -> Contest | None:
        return self.session.get(Contest, contest_id)

    def get_by_slug(self, slug: str) -> Contest | None:
        return self.session.scalar(select(Contest).where(Contest.slug == slug))


class EntryRepository:
    """ORM persistence operations for entries and immutable input revisions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: Entry) -> Entry:
        self.session.add(entry)
        self.session.flush()
        return entry

    def get(self, entry_id: int) -> Entry | None:
        return self.session.get(Entry, entry_id)

    def add_revision(self, revision: EntryRevision) -> EntryRevision:
        self.session.add(revision)
        self.session.flush()
        return revision

    def list_revisions(self, entry_id: int) -> list[EntryRevision]:
        statement = (
            select(EntryRevision)
            .where(EntryRevision.entry_id == entry_id)
            .order_by(EntryRevision.revision_number)
        )
        return list(self.session.scalars(statement))
