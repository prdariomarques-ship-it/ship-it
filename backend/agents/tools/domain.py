"""Tools over the church and store domains."""

from datetime import datetime, timezone
from decimal import Decimal

from agents.tools.base import Tool, ToolContext, ok
from models.store import StoreCustomer
from repositories.base import SQLAlchemyRepository
from repositories.church import ChurchMemberRepository
from repositories.product import ProductRepository
from services.validation import validate_email, validate_phone_e164

# Mantido em espelho com api/schemas.py::_STORE_SEGMENTS -- não importar
# daqui para lá (API não deve depender da camada de agentes/tools).
_VALID_SEGMENTS = {"pintor", "lojista", "consumidor_final"}


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
    context: ToolContext,
    name: str,
    phone: str | None = None,
    email: str | None = None,
    segment: str | None = None,
) -> str:
    if phone is not None and not validate_phone_e164(phone):
        raise ValueError("phone must be in E.164 format, e.g. +5511987654321")
    if email is not None and not validate_email(email):
        raise ValueError("email is not a valid address")
    if segment is not None and segment not in _VALID_SEGMENTS:
        raise ValueError(f"segment inválido: {segment!r}. Use um de: {sorted(_VALID_SEGMENTS)}")
    customer = await _StoreRepo(context.db).create(
        name=name, phone=phone, email=email, segment=segment
    )
    return ok(customer_id=customer.id, name=customer.name, segment=customer.segment)


async def _update_store_customer_segment(
    context: ToolContext, customer_name: str, segment: str
) -> str:
    if segment not in _VALID_SEGMENTS:
        raise ValueError(f"segment inválido: {segment!r}. Use um de: {sorted(_VALID_SEGMENTS)}")
    repository = _StoreRepo(context.db)
    customer = await repository.find_one(name=customer_name)
    if customer is None:
        raise ValueError(f"cliente {customer_name!r} não encontrado")
    updated = await repository.update(customer, segment=segment)
    return ok(customer_id=updated.id, segment=updated.segment)


async def _list_products(context: ToolContext, category: str | None = None) -> str:
    filters: dict = {"active": True}
    if category is not None:
        filters["category"] = category
    products = await ProductRepository(context.db).list(limit=100, **filters)
    return ok(
        products=[
            {
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "unit": product.unit,
                "unit_price": str(product.unit_price),
                "stock_quantity": product.stock_quantity,
            }
            for product in products
        ]
    )


async def _search_products(context: ToolContext, query: str) -> str:
    products = await ProductRepository(context.db).search_by_name(query, limit=10)
    return ok(
        products=[
            {
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "unit": product.unit,
                "unit_price": str(product.unit_price),
                "stock_quantity": product.stock_quantity,
            }
            for product in products
        ]
    )


