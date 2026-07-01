# Pedro — Rules Consolidadas

> Arquivo único de referência. Para uso no Cursor (`alwaysApply: true`) e no KIRO (`.kiro/steering/pedro-rules.md`).

---

## 1. Tom e comunicação

- PT-BR por padrão; EN só se Pedro iniciar em EN ou pedir explicitamente
- Direto, sem enrolação — foco em execução, não em explicações pedagógicas
- Sem emojis, sem comentários óbvios no código
- Nunca narrar o que o código faz em comentários — comentar apenas intenção não-óbvia, trade-offs ou constraints

---

## 2. Protocolo obrigatório antes de qualquer implementação

Antes de escrever **qualquer** linha de código, produzir obrigatoriamente:

```
PRÉ-EXECUÇÃO
─────────────────
Arquivos a tocar:  <path + motivo por arquivo>
Arquitetura:       <descrição ou diagrama da solução>
Testes previstos:  <casos de teste e fixtures necessárias>
Riscos:            <multi-tenancy, breaking changes, deps externas>
─────────────────
Aguardando confirmação para executar.
```

Só prosseguir após confirmação explícita de Pedro.

---

## 3. Cirurgia mínima — PRIORIDADE ABSOLUTA em projetos em andamento

- **Regra de ouro:** modificar o mínimo de arquivos e linhas que entregue o resultado com segurança total
- Antes de criar arquivo → verificar se existe um existente que pode ser estendido
- Antes de adicionar dependência → verificar se já há lib equivalente em `requirements.txt`
- Antes de refatorar → confirmar se refatoração foi explicitamente solicitada
- Se a mudança tocar mais de 5 arquivos não relacionados → questionar escopo antes de continuar
- Nunca aproveitar o contexto de uma task para "melhorar" código não relacionado ao pedido

---

## 4. Stack

| Camada | Tecnologia | Restrições |
|--------|-----------|------------|
| Backend | Python · FastAPI | Sempre async; nunca Flask/Django sem pedido explícito |
| Banco | PostgreSQL + asyncpg | Driver sempre asyncpg, nunca psycopg2 síncrono |
| ORM | SQLAlchemy async | Nunca `Base.metadata.create_all()` em produção |
| Migrations | Alembic | Toda alteração de schema via migration, inclusive `CREATE EXTENSION` |
| Config | Pydantic Settings | Nunca `os.getenv()` direto no código |
| Validação | Pydantic v2 | Validar inputs antes de qualquer operação de escrita |
| LLM | Factory pattern | Nunca instanciar provider diretamente; multi-provider via abstração |
| Vetorial / RAG | pgvector (Postgres) | Saturar o que o Postgres oferece antes de introduzir Pinecone, Qdrant, etc. |
| Testes | pytest + pytest-asyncio | `asyncio_mode = auto` em `pyproject.toml` |

### Estrutura de módulos obrigatória

```
routers/    → entrada HTTP, validação de schema, zero lógica de negócio
schemas/    → Pydantic models de request/response
modules/    → lógica de negócio e orquestração
models/     → SQLAlchemy ORM models
core/       → logging, exceptions, middlewares transversais
```

### Async — regras inegociáveis

- Todo I/O é `async def` + `await` — sem exceção
- Nunca chamar operação blocking (requests síncrono, `open()` sem `aiofiles`, sleep) dentro de coroutine
- Queries ao banco sempre via sessão async do SQLAlchemy

---

## 5. Padrões de código

### Logging estruturado — obrigatório em toda função de I/O ou negócio

```python
import logging
logger = logging.getLogger(__name__)

async def processar_documento(doc_id: str, tenant_id: str) -> dict:
    logger.info("processar_documento | inicio", extra={"doc_id": doc_id, "tenant_id": tenant_id})
    try:
        resultado = await _fazer_algo(doc_id)
        logger.info("processar_documento | ok", extra={"doc_id": doc_id, "status": resultado.get("status")})
        return resultado
    except Exception as e:
        logger.error("processar_documento | erro", extra={"doc_id": doc_id, "error": str(e)})
        raise
```

**Regras do `extra={}`:**
- Apenas campos escalares: IDs, status codes, contagens, booleanos
- Nunca logar dicts/listas grandes (payload de LLM, body de request completo)
- Nunca logar dados sensíveis: tokens, senhas, PII em texto claro

### Tratamento de erros

```python
# CORRETO
except Exception as e:
    logger.error("funcao | erro", extra={"error": str(e)})
    raise

# ERRADO — nunca
except:
    pass
```

### Incertezas

Marcar com `TODO(Pedro):` — nunca inventar valores, endpoints ou comportamentos não confirmados.

---

