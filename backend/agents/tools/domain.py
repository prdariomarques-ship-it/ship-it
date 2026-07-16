"""Tools over the church and store domains."""

from agents.tools.base import Tool, ToolContext, ok
from models.store import StoreCustomer
from repositories.base import SQLAlchemyRepository
from repositories.church import ChurchMemberRepository


class _StoreRepo(SQLAlchemyRepository[StoreCustomer]):
    model = StoreCustomer


async def _list_church_members(context: ToolContext) -> str:
    members = await ChurchMemberRepository(context.db).list(limit=50)
    return ok(
        members=[
            {
                "id": member.id,
                "name": member.name,
                "role": member.role,
                "ministries": member.ministries,
                "prayer_requests": member.prayer_requests,
            }
            for member in members
        ]
    )


async def _add_prayer_request(
    context: ToolContext, member_name: str, request: str
) -> str:
    repository = ChurchMemberRepository(context.db)
    matches = await repository.search_by_name(member_name, limit=1)
    member = matches[0] if matches else await repository.create(name=member_name)
    await repository.update(member, prayer_requests=[*member.prayer_requests, request])
    return ok(member_id=member.id, prayer_requests=member.prayer_requests)


async def _list_store_customers(context: ToolContext) -> str:
    customers = await _StoreRepo(context.db).list(limit=50)
    return ok(
        customers=[
            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "email": customer.email,
                "orders": len(customer.orders),
            }
            for customer in customers
        ]
    )


async def _add_store_customer(
    context: ToolContext, name: str, phone: str | None = None, email: str | None = None
) -> str:
    customer = await _StoreRepo(context.db).create(name=name, phone=phone, email=email)
    return ok(customer_id=customer.id, name=customer.name)


list_church_members_tool = Tool(
    name="list_church_members",
    description="Lista os membros da igreja com funções, ministérios e pedidos de oração.",
    handler=_list_church_members,
)

add_prayer_request_tool = Tool(
    name="add_prayer_request",
    description="Registra um pedido de oração para um membro (cria o membro se não existir).",
    handler=_add_prayer_request,
    parameters={
        "type": "object",
        "properties": {
            "member_name": {"type": "string"},
            "request": {"type": "string"},
        },
        "required": ["member_name", "request"],
    },
)

list_store_customers_tool = Tool(
    name="list_store_customers",
    description="Lista os clientes da loja.",
    handler=_list_store_customers,
)

add_store_customer_tool = Tool(
    name="add_store_customer",
    description="Cadastra um novo cliente da loja.",
    handler=_add_store_customer,
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
        },
        "required": ["name"],
    },
)
