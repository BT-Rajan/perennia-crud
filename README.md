# perennia-crud

Reusable business data operations engine for Perennia applications: create,
read, update, delete, restore, exists, list — with filtering, sorting,
pagination, field selection, bulk operations, and lifecycle hooks. Not an
ORM, not a framework, no business logic.

## Install

```
pip install perennia-crud
```

## Usage

```python
from perennia_crud import CrudEngine, CrudConfig, DatabaseConfig, EntitySchema, ListQuery, FilterCondition, SortField

customer_schema = EntitySchema(
    table="customers",
    fields=["name", "email", "phone"],   # writable/filterable/sortable allowlist
    primary_key="id",
    soft_delete=True,
)

config = CrudConfig(database=DatabaseConfig(host="localhost", user="app", password="...", database="myapp"))
customers = CrudEngine(config, customer_schema)

record = customers.create({"name": "Acme Ltd", "email": "billing@acme.example"})
customers.update(record["id"], {"phone": "+1-555-0100"})

page = customers.list(ListQuery(
    filters=[FilterCondition("name", "like", "%acme%")],
    sort=[SortField("name", "asc")],
    page=1,
))
for row in page.items:
    print(row)

customers.delete(record["id"])   # soft delete
customers.restore(record["id"])
```

## Lifecycle hooks

Pass any object exposing `before_create`, `after_create`, `before_update`,
`after_update`, `before_delete`, `after_delete`, `before_restore`,
`after_restore` as `hooks=`. perennia-crud calls whichever are present and
never inspects what they do — business logic (validation, notifications,
search indexing, audit) stays in the consuming module.

```python
class CustomerHooks:
    def after_create(self, record):
        search.index("customer", record["id"])

customers = CrudEngine(config, customer_schema, hooks=CustomerHooks())
```

## Authorization

Pass a `perennia-access` `PerenniaAccess` instance (or anything exposing
`.require(identity, permission_code)`) as `access=`. Permission codes are
`<table>.<action>` (e.g. `customers.create`, `customers.delete`), or override
the prefix with `EntitySchema(permission_prefix=...)`.

## Persistence

perennia-crud never creates or migrates tables — the consuming module owns
its own schema. `EntitySchema.fields` is a strict allowlist: any field not
listed is rejected before it reaches SQL, since column names cannot be
parameterized.

## Design boundaries

No auth, no RBAC, no ORM, no code generation, no business validation, no
notifications, no search indexing, no workflow. See `perennia-auth`,
`perennia-access`, and `perennia-search` for those concerns.