async def _build_quote_lines(
    repository: ProductRepository, items: list[dict]
) -> tuple[list[dict], Decimal]:
    """Shared by create_quote (read-only) and record_order (persists): resolve
    each {sku, quantity} against the real catalog and price/stock it. Raises
    ValueError on any unknown SKU, non-positive quantity, or short stock --
    the model gets that back as a tool error and can correct the call."""
    lines: list[dict] = []
    total = Decimal("0")
    for raw_item in items:
        sku = raw_item.get("sku")
        try:
            quantity = int(raw_item.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValueError(f"quantity inválida para o item {sku!r}") from None
        if not sku or quantity <= 0:
            raise ValueError("cada item precisa de 'sku' e 'quantity' > 0")

        product = await repository.get_by_sku(sku)
        if product is None or not product.active:
            raise ValueError(f"produto não encontrado ou inativo: {sku!r}")
        if product.stock_quantity < quantity:
            raise ValueError(
                f"estoque insuficiente para {product.name}: "
                f"disponível {product.stock_quantity}, solicitado {quantity}"
            )

        line_total = product.unit_price * quantity
        total += line_total
        lines.append(
            {
                "sku": product.sku,
                "name": product.name,
                "unit": product.unit,
                "quantity": quantity,
                "unit_price": str(product.unit_price),
                "line_total": str(line_total),
            }
        )
    return lines, total


async def _create_quote(
    context: ToolContext, items: list[dict], customer_name: str | None = None
) -> str:
    lines, total = await _build_quote_lines(ProductRepository(context.db), items)
    return ok(customer_name=customer_name, items=lines, total=str(total))


async def _record_order(
    context: ToolContext, customer_name: str, items: list[dict]
) -> str:
    store_repository = _StoreRepo(context.db)
    customer = await store_repository.find_one(name=customer_name)
    if customer is None:
        raise ValueError(
            f"cliente {customer_name!r} não encontrado — cadastre com "
            "add_store_customer antes de registrar um pedido"
        )

    product_repository = ProductRepository(context.db)
    lines, total = await _build_quote_lines(product_repository, items)

    # Baixa de estoque: melhor esforço, sem lock -- consistente com o resto
    # do repo (nenhum outro fluxo usa SELECT ... FOR UPDATE hoje). Aceitável
    # na escala de uma loja física com um único operador comercial por vez.
    for line in lines:
        product = await product_repository.get_by_sku(line["sku"])
        if product is None:
            # Só ocorre se o produto foi removido entre _build_quote_lines
            # (linha acima) e aqui -- corrida rara, mas o pedido já teria
            # sido apresentado ao cliente com valores calculados, então
            # falhar alto é melhor do que gravar um pedido incompleto.
            raise ValueError(f"produto removido durante o registro do pedido: {line['sku']!r}")
        await product_repository.update(
            product, stock_quantity=product.stock_quantity - line["quantity"]
        )

    order_entry = {
        "items": lines,
        "total": str(total),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    updated_orders = [*customer.orders, order_entry]
    updated = await store_repository.update(customer, orders=updated_orders)
    return ok(
        customer_id=updated.id,
        order=order_entry,
        order_count=len(updated_orders),
    )


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
            "segment": {
                "type": "string",
                "enum": sorted(_VALID_SEGMENTS),
                "description": "Qualificação comercial do cliente, se já souber.",
            },
        },
        "required": ["name"],
    },
)

update_store_customer_segment_tool = Tool(
    name="update_store_customer_segment",
    description=(
        "Classifica ou reclassifica um cliente já cadastrado por segmento comercial "
        "('pintor', 'lojista' ou 'consumidor_final'). Use assim que identificar o "
        "perfil do cliente na conversa -- é o principal sinal de qualificação de lead."
    ),
    handler=_update_store_customer_segment,
    parameters={
        "type": "object",
        "properties": {
            "customer_name": {"type": "string"},
            "segment": {"type": "string", "enum": sorted(_VALID_SEGMENTS)},
        },
        "required": ["customer_name", "segment"],
    },
)

list_products_tool = Tool(
    name="list_products",
    description="Lista os produtos ativos do catálogo, opcionalmente filtrando por categoria.",
    handler=_list_products,
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Ex: 'tinta_latex', 'esmalte', 'verniz', 'acessorio'",
            }
        },
        "required": [],
    },
)

search_products_tool = Tool(
    name="search_products",
    description="Busca produtos ativos do catálogo pelo nome (ex: 'tinta acrílica branca').",
    handler=_search_products,
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)

_QUOTE_ITEMS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "sku": {"type": "string", "description": "SKU do produto (ver list_products/search_products)"},
            "quantity": {"type": "integer", "minimum": 1},
        },
        "required": ["sku", "quantity"],
    },
}

create_quote_tool = Tool(
    name="create_quote",
    description=(
        "Monta um orçamento a partir de itens (sku + quantidade), calculando preço "
        "unitário e total com base no catálogo e estoque reais. Não gera pedido nem "
        "baixa estoque -- é só a cotação. Use record_order depois que o cliente "
        "confirmar a compra."
    ),
    handler=_create_quote,
    parameters={
        "type": "object",
        "properties": {
            "items": _QUOTE_ITEMS_SCHEMA,
            "customer_name": {
                "type": "string",
                "description": "Nome do cliente, se já conhecido (só para exibição no orçamento).",
            },
        },
        "required": ["items"],
    },
)

record_order_tool = Tool(
    name="record_order",
    description=(
        "Registra um pedido confirmado para um cliente já cadastrado: recalcula os "
        "valores contra o catálogo, grava no histórico do cliente (orders) e baixa "
        "o estoque dos produtos vendidos."
    ),
    handler=_record_order,
    parameters={
        "type": "object",
        "properties": {
            "customer_name": {"type": "string"},
            "items": _QUOTE_ITEMS_SCHEMA,
        },
        "required": ["customer_name", "items"],
    },
)
