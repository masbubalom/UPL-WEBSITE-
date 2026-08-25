
import os, re, sqlite3, secrets
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, send_from_directory, render_template, url_for
from werkzeug.security import generate_password_hash, check_password_hash

BASE=Path(__file__).resolve().parent
DB=BASE/"upl.db"
UPLOADS=BASE/"uploads"
UPLOADS.mkdir(exist_ok=True)

app=Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key=os.environ.get("UPL_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"]=8*1024*1024

PANCHAYATS=[
"Uttar Laxmipur","Mothabari","Uttar Panchanandapur-I","Uttar Panchanandapur-II",
"Gangaprasad","Bangitola","Rathbari","Hamidpur","Rajnagar"
]
ROLES={"Batter","Bowler","All-Rounder"}
BATTING={"Right-hand Batsman","Left-hand Batsman"}
BOWLING={"Right-hand Bowling","Left-hand Bowling"}

def db():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if not session.get("admin"): return redirect("/admin/login")
        return fn(*a,**kw)
    return wrapped

def next_reg(c):
    return f"UPL25-{c.execute('SELECT COALESCE(MAX(id),0)+1 FROM players').fetchone()[0]:04d}"

@app.context_processor
def globals_():
    return {"panchayats":PANCHAYATS}

@app.get("/")
def home():
    c=db()
    fixtures=c.execute("SELECT * FROM fixtures ORDER BY match_date,match_time LIMIT 3").fetchall()
    news=c.execute("SELECT * FROM news WHERE published=1 ORDER BY id DESC LIMIT 3").fetchall()
    points=c.execute("SELECT * FROM points_table ORDER BY points DESC,nrr DESC").fetchall()
    teams=c.execute("SELECT * FROM teams ORDER BY name").fetchall()
    c.close()
    return render_template("home.html",fixtures=fixtures,news=news,points=points,teams=teams)

@app.get("/registration")
def registration():
    return render_template("registration.html")

@app.post("/api/register")
def register():
    f=request.form
    name=f.get("name","").strip(); age_raw=f.get("age","").strip()
    phone=re.sub(r"\D","",f.get("phone","")); email=f.get("email","").strip().lower()
    village=f.get("village","").strip(); p=f.get("panchayat","").strip()
    role=f.get("role","").strip(); bat=f.get("battingHand","").strip() or None
    bowl=f.get("bowlingHand","").strip() or None; photo=request.files.get("photo")
    if not all([name,age_raw,phone,email,village,p,role,photo]):
        return jsonify(ok=False,error="Please complete all required fields."),400
    try: age=int(age_raw)
    except: return jsonify(ok=False,error="Age must be a number."),400
    if not 10<=age<=80: return jsonify(ok=False,error="Please enter a valid age."),400
    if len(phone)!=10: return jsonify(ok=False,error="Phone/WhatsApp number must be 10 digits."),400
    if p not in PANCHAYATS or role not in ROLES: return jsonify(ok=False,error="Invalid selection."),400
    if role=="Batter":
        if bat not in BATTING: return jsonify(ok=False,error="Select batting style."),400
        bowl=None
    elif role=="Bowler":
        if bowl not in BOWLING: return jsonify(ok=False,error="Select bowling style."),400
        bat=None
    else:
        if bat not in BATTING or bowl not in BOWLING:
            return jsonify(ok=False,error="Select both batting and bowling styles."),400
    ext=Path(photo.filename or "").suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp"}:
        return jsonify(ok=False,error="Photo must be JPG, PNG or WebP."),400

    c=db()
    try:
        reg=next_reg(c)
        safe=re.sub(r"[^A-Za-z0-9_-]","_",name)[:40]
        filename=f"{reg}_{safe}{ext}"
        photo.save(UPLOADS/filename)
        c.execute("""INSERT INTO players
        (registration_no,full_name,age,phone,email,village,gram_panchayat,primary_role,
         batting_style,bowling_style,photo_path,status)
         VALUES(?,?,?,?,?,?,?,?,?,?,?,'Pending')""",
         (reg,name,age,phone,email,village,p,role,bat,bowl,filename))
        c.commit()
        return jsonify(ok=True,registration_no=reg)
    except sqlite3.IntegrityError:
        c.rollback()
        return jsonify(ok=False,error="This phone number or e-mail is already registered."),409
    finally: c.close()

@app.get("/teams")
def teams():
    c=db()
    teams=c.execute("SELECT * FROM teams ORDER BY name").fetchall()
    c.close()
    return render_template("teams.html",teams=teams)

@app.get("/players")
def players():
    c=db()
    rows=c.execute("SELECT * FROM players WHERE status='Approved' ORDER BY full_name").fetchall()
    c.close()
    return render_template("players.html",players=rows)

@app.get("/fixtures")
def fixtures():
    c=db()
    rows=c.execute("SELECT * FROM fixtures ORDER BY match_date,match_time,match_no").fetchall()
    c.close()
    return render_template("fixtures.html",fixtures=rows)

@app.get("/points-table")
def pointstable():
    c=db()
    rows=c.execute("SELECT * FROM points_table ORDER BY points DESC,nrr DESC,team_name").fetchall()
    c.close()
    return render_template("points.html",points=rows)

@app.get("/news")
def news():
    c=db()
    rows=c.execute("SELECT * FROM news WHERE published=1 ORDER BY id DESC").fetchall()
    c.close()
    return render_template("news.html",news=rows)

