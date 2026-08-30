import os
import re
import secrets
import hmac
import hashlib
import json
import smtplib

from pathlib import Path
from functools import wraps
from email.message import EmailMessage

import psycopg
import cloudinary
import cloudinary.uploader
from psycopg.rows import dict_row

from flask import (
    Flask,
    request,
    jsonify,
    session,
    redirect,
    render_template,
)

from werkzeug.security import check_password_hash

try:
    import razorpay
except ImportError:
    razorpay = None


# ============================================================
# BASIC CONFIG
# ============================================================

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.environ["DATABASE_URL"]

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("UPL_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)

PANCHAYATS = [
    "Uttar Laxmipur", "Mothabari", "Uttar Panchanandapur-I",
    "Uttar Panchanandapur-II", "Gangaprasad", "Bangitola",
    "Rathbari", "Hamidpur", "Rajnagar",
]
ROLES = {"Batter", "Bowler", "All-Rounder"}
BATTING = {"Right-hand Batsman", "Left-hand Batsman"}
BOWLING = {"Right-hand Bowling", "Left-hand Bowling"}


class DBConnection:
    def __init__(self):
        self.c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    def execute(self, query, params=None):
        return self.c.execute(query.replace("?", "%s"), params or ())
    def commit(self): self.c.commit()
    def rollback(self): self.c.rollback()
    def close(self): self.c.close()


def db(): return DBConnection()


def create_extra_tables():
    c = None
    try:
        c = db()
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_interest (
                id SERIAL PRIMARY KEY, interest_no TEXT UNIQUE NOT NULL,
                team_name TEXT NOT NULL, contact_name TEXT NOT NULL,
                phone TEXT NOT NULL, email TEXT NOT NULL, village TEXT NOT NULL,
                gram_panchayat TEXT NOT NULL, registration_fee INTEGER DEFAULT 5000,
                interest_charge INTEGER DEFAULT 100, payment_status TEXT DEFAULT 'Pending',
                status TEXT DEFAULT 'Interested', razorpay_order_id TEXT,
                razorpay_payment_id TEXT, paid_amount INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        migrations = [
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS paid_amount INTEGER DEFAULT 0",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS registration_fee INTEGER DEFAULT 5000",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS interest_charge INTEGER DEFAULT 100",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'Pending'",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Pending'",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS contact_name TEXT",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS representative_name TEXT",
            "ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS payment_reference TEXT",
            "ALTER TABLE points_table ADD COLUMN IF NOT EXISTS group_name TEXT DEFAULT 'A'",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'Paid'",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS paid_amount INTEGER DEFAULT 0",
        ]
        for sql in migrations: c.execute(sql)
        c.execute("UPDATE team_interest SET contact_name = representative_name WHERE contact_name IS NULL AND representative_name IS NOT NULL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS player_payment (
                id SERIAL PRIMARY KEY, registration_no TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL, age INTEGER NOT NULL, phone TEXT NOT NULL,
                email TEXT NOT NULL, village TEXT NOT NULL, gram_panchayat TEXT NOT NULL,
                primary_role TEXT NOT NULL, batting_style TEXT, bowling_style TEXT,
                photo_path TEXT, amount INTEGER NOT NULL DEFAULT 100,
                payment_status TEXT DEFAULT 'Created', razorpay_order_id TEXT UNIQUE,
                razorpay_payment_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.commit()
    except Exception as e:
        print("EXTRA TABLE ERROR:", repr(e))
        if c: c.rollback()
    finally:
        if c: c.close()


create_extra_tables()


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"): return redirect("/admin/login")
        return fn(*args, **kwargs)
    return wrapped


def next_reg(c):
    while True:
        registration_no = f"UPL26-{secrets.token_hex(4).upper()[:6]}"
        if not c.execute("SELECT 1 FROM players WHERE registration_no=?", (registration_no,)).fetchone():
            return registration_no


def next_team_interest(c):
    while True:
        interest_no = f"UPL-26-TI-{secrets.token_hex(4).upper()[:6]}"
        if not c.execute("SELECT 1 FROM team_interest WHERE interest_no=?", (interest_no,)).fetchone():
            return interest_no


@app.context_processor
def global_variables(): return {"panchayats": PANCHAYATS}


@app.get("/")
def home():
    c = db()
    try:
        fixtures = c.execute("SELECT * FROM fixtures ORDER BY match_date, match_time LIMIT 3").fetchall()
        news = c.execute("SELECT * FROM news WHERE published=1 ORDER BY id DESC LIMIT 3").fetchall()
        points = c.execute("SELECT * FROM points_table ORDER BY points DESC, nrr DESC, team_name").fetchall()
        teams = c.execute("SELECT * FROM teams ORDER BY name").fetchall()
    finally: c.close()
    return render_template("home.html", fixtures=fixtures, news=news, points=points, teams=teams)


@app.get("/registration")
def registration():
    return render_template("registration.html", player_registration_fee=int(os.environ.get("PLAYER_REGISTRATION_FEE", "100")))


# Legacy direct registration is disabled: payment verification is mandatory.
@app.post("/api/register")
def register():
    return jsonify(ok=False, error="Please use the secure payment registration form."), 400


@app.post("/api/player-payment/create-order")
def player_payment_create_order():
    if razorpay is None: return jsonify(ok=False, error="Razorpay package is not installed."), 500
    key_id, key_secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret: return jsonify(ok=False, error="Razorpay test keys are not configured."), 500
    f = request.form
    name, age_raw = f.get("name", "").strip(), f.get("age", "").strip()
    phone = re.sub(r"\D", "", f.get("phone", "")); email = f.get("email", "").strip().lower()
    village, panchayat, role = f.get("village", "").strip(), f.get("panchayat", "").strip(), f.get("role", "").strip()
    batting, bowling, photo = f.get("battingHand", "").strip() or None, f.get("bowlingHand", "").strip() or None, request.files.get("photo")
    if not all([name, age_raw, phone, email, village, panchayat, role, photo]): return jsonify(ok=False, error="Please complete all required fields."), 400
    try: age = int(age_raw)
    except ValueError: return jsonify(ok=False, error="Age must be a number."), 400
    if not 10 <= age <= 80: return jsonify(ok=False, error="Please enter a valid age."), 400
    if len(phone) != 10: return jsonify(ok=False, error="Phone/WhatsApp number must be 10 digits."), 400
    if panchayat not in PANCHAYATS: return jsonify(ok=False, error="Invalid panchayat selection."), 400
    if role not in ROLES: return jsonify(ok=False, error="Invalid role selection."), 400
    if role == "Batter":
        if batting not in BATTING: return jsonify(ok=False, error="Select batting style."), 400
        bowling = None
    elif role == "Bowler":
        if bowling not in BOWLING: return jsonify(ok=False, error="Select bowling style."), 400
        batting = None
    elif batting not in BATTING or bowling not in BOWLING:
        return jsonify(ok=False, error="Select both batting and bowling styles."), 400
    if Path(photo.filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}: return jsonify(ok=False, error="Photo must be JPG, PNG or WebP."), 400
    amount_rupees = int(os.environ.get("PLAYER_REGISTRATION_FEE", "100"))
    if amount_rupees <= 0: return jsonify(ok=False, error="Player registration fee is not configured correctly."), 500
    c = db()
    try:
        dup = c.execute("SELECT 1 FROM players WHERE phone=? OR email=? UNION ALL SELECT 1 FROM player_payment WHERE phone=? OR email=? LIMIT 1", (phone,email,phone,email)).fetchone()
        if dup: return jsonify(ok=False, error="This phone number or e-mail is already registered or has a pending payment."), 409
        registration_no = next_reg(c)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40]
        if not os.environ.get("CLOUDINARY_CLOUD_NAME"): raise RuntimeError("Cloudinary is not configured.")
        upload_result = cloudinary.uploader.upload(photo, folder="upl/player-pending", public_id=f"{registration_no}_{safe_name}", resource_type="image")
        photo_url = upload_result["secure_url"]
        client = razorpay.Client(auth=(key_id, key_secret)); amount_paise = amount_rupees * 100
        order = client.order.create(data={"amount": amount_paise, "currency":"INR", "receipt":registration_no, "payment_capture":1, "notes":{"registration_no":registration_no,"name":name}})
        order_id = order.get("id")
        if not order_id: raise RuntimeError("Razorpay did not return an order ID.")
        c.execute("""INSERT INTO player_payment (registration_no,full_name,age,phone,email,village,gram_panchayat,primary_role,batting_style,bowling_style,photo_path,amount,payment_status,razorpay_order_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (registration_no,name,age,phone,email,village,panchayat,role,batting,bowling,photo_url,amount_rupees,"Created",order_id))
        c.commit()
        return jsonify(ok=True,key_id=key_id,order_id=order_id,amount=amount_paise,currency="INR",registration_no=registration_no,form_token=registration_no)
    except psycopg.IntegrityError:
        c.rollback(); return jsonify(ok=False,error="This phone number, e-mail or payment order is already in use."),409
    except Exception as e:
        c.rollback(); print("PLAYER PAYMENT ORDER ERROR:",repr(e)); return jsonify(ok=False,error="Payment could not be started. Please try again."),500
    finally: c.close()


@app.post("/api/player-payment/verify")
def player_payment_verify():
    if razorpay is None: return jsonify(ok=False,error="Razorpay package is not installed."),500
    key_id, key_secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret: return jsonify(ok=False,error="Razorpay keys are not configured."),500
    data=request.get_json(silent=True) or {}; registration_no=str(data.get("registration_no","")).strip(); order_id=str(data.get("razorpay_order_id","")).strip(); payment_id=str(data.get("razorpay_payment_id","")).strip(); signature=str(data.get("razorpay_signature","")).strip()
    if not all([registration_no,order_id,payment_id,signature]): return jsonify(ok=False,error="Incomplete payment verification data."),400
    generated=hmac.new(key_secret.encode(),f"{order_id}|{payment_id}".encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(generated,signature): return jsonify(ok=False,error="Payment verification failed."),400
    c=db()
    try:
        pending=c.execute("SELECT * FROM player_payment WHERE registration_no=? AND razorpay_order_id=?",(registration_no,order_id)).fetchone()
        if not pending: return jsonify(ok=False,error="Player payment application not found."),404
        if pending["payment_status"]=="Paid": return jsonify(ok=True,registration_no=registration_no,message="Payment already verified.")
        if c.execute("SELECT 1 FROM players WHERE registration_no=?",(registration_no,)).fetchone(): return jsonify(ok=True,registration_no=registration_no,message="Registration already completed.")
        if c.execute("SELECT 1 FROM players WHERE phone=? OR email=?",(pending["phone"],pending["email"])).fetchone(): return jsonify(ok=False,error="This phone number or e-mail is already registered."),409
        client=razorpay.Client(auth=(key_id,key_secret)); expected=int(pending["amount"])*100
        order_info=client.order.fetch(order_id); payment_info=client.payment.fetch(payment_id)
        if int(order_info.get("amount",0))!=expected or payment_info.get("order_id")!=order_id or int(payment_info.get("amount",0))!=expected: return jsonify(ok=False,error="Payment amount/order mismatch."),400
        if payment_info.get("status") not in {"captured","authorized"}: return jsonify(ok=False,error="Payment has not been captured."),400
        c.execute("""INSERT INTO players (registration_no,full_name,age,phone,email,village,gram_panchayat,primary_role,batting_style,bowling_style,photo_path,status,payment_status,razorpay_order_id,razorpay_payment_id,paid_amount) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(pending["registration_no"],pending["full_name"],pending["age"],pending["phone"],pending["email"],pending["village"],pending["gram_panchayat"],pending["primary_role"],pending["batting_style"],pending["bowling_style"],pending["photo_path"],"Pending","Paid",order_id,payment_id,pending["amount"]))
        c.execute("UPDATE player_payment SET payment_status='Paid',razorpay_payment_id=? WHERE id=?",(payment_id,pending["id"])); c.commit()
        saved=c.execute("SELECT * FROM players WHERE registration_no=?",(registration_no,)).fetchone()
        try: append_player_to_google_sheet(saved)
        except Exception as e: print("PLAYER GOOGLE SHEETS ERROR:",repr(e))
        return jsonify(ok=True,registration_no=registration_no,message="Player registration successful.")
    except psycopg.IntegrityError:
        c.rollback(); return jsonify(ok=False,error="This player is already registered."),409
    except Exception as e:
        c.rollback(); print("PLAYER PAYMENT VERIFY ERROR:",repr(e)); return jsonify(ok=False,error="Payment was received, but registration verification could not be completed."),500
    finally: c.close()


@app.get("/team-registration")
def team_registration(): return render_template("team_registration.html",razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID",""))


@app.post("/api/team-interest/create-order")
def team_interest_create_order():
    if razorpay is None: return jsonify(ok=False,error="Razorpay package is not installed."),500
    key_id,key_secret=os.environ.get("RAZORPAY_KEY_ID"),os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret: return jsonify(ok=False,error="Razorpay test keys are not configured."),500
    f=request.form; team_name=f.get("team_name","").strip(); contact_name=f.get("contact_name","").strip(); phone=re.sub(r"\D","",f.get("phone","")); email=f.get("email","").strip().lower(); village=f.get("village","").strip(); panchayat=f.get("panchayat","").strip()
    if not all([team_name,contact_name,phone,email,village,panchayat]): return jsonify(ok=False,error="Please complete all required fields."),400
    if len(phone)!=10: return jsonify(ok=False,error="Phone number must be 10 digits."),400
    if panchayat not in PANCHAYATS: return jsonify(ok=False,error="Invalid panchayat selection."),400
    c=db()
    try:
        interest_no=next_team_interest(c); amount_paise=10000; client=razorpay.Client(auth=(key_id,key_secret)); order=client.order.create(data={"amount":amount_paise,"currency":"INR","receipt":interest_no,"payment_capture":1,"notes":{"interest_no":interest_no,"team_name":team_name}}); order_id=order.get("id")
        if not order_id: raise RuntimeError("Razorpay did not return an order ID.")
        c.execute("""INSERT INTO team_interest (interest_no,team_name,contact_name,representative_name,phone,email,village,gram_panchayat,registration_fee,interest_charge,payment_status,status,razorpay_order_id,paid_amount) VALUES (?,?,?,?,?,?,?,?,5000,100,'Created','Interested',?,0)""",(interest_no,team_name,contact_name,contact_name,phone,email,village,panchayat,order_id)); c.commit()
        return jsonify(ok=True,key_id=key_id,order_id=order_id,amount=amount_paise,currency="INR",interest_no=interest_no)
    except Exception as e:
        c.rollback(); print("TEAM PAYMENT ORDER ERROR:",repr(e)); return jsonify(ok=False,error="Payment could not be started. Please try again."),500
    finally: c.close()


@app.post("/api/team-interest/verify-payment")
def team_interest_verify_payment():
    key_secret=os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_secret: return jsonify(ok=False,error="Razorpay key is not configured."),500
    data=request.get_json(silent=True) or {}; interest_no=str(data.get("interest_no","")).strip(); order_id=str(data.get("razorpay_order_id","")).strip(); payment_id=str(data.get("razorpay_payment_id","")).strip(); signature=str(data.get("razorpay_signature","")).strip()
    if not all([interest_no,order_id,payment_id,signature]): return jsonify(ok=False,error="Incomplete payment verification data."),400
    generated=hmac.new(key_secret.encode(),f"{order_id}|{payment_id}".encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(generated,signature): return jsonify(ok=False,error="Payment verification failed."),400
    c=db()
    try:
        row=c.execute("SELECT * FROM team_interest WHERE interest_no=? AND razorpay_order_id=?",(interest_no,order_id)).fetchone()
        if not row: return jsonify(ok=False,error="Team interest application not found."),404
        if row["payment_status"]=="Paid": return jsonify(ok=True,interest_no=interest_no,message="Payment already verified.")
        if razorpay:
            client=razorpay.Client(auth=(os.environ.get("RAZORPAY_KEY_ID"),key_secret)); expected=10000; pi=client.payment.fetch(payment_id)
            if pi.get("order_id")!=order_id or int(pi.get("amount",0))!=expected or pi.get("status") not in {"captured","authorized"}: return jsonify(ok=False,error="Payment verification failed."),400
        c.execute("UPDATE team_interest SET payment_status='Paid',razorpay_payment_id=?,paid_amount=100 WHERE id=?",(payment_id,row["id"])); c.commit(); updated=c.execute("SELECT * FROM team_interest WHERE id=?",(row["id"],)).fetchone()
        try: send_team_interest_email(updated["email"],updated["team_name"],updated["contact_name"],updated["interest_no"])
        except Exception as e: print("TEAM EMAIL ERROR:",repr(e))
        try: append_team_interest_to_google_sheet(updated)
        except Exception as e: print("GOOGLE SHEETS ERROR:",repr(e))
        return jsonify(ok=True,interest_no=interest_no,message="Thank you for showing interest. Our UPL Organising Committee will contact you soon if a team slot is available.")
    except Exception as e:
        c.rollback(); print("TEAM PAYMENT VERIFY ERROR:",repr(e)); return jsonify(ok=False,error="Payment was received but verification could not be completed."),500
    finally: c.close()


# ============================================================
# GOOGLE SHEETS HELPERS
# ============================================================

def get_google_worksheet(title,headers):
    service_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"); sheet_id=os.environ.get("GOOGLE_SHEET_ID")
    if not service_json or not sheet_id: raise RuntimeError("Google Sheets settings are not configured.")
    import gspread
    from google.oauth2.service_account import Credentials
    credentials=Credentials.from_service_account_info(json.loads(service_json),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    spreadsheet=gspread.authorize(credentials).open_by_key(sheet_id)
    try: worksheet=spreadsheet.worksheet(title)
    except Exception: worksheet=spreadsheet.add_worksheet(title=title,rows=1000,cols=max(len(headers),20))
    if not worksheet.get_all_values(): worksheet.append_row(headers)
    return worksheet


def append_player_to_google_sheet(row):
    headers=["Registration No.","Name","Age","Phone","Email","Village","Gram Panchayat","Role","Batting","Bowling","Status","Photo URL","Payment Status","Paid Amount","Razorpay Order ID","Razorpay Payment ID"]
    worksheet=get_google_worksheet("Players",headers)
    worksheet.append_row([row["registration_no"],row["full_name"],row["age"],row["phone"],row["email"],row["village"],row["gram_panchayat"],row["primary_role"],row["batting_style"] or "-",row["bowling_style"] or "-",row["status"],row["photo_path"] or "",row["payment_status"] or "Paid",row["paid_amount"] or 0,row["razorpay_order_id"] or "",row["razorpay_payment_id"] or ""])


def append_team_interest_to_google_sheet(row):
    headers=["Interest No.","Team Name","Contact Name","Phone","Email","Village","Gram Panchayat","Registration Fee","Interest Charge","Payment Status","Status","Razorpay Order ID","Razorpay Payment ID","Paid Amount","Created At"]
    worksheet=get_google_worksheet("Team Registrations",headers)
    worksheet.append_row([row["interest_no"],row["team_name"],row["contact_name"],row["phone"],row["email"],row["village"],row["gram_panchayat"],row["registration_fee"],row["interest_charge"],row["payment_status"],row["status"],row["razorpay_order_id"] or "",row["razorpay_payment_id"] or "",row["paid_amount"],str(row["created_at"])])


def send_team_interest_email(email,team_name,contact_name,interest_no):
    smtp_host=os.environ.get("SMTP_HOST"); smtp_port=int(os.environ.get("SMTP_PORT","587")); smtp_user=os.environ.get("SMTP_USERNAME"); smtp_password=os.environ.get("SMTP_PASSWORD"); from_email=os.environ.get("UPL_FROM_EMAIL",smtp_user or "")
    if not all([smtp_host,smtp_user,smtp_password,from_email]): raise RuntimeError("SMTP email settings are not configured.")
    msg=EmailMessage(); msg["Subject"]="UPL – Team Interest Received"; msg["From"]=from_email; msg["To"]=email
    msg.set_content(f"Dear {contact_name},\n\nThank you for showing interest in participating in UPL.\n\nTeam Name: {team_name}\nInterest No.: {interest_no}\nInterest Charge Paid: ₹100\nActual Team Registration Fee: ₹5,000\nThe ₹5,000 registration fee is NOT collected at this stage.\n\nOur UPL Organising Committee will contact you very soon if a team slot is available.\n\nPlease keep your Interest Number for future communication.\n\nThanks & regards,\nUPL Organising Committee\n")
    with smtplib.SMTP(smtp_host,smtp_port,timeout=20) as server:
        server.starttls(); server.login(smtp_user,smtp_password); server.send_message(msg)


@app.post("/api/team-interest")
def team_interest_legacy(): return jsonify(ok=False,error="Please use the Team Registration payment form. A ₹100 interest charge is required."),400


@app.get("/teams")
def teams():
    c=db()
    try: rows=c.execute("SELECT * FROM teams ORDER BY name").fetchall()
    finally: c.close()
    return render_template("teams.html",teams=rows)


@app.get("/players")
def players():
    c=db()
    try: rows=c.execute("SELECT * FROM players WHERE status='Approved' ORDER BY full_name").fetchall()
    finally: c.close()
    return render_template("players.html",players=rows)


@app.get("/fixtures")
def fixtures():
    c=db()
    try: rows=c.execute("SELECT * FROM fixtures ORDER BY match_date,match_time").fetchall()
    finally: c.close()
    return render_template("fixtures.html",fixtures=rows)


@app.get("/points-table")
def pointstable():
    c=db()
    try: rows=c.execute("SELECT * FROM points_table ORDER BY group_name,points DESC,nrr DESC,team_name").fetchall()
    finally: c.close()
    return render_template("points.html",points=rows)


@app.get("/news")
def news():
    c=db()
    try: rows=c.execute("SELECT * FROM news WHERE published=1 ORDER BY id DESC").fetchall()
    finally: c.close()
    return render_template("news.html",news=rows)


@app.get("/gallery")
def gallery():
    c=db()
    try: rows=c.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall()
    finally: c.close()
    return render_template("gallery.html",gallery=rows)


@app.get("/admin/login")
def admin_login(): return render_template("login.html")


@app.post("/admin/login")
def admin_login_post():
    username=request.form.get("username","").strip(); password=request.form.get("password",""); c=db()
    try: row=c.execute("SELECT * FROM admins WHERE username=?",(username,)).fetchone()
    finally: c.close()
    if row and check_password_hash(row["password_hash"],password): session["admin"]=True; return redirect("/admin")
    return render_template("login.html",error="Invalid username or password."),401


@app.get("/admin/logout")
def logout(): session.clear(); return redirect("/admin/login")


@app.get("/admin")
@admin_required
def admin():
    c=db()
    try:
        players=c.execute("SELECT * FROM players ORDER BY id DESC").fetchall()
        teams=c.execute("SELECT * FROM teams ORDER BY name").fetchall()
        fixtures=c.execute("SELECT * FROM fixtures ORDER BY match_date,match_time").fetchall()
        news_rows=c.execute("SELECT * FROM news ORDER BY id DESC").fetchall()
        points=c.execute("SELECT * FROM points_table ORDER BY group_name,points DESC,nrr DESC,team_name").fetchall()
        gallery_rows=c.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall()
        team_interest=c.execute("SELECT * FROM team_interest ORDER BY id DESC").fetchall()
    finally: c.close()
    return render_template("admin.html",players=players,teams=teams,fixtures=fixtures,news=news_rows,points=points,gallery=gallery_rows,team_interest=team_interest)


@app.post("/admin/player/<int:id>/<action>")
@admin_required
def player_action(id,action):
    if action not in {"Approved","Rejected","Pending"}: return redirect("/admin")
    c=db()
    try: c.execute("UPDATE players SET status=? WHERE id=?",(action,id)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/team/add")
@admin_required
def team_add():
    name=request.form.get("name","").strip(); description=request.form.get("description","").strip()
    if name:
        c=db()
        try: c.execute("INSERT INTO teams(name,description) VALUES(?,?) ON CONFLICT(name) DO NOTHING",(name,description)); c.commit()
        finally: c.close()
    return redirect("/admin")


@app.post("/admin/team/delete/<int:id>")
@admin_required
def team_delete(id):
    c=db()
    try: c.execute("DELETE FROM teams WHERE id=?",(id,)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/team-interest/<int:id>/<status>")
@admin_required
def team_interest_status(id,status):
    if status not in {"Interested","Contacted","Approved","Rejected"}: return redirect("/admin")
    c=db()
    try: c.execute("UPDATE team_interest SET status=? WHERE id=?",(status,id)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/fixture/add")
@admin_required
def fixture_add():
    f=request.form; c=db()
    try:
        c.execute("INSERT INTO fixtures(match_no,team1,team2,match_date,match_time,venue,status,result_text) VALUES(?,?,?,?,?,?,?,?)",(f.get("match_no") or None,f.get("team1","").strip(),f.get("team2","").strip(),f.get("date") or None,f.get("time") or None,f.get("venue") or "Uttar Lakshmipur High School",f.get("status") or "Upcoming",f.get("result") or "")); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/fixture/delete/<int:id>")
@admin_required
def fixture_delete(id):
    c=db()
    try: c.execute("DELETE FROM fixtures WHERE id=?",(id,)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/news/add")
@admin_required
def news_add():
    title=request.form.get("title","").strip(); body=request.form.get("body","").strip()
    if title and body:
        c=db()
        try: c.execute("INSERT INTO news(title,body,published) VALUES(?,?,1)",(title,body)); c.commit()
        finally: c.close()
    return redirect("/admin")


@app.post("/admin/news/delete/<int:id>")
@admin_required
def news_delete(id):
    c=db()
    try: c.execute("DELETE FROM news WHERE id=?",(id,)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/points/add")
@admin_required
def points_add():
    f=request.form; team=f.get("team_name","").strip(); group=f.get("group_name","A").strip().upper()
    if team and group in {"A","B"}:
        c=db()
        try:
            c.execute("""INSERT INTO points_table(team_name,group_name,played,won,lost,tied,points,nrr) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(team_name) DO UPDATE SET group_name=EXCLUDED.group_name,played=EXCLUDED.played,won=EXCLUDED.won,lost=EXCLUDED.lost,tied=EXCLUDED.tied,points=EXCLUDED.points,nrr=EXCLUDED.nrr""",(team,group,int(f.get("played") or 0),int(f.get("won") or 0),int(f.get("lost") or 0),int(f.get("tied") or 0),int(f.get("points") or 0),float(f.get("nrr") or 0))); c.commit()
        finally: c.close()
    return redirect("/admin")


@app.post("/admin/points/delete/<int:id>")
@admin_required
def points_delete(id):
    c=db()
    try: c.execute("DELETE FROM points_table WHERE id=?",(id,)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.post("/admin/gallery/add")
@admin_required
def gallery_add():
    image=request.files.get("image"); title=request.form.get("title","").strip()
    if not image or not image.filename: return redirect("/admin")
    if Path(image.filename).suffix.lower() not in {".jpg",".jpeg",".png",".webp"}: return redirect("/admin")
    c=None
    try:
        if not os.environ.get("CLOUDINARY_CLOUD_NAME"): raise RuntimeError("Cloudinary is not configured.")
        upload_result=cloudinary.uploader.upload(image,folder="upl/gallery",resource_type="image"); image_url=upload_result["secure_url"]; c=db(); c.execute("INSERT INTO gallery(title,image_path) VALUES(?,?)",(title,image_url)); c.commit()
    except Exception as e:
        print("GALLERY ERROR:",repr(e));
        if c: c.rollback()
    finally:
        if c: c.close()
    return redirect("/admin")


@app.post("/admin/gallery/delete/<int:id>")
@admin_required
def gallery_delete(id):
    c=db()
    try: c.execute("DELETE FROM gallery WHERE id=?",(id,)); c.commit()
    finally: c.close()
    return redirect("/admin")


@app.get("/health")
def health(): return jsonify(status="ok",service="UPL Website")


if __name__ == "__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
