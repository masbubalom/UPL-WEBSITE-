import os
import re
import secrets

import psycopg
import cloudinary
import cloudinary.uploader

from psycopg.rows import dict_row
from pathlib import Path
from functools import wraps

from flask import (
    Flask,
    request,
    jsonify,
    session,
    redirect,
    send_from_directory,
    render_template
)

from werkzeug.security import check_password_hash


# =========================================================
# CONFIGURATION
# =========================================================

BASE = Path(__file__).resolve().parent

DATABASE_URL = os.environ["DATABASE_URL"]


# =========================================================
# CLOUDINARY
# =========================================================

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"],
    secure=True
)


# Legacy/local uploads folder
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)


# =========================================================
# FLASK
# =========================================================

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

app.secret_key = os.environ.get(
    "UPL_SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# =========================================================
# CONSTANTS
# =========================================================

PANCHAYATS = [
    "Uttar Laxmipur",
    "Mothabari",
    "Uttar Panchanandapur-I",
    "Uttar Panchanandapur-II",
    "Gangaprasad",
    "Bangitola",
    "Rathbari",
    "Hamidpur",
    "Rajnagar"
]


ROLES = {
    "Batter",
    "Bowler",
    "All-Rounder"
}


BATTING = {
    "Right-hand Batsman",
    "Left-hand Batsman"
}


BOWLING = {
    "Right-hand Bowling",
    "Left-hand Bowling"
}


# =========================================================
# DATABASE HELPER
# =========================================================

class DBConnection:

    def __init__(self):

        self.c = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row
        )

    def execute(self, query, params=None):

        query = query.replace(
            "?",
            "%s"
        )

        return self.c.execute(
            query,
            params or ()
        )

    def commit(self):
        self.c.commit()

    def rollback(self):
        self.c.rollback()

    def close(self):
        self.c.close()


def db():
    return DBConnection()


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

def admin_required(fn):

    @wraps(fn)
    def wrapped(*a, **kw):

        if not session.get("admin"):
            return redirect("/admin/login")

        return fn(*a, **kw)

    return wrapped


# =========================================================
# REGISTRATION NUMBERS
# =========================================================

def next_reg(c):

    row = c.execute(
        """
        SELECT COALESCE(MAX(id), 0) + 1 AS next_id
        FROM players
        """
    ).fetchone()

    return f"UPL25-{row['next_id']:04d}"


def next_team_interest(c):

    row = c.execute(
        """
        SELECT COALESCE(MAX(id), 0) + 1 AS next_id
        FROM team_interest
        """
    ).fetchone()

    return f"UPL-TI-{row['next_id']:04d}"


# =========================================================
# GLOBAL TEMPLATE DATA
# =========================================================

@app.context_processor
def globals_():

    return {
        "panchayats": PANCHAYATS
    }


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    c = db()

    fixtures = c.execute(
        """
        SELECT *
        FROM fixtures
        ORDER BY match_date, match_time
        LIMIT 3
        """
    ).fetchall()

    news = c.execute(
        """
        SELECT *
        FROM news
        WHERE published = 1
        ORDER BY id DESC
        LIMIT 3
        """
    ).fetchall()

    points = c.execute(
        """
        SELECT *
        FROM points_table
        ORDER BY points DESC, nrr DESC
        """
    ).fetchall()

    teams = c.execute(
        """
        SELECT *
        FROM teams
        ORDER BY name
        """
    ).fetchall()

    c.close()

    return render_template(
        "home.html",
        fixtures=fixtures,
        news=news,
        points=points,
        teams=teams
    )


# =========================================================
# PLAYER REGISTRATION PAGE
# =========================================================

@app.get("/registration")
def registration():

    return render_template(
        "registration.html"
    )


# =========================================================
# PLAYER REGISTRATION API
# =========================================================

