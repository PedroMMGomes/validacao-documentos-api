<p align="center">
  <img src="docs/readme-hero.png" alt="API de Validação de Documentos Médicos" width="100%">
</p>

<h1 align="center">🩺 API de Validação de Documentos Médicos</h1>
<p align="center"><strong>API REST multi-tenant (FastAPI) que valida laudos/documentos clínicos com LLM.</strong></p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-produção-22D3EE?style=flat-square">
  <img alt="stack" src="https://img.shields.io/badge/FastAPI-Python-009688?logo=fastapi&logoColor=white&style=flat-square">
  <img alt="db" src="https://img.shields.io/badge/Postgres%20%2B%20Alembic-migrations-4169E1?style=flat-square">
  <img alt="LLM" src="https://img.shields.io/badge/LLM-Gemini%20%7C%20Bedrock%20%7C%20Ollama-412991?style=flat-square">
  <img alt="deploy" src="https://img.shields.io/badge/deploy-Docker%20%2B%20Gunicorn-2496ED?logo=docker&logoColor=white&style=flat-square">
  <img alt="multi-tenant" src="https://img.shields.io/badge/arquitetura-multi--tenant%20%2B%20billing-F59E0B?style=flat-square">
</p>

---

## 🎯 O que é

Uma **API de produção** para validação de documentos médicos. Você envia um documento
(ex.: laudo em PDF), um **LLM** avalia contra regras e a API devolve um **veredito
estruturado** (válido + lista de issues). Multi-tenant, com **billing** e **métricas**.

> Complementa o [`glosador-contas-medicas`](https://github.com/PedroMMGomes/glosador-contas-medicas):
> o glosador audita a **conta** (TISS); esta API valida o **documento clínico** (laudo).

## 🚀 Início rápido

```bash
cp .env.example .env            # edite com suas chaves de API
docker compose up -d
docker compose exec app alembic upgrade head
```

API em `http://localhost:8000` · Docs (Swagger) em `http://localhost:8000/docs`.

## 🔌 Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | `/v1/validate` | Submete documento para validação |
| GET | `/v1/requests/{request_id}` | Consulta resultado da requisição |
| GET | `/v1/billing/summary?from=&to=` | Resumo de consumo do tenant |
| GET | `/health` | Health check |
| GET | `/metrics` | Métricas do serviço |

```bash
curl -X POST http://localhost:8000/v1/validate \
  -H "X-API-Key: sua-api-key" \
  -F "file=@laudo.pdf" \
  -F "document_type=laudo_medico"
```

## 🧠 Provedores LLM (rota selecionável)

- **Google Gemini** — `LLM_PROVIDER=gemini`
- **AWS Bedrock (Sonnet)** — `LLM_PROVIDER=bedrock`
- **Ollama (local)** — `LLM_PROVIDER=ollama`

## 🏗️ Arquitetura

```
app/
  core/            # config, segurança, dependências
  models/          # ORM (SQLAlchemy) — tenants, requisições, billing
  modules/
    llm/           # roteamento multi-provedor (Gemini/Bedrock/Ollama)
    Billing/       # contabilidade de consumo por tenant
  routers/         # endpoints (/v1/validate, /v1/requests, /v1/billing, /health, /metrics)
  schemas/         # Pydantic (request/response)
  static/          # assets
migrations/        # Alembic
tests/             # pytest
docker-compose.yml · Dockerfile · gunicorn.conf.py · alembic.ini
```

Stack: **FastAPI · SQLAlchemy · Alembic · Postgres · Docker · Gunicorn**.

## 🔒 Segurança e LGPD

- **Nenhum dado de paciente** neste repositório — só o código. `.gitignore` bloqueia
  `.env`, `storage/`, `artifacts/`, `*.xml`, laudos (`*_laudo*.pdf`).
- Autenticação por **`X-API-Key`** (multi-tenant, isolamento por tenant).
- Em produção, trate documentos e saídas conforme **LGPD**.

## 📚 Docs

- [`DOCs-API.md`](DOCs-API.md) — documentação detalhada da API
- [`Rules.md`](Rules.md) — regras de validação

---

<sub>Capa: OpenAI <code>gpt-image-2</code>.</sub>
