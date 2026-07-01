# Painel Admin Completo — Instrucoes de Implementacao

> Gerado em 2026-05-14. Este arquivo contem TODO o contexto necessario para implementar o plano sem depender de historico de conversa.

---

## 1. State Atual do Sistema

### Models existentes

**`app/models/tenant.py`** — campos: `id (UUID)`, `nome (str)`, `plano (str, default="basico")`, `email_contato (str)`, `ativo (bool, default=True)`

**`app/models/api_key.py`** — campos: `id (UUID)`, `tenant_id (FK)`, `key_hash (str 128)`, `nome_cliente (str 255)`, `status (str 20, default="active")`, `quota_diaria (int, default=1000)`, `owner (str 255, nullable)`, `created_at (datetime)`

**`app/models/billing_record.py`** — campos: `id (UUID)`, `tenant_id (FK)`, `request_id (FK)`, `api_key_id (FK nullable)`, `tokens_input (int)`, `tokens_output (int)`, `modelo (str 100)`, `llm_provider (str 50 nullable)`, `custo_unitario (float)`, `custo_total (float)`, `created_at (datetime)`

**`app/models/validation_request.py`** — campos: `id (UUID)`, `tenant_id (FK)`, `api_key_id (FK)`, `arquivo_path`, `document_type`, `regra`, `status`, `resultado_ok`, `resultado_reason`, `resultado_confidence`, `llm_model`, `tokens_input`, `tokens_output`, `custo_estimado`, `llm_results (JSONB)`, `created_at`, `updated_at`

### Migrations aplicadas
- 001_initial, 002_add_regra, 003_add_llm_results, 004_billing_breakdown

### Routers registrados em `app/main.py`
- validate, requests, billing, health, admin_keys, dashboard

### Auth flow
- **Cliente:** `X-API-Key` header → `auth.authenticate(db, raw_key)` → retorna `(Tenant, APIKey)`. Verifica hash SHA-256, tenant ativo, quota diaria via `ValidationRequest` count.
- **Admin:** `X-Admin-Key` header → `verify_admin_key()` em `admin_keys.py` → `secrets.compare_digest` contra `settings.ADMIN_API_KEY`. Se vazio, retorna 503.

### Billing endpoints existentes (publicos, exigem X-API-Key)
- `GET /v1/billing/summary` → `BillingSummary`
- `GET /v1/billing/usage` → `UsageSummaryResponse` (by_provider + by_api_key)
- `GET /v1/billing/usage/detail` → `list[UsageDetailRow]`

### Admin endpoints existentes (exigem X-Admin-Key)
- `POST /v1/admin/api-keys` → criar key
- `GET /v1/admin/api-keys?tenant_id=...` → listar keys
- `PATCH /v1/admin/api-keys/{key_id}` → editar key
- `DELETE /v1/admin/api-keys/{key_id}?tenant_id=...` → revogar key
- `GET /v1/admin/tenants` → listar tenants

### Schemas existentes em `app/schemas/billing.py`
- `BillingSummary`, `APIKeyCreate`, `APIKeyCreated`, `APIKeyRead`, `APIKeyUpdate`, `UsageByProvider`, `UsageByAPIKey`, `UsageDetailRow`, `UsageSummaryResponse`

### Services existentes em `app/modules/Billing/`
- `api_key_service.py` — create, list, update, delete (soft delete com status="revoked")
- `usage_service.py` — `usage_by_provider(db, tenant_id, from_dt, to_dt)`, `usage_by_api_key(db, tenant_id, from_dt, to_dt)`, `usage_detail(db, tenant_id, from_dt, to_dt, api_key_id, limit)`
- `cost_config.py` — custos por token por provider
- `record.py` — `record_billing()`

---

## 2. Bugs Confirmados

### Bug 1 — 422 admin em `/billing/usage` e `/billing/usage/detail`
- **Causa:** endpoints em `app/routers/billing.py` linhas 72 e 100 declaram `x_api_key: str = Header(..., alias="X-API-Key")` como obrigatorio. Admin manda `X-Admin-Key`.
- **Correcao:** criar endpoints admin equivalentes em `admin_keys.py` que aceitam `X-Admin-Key` + `tenant_id` como query param.

