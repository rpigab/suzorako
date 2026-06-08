from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from suzorako.database import async_engine, get_db, metadata
from suzorako.routers import accounts, budget, imports, register, transactions
from suzorako.services.account_service import get_all_accounts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Créer les tables si elles n'existent pas (en complément d'Alembic)
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield


app = FastAPI(title="Suzorako", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="suzorako/static"), name="static")

templates = Jinja2Templates(directory="suzorako/templates")

app.include_router(accounts.router)
app.include_router(register.router)
app.include_router(transactions.router)
app.include_router(budget.router)
app.include_router(imports.router)


@app.get("/")
async def root():
    return RedirectResponse("/accounts")


# Endpoint pour ajouter dynamiquement une ventilation au formulaire de transaction.
@app.get("/transactions/split-row", response_class=HTMLResponse)
async def get_split_row(request: Request, idx: int = 0):
    async for db in get_db():
        all_accts = await get_all_accounts(db)
        break
    return templates.TemplateResponse(request, "partials/split_row.html", {
        "i": idx,
        "sp": None,
        "all_accounts": all_accts,
    })
