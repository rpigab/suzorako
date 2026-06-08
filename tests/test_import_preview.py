"""Garde-fou : la prévisualisation d'import doit se rendre sans erreur.

Régression historique : le template utilisait un filtre Jinja `enumerate`
enregistré sur une seule instance `Jinja2Templates`, absent de celle du
router d'import → 500. Le template n'utilise plus que `loop.index0`.
"""

from fastapi.templating import Jinja2Templates


def render_preview(**context) -> str:
    templates = Jinja2Templates(directory="suzorako/templates")
    return templates.env.get_template("partials/import_preview.html").render(**context)


def _sample_preview():
    return [
        {
            "post_date": "2026-06-01",
            "description": "Salaire",
            "notes": "",
            "is_duplicate": False,
            "splits": [
                {"account_id": 1, "account_name": "Compte Chèque", "value_num": 200000, "value_denom": 100, "memo": ""},
                {"account_id": None, "account_name": "Revenus:Salaire", "value_num": -200000, "value_denom": 100, "memo": ""},
            ],
        }
    ]


def test_import_preview_renders():
    html = render_preview(
        preview=_sample_preview(),
        import_id="abc123",
        all_accounts=[{"id": 1, "name": "Compte Chèque"}],
        source="csv",
    )
    assert "Salaire" in html
    assert "1 transaction(s) trouvée(s)" in html
    # Les noms de champs encodent les indices ventilation (ex-filtre enumerate).
    assert "account_abc123_0_0" in html
    assert "account_abc123_0_1" in html


def test_import_preview_empty():
    html = render_preview(preview=[], import_id="x", all_accounts=[], source="csv")
    assert "Aucune transaction" in html