@app.post("/api/register")
def register():

    f = request.form

    name = f.get(
        "name",
        ""
    ).strip()

    age_raw = f.get(
        "age",
        ""
    ).strip()

    phone = re.sub(
        r"\D",
        "",
        f.get(
            "phone",
            ""
        )
    )

    email = f.get(
        "email",
        ""
    ).strip().lower()

    village = f.get(
        "village",
        ""
    ).strip()

    p = f.get(
        "panchayat",
        ""
    ).strip()

    role = f.get(
        "role",
        ""
    ).strip()

    bat = f.get(
        "battingHand",
        ""
    ).strip() or None

    bowl = f.get(
        "bowlingHand",
        ""
    ).strip() or None

    photo = request.files.get(
        "photo"
    )


    # Required fields

    if not all([
        name,
        age_raw,
        phone,
        email,
        village,
        p,
        role,
        photo
    ]):

        return jsonify(
            ok=False,
            error="Please complete all required fields."
        ), 400


    # Age

    try:

        age = int(age_raw)

    except Exception:

        return jsonify(
            ok=False,
            error="Age must be a number."
        ), 400


    if not 10 <= age <= 80:

        return jsonify(
            ok=False,
            error="Please enter a valid age."
        ), 400


    # Phone

    if len(phone) != 10:

        return jsonify(
            ok=False,
            error="Phone/WhatsApp number must be 10 digits."
        ), 400


    # Selection validation

    if p not in PANCHAYATS:

        return jsonify(
            ok=False,
            error="Invalid Gram Panchayat."
        ), 400


    if role not in ROLES:

        return jsonify(
            ok=False,
            error="Invalid player role."
        ), 400


    # Batter

    if role == "Batter":

        if bat not in BATTING:

            return jsonify(
                ok=False,
                error="Select batting style."
            ), 400

        bowl = None


    # Bowler

    elif role == "Bowler":

        if bowl not in BOWLING:

            return jsonify(
                ok=False,
                error="Select bowling style."
            ), 400

        bat = None


    # All Rounder

    else:

        if (
            bat not in BATTING
            or bowl not in BOWLING
        ):

            return jsonify(
                ok=False,
                error="Select both batting and bowling styles."
            ), 400


    # Photo extension

    ext = Path(
        photo.filename or ""
    ).suffix.lower()


    if ext not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    }:

        return jsonify(
            ok=False,
            error="Photo must be JPG, PNG or WebP."
        ), 400


    c = db()

    try:

        reg = next_reg(c)


        safe = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            name
        )[:40]


        # Cloudinary upload

        upload_result = cloudinary.uploader.upload(
            photo,
            folder="upl/players",
            public_id=f"{reg}_{safe}",
            resource_type="image"
        )


        photo_url = upload_result[
            "secure_url"
        ]


        # Database

        c.execute(
            """
            INSERT INTO players
            (
                registration_no,
                full_name,
                age,
                phone,
                email,
                village,
                gram_panchayat,
                primary_role,
                batting_style,
                bowling_style,
                photo_path,
                status
            )

            VALUES
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending')
            """,

            (
                reg,
                name,
                age,
                phone,
                email,
                village,
                p,
                role,
                bat,
                bowl,
                photo_url
            )
        )


        c.commit()


        return jsonify(
            ok=True,
            registration_no=reg
        )


    except psycopg.IntegrityError:

        c.rollback()

        return jsonify(
            ok=False,
            error="This phone number or e-mail is already registered."
        ), 409


    except Exception:

        c.rollback()

        return jsonify(
            ok=False,
            error="Registration failed. Please try again."
        ), 500


    finally:

        c.close()


# =========================================================
# TEAM INTEREST REGISTRATION PAGE
# =========================================================

@app.get("/team-registration")
def team_registration():

    return render_template(
        "team-registration.html"
    )


# =========================================================
# TEAM INTEREST REGISTRATION API
# =========================================================

@app.post("/api/team-interest")
def team_interest_submit():

    f = request.form


    team_name = f.get(
        "team_name",
        ""
    ).strip()


    representative_name = f.get(
        "representative_name",
        ""
    ).strip()


    phone = re.sub(
        r"\D",
        "",
        f.get(
            "phone",
            ""
        )
    )


    email = f.get(
        "email",
        ""
    ).strip().lower()


    village = f.get(
        "village",
        ""
    ).strip()


    panchayat = f.get(
        "panchayat",
        ""
    ).strip()


    # Required fields

    if not all([
        team_name,
        representative_name,
        phone,
        email,
        village,
        panchayat
    ]):

        return jsonify(
            ok=False,
            error="Please complete all required fields."
        ), 400


    # Phone validation

    if len(phone) != 10:

        return jsonify(
            ok=False,
            error="Phone/WhatsApp number must be 10 digits."
        ), 400


    # Panchayat validation

    if panchayat not in PANCHAYATS:

        return jsonify(
            ok=False,
            error="Invalid Gram Panchayat."
        ), 400


    c = db()

    try:

        interest_no = next_team_interest(c)


        # Current amount is only an interest/processing charge.
        # Official team registration fee is ₹5,000.

        c.execute(
            """
            INSERT INTO team_interest
            (
                interest_no,
                team_name,
                representative_name,
                phone,
                email,
                village,
                gram_panchayat,
                interest_amount,
                payment_status,
                status
            )

            VALUES
            (?,?,?,?,?,?,?,?,?,?)
            """,

            (
                interest_no,
                team_name,
                representative_name,
                phone,
                email,
                village,
                panchayat,
                100,
                "Pending",
                "Pending"
            )
        )


        c.commit()


        return jsonify(
            ok=True,
            interest_no=interest_no,
            message=(
                "Thank you for showing interest in UPL. "
                "Our organising committee will contact you "
                "shortly if a team slot is available."
            )
        )


    except psycopg.IntegrityError:

        c.rollback()

        return jsonify(
            ok=False,
            error="This application could not be submitted."
        ), 409


    except Exception:

        c.rollback()

        return jsonify(
            ok=False,
            error="Something went wrong. Please try again."
        ), 500


    finally:

        c.close()


# =========================================================
# PUBLIC TEAMS
# =========================================================

@app.get("/teams")
def teams():

    c = db()

    teams = c.execute(
        """
        SELECT *
        FROM teams
        ORDER BY name
        """
    ).fetchall()

    c.close()


    return render_template(
        "teams.html",
        teams=teams
    )