### Bug 2 — Dropdown tenants vazio na tab API Keys
- **Causa:** `loadTenants()` (linha 216-219 do dashboard.html) e async fire-and-forget. `enterApp()` chama sem await. Quando admin clica em API Keys, `tenantsCache` pode estar vazio.
- **Correcao:** `renderKeys()` deve fazer fetch de tenants antes de montar HTML.

### Bug 3 — Filtros de data compartilhados entre tabs
- **Causa:** `loadDetail()` (linha 410) usa `usagePreset` (variavel do tab Usage) e le `detailFrom`/`detailTo` que so existem quando o tab foi renderizado.
- **Correcao:** criar variavel `detailPreset` independente; filtros isolados por tab.

---

## 3. Plano de Implementacao (7 tarefas)

### TODO 1: migration-key-prefix
**Arquivos:** `migrations/versions/005_key_prefix.py` (NOVO), `app/models/api_key.py` (EDIT), `app/modules/Billing/api_key_service.py` (EDIT)

**Migration 005:**
```python
revision = "005"
down_revision = "004"

def upgrade():
    op.add_column("api_keys", sa.Column("key_prefix", sa.String(8), nullable=True))

def downgrade():
    op.drop_column("api_keys", "key_prefix")
```

**Model `app/models/api_key.py`** — adicionar apos `key_hash` (linha 16):
```python
key_prefix: Mapped[str | None] = mapped_column(String(8), nullable=True)
```

**Service `app/modules/Billing/api_key_service.py`** — em `create_api_key()`:
- Apos `raw_key = uuid.uuid4().hex` (linha 24), adicionar: `key_prefix = raw_key[:8]`
- No construtor APIKey (linha 27), adicionar: `key_prefix=key_prefix,`

---

### TODO 2: usage-all-tenants
**Arquivo:** `app/modules/Billing/usage_service.py` (EDIT)

Adicionar funcao `usage_all_tenants(db: AsyncSession, from_dt: datetime, to_dt: datetime) -> list[dict]`:
- Importar `Tenant` de `app.models.tenant`
- Query: `select(Tenant.id, Tenant.nome, Tenant.plano, func.count(distinct BillingRecord.request_id), func.sum(tokens_input), func.sum(tokens_output), func.sum(custo_total))`
- JOIN `BillingRecord.tenant_id == Tenant.id`
- WHERE `BillingRecord.created_at >= from_dt AND <= to_dt`
- GROUP BY `Tenant.id, Tenant.nome, Tenant.plano`
- Retorna dicts: `{tenant_id, nome, plano, validacoes, tokens_input, tokens_output, custo_total}`

---

### TODO 3: new-schemas
**Arquivo:** `app/schemas/billing.py` (EDIT)

**Alterar `APIKeyRead`** — adicionar campo:
```python
key_prefix: str | None = None
```

**Novos schemas:**
```python
class TenantCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    plano: str = Field("basico", max_length=100)
    email_contato: str = Field(..., min_length=1, max_length=255)

class TenantRead(BaseModel):
    id: str
    nome: str
    plano: str
    email_contato: str
    ativo: bool

class TenantUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=255)
    plano: str | None = Field(None, max_length=100)
    email_contato: str | None = Field(None, min_length=1, max_length=255)
    ativo: bool | None = None

class UsageByTenant(BaseModel):
    tenant_id: str
    nome: str
    plano: str
    validacoes: int
    tokens_input: int
    tokens_output: int
    custo_total: float

class QuotaUsageRow(BaseModel):
    id: str
    nome_cliente: str
    owner: str | None
    quota_diaria: int
    usado_hoje: int
    pct_usado: float

class AdminBillingSummary(BaseModel):
    tenant_id: str
    total_requests: int
    total_tokens_input: int
    total_tokens_output: int
    estimated_cost_brl: float
    period_from: datetime
    period_to: datetime

class AdminUsageSummaryResponse(BaseModel):
    period_from: datetime
    period_to: datetime
    by_provider: list[UsageByProvider]
    by_api_key: list[UsageByAPIKey]
```

---

### TODO 4: admin-billing-endpoints
**Arquivo:** `app/routers/admin_keys.py` (EDIT)

Adicionar 5 endpoints. Todos com `Depends(verify_admin_key)`:

