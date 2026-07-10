"""Learning: tags a contact with the domains it interacts with, deduplicated
at the storage boundary so repeat conversations never grow the list."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from orchestrator.intent import Intent, IntentHypothesis, IntentResult
from orchestrator.learning import LearningEngine
from orchestrator.planning import Plan, PlanStep
from orchestrator.priority import Priority, PriorityResult


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Aprendiz", phone="5511900112233")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


def _intent(top: Intent) -> IntentResult:
    return IntentResult(top=top, hypotheses=[IntentHypothesis(intent=top, confidence=0.9)])


_PRIORITY = PriorityResult(level=Priority.NORMAL)


@pytest.mark.asyncio
async def test_learning_tags_contact_with_agent_domain(session_factory, contact):
    plan = Plan(steps=[PlanStep(objective="comprar produto", agent="store")])
    async with session_factory() as session:
        added = await LearningEngine().apply(session, contact.id, _intent(Intent.STORE), _PRIORITY, plan)
    assert added == ["loja"]

    async with session_factory() as session:
        refreshed = await session.get(Contact, contact.id)
    assert "loja" in refreshed.categories


@pytest.mark.asyncio
async def test_learning_does_not_duplicate_existing_categories(session_factory, contact):
    plan = Plan(steps=[PlanStep(objective="comprar produto", agent="store")])
    async with session_factory() as session:
        await LearningEngine().apply(session, contact.id, _intent(Intent.STORE), _PRIORITY, plan)

    async with session_factory() as session:
        added_again = await LearningEngine().apply(session, contact.id, _intent(Intent.STORE), _PRIORITY, plan)
    assert added_again == []  # already tagged — no redundant write

    async with session_factory() as session:
        refreshed = await session.get(Contact, contact.id)
    assert refreshed.categories.count("loja") == 1


@pytest.mark.asyncio
async def test_learning_skips_agents_with_no_category_mapping(session_factory, contact):
    plan = Plan(steps=[PlanStep(objective="oi", agent="assistant")])
    async with session_factory() as session:
        added = await LearningEngine().apply(session, contact.id, _intent(Intent.GREETING), _PRIORITY, plan)
    assert added == []


@pytest.mark.asyncio
async def test_learning_is_a_no_op_without_a_contact():
    plan = Plan(steps=[PlanStep(objective="oi", agent="store")])
    added = await LearningEngine().apply(None, None, _intent(Intent.STORE), _PRIORITY, plan)
    assert added == []