# =========================================================
# PUBLIC PLAYERS
# =========================================================

@app.get("/players")
def players():

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM players
        WHERE status='Approved'
        ORDER BY full_name
        """
    ).fetchall()

    c.close()


    return render_template(
        "players.html",
        players=rows
    )


# =========================================================
# PUBLIC FIXTURES
# =========================================================

@app.get("/fixtures")
def fixtures():

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM fixtures
        ORDER BY match_date, match_time, match_no
        """
    ).fetchall()

    c.close()


    return render_template(
        "fixtures.html",
        fixtures=rows
    )


# =========================================================
# PUBLIC POINTS TABLE
# =========================================================

@app.get("/points-table")
def pointstable():

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM points_table
        ORDER BY points DESC, nrr DESC, team_name
        """
    ).fetchall()

    c.close()


    return render_template(
        "points.html",
        points=rows
    )


# =========================================================
# PUBLIC NEWS
# =========================================================

@app.get("/news")
def news():

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM news
        WHERE published=1
        ORDER BY id DESC
        """
    ).fetchall()

    c.close()


    return render_template(
        "news.html",
        news=rows
    )


# =========================================================
# PUBLIC GALLERY
# =========================================================

@app.get("/gallery")
def gallery():

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM gallery
        ORDER BY id DESC
        """
    ).fetchall()

    c.close()


    return render_template(
        "gallery.html",
        gallery=rows
    )


# =========================================================
# LEGACY LOCAL UPLOADS
# =========================================================

@app.get("/uploads/<path:filename>")
def uploaded(filename):

    return send_from_directory(
        UPLOADS,
        filename
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.get("/admin/login")
def admin_login():

    return render_template(
        "login.html"
    )


@app.post("/admin/login")
def admin_login_post():

    u = request.form.get(
        "username",
        ""
    )

    pw = request.form.get(
        "password",
        ""
    )


    c = db()

    row = c.execute(
        """
        SELECT *
        FROM admins
        WHERE username=?
        """,
        (u,)
    ).fetchone()

    c.close()


    if row and check_password_hash(
        row["password_hash"],
        pw
    ):

        session["admin"] = True

        return redirect(
            "/admin"
        )


    return render_template(
        "login.html",
        error="Invalid username or password."
    ), 401


@app.get("/admin/logout")
def logout():

    session.clear()

    return redirect(
        "/admin/login"
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.get("/admin")
@admin_required
def admin():

    c = db()


    players = c.execute(
        """
        SELECT *
        FROM players
        ORDER BY id DESC
        """
    ).fetchall()


    teams = c.execute(
        """
        SELECT *
        FROM teams
        ORDER BY name
        """
    ).fetchall()


    fixtures = c.execute(
        """
        SELECT *
        FROM fixtures
        ORDER BY match_date, match_time
        """
    ).fetchall()


    news = c.execute(
        """
        SELECT *
        FROM news
        ORDER BY id DESC
        """
    ).fetchall()


    points = c.execute(
        """
        SELECT *
        FROM points_table
        ORDER BY points DESC, nrr DESC
        """
    ).fetchall()


    gallery = c.execute(
        """
        SELECT *
        FROM gallery
        ORDER BY id DESC
        """
    ).fetchall()


    # Team Interest Applications

    team_interests = c.execute(
        """
        SELECT *
        FROM team_interest
        ORDER BY id DESC
        """
    ).fetchall()


    c.close()


    return render_template(
        "admin.html",

        players=players,

        teams=teams,

        fixtures=fixtures,

        news=news,

        points=points,

        gallery=gallery,

        team_interests=team_interests
    )


# =========================================================
# PLAYER APPROVAL
# =========================================================

@app.post("/admin/player/<int:id>/<action>")
@admin_required
def player_action(id, action):

    if action not in {
        "Approved",
        "Rejected",
        "Pending"
    }:

        return redirect(
            "/admin"
        )


    c = db()


    c.execute(
        """
        UPDATE players
        SET status=?
        WHERE id=?
        """,
        (
            action,
            id
        )
    )


    c.commit()
    c.close()


    return redirect(
        "/admin"
    )


# =========================================================
# TEAM INTEREST MANAGEMENT
# =========================================================

@app.post("/admin/team-interest/<int:id>/<action>")
@admin_required
def team_interest_action(id, action):

    if action not in {
        "Approved",
        "Rejected",
        "Contacted",
        "Pending"
    }:

        return redirect(
            "/admin"
        )


    c = db()


    c.execute(
        """
        UPDATE team_interest
        SET status=?
        WHERE id=?
        """,
        (
            action,
            id
        )
    )


    c.commit()
    c.close()


    return redirect(
        "/admin"
    )


# =========================================================
# ADD TEAM
# =========================================================

@app.post("/admin/team/add")
@admin_required
def team_add():

    name = request.form.get(
        "name",
        ""
    ).strip()


    description = request.form.get(
        "description",
        ""
    ).strip()


    if name:

        c = db()


        c.execute(
            """
            INSERT INTO teams(
                nam
