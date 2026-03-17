"""
WEEK25 — API REST (FastAPI + PostgreSQL Supabase)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncpg
from datetime import datetime
import random
import string
import os

app = FastAPI(title="WEEK25 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════
#  CONFIG SUPABASE
# ══════════════════════════════════════
DB_HOST     = os.getenv("DB_HOST",     "aws-1-eu-west-1.pooler.supabase.com")
DB_NAME     = os.getenv("DB_NAME",     "postgres")
DB_USER     = os.getenv("DB_USER",     "postgres.jlpmpxmcexaffpqjyxlz")
DB_PASSWORD = os.getenv("DB_PASSWORD", "tekojude2006@")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
NUMERO_PAIEMENT = "90548682"

# ══════════════════════════════════════
#  CONNEXION
# ══════════════════════════════════════
async def get_conn():
    return await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD, ssl="require"
    )

async def run(sql: str, params=None, fetch=True):
    conn = await get_conn()
    try:
        if fetch:
            rows = await conn.fetch(sql, *(params or []))
            return [dict(r) for r in rows]
        else:
            await conn.execute(sql, *(params or []))
    finally:
        await conn.close()

# ══════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════
async def generer_ticket(type_ticket: str) -> str:
    prefix = "SO" if type_ticket == "soiree" else "SW"
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    ticket = f"{prefix}2026{suffix}"
    existing = await run("SELECT numero_ticket FROM participants WHERE numero_ticket = $1", [ticket])
    return ticket if not existing else await generer_ticket(type_ticket)

def fmt(row: dict) -> dict:
    if not row:
        return row
    return {
        **row,
        "nom_complet":    f"{row.get('prenom','')} {row.get('nom','')}".strip(),
        "montant":        float(row.get("montant") or 0),
        "utilise":        bool(row.get("utilise", False)),
        "billet_utilise": bool(row.get("utilise", False)),
        "est_interne":    bool(row.get("est_interne", False)),
        "statut":         row.get("statut", "pending"),
        "created_at":     str(row.get("inscription_le") or ""),
        "inscription_le": str(row.get("inscription_le") or ""),
    }

def fmt_evenement(row: dict) -> dict:
    if not row:
        return row
    heure = str(row.get("heure_debut") or "")
    return {
        **row,
        "id":         str(row.get("id", "")),
        "date":       str(row.get("date_evt") or ""),
        "time":       heure[:5] if len(heure) >= 5 else heure,
        "title":      row.get("titre", ""),
        "desc":       row.get("description", "") or "",
        "cat":        row.get("categorie", "autre"),
        "lieu":       row.get("lieu", "") or "",
        "est_soiree": bool(row.get("est_soiree", False)),
    }

# ══════════════════════════════════════
#  SCHEMAS
# ══════════════════════════════════════
class InscriptionIn(BaseModel):
    # Champs envoyés par le HTML
    nom:              str
    prenom:           str
    telephone:        str
    email:            Optional[str]  = None
    origine:          str
    est_interne:      bool
    type_ticket:      str            = "semaine"
    evenement_id:     Optional[str]  = None   # soiree_id du HTML
    operateur:        str            = "Mix by Yas (Moov)"
    code_transaction: str
    montant:          float
    # Champs optionnels envoyés par le HTML (ignorés côté API)
    numero_ticket:    Optional[str]  = None
    soiree_id:        Optional[str]  = None
    soiree_titre:     Optional[str]  = None

class StatutUpdate(BaseModel):
    statut: str

class InscriptionUpdate(BaseModel):
    nom:              Optional[str]  = None
    prenom:           Optional[str]  = None
    telephone:        Optional[str]  = None
    email:            Optional[str]  = None
    origine:          Optional[str]  = None
    est_interne:      Optional[bool] = None
    operateur:        Optional[str]  = None
    code_transaction: Optional[str]  = None
    statut:           Optional[str]  = None

class EvenementIn(BaseModel):
    date_evt:    str
    heure_debut: str
    titre:       str
    description: Optional[str] = None
    categorie:   str           = "autre"
    lieu:        Optional[str] = None
    est_soiree:  bool          = False

class TarifsUpdate(BaseModel):
    semaine_interne: Optional[float] = None
    semaine_externe: Optional[float] = None
    soiree_interne:  Optional[float] = None
    soiree_externe:  Optional[float] = None

class CommentaireIn(BaseModel):
    evenement_id: str
    pseudo:       str = "Anonyme"
    contenu:      str

# ══════════════════════════════════════
#  ROOT
# ══════════════════════════════════════
@app.get("/")
def root():
    return {"app": "WEEK25 API", "status": "en ligne"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ══════════════════════════════════════
#  INSCRIPTIONS
# ══════════════════════════════════════
@app.get("/api/inscriptions")
async def get_inscriptions(
    statut:      Optional[str] = None,
    type_ticket: Optional[str] = None,
    recherche:   Optional[str] = None,
    limit:       int = 500,
):
    sql = """
        SELECT p.*, e.titre AS soiree_titre
        FROM participants p
        LEFT JOIN evenements e ON e.id::text = p.evenement_id
        WHERE 1=1
    """
    conditions, params = [], []
    i = 1
    if statut:
        conditions.append(f"AND p.statut = ${i}"); params.append(statut); i += 1
    if type_ticket:
        conditions.append(f"AND p.type_ticket = ${i}"); params.append(type_ticket); i += 1
    if recherche:
        q = f"%{recherche}%"
        conditions.append(f"AND (p.nom ILIKE ${i} OR p.prenom ILIKE ${i+1} OR p.numero_ticket ILIKE ${i+2})")
        params.extend([q, q, q]); i += 3
    sql += " ".join(conditions) + f" ORDER BY p.inscription_le DESC LIMIT {limit}"
    rows = await run(sql, params)
    return [fmt(r) for r in rows]


@app.get("/api/inscriptions/export/csv")
async def export_csv(statut: Optional[str] = None):
    from fastapi.responses import StreamingResponse
    import csv, io
    sql = "SELECT * FROM participants ORDER BY inscription_le DESC"
    params = []
    if statut:
        sql = "SELECT * FROM participants WHERE statut = $1 ORDER BY inscription_le DESC"
        params = [statut]
    rows = await run(sql, params)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticket","Type","Nom","Prénom","École","Origine","Tél","Email","Montant","Transaction","Opérateur","Statut","Utilisé","Date"])
    for r in rows:
        writer.writerow([r.get("numero_ticket",""),r.get("type_ticket",""),r.get("nom",""),r.get("prenom",""),"Oui" if r.get("est_interne") else "Non",r.get("origine",""),r.get("telephone",""),r.get("email",""),r.get("montant",""),r.get("code_transaction",""),r.get("operateur",""),r.get("statut",""),"Oui" if r.get("utilise") else "Non",str(r.get("inscription_le",""))[:10]])
    output.seek(0)
    return StreamingResponse(iter(["\ufeff" + output.getvalue()]),media_type="text/csv",headers={"Content-Disposition": f'attachment; filename="inscriptions-week25-{datetime.now().strftime("%Y%m%d")}.csv"'})


@app.get("/api/inscriptions/{numero_ticket}")
async def get_inscription(numero_ticket: str):
    rows = await run("SELECT p.*, e.titre AS soiree_titre FROM participants p LEFT JOIN evenements e ON e.id::text = p.evenement_id WHERE p.numero_ticket = $1",[numero_ticket.upper()])
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt(rows[0])


@app.post("/api/inscriptions", status_code=201)
async def creer_inscription(body: InscriptionIn):
    # Utilise soiree_id si evenement_id absent
    evt_id = body.evenement_id or body.soiree_id or None
    ticket = await generer_ticket(body.type_ticket)
    await run(
        """INSERT INTO participants
            (numero_ticket, nom, prenom, telephone, email, origine,
             est_interne, type_ticket, evenement_id, operateur,
             code_transaction, montant, statut, utilise)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'pending',FALSE)""",
        [ticket, body.nom.strip(), body.prenom.strip(),
         body.telephone.strip(), body.email or None,
         body.origine.strip(), body.est_interne,
         body.type_ticket, evt_id,
         body.operateur, body.code_transaction.strip(), body.montant],
        fetch=False
    )
    rows = await run("SELECT * FROM participants WHERE numero_ticket = $1", [ticket])
    return fmt(rows[0])


@app.patch("/api/inscriptions/{numero_ticket}/statut")
async def changer_statut(numero_ticket: str, body: StatutUpdate):
    if body.statut not in ("pending", "confirmed", "rejected"):
        raise HTTPException(400, "Statut invalide")
    now = datetime.now()
    # Remplit statut_modifie_par_admin + valide_par_admin si confirmed
    if body.statut == "confirmed":
        await run(
            """UPDATE participants
               SET statut = $1,
                   statut_modifie_par_admin = $2,
                   valide_par_admin = $3
               WHERE numero_ticket = $4""",
            [body.statut, str(now), str(now), numero_ticket.upper()],
            fetch=False
        )
    else:
        await run(
            """UPDATE participants
               SET statut = $1,
                   statut_modifie_par_admin = $2
               WHERE numero_ticket = $3""",
            [body.statut, str(now), numero_ticket.upper()],
            fetch=False
        )
    rows = await run("SELECT * FROM participants WHERE numero_ticket = $1", [numero_ticket.upper()])
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt(rows[0])


@app.patch("/api/inscriptions/{numero_ticket}")
async def modifier_inscription(numero_ticket: str, body: InscriptionUpdate):
    champs = {k: v for k, v in body.model_dump().items() if v is not None}
    if not champs:
        raise HTTPException(400, "Aucun champ à modifier")
    sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(champs))
    vals = list(champs.values()) + [numero_ticket.upper()]
    await run(f"UPDATE participants SET {sets} WHERE numero_ticket = ${len(vals)}", vals, fetch=False)
    rows = await run("SELECT * FROM participants WHERE numero_ticket = $1", [numero_ticket.upper()])
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt(rows[0])


@app.delete("/api/inscriptions/{numero_ticket}")
async def supprimer_inscription(numero_ticket: str):
    await run("DELETE FROM participants WHERE numero_ticket = $1", [numero_ticket.upper()], fetch=False)
    return {"success": True}

# ══════════════════════════════════════
#  VALIDATION
# ══════════════════════════════════════
@app.post("/api/validation/entree")
async def valider_entree(numero_ticket: str):
    rows = await run("SELECT * FROM participants WHERE numero_ticket = $1", [numero_ticket.upper()])
    if not rows:
        return {"succes": False, "code": "NOT_FOUND", "message": "Ticket introuvable"}
    p = rows[0]
    if p["statut"] == "rejected":
        return {"succes": False, "code": "REJECTED", "message": "Ticket refusé"}
    if p["statut"] == "pending":
        return {"succes": False, "code": "PENDING", "message": "Paiement non confirmé"}
    if p["utilise"]:
        return {"succes": False, "code": "ALREADY_USED", "message": "Ticket déjà utilisé"}
    now = datetime.now()
    await run(
        """UPDATE participants
           SET utilise = TRUE,
               utilise_le = $1
           WHERE numero_ticket = $2""",
        [now, numero_ticket.upper()], fetch=False
    )
    return {"succes": True, "code": "OK", "message": "Entrée validée", "nom": f"{p.get('prenom','')} {p.get('nom','')}".strip(), "ticket": p["numero_ticket"], "type": p["type_ticket"], "montant": float(p.get("montant") or 0)}


@app.get("/api/validation/ticket/{numero_ticket}")
async def verifier_ticket(numero_ticket: str):
    rows = await run("SELECT * FROM participants WHERE numero_ticket = $1", [numero_ticket.upper()])
    if not rows:
        return {"found": False}
    d = rows[0]
    return {"found": True, "numero_ticket": d.get("numero_ticket"), "nom_complet": f"{d.get('prenom','')} {d.get('nom','')}".strip(), "type_ticket": d.get("type_ticket"), "statut": d.get("statut"), "utilise": d.get("utilise"), "montant": float(d.get("montant") or 0)}


@app.get("/api/validation/recherche")
async def rechercher_par_nom(q: str):
    if len(q) < 2:
        raise HTTPException(400, "Tape au moins 2 caractères")
    terme = f"%{q}%"
    rows = await run("SELECT numero_ticket, nom, prenom, statut, type_ticket, utilise FROM participants WHERE nom ILIKE $1 OR prenom ILIKE $2 ORDER BY nom LIMIT 20",[terme, terme])
    for r in rows:
        r["nom_complet"] = f"{r.get('prenom','')} {r.get('nom','')}".strip()
    return {"total": len(rows), "items": rows}

# ══════════════════════════════════════
#  ÉVÉNEMENTS
# ══════════════════════════════════════
@app.get("/api/evenements")
async def get_evenements(date: Optional[str] = None, categorie: Optional[str] = None):
    sql = "SELECT * FROM evenements WHERE actif = TRUE"
    params, i = [], 1
    if date:
        sql += f" AND date_evt = ${i}"; params.append(date); i += 1
    if categorie:
        sql += f" AND categorie = ${i}"; params.append(categorie); i += 1
    sql += " ORDER BY date_evt, heure_debut"
    rows = await run(sql, params)
    return [fmt_evenement(r) for r in rows]


@app.get("/api/evenements/soirees")
async def get_soirees():
    rows = await run("SELECT * FROM evenements WHERE actif = TRUE AND est_soiree = TRUE ORDER BY date_evt, heure_debut", [])
    return [fmt_evenement(r) for r in rows]


@app.get("/api/evenements/{evenement_id}")
async def get_evenement(evenement_id: str):
    rows = await run("SELECT * FROM evenements WHERE id::text = $1", [evenement_id])
    if not rows:
        raise HTTPException(404, "Événement introuvable")
    return fmt_evenement(rows[0])


@app.post("/api/evenements", status_code=201)
async def creer_evenement(body: EvenementIn):
    heure = body.heure_debut + ":00" if len(body.heure_debut) == 5 else body.heure_debut
    await run("INSERT INTO evenements (date_evt, heure_debut, titre, description, categorie, lieu, est_soiree, actif) VALUES ($1,$2,$3,$4,$5,$6,$7,TRUE)",[body.date_evt, heure, body.titre, body.description, body.categorie, body.lieu or "", body.est_soiree or body.categorie == "soiree"],fetch=False)
    rows = await run("SELECT * FROM evenements WHERE titre = $1 ORDER BY cree_le DESC LIMIT 1", [body.titre])
    return fmt_evenement(rows[0]) if rows else {"success": True}


@app.delete("/api/evenements/{evenement_id}")
async def supprimer_evenement(evenement_id: str):
    await run("UPDATE evenements SET actif = FALSE WHERE id::text = $1", [evenement_id], fetch=False)
    return {"success": True}

# ══════════════════════════════════════
#  TARIFS
# ══════════════════════════════════════
@app.get("/api/tarifs")
async def get_tarifs():
    rows = await run("SELECT type_ticket, profil, montant FROM tarifs WHERE actif = TRUE", [])
    result = {"semaine_interne": 2500, "semaine_externe": 5000, "soiree_interne": 1500, "soiree_externe": 3000}
    for r in rows:
        result[f"{r['type_ticket']}_{r['profil']}"] = float(r["montant"])
    return result


@app.patch("/api/tarifs")
async def update_tarifs(body: TarifsUpdate):
    mapping = {"semaine_interne": ("semaine","interne"), "semaine_externe": ("semaine","externe"), "soiree_interne": ("soiree","interne"), "soiree_externe": ("soiree","externe")}
    for attr, montant in {k: v for k, v in body.model_dump().items() if v is not None}.items():
        t, p = mapping[attr]
        await run("UPDATE tarifs SET montant = $1 WHERE type_ticket = $2 AND profil = $3", [montant, t, p], fetch=False)
    return await get_tarifs()


@app.get("/api/tarifs/ussd")
def get_ussd(montant: float = 2500):
    n = NUMERO_PAIEMENT
    return [{"operateur": "Mix by Yas (Moov)", "code": f"*145*1*{int(montant)}*{n}#"},{"operateur": "Flooz (Togocel)", "code": f"*155*1*{int(montant)}*{n}#"}]

# ══════════════════════════════════════
#  COMMENTAIRES
# ══════════════════════════════════════
@app.get("/api/commentaires/{evenement_id}")
async def get_commentaires(evenement_id: str):
    rows = await run("SELECT id, pseudo, contenu, cree_le FROM commentaires WHERE evenement_id = $1 AND approuve = TRUE ORDER BY cree_le DESC LIMIT 50",[evenement_id])
    for r in rows:
        r["cree_le"] = str(r.get("cree_le") or "")
    return rows


@app.post("/api/commentaires", status_code=201)
async def publier_commentaire(body: CommentaireIn):
    if not body.contenu.strip():
        raise HTTPException(400, "Commentaire vide")
    await run("INSERT INTO commentaires (evenement_id, pseudo, contenu) VALUES ($1,$2,$3)",[body.evenement_id, body.pseudo.strip() or "Anonyme", body.contenu.strip()],fetch=False)
    return {"success": True}

# ══════════════════════════════════════
#  GALERIE
# ══════════════════════════════════════
@app.get("/api/galerie")
async def get_photos():
    rows = await run("SELECT id, url, legende, cree_le FROM photos WHERE approuve = TRUE ORDER BY cree_le DESC LIMIT 100", [])
    for r in rows:
        r["cree_le"] = str(r.get("cree_le") or "")
    return rows

# ══════════════════════════════════════
#  STATISTIQUES
# ══════════════════════════════════════
@app.get("/api/stats/dashboard")
async def get_dashboard():
    rows = await run("SELECT * FROM v_dashboard", [])
    if not rows:
        return {}
    d = rows[0]
    return {"total_inscrits": int(d.get("total_inscrits") or 0),"en_attente": int(d.get("en_attente") or 0),"confirmes": int(d.get("confirmes") or 0),"refuses": int(d.get("refuses") or 0),"entrees_validees": int(d.get("entrees_validees") or 0),"revenus_confirmes": float(d.get("revenus_confirmes") or 0),"inscrits_aujourdhui": int(d.get("inscrits_aujourdhui") or 0)}


@app.get("/api/stats/operateurs")
async def get_stats_operateurs():
    rows = await run("SELECT * FROM v_stats_operateurs", [])
    return [{"operateur": r.get("operateur",""), "nb_inscriptions": int(r.get("nb_inscriptions") or 0), "confirmes": int(r.get("confirmes") or 0), "revenus": float(r.get("revenus") or 0)} for r in rows]


@app.get("/api/stats/par-jour")
async def get_stats_par_jour():
    rows = await run("SELECT * FROM v_inscriptions_par_jour", [])
    return [{"jour": str(r.get("jour","")), "total": int(r.get("total") or 0), "confirmes": int(r.get("confirmes") or 0), "revenus": float(r.get("revenus") or 0)} for r in rows]

# ══════════════════════════════════════
#  ENTRÉE
# ══════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