## 6. Segurança e multi-tenancy

- **Toda query filtra `tenant_id` no WHERE** — sem exceção
- Validação de `tenant_id` ocorre no layer de auth, antes de qualquer módulo de negócio
- `tenant_id` é parâmetro obrigatório em toda função que toca o banco — nunca opcional
- Nunca expor dados de tenant A para tenant B — RLS no Postgres como segunda linha de defesa
- Env vars para todos os segredos — nunca hardcode

---

## 7. Testes

- `pytest` + `pytest-asyncio` com `asyncio_mode = auto`
- Fixtures em `conftest.py` — nunca estado global nos testes
- Testes unitários: mocks de LLM, storage e banco
- Testes de integração: DB de teste isolado, nunca o banco de produção/dev compartilhado
- Nomear testes como `test_<modulo>_<cenario>_<resultado_esperado>`

---

## 8. Architecture Guardrail — Score automático

### Quando rodar

- Projeto ou serviço novo proposto
- Feature que altera significativamente um domínio
- Novo arquivo proposto em `routers/` ou `modules/`
- Qualquer proposta de novo serviço/container/processo separado
- Pedro perguntar "como devo estruturar isso?" ou similar

### Score — 7 dimensões (0–2 pts cada, total 0–14)

| # | Dimensão | 0 pts | 1 pt | 2 pts |
|---|---|---|---|---|
| 1 | Ownership do domínio | Um dev/time dono de tudo | Times diferentes compartilham partes | Times completamente separados com SLAs distintos |
| 2 | Estabilidade do contrato | Schema/API muda toda semana | Muda mensalmente | Estável ≥ 2 meses com versionamento |
| 3 | Escala diferenciada | Tudo escala junto | Uma parte escala 2–5x mais | Partes com ordens de magnitude distintas de carga |
| 4 | Ciclo de deploy independente | Deploy sempre junto | Pode ser separado mas raramente é | Deploy independente necessário para não bloquear |
| 5 | Isolamento de falha | Falha pode propagar livremente | Algumas partes precisam de isolamento | Falha em X não pode derrubar Y |
| 6 | Complexidade operacional disponível | Solo dev, sem infra dedicada | Time pequeno, infra básica | DevOps presente, logs/tracing/alertas já existem |
| 7 | Latência tolerável entre componentes | < 5ms necessário | < 50ms OK | Pode ser assíncrono / eventual |

### Interpretação

- **0–4 → Monolito Modular** — Um repo, módulos com interfaces claras, deploy único, DB único
- **5–8 → Monolito + Workers Async** — Core monolítico; tarefas pesadas extraídas como workers, mesmo repo
- **9–11 → Macroserviços** — 2–4 serviços com fronteiras de domínio reais, cada um com seu DB
- **12–14 → Micro-serviços** — Apenas quando infra, time e operação suportam o overhead

### Escada de desacoplamento — NUNCA pular etapas

```
Módulo bem definido (mesmo arquivo/pasta)
 → Worker / task assíncrono (mesmo repo, processo separado)
   → Serviço separado com contrato explícito e DB próprio
     → Micro-serviço com infra e observabilidade dedicadas
```

### Anti-patterns — bloquear ativamente

- **Shared DB entre serviços** → monolito distribuído disfarçado
- **HTTP síncrono entre serviços sem timeout + circuit-breaker** → cascading failure garantido
- **Novo repo/serviço porque o módulo ficou grande** → tamanho não é critério de separação
- **Separar antes do contrato estabilizar** → reescrever duas vezes com complexidade distribuída
- **Micro-serviço sem logs/tracing/health check** → caixa-preta irrastreável

### Formato de resposta obrigatório

```
ARQUITETURA SCORE
─────────────────
[1] Ownership:        X/2 — <justificativa 1 linha>
[2] Estabilidade:     X/2 — <justificativa 1 linha>
[3] Escala:           X/2 — <justificativa 1 linha>
[4] Deploy indep.:    X/2 — <justificativa 1 linha>
[5] Isolamento falha: X/2 — <justificativa 1 linha>
[6] Complexidade ops: X/2 — <justificativa 1 linha>
[7] Latência:         X/2 — <justificativa 1 linha>
─────────────────
TOTAL: XX/14 → [PADRÃO RECOMENDADO]

DECISÃO: <1 parágrafo — por que esse padrão, e o que NÃO fazer>
PRÓXIMO PASSO: <ação concreta>
```

---

## 9. Compatibilidade com KIRO

Este arquivo funciona diretamente como Steering Document no KIRO.

Copiar para `.kiro/steering/pedro-rules.md` no repositório alvo — KIRO injeta automaticamente em todas as sessões de agente do projeto.
