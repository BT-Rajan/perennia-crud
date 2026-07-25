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

## Bulk operations

`bulk_create`, `bulk_update`, `bulk_delete`, and `bulk_restore` run as a
single database transaction: all records succeed or none do. If any record
in a batch is missing, or is changed or removed by another request while
the batch is in flight, the entire batch is rolled back and a
`RecordNotFoundError` or `ConcurrentModificationError` is raised — none of
the batch is left partially applied. If you need best-effort/partial-success
behavior instead, loop over the single-record methods yourself.

## Errors

All exceptions inherit from `PerenniaCrudError` and carry a stable `.code`.
Database-driver failures are translated rather than leaking `pymysql`
exceptions to callers: a unique-constraint violation raises
`DuplicateRecordError`, and other database failures raise
`CrudDatabaseError`. A `ConcurrentModificationError` means a record was
read successfully but had already changed or disappeared by the time a
write reached it — safe for the caller to re-fetch and retry, unlike the
other errors above.

## Connection resilience

`DatabaseConfig` sets `connect_timeout` / `read_timeout` / `write_timeout`
(all default to sane finite values, so a hung connection can't block
forever). `CrudConfig.max_connect_retries` /
`retry_backoff_seconds` control retrying a *new connection* after a
transient failure (connection refused, server gone away, deadlock, lock
wait timeout). Retries never apply to an in-flight statement, since a
statement that already partially executed on the server should not be
silently re-sent.

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
