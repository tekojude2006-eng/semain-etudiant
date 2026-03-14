"""
WEEK25 — API REST (FastAPI + PostgreSQL Supabase)
=================================================
Semaine Étudiante 2026
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
import psycopg2.extras
from datetime import datetime
import random
import string
import os

app = FastAPI(title="WEEK25 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════
#  ⚙️  CONFIGURATION SUPABASE
# ════════════════════════════════════════════════

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "aws-1-eu-west-1.pooler.supabase.com"),
    "database": os.getenv("DB_NAME",     "postgres"),
    "user":     os.getenv("DB_USER",     "postgres.jlpmpxmcexaffpqjyxlz"),
    "password": os.getenv("DB_PASSWORD", "tekojude2006@"),
    "port":     os.getenv("DB_PORT",     "5432"),
    "sslmode":  "require",
}

NUMERO_PAIEMENT = "90548682"


# ════════════════════════════════════════════════
#  CONNEXION
# ════════════════════════════════════════════════

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def run(sql: str, params=None, fetch=True):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        if fetch:
            rows = cur.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        else:
            conn.commit()
            conn.close()
            return None
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e


# ════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════

def generer_ticket(type_ticket: str) -> str:
    prefix = "SO" if type_ticket == "soiree" else "SW"
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    ticket = f"{prefix}2026{suffix}"
    existing = run("SELECT numero_ticket FROM participants WHERE numero_ticket = %s", (ticket,))
    if existing:
        return generer_ticket(type_ticket)
    return ticket

def fmt_participant(row: dict) -> dict:
    if not row:
        return row
    return {
        **row,
        "nom_complet":    f"{row.get('prenom','')} {row.get('nom','')}".strip(),
        "montant":        float(row.get("montant") or 0),
        "utilise":        bool(row.get("utilise", False)),
        "est_interne":    bool(row.get("est_interne", False)),
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
        "desc":        row.get("description", "") or "",
        "cat":         row.get("categorie", "autre"),
        "lieu":        row.get("lieu", "") or "",
        "est_soiree":  bool(row.get("est_soiree", False)),
    }


# ════════════════════════════════════════════════
#  SCHEMAS PYDANTIC
# ════════════════════════════════════════════════

class InscriptionIn(BaseModel):
    nom:              str
    prenom:           str
    telephone:        str
    email:            Optional[str]  = None
    origine:          str
    est_interne:      bool
    type_ticket:      str            = "semaine"
    evenement_id:     Optional[str]  = None
    operateur:        str            = "Mix by Yas (Moov)"
    code_transaction: str
    montant:          float

class StatutUpdate(BaseModel):
    statut: str

class InscriptionUpdate(BaseModel):
    nom:              Optional[str]   = None
    prenom:           Optional[str]   = None
    telephone:        Optional[str]   = None
    email:            Optional[str]   = None
    origine:          Optional[str]   = None
    est_interne:      Optional[bool]  = None
    operateur:        Optional[str]   = None
    code_transaction: Optional[str]   = None
    statut:           Optional[str]   = None
    notes_admin:      Optional[str]   = None

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


# ════════════════════════════════════════════════
#  ROOT
# ════════════════════════════════════════════════

@app.get("/")
def root():
    return {"app": "WEEK25 API", "status": "en ligne"}

@app.get("/health")
def health():
    return {"status": "ok"}


# ════════════════════════════════════════════════
#  INSCRIPTIONS
# ════════════════════════════════════════════════

@app.get("/api/inscriptions")
def get_inscriptions(
    statut:      Optional[str] = None,
    type_ticket: Optional[str] = None,
    recherche:   Optional[str] = None,
):
    sql = """
        SELECT p.*, e.titre AS soiree_titre
        FROM participants p
        LEFT JOIN evenements e ON e.id = p.evenement_id::uuid
        WHERE 1=1
    """
    params = []
    if statut:
        sql += " AND p.statut = %s"
        params.append(statut)
    if type_ticket:
        sql += " AND p.type_ticket = %s"
        params.append(type_ticket)
    if recherche:
        sql += " AND (p.nom ILIKE %s OR p.prenom ILIKE %s OR p.numero_ticket ILIKE %s OR p.telephone ILIKE %s)"
        q = f"%{recherche}%"
        params.extend([q, q, q, q])
    sql += " ORDER BY p.inscription_le DESC"
    rows = run(sql, params)
    return [fmt_participant(r) for r in rows]


@app.get("/api/inscriptions/export/csv")
def export_csv(statut: Optional[str] = None):
    from fastapi.responses import StreamingResponse
    import csv, io
    sql = "SELECT * FROM participants ORDER BY inscription_le DESC"
    params = None
    if statut:
        sql = "SELECT * FROM participants WHERE statut = %s ORDER BY inscription_le DESC"
        params = (statut,)
    rows = run(sql, params)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticket","Type","Nom","Prénom","École","Origine","Tél","Email","Montant","Transaction","Opérateur","Statut","Utilisé","Date"])
    for r in rows:
        writer.writerow([
            r.get("numero_ticket",""), r.get("type_ticket",""),
            r.get("nom",""), r.get("prenom",""),
            "Oui" if r.get("est_interne") else "Non",
            r.get("origine",""), r.get("telephone",""), r.get("email",""),
            r.get("montant",""), r.get("code_transaction",""), r.get("operateur",""),
            r.get("statut",""), "Oui" if r.get("utilise") else "Non",
            str(r.get("inscription_le",""))[:10],
        ])
    output.seek(0)
    filename = f"inscriptions-week25-{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter(["\ufeff" + output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/inscriptions/{numero_ticket}")
def get_inscription(numero_ticket: str):
    rows = run(
        "SELECT p.*, e.titre AS soiree_titre FROM participants p "
        "LEFT JOIN evenements e ON e.id = p.evenement_id::uuid "
        "WHERE p.numero_ticket = %s",
        (numero_ticket.upper(),)
    )
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt_participant(rows[0])


@app.post("/api/inscriptions", status_code=201)
def creer_inscription(body: InscriptionIn):
    ticket = generer_ticket(body.type_ticket)
    run(
        """
        INSERT INTO participants
            (numero_ticket, nom, prenom, telephone, email, origine,
             est_interne, type_ticket, evenement_id, operateur,
             code_transaction, montant, statut, utilise)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',FALSE)
        """,
        (
            ticket, body.nom.strip(), body.prenom.strip(),
            body.telephone.strip(), body.email or None,
            body.origine.strip(), body.est_interne,
            body.type_ticket, body.evenement_id or None,
            body.operateur, body.code_transaction.strip(), body.montant,
        ),
        fetch=False
    )
    rows = run("SELECT * FROM participants WHERE numero_ticket = %s", (ticket,))
    return fmt_participant(rows[0])


@app.patch("/api/inscriptions/{numero_ticket}/statut")
def changer_statut(numero_ticket: str, body: StatutUpdate):
    if body.statut not in ("pending", "confirmed", "rejected"):
        raise HTTPException(400, "Statut invalide")
    run(
        "UPDATE participants SET statut = %s, statut_modifie_le = %s WHERE numero_ticket = %s",
        (body.statut, datetime.now(), numero_ticket.upper()), fetch=False
    )
    rows = run("SELECT * FROM participants WHERE numero_ticket = %s", (numero_ticket.upper(),))
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt_participant(rows[0])


@app.patch("/api/inscriptions/{numero_ticket}")
def modifier_inscription(numero_ticket: str, body: InscriptionUpdate):
    champs = {k: v for k, v in body.model_dump().items() if v is not None}
    if not champs:
        raise HTTPException(400, "Aucun champ à modifier")
    sets = ", ".join(f"{k} = %s" for k in champs)
    vals = list(champs.values()) + [numero_ticket.upper()]
    run(f"UPDATE participants SET {sets} WHERE numero_ticket = %s", vals, fetch=False)
    rows = run("SELECT * FROM participants WHERE numero_ticket = %s", (numero_ticket.upper(),))
    if not rows:
        raise HTTPException(404, "Ticket introuvable")
    return fmt_participant(rows[0])


@app.delete("/api/inscriptions/{numero_ticket}")
def supprimer_inscription(numero_ticket: str):
    run("DELETE FROM participants WHERE numero_ticket = %s", (numero_ticket.upper(),), fetch=False)
    return {"success": True}


# ════════════════════════════════════════════════
#  VALIDATION À L'ENTRÉE
# ════════════════════════════════════════════════

@app.post("/api/validation/entree")
def valider_entree(numero_ticket: str):
    rows = run("SELECT * FROM participants WHERE numero_ticket = %s", (numero_ticket.upper(),))
    if not rows:
        return {"succes": False, "code": "NOT_FOUND", "message": "Ticket introuvable"}
    p = rows[0]
    if p["statut"] == "rejected":
        return {"succes": False, "code": "REJECTED", "message": "Ticket refusé"}
    if p["statut"] == "pending":
        return {"succes": False, "code": "PENDING", "message": "Paiement non confirmé"}
    if p["utilise"]:
        return {"succes": False, "code": "ALREADY_USED", "message": "Ticket déjà utilisé", "utilise_le": str(p.get("utilise_le") or "")}
    run(
        "UPDATE participants SET utilise = TRUE, utilise_le = %s WHERE numero_ticket = %s",
        (datetime.now(), numero_ticket.upper()), fetch=False
    )
    return {
        "succes": True, "code": "OK", "message": "Entrée validée",
        "nom":    f"{p.get('prenom','')} {p.get('nom','')}".strip(),
        "ticket": p["numero_ticket"],
        "type":   p["type_ticket"],
        "montant": float(p.get("montant") or 0),
    }


@app.get("/api/validation/recherche")
def rechercher_par_nom(q: str):
    if len(q) < 2:
        raise HTTPException(400, "Tape au moins 2 caractères")
    terme = f"%{q}%"
    rows = run(
        "SELECT numero_ticket, nom, prenom, statut, type_ticket, utilise "
        "FROM participants WHERE nom ILIKE %s OR prenom ILIKE %s ORDER BY nom LIMIT 20",
        (terme, terme)
    )
    for r in rows:
        r["nom_complet"] = f"{r.get('prenom','')} {r.get('nom','')}".strip()
    return {"total": len(rows), "items": rows}


# ════════════════════════════════════════════════
#  ÉVÉNEMENTS
# ════════════════════════════════════════════════

@app.get("/api/evenements")
def get_evenements(date: Optional[str] = None, categorie: Optional[str] = None):
    sql = "SELECT * FROM evenements WHERE actif = TRUE"
    params = []
    if date:
        sql += " AND date_evt = %s"; params.append(date)
    if categorie:
        sql += " AND categorie = %s"; params.append(categorie)
    sql += " ORDER BY date_evt, heure_debut"
    rows = run(sql, params)
    return [fmt_evenement(r) for r in rows]


@app.get("/api/evenements/soirees")
def get_soirees():
    rows = run("SELECT * FROM evenements WHERE actif = TRUE AND est_soiree = TRUE ORDER BY date_evt, heure_debut")
    return [fmt_evenement(r) for r in rows]


@app.get("/api/evenements/{evenement_id}")
def get_evenement(evenement_id: str):
    rows = run("SELECT * FROM evenements WHERE id = %s", (evenement_id,))
    if not rows:
        raise HTTPException(404, "Événement introuvable")
    return fmt_evenement(rows[0])


@app.post("/api/evenements", status_code=201)
def creer_evenement(body: EvenementIn):
    heure = body.heure_debut + ":00" if len(body.heure_debut) == 5 else body.heure_debut
    run(
        "INSERT INTO evenements (date_evt, heure_debut, titre, description, categorie, lieu, est_soiree, actif) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)",
        (body.date_evt, heure, body.titre, body.description, body.categorie, body.lieu or "", body.est_soiree or body.categorie == "soiree"),
        fetch=False
    )
    rows = run("SELECT * FROM evenements WHERE titre = %s ORDER BY cree_le DESC LIMIT 1", (body.titre,))
    return fmt_evenement(rows[0]) if rows else {"success": True}


@app.delete("/api/evenements/{evenement_id}")
def supprimer_evenement(evenement_id: str):
    run("UPDATE evenements SET actif = FALSE WHERE id = %s", (evenement_id,), fetch=False)
    return {"success": True}


# ════════════════════════════════════════════════
#  TARIFS
# ════════════════════════════════════════════════

@app.get("/api/tarifs")
def get_tarifs():
    rows = run("SELECT type_ticket, profil, montant FROM tarifs WHERE actif = TRUE")
    result = {"semaine_interne": 2500, "semaine_externe": 5000, "soiree_interne": 1500, "soiree_externe": 3000}
    for r in rows:
        result[f"{r['type_ticket']}_{r['profil']}"] = float(r["montant"])
    return result


@app.patch("/api/tarifs")
def update_tarifs(body: TarifsUpdate):
    mapping = {"semaine_interne": ("semaine","interne"), "semaine_externe": ("semaine","externe"), "soiree_interne": ("soiree","interne"), "soiree_externe": ("soiree","externe")}
    for attr, montant in {k: v for k, v in body.model_dump().items() if v is not None}.items():
        t, p = mapping[attr]
        run("UPDATE tarifs SET montant = %s WHERE type_ticket = %s AND profil = %s", (montant, t, p), fetch=False)
    return get_tarifs()


@app.get("/api/tarifs/ussd")
def get_ussd(montant: float = 2500):
    n = NUMERO_PAIEMENT
    return [
        {"operateur": "Mix by Yas (Moov)", "code": f"*145*1*{int(montant)}*{n}#", "lien_tel": f"tel:*145*1*{int(montant)}*{n}%23"},
        {"operateur": "Flooz (Togocel)",   "code": f"*155*1*{int(montant)}*{n}#", "lien_tel": f"tel:*155*1*{int(montant)}*{n}%23"},
    ]


# ════════════════════════════════════════════════
#  COMMENTAIRES
# ════════════════════════════════════════════════

@app.get("/api/commentaires/{evenement_id}")
def get_commentaires(evenement_id: str):
    rows = run(
        "SELECT id, pseudo, contenu, cree_le FROM commentaires WHERE evenement_id = %s AND approuve = TRUE ORDER BY cree_le DESC LIMIT 50",
        (evenement_id,)
    )
    for r in rows: r["cree_le"] = str(r.get("cree_le") or "")
    return rows


@app.post("/api/commentaires", status_code=201)
def publier_commentaire(body: CommentaireIn):
    if not body.contenu.strip(): raise HTTPException(400, "Commentaire vide")
    run("INSERT INTO commentaires (evenement_id, pseudo, contenu) VALUES (%s,%s,%s)",
        (body.evenement_id, body.pseudo.strip() or "Anonyme", body.contenu.strip()), fetch=False)
    return {"success": True}


@app.delete("/api/commentaires/{commentaire_id}")
def supprimer_commentaire(commentaire_id: str):
    run("DELETE FROM commentaires WHERE id = %s", (commentaire_id,), fetch=False)
    return {"success": True}


# ════════════════════════════════════════════════
#  GALERIE
# ════════════════════════════════════════════════

@app.get("/api/galerie")
def get_photos():
    rows = run("SELECT id, url, legende, cree_le FROM photos WHERE approuve = TRUE ORDER BY cree_le DESC LIMIT 100")
    for r in rows: r["cree_le"] = str(r.get("cree_le") or "")
    return rows


@app.post("/api/galerie", status_code=201)
def ajouter_photo(url: str, legende: Optional[str] = None, evenement_id: Optional[str] = None):
    run("INSERT INTO photos (url, legende, evenement_id, uploade_par) VALUES (%s,%s,%s,'public')",
        (url, legende or None, evenement_id or None), fetch=False)
    return {"success": True}


@app.delete("/api/galerie/{photo_id}")
def supprimer_photo(photo_id: str):
    run("DELETE FROM photos WHERE id = %s", (photo_id,), fetch=False)
    return {"success": True}


# ════════════════════════════════════════════════
#  STATISTIQUES
# ════════════════════════════════════════════════

@app.get("/api/stats/dashboard")
def get_dashboard():
    rows = run("SELECT * FROM v_dashboard")
    if not rows: return {}
    d = rows[0]
    return {
        "total_inscrits":      int(d.get("total_inscrits") or 0),
        "en_attente":          int(d.get("en_attente") or 0),
        "confirmes":           int(d.get("confirmes") or 0),
        "refuses":             int(d.get("refuses") or 0),
        "entrees_validees":    int(d.get("entrees_validees") or 0),
        "tickets_semaine":     int(d.get("tickets_semaine") or 0),
        "tickets_soiree":      int(d.get("tickets_soiree") or 0),
        "internes":            int(d.get("internes") or 0),
        "externes":            int(d.get("externes") or 0),
        "revenus_confirmes":   float(d.get("revenus_confirmes") or 0),
        "revenus_total":       float(d.get("revenus_total") or 0),
        "inscrits_aujourdhui": int(d.get("inscrits_aujourdhui") or 0),
    }


@app.get("/api/stats/operateurs")
def get_stats_operateurs():
    rows = run("SELECT * FROM v_stats_operateurs")
    return [{"operateur": r.get("operateur",""), "nb_inscriptions": int(r.get("nb_inscriptions") or 0), "confirmes": int(r.get("confirmes") or 0), "revenus": float(r.get("revenus") or 0)} for r in rows]


@app.get("/api/stats/par-jour")
def get_stats_par_jour():
    rows = run("SELECT * FROM v_inscriptions_par_jour")
    return [{"jour": str(r.get("jour","")), "total": int(r.get("total") or 0), "confirmes": int(r.get("confirmes") or 0), "revenus": float(r.get("revenus") or 0)} for r in rows]


# ════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
