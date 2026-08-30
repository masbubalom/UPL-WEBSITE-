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
from flask import Flask, request, jsonify, session, redirect, render_template
from werkzeug.security import check_password_hash
try:
    import razorpay
except ImportError:
    razorpay = None

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.environ["DATABASE_URL"]
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("UPL_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
cloudinary.config(cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"), api_key=os.environ.get("CLOUDINARY_API_KEY"), api_secret=os.environ.get("CLOUDINARY_API_SECRET"), secure=True)
PANCHAYATS=["Uttar Laxmipur","Mothabari","Uttar Panchanandapur-I","Uttar Panchanandapur-II","Gangaprasad","Bangitola","Rathbari","Hamidpur","Rajnagar"]
ROLES={"Batter","Bowler","All-Rounder"}; BATTING={"Right-hand Batsman","Left-hand Batsman"}; BOWLING={"Right-hand Bowling","Left-hand Bowling"}
class DBConnection:
    def __init__(self): self.c=psycopg.connect(DATABASE_URL,row_factory=dict_row)
    def execute(self,q,p=None): return self.c.execute(q.replace("?","%s"),p or ())
    def commit(self): self.c.commit()
    def rollback(self): self.c.rollback()
    def close(self): self.c.close()
def db(): return DBConnection()
def create_extra_tables():
    c=None
    try:
        c=db(); c.execute("CREATE TABLE IF NOT EXISTS team_interest (id SERIAL PRIMARY KEY, interest_no TEXT UNIQUE NOT NULL, team_name TEXT NOT NULL, contact_name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL, village TEXT NOT NULL, gram_panchayat TEXT NOT NULL, registration_fee INTEGER DEFAULT 5000, interest_charge INTEGER DEFAULT 100, payment_status TEXT DEFAULT 'Pending', status TEXT DEFAULT 'Interested', razorpay_order_id TEXT, razorpay_payment_id TEXT, paid_amount INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        for sql in ["ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS paid_amount INTEGER DEFAULT 0","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS registration_fee INTEGER DEFAULT 5000","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS interest_charge INTEGER DEFAULT 100","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'Pending'","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Pending'","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS contact_name TEXT","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS representative_name TEXT","ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS payment_reference TEXT","ALTER TABLE points_table ADD COLUMN IF NOT EXISTS group_name TEXT DEFAULT 'A'","ALTER TABLE players ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'Paid'","ALTER TABLE players ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT","ALTER TABLE players ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT","ALTER TABLE players ADD COLUMN IF NOT EXISTS paid_amount INTEGER DEFAULT 0"]: c.execute(sql)
        c.execute("UPDATE team_interest SET contact_name=representative_name WHERE contact_name IS NULL AND representative_name IS NOT NULL")
        c.execute("CREATE TABLE IF NOT EXISTS player_payment (id SERIAL PRIMARY KEY, registration_no TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, age INTEGER NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL, village TEXT NOT NULL, gram_panchayat TEXT NOT NULL, primary_role TEXT NOT NULL, batting_style TEXT, bowling_style TEXT, photo_path TEXT, amount INTEGER NOT NULL DEFAULT 100, payment_status TEXT DEFAULT 'Created', razorpay_order_id TEXT UNIQUE, razorpay_payment_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"); c.commit()
    except Exception as e:
        print('EXTRA TABLE ERROR:',repr(e));
        if c: c.rollback()
    finally:
        if c: c.close()
create_extra_tables()
def admin_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('admin'): return redirect('/admin/login')
        return fn(*args,**kwargs)
    return wrapped
def next_reg(c):
    while True:
        n=f"UPL26-{secrets.token_hex(4).upper()[:6]}"
        if not c.execute('SELECT 1 FROM players WHERE registration_no=?',(n,)).fetchone(): return n
def next_team_interest(c):
    while True:
        n=f"UPL-26-TI-{secrets.token_hex(4).upper()[:6]}"
        if not c.execute('SELECT 1 FROM team_interest WHERE interest_no=?',(n,)).fetchone(): return n
@app.context_processor
def global_variables(): return {'panchayats':PANCHAYATS}
@app.get('/')
def home():
    c=db()
    try: fixtures=c.execute('SELECT * FROM fixtures ORDER BY match_date,match_time LIMIT 3').fetchall(); news=c.execute('SELECT * FROM news WHERE published=1 ORDER BY id DESC LIMIT 3').fetchall(); points=c.execute('SELECT * FROM points_table ORDER BY group_name,points DESC,nrr DESC,team_name').fetchall(); teams=c.execute('SELECT * FROM teams ORDER BY name').fetchall()
    finally: c.close()
    return render_template('home.html',fixtures=fixtures,news=news,points=points,teams=teams)
@app.get('/registration')
def registration(): return render_template('registration.html',player_registration_fee=int(os.environ.get('PLAYER_REGISTRATION_FEE','100')))
@app.post('/api/register')
def register(): return jsonify(ok=False,error='Please use the secure payment registration form.'),400
@app.get('/team-registration')
def team_registration(): return render_template('team_registration.html',razorpay_key_id=os.environ.get('RAZORPAY_KEY_ID',''))
@app.get('/teams')
def teams():
    c=db()
    try: rows=c.execute('SELECT * FROM teams ORDER BY name').fetchall()
    finally: c.close()
    return render_template('teams.html',teams=rows)
@app.get('/players')
def players():
    c=db()
    try: rows=c.execute("SELECT * FROM players WHERE status='Approved' ORDER BY full_name").fetchall()
    finally: c.close()
    return render_template('players.html',players=rows)
@app.get('/fixtures')
def fixtures():
    c=db()
    try: rows=c.execute('SELECT * FROM fixtures ORDER BY match_date,match_time').fetchall()
    finally: c.close()
    return render_template('fixtures.html',fixtures=rows)
@app.get('/points-table')
def pointstable():
    c=db()
    try: rows=c.execute('SELECT * FROM points_table ORDER BY group_name,points DESC,nrr DESC,team_name').fetchall()
    finally: c.close()
    return render_template('points.html',points=rows)
@app.get('/news')
def news():
    c=db()
    try: rows=c.execute('SELECT * FROM news WHERE published=1 ORDER BY id DESC').fetchall()
    finally: c.close()
    return render_template('news.html',news=rows)
@app.get('/gallery')
def gallery():
    c=db()
    try: rows=c.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall()
    finally: c.close()
    return render_template('gallery.html',gallery=rows)
@app.get('/admin/login')
def admin_login(): return render_template('login.html')
@app.post('/admin/login')
def admin_login_post():
    username=request.form.get('username','').strip(); password=request.form.get('password',''); c=db()
    try: row=c.execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone()
    finally: c.close()
    if row and check_password_hash(row['password_hash'],password): session['admin']=True; return redirect('/admin')
    return render_template('login.html',error='Invalid username or password.'),401
@app.get('/admin/logout')
def logout(): session.clear(); return redirect('/admin/login')
@app.get('/admin')
@admin_required
def admin():
    c=db()
    try:
        players=c.execute('SELECT * FROM players ORDER BY id DESC').fetchall(); teams=c.execute('SELECT * FROM teams ORDER BY name').fetchall(); fixtures=c.execute('SELECT * FROM fixtures ORDER BY match_date,match_time').fetchall(); news_rows=c.execute('SELECT * FROM news ORDER BY id DESC').fetchall(); points=c.execute('SELECT * FROM points_table ORDER BY group_name,points DESC,nrr DESC,team_name').fetchall(); gallery_rows=c.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall(); team_interest=c.execute('SELECT * FROM team_interest ORDER BY id DESC').fetchall()
    finally: c.close()
    return render_template('admin.html',players=players,teams=teams,fixtures=fixtures,news=news_rows,points=points,gallery=gallery_rows,team_interest=team_interest)
@app.post('/admin/player/<int:id>/<action>')
@admin_required
def player_action(id,action):
    if action not in {'Approved','Rejected','Pending'}: return redirect('/admin')
    c=db()
    try: c.execute('UPDATE players SET status=? WHERE id=?',(action,id)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/player/<int:id>/delete')
@admin_required
def player_delete(id):
    c=db()
    try: c.execute('DELETE FROM players WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/team-interest/<int:id>/delete')
@admin_required
def team_interest_delete(id):
    c=db()
    try: c.execute('DELETE FROM team_interest WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/team/add')
@admin_required
def team_add():
    name=request.form.get('name','').strip(); description=request.form.get('description','').strip(); c=db()
    try:
        if name: c.execute('INSERT INTO teams(name,description) VALUES(?,?) ON CONFLICT(name) DO NOTHING',(name,description)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/team/delete/<int:id>')
@admin_required
def team_delete(id):
    c=db()
    try: c.execute('DELETE FROM teams WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/team-interest/<int:id>/<status>')
@admin_required
def team_interest_status(id,status):
    if status not in {'Interested','Contacted','Approved','Rejected'}: return redirect('/admin')
    c=db()
    try: c.execute('UPDATE team_interest SET status=? WHERE id=?',(status,id)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/fixture/add')
@admin_required
def fixture_add():
    f=request.form; c=db()
    try:
        c.execute('INSERT INTO fixtures(match_no,team1,team2,match_date,match_time,venue,status,result_text) VALUES(?,?,?,?,?,?,?,?)',(f.get('match_no') or None,f.get('team1','').strip(),f.get('team2','').strip(),f.get('date') or None,f.get('time') or None,f.get('venue') or 'Uttar Lakshmipur High School',f.get('status') or 'Upcoming',f.get('result') or '')); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/fixture/<int:id>/edit')
@admin_required
def fixture_edit(id):
    f=request.form; status=f.get('status','Upcoming').strip(); result=f.get('result','').strip(); team1=f.get('team1','').strip(); team2=f.get('team2','').strip()
    if status not in {'Upcoming','Live','Completed'}: return redirect('/admin')
    if status=='Completed' and not result: result='Result not entered yet.'
    c=db()
    try:
        c.execute('UPDATE fixtures SET match_no=?,team1=?,team2=?,match_date=?,match_time=?,venue=?,status=?,result_text=? WHERE id=?',(f.get('match_no') or None,team1,team2,f.get('date') or None,f.get('time') or None,f.get('venue') or 'Uttar Lakshmipur High School',status,result,id)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/fixture/delete/<int:id>')
@admin_required
def fixture_delete(id):
    c=db()
    try: c.execute('DELETE FROM fixtures WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')

@app.post('/admin/news/<int:id>/edit')
@admin_required
def news_edit(id):
    title=request.form.get('title','').strip()
    body=request.form.get('body','').strip()
    c=db()
    try:
        if title and body:
            c.execute('UPDATE news SET title=?, body=? WHERE id=?',(title,body,id))
            c.commit()
    finally:
        c.close()
    return redirect('/admin')

@app.post('/admin/gallery/<int:id>/edit')
@admin_required
def gallery_edit(id):
    title=request.form.get('title','').strip()
    image=request.files.get('image')
    c=None
    try:
        if image and image.filename:
            if Path(image.filename).suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
                return redirect('/admin')
            if not os.environ.get('CLOUDINARY_CLOUD_NAME'):
                return redirect('/admin')
            r=cloudinary.uploader.upload(image,folder='upl/gallery',resource_type='image')
            c=db()
            c.execute('UPDATE gallery SET title=?, image_path=? WHERE id=?',(title,r['secure_url'],id))
        else:
            c=db()
            c.execute('UPDATE gallery SET title=? WHERE id=?',(title,id))
        c.commit()
    except Exception as e:
        print('GALLERY EDIT ERROR:',repr(e))
        if c: c.rollback()
    finally:
        if c: c.close()
    return redirect('/admin')

@app.post('/admin/news/add')
@admin_required
def news_add():
    title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); c=db()
    try:
        if title and body: c.execute('INSERT INTO news(title,body,published) VALUES(?,?,1)',(title,body)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/news/delete/<int:id>')
@admin_required
def news_delete(id):
    c=db()
    try: c.execute('DELETE FROM news WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/points/add')
@admin_required
def points_add():
    f=request.form; team=f.get('team_name','').strip(); group=f.get('group_name','A').strip().upper(); c=db()
    try:
        if team and group in {'A','B'}: c.execute('INSERT INTO points_table(team_name,group_name,played,won,lost,tied,points,nrr) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(team_name) DO UPDATE SET group_name=EXCLUDED.group_name,played=EXCLUDED.played,won=EXCLUDED.won,lost=EXCLUDED.lost,tied=EXCLUDED.tied,points=EXCLUDED.points,nrr=EXCLUDED.nrr',(team,group,int(f.get('played') or 0),int(f.get('won') or 0),int(f.get('lost') or 0),int(f.get('tied') or 0),int(f.get('points') or 0),float(f.get('nrr') or 0))); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/points/delete/<int:id>')
@admin_required
def points_delete(id):
    c=db()
    try: c.execute('DELETE FROM points_table WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.post('/admin/gallery/add')
@admin_required
def gallery_add():
    image=request.files.get('image'); title=request.form.get('title','').strip(); c=None
    if image and image.filename and Path(image.filename).suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:
        try:
            if not os.environ.get('CLOUDINARY_CLOUD_NAME'): raise RuntimeError('Cloudinary is not configured.')
            r=cloudinary.uploader.upload(image,folder='upl/gallery',resource_type='image'); c=db(); c.execute('INSERT INTO gallery(title,image_path) VALUES(?,?)',(title,r['secure_url'])); c.commit()
        except Exception as e:
            print('GALLERY ERROR:',repr(e));
            if c: c.rollback()
        finally:
            if c: c.close()
    return redirect('/admin')
@app.post('/admin/gallery/delete/<int:id>')
@admin_required
def gallery_delete(id):
    c=db()
    try: c.execute('DELETE FROM gallery WHERE id=?',(id,)); c.commit()
    finally: c.close()
    return redirect('/admin')
@app.get('/health')
def health(): return jsonify(status='ok',service='UPL Website')
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)

@app.after_request
def add_admin_delete_controls(response):
    if request.path == '/admin' and response.content_type.startswith('text/html'):
        script = """<style>.admin-delete-btn{margin-left:6px!important;background:#5b1720!important;color:#fff!important;border:1px solid #8b2330!important}</style><script>document.addEventListener('DOMContentLoaded',function(){function addDelete(section,endpoint,confirmText){var box=document.getElementById(section);if(!box)return;box.querySelectorAll('table tbody tr').forEach(function(row){var cells=row.querySelectorAll('td');if(!cells.length)return;var idMatch=row.innerHTML.match(/(?:player|team-interest)\/(\d+)/);if(!idMatch)return;var id=idMatch[1];var cell=cells[cells.length-1];if(cell.querySelector('.admin-delete-btn'))return;var form=document.createElement('form');form.method='post';form.action=endpoint.replace('__ID__',id);form.style.display='inline';var b=document.createElement('button');b.type='submit';b.className='btn small danger admin-delete-btn';b.textContent='DELETE';b.onclick=function(){return confirm(confirmText)};form.appendChild(b);cell.appendChild(form);});}addDelete('players','/admin/player/__ID__/delete','Delete this player registration permanently?');addDelete('team-applications','/admin/team-interest/__ID__/delete','Delete this team application permanently?');});</script>"""
        data = response.get_data(as_text=True)
        data = data.replace('</body>', script + '</body>')
        response.set_data(data)
    return response
