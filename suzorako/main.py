from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from suzorako.database import async_engine, metadata
from suzorako.routers import accounts, budget, imports, register, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Créer les tables si elles n'existent pas (en complément d'Alembic)
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield


app = FastAPI(title="Suzorako", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="suzorako/static"), name="static")

templates = Jinja2Templates(directory="suzorako/templates")

# Filtre Jinja2 utilitaire
def do_enumerate(iterable):
    return enumerate(iterable)

def do_any(iterable):
    return any(iterable)

templates.env.filters["enumerate"] = do_enumerate
templates.env.globals["any"] = do_any
templates.env.globals["today"] = lambda: date.today().isoformat()

# Injecter today dans tous les templates
@app.middleware("http")
async def inject_today(request: Request, call_next):
    response = await call_next(request)
    return response


app.include_router(accounts.router)
app.include_router(register.router)
app.include_router(transactions.router)
app.include_router(budget.router)
app.include_router(imports.router)


@app.get("/")
async def root():
    return RedirectResponse("/accounts")


# Endpoint pour ajouter dynamiquement un split au formulaire
@app.get("/transactions/split-row")
async def get_split_row(request: Request, idx: int = 0):
    from fastapi.responses import HTMLResponse
    all_accts_result = []
    # On utilise une session DB rapide
    from suzorako.database import get_db
    async for db in get_db():
        from suzorako.services.account_service import get_all_accounts
        all_accts_result = await get_all_accounts(db)
        break
    return templates.TemplateResponse(request, "partials/split_row.html", {
        "i": idx,
        "sp": None,
        "all_accounts": all_accts_result,
        "prefill_account_id": None,
    })