**`GET /admin/billing/summary?tenant_id=...&from=...&to=...`**
- Mesma logica de `billing.py:35-47` mas sem auth por API Key
- Recebe `tenant_id` como query param, faz `uuid.UUID(tenant_id)`
- Query direta em `BillingRecord` com `tenant_id` fornecido
- Retorna `AdminBillingSummary`

**`GET /admin/billing/usage?tenant_id=...&from=...&to=...`**
- Chama `usage_by_provider(db, tenant_id, from_dt, to_dt)` e `usage_by_api_key(db, tenant_id, from_dt, to_dt)`
- Retorna `AdminUsageSummaryResponse`

**`GET /admin/billing/usage/detail?tenant_id=...&from=...&to=...&api_key_id=...`**
- Chama `usage_detail(db, tenant_id, from_dt, to_dt, api_key_id)`
- Retorna `list[UsageDetailRow]`

**`GET /admin/billing/usage/all-tenants?from=...&to=...`**
- Chama `usage_all_tenants(db, from_dt, to_dt)` (novo)
- Retorna `list[UsageByTenant]`

**`GET /admin/api-keys/quota-usage?tenant_id=...`**
- Para cada APIKey ativa do tenant:
  - Contar `ValidationRequest` com `created_at` entre inicio e fim do dia atual para aquela `api_key_id`
  - `pct_usado = (usado_hoje / quota_diaria) * 100`
- Retorna `list[QuotaUsageRow]`

---

### TODO 5: tenant-crud
**Arquivo:** `app/routers/admin_keys.py` (EDIT)

**`POST /admin/tenants`**
- Body: `TenantCreate`
- Cria `Tenant(nome=..., plano=..., email_contato=..., ativo=True)`
- Retorna `TenantRead`

**`PATCH /admin/tenants/{tenant_id}`**
- Body: `TenantUpdate`
- Busca tenant por UUID, atualiza campos nao-None
- Retorna `TenantRead`

---

### TODO 6: dashboard-rewrite
**Arquivo:** `app/static/dashboard.html` (REESCRITA COMPLETA)

Estrutura: 1 arquivo HTML/CSS/JS puro, sem frameworks, sem CDNs.

**5 tabs:**

| Tab | Quem ve | Descricao |
|-----|---------|-----------|
| Tenants | Admin | CRUD: tabela com nome, plano, email, ativo. Modal criar. Inline editar. Colunas ordenaveis |
| API Keys | Admin | CRUD keys. Corrigido dropdown (fetch antes). Coluna key_prefix. Coluna quota com barra CSS (verde <70%, amarelo 70-90%, vermelho >90%) |
| Consumo | Admin + Cliente | Admin: dropdown tenant + chama `/admin/billing/usage?tenant_id=...`. Cliente: chama `/billing/usage`. Cards, grafico barras, tabela por provider e key |
| Visao Geral | Admin | Cards totais. Tabela por tenant (nome, plano, validacoes, tokens, custo). Grafico barras top 10. Chama `/admin/billing/usage/all-tenants` |
| Detalhes | Admin + Cliente | Filtros isolados (detailPreset). Admin: chama `/admin/billing/usage/detail?tenant_id=...`. Cliente: chama `/billing/usage/detail` |

**Auth flow (sem mudanca):**
- Login com radio admin/cliente
- sessionStorage para persistir
- `authHeaders()` retorna header correto

**Bugs corrigidos no dashboard:**
1. Admin chama `/admin/billing/*` com `X-Admin-Key`, cliente chama `/billing/*` com `X-API-Key`
2. `renderKeys()` faz fetch de tenants antes de montar HTML
3. Variavel `detailPreset` independente de `usagePreset`

---

### TODO 7: run-migration
- Executar `alembic upgrade head` no diretorio do projeto

---

## 4. Regras do Projeto (Pedro)

- PT-BR por padrao
- Logs estruturados em toda funcao (inicio, ok, erro com extra)
- Nenhum `except: pass` ou `catch` vazio
- Pydantic para validar inputs
- RLS/multi-tenancy: checar tenant_id em toda query
- Nunca logar dados sensiveis em texto claro
- Nao criar arquivos sem necessidade; editar existente e o default
- TODO(Pedro): para incertezas, nunca inventar valores