@app.get("/gallery")
def gallery():
    c=db()
    rows=c.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall()
    c.close()
    return render_template("gallery.html",gallery=rows)

@app.get("/uploads/<path:filename>")
def uploaded(filename): return send_from_directory(UPLOADS,filename)

# ---------- Admin ----------
@app.get("/admin/login")
def admin_login(): return render_template("login.html")

@app.post("/admin/login")
def admin_login_post():
    u=request.form.get("username",""); pw=request.form.get("password","")
    c=db(); row=c.execute("SELECT * FROM admins WHERE username=?",(u,)).fetchone(); c.close()
    if row and check_password_hash(row["password_hash"],pw):
        session["admin"]=True; return redirect("/admin")
    return render_template("login.html",error="Invalid username or password."),401

@app.get("/admin/logout")
def logout(): session.clear(); return redirect("/admin/login")

@app.get("/admin")
@admin_required
def admin():
    c=db()
    players=c.execute("SELECT * FROM players ORDER BY id DESC").fetchall()
    teams=c.execute("SELECT * FROM teams ORDER BY name").fetchall()
    fixtures=c.execute("SELECT * FROM fixtures ORDER BY match_date,match_time").fetchall()
    news=c.execute("SELECT * FROM news ORDER BY id DESC").fetchall()
    points=c.execute("SELECT * FROM points_table ORDER BY points DESC,nrr DESC").fetchall()
    c.close()
    return render_template("admin.html",players=players,teams=teams,fixtures=fixtures,news=news,points=points)

@app.post("/admin/player/<int:id>/<action>")
@admin_required
def player_action(id,action):
    if action not in {"Approved","Rejected","Pending"}: return redirect("/admin")
    c=db(); c.execute("UPDATE players SET status=? WHERE id=?",(action,id)); c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/team/add")
@admin_required
def team_add():
    name=request.form.get("name","").strip()
    if name:
        c=db(); c.execute("INSERT OR IGNORE INTO teams(name,description) VALUES(?,?)",(name,request.form.get("description",""))); c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/team/delete/<int:id>")
@admin_required
def team_delete(id):
    c=db(); c.execute("DELETE FROM teams WHERE id=?",(id,)); c.commit(); c.close(); return redirect("/admin")

@app.post("/admin/fixture/add")
@admin_required
def fixture_add():
    f=request.form
    c=db()
    c.execute("""INSERT INTO fixtures(match_no,team1,team2,match_date,match_time,venue,status,result_text)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (f.get("match_no") or None,f.get("team1"),f.get("team2"),f.get("date"),f.get("time"),
               f.get("venue") or "Uttar Lakshmipur High School",f.get("status") or "Upcoming",f.get("result") or ""))
    c.commit(); c.close(); return redirect("/admin")

@app.post("/admin/fixture/delete/<int:id>")
@admin_required
def fixture_delete(id):
    c=db(); c.execute("DELETE FROM fixtures WHERE id=?",(id,)); c.commit(); c.close(); return redirect("/admin")

@app.post("/admin/news/add")
@admin_required
def news_add():
    title=request.form.get("title","").strip(); body=request.form.get("body","").strip()
    if title and body:
        c=db(); c.execute("INSERT INTO news(title,body,published) VALUES(?,?,1)",(title,body)); c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/news/delete/<int:id>")
@admin_required
def news_delete(id):
    c=db(); c.execute("DELETE FROM news WHERE id=?",(id,)); c.commit(); c.close(); return redirect("/admin")

@app.post("/admin/points/add")
@admin_required
def points_add():
    f=request.form; team=f.get("team_name","").strip()
    if team:
        c=db(); c.execute("""INSERT INTO points_table(team_name,played,won,lost,tied,points,nrr)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(team_name) DO UPDATE SET played=excluded.played,won=excluded.won,
        lost=excluded.lost,tied=excluded.tied,points=excluded.points,nrr=excluded.nrr""",
        (team,int(f.get("played") or 0),int(f.get("won") or 0),int(f.get("lost") or 0),
         int(f.get("tied") or 0),int(f.get("points") or 0),float(f.get("nrr") or 0)))
        c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/points/delete/<int:id>")
@admin_required
def points_delete(id):
    c=db(); c.execute("DELETE FROM points_table WHERE id=?",(id,)); c.commit(); c.close(); return redirect("/admin")

@app.post("/admin/gallery/add")
@admin_required
def gallery_add():
    f=request.files.get("image"); title=request.form.get("title","").strip()
    if f and f.filename:
        ext=Path(f.filename).suffix.lower()
        if ext in {".jpg",".jpeg",".png",".webp"}:
            name=f"GAL-{secrets.token_hex(6)}{ext}"; f.save(UPLOADS/name)
            c=db(); c.execute("INSERT INTO gallery(title,image_path) VALUES(?,?)",(title,name)); c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/gallery/delete/<int:id>")
@admin_required
def gallery_delete(id):
    c=db(); row=c.execute("SELECT image_path FROM gallery WHERE id=?",(id,)).fetchone()
    if row:
        try: (UPLOADS/row["image_path"]).unlink(missing_ok=True)
        except: pass
    c.execute("DELETE FROM gallery WHERE id=?",(id,)); c.commit(); c.close(); return redirect("/admin")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
