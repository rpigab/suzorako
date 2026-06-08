# Suzorako

Application web de comptabilité personnelle en partie double, alternative moderne à GnuCash.

## Stack

- **Backend** : Python 3.12 + FastAPI + SQLAlchemy Core (pas l'ORM) + Alembic
- **Base de données** : SQLite (`suzorako.db`)
- **Templates** : Jinja2 (server-side rendering)
- **Frontend** : HTMX 2.x (vendored) — pas de SPA, pas de framework JS
- **CSS** : Pico.css (classless) + `suzorako/static/css/style.css`
- **Charts** : D3.js v7 (vendored, uniquement sur `/budget`)
- **Gestionnaire de paquets** : uv

## Lancer l'application

```bash
uv run uvicorn suzorako.main:app --reload
```

Ouvre http://localhost:8000

## Migrations

```bash
uv run alembic upgrade head                         # appliquer
uv run alembic revision --autogenerate -m "nom"     # générer après modif schema
```

## Tests

```bash
uv run pytest
```

## Structure

```
suzorako/
├── main.py               # App FastAPI, lifespan, montage routes
├── config.py             # Paramètres (pydantic-settings, .env)
├── database.py           # Tables SQLAlchemy Core + engines async/sync
├── utils/money.py        # to_decimal / from_decimal (jamais float)
├── services/             # Logique métier pure (pas de HTTP ici)
│   ├── account_service.py
│   ├── transaction_service.py
│   ├── budget_service.py
│   ├── import_csv.py
│   └── import_ofx.py
├── routers/              # Routes FastAPI (accounts, register, transactions, budget, imports)
├── templates/            # Jinja2 — base.html + partials/ pour fragments HTMX
└── static/               # htmx.min.js, d3.min.js, pico.min.css, style.css
```

## Conventions

- **Arithmétique monétaire** : toujours `decimal.Decimal`, jamais `float`. Les montants sont stockés en paires entières `(value_num, value_denom)` comme GnuCash. Utiliser `suzorako/utils/money.py`.
- **Templates** : API Starlette 1.x — `templates.TemplateResponse(request, "name.html", context_dict)` (le `request` est le 1er argument, pas dans le dict).
- **HTMX partials** : les endpoints qui retournent des fragments HTML vérifient `request.headers.get("HX-Request")` si besoin. Les POST réussis font soit un swap fragment, soit un `HX-Redirect`.
- **Schéma** : miroir GnuCash, pas d'innovation — 5 types de comptes : `ASSET`, `LIABILITY`, `INCOME`, `EXPENSE`, `EQUITY`.
- **Mobile-first** : cibles tactiles ≥ 44px, layout colonne unique sur mobile.
