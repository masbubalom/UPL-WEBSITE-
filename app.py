import os
import re
import secrets
from pathlib import Path
from functools import wraps

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


# ============================================================
# BASIC CONFIG
# ============================================================

BASE = Path(__file__).resolve().parent

DATABASE_URL = os.environ["DATABASE_URL"]

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

app.secret_key = os.environ.get(
    "UPL_SECRET_KEY",
    secrets.token_hex(32),
)

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# ============================================================
# CLOUDINARY
# ============================================================

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)


# ============================================================
# UPL DATA
# ============================================================

PANCHAYATS = [
    "Uttar Laxmipur",
    "Mothabari",
    "Uttar Panchanandapur-I",
    "Uttar Panchanandapur-II",
    "Gangaprasad",
    "Bangitola",
    "Rathbari",
    "Hamidpur",
    "Rajnagar",
]

ROLES = {
    "Batter",
    "Bowler",
    "All-Rounder",
}

BATTING = {
    "Right-hand Batsman",
    "Left-hand Batsman",
}

BOWLING = {
    "Right-hand Bowling",
    "Left-hand Bowling",
}


# ============================================================
# DATABASE
# ============================================================

class DBConnection:

    def __init__(self):
        self.c = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
        )

    def execute(self, query, params=None):
        query = query.replace("?", "%s")
        return self.c.execute(
            query,
            params or (),
        )

    def commit(self):
        self.c.commit()

    def rollback(self):
        self.c.rollback()

    def close(self):
        self.c.close()


def db():
    return DBConnection()


# ============================================================
# EXTRA DATABASE TABLE
# Team Registration Interest
# ============================================================

def create_extra_tables():

    c = None

    try:
        c = db()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS team_interests (
                id SERIAL PRIMARY KEY,
                interest_no TEXT UNIQUE NOT NULL,
                team_name TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                village TEXT NOT NULL,
                gram_panchayat TEXT NOT NULL,
                registration_fee INTEGER DEFAULT 5000,
                interest_charge INTEGER DEFAULT 100,
                payment_status TEXT DEFAULT 'Pending',
                status TEXT DEFAULT 'Interested',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        c.commit()

    except Exception as e:
        print(
            "EXTRA TABLE ERROR:",
            repr(e),
        )

        if c:
            c.rollback()

    finally:
        if c:
            c.close()


create_extra_tables()


# ============================================================
# ADMIN
# ============================================================

def admin_required(fn):

    @wraps(fn)
    def wrapped(*args, **kwargs):

        if not session.get("admin"):
            return redirect("/admin/login")

        return fn(*args, **kwargs)

    return wrapped


def next_player_registration(c):

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
        FROM team_interests
        """
    ).fetchone()

    return f"UPL-TI-{row['next_id']:04d}"


@app.context_processor
def global_variables():

    return {
        "panchayats": PANCHAYATS
    }


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    c = db()

    try:

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
            ORDER BY points DESC, nrr DESC, team_name
            """
        ).fetchall()

        teams = c.execute(
            """
            SELECT *
            FROM teams
            ORDER BY name
            """
        ).fetchall()

    finally:

        c.close()

    return render_template(
        "home.html",
        fixtures=fixtures,
        news=news,
        points=points,
        teams=teams,
    )


# ============================================================
# PLAYER REGISTRATION PAGE
# ============================================================

@app.get("/registration")
def registration():

    return render_template(
        "registration.html"
    )


# ============================================================
# PLAYER REGISTRATION API
# ============================================================

@app.post("/api/register")
def register():

    f = request.form

    name = f.get(
        "name",
        "",
    ).strip()

    age_raw = f.get(
        "age",
        "",
    ).strip()

    phone = re.sub(
        r"\D",
        "",
        f.get("phone", ""),
    )

    email = f.get(
        "email",
        "",
    ).strip().lower()

    village = f.get(
        "village",
        "",
    ).strip()

    panchayat = f.get(
        "panchayat",
        "",
    ).strip()

    role = f.get(
        "role",
        "",
    ).strip()

    batting = (
        f.get("battingHand", "").strip()
        or None
    )

    bowling = (
        f.get("bowlingHand", "").strip()
        or None
    )

    photo = request.files.get("photo")


    # --------------------------------------------------------
    # REQUIRED FIELDS
    # --------------------------------------------------------

    if not all([
        name,
        age_raw,
        phone,
        email,
        village,
        panchayat,
        role,
        photo,
    ]):

        return jsonify(
            ok=False,
            error="Please complete all required fields.",
        ), 400


    # --------------------------------------------------------
    # AGE
    # --------------------------------------------------------

    try:

        age = int(age_raw)

    except ValueError:

        return jsonify(
            ok=False,
            error="Age must be a number.",
        ), 400


    if age < 10 or age > 80:

        return jsonify(
            ok=False,
            error="Please enter a valid age.",
        ), 400


    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    if len(phone) != 10:

        return jsonify(
            ok=False,
            error="Phone/WhatsApp number must be 10 digits.",
        ), 400


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if panchayat not in PANCHAYATS:

        return jsonify(
            ok=False,
            error="Invalid panchayat selection.",
        ), 400


    if role not in ROLES:

        return jsonify(
            ok=False,
            error="Invalid role selection.",
        ), 400


    if role == "Batter":

        if batting not in BATTING:

            return jsonify(
                ok=False,
                error="Select batting style.",
            ), 400

        bowling = None


    elif role == "Bowler":

        if bowling not in BOWLING:

            return jsonify(
                ok=False,
                error="Select bowling style.",
            ), 400

        batting = None


    else:

        if (
            batting not in BATTING
            or bowling not in BOWLING
        ):

            return jsonify(
                ok=False,
                error="Select both batting and bowling styles.",
            ), 400


    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    ext = Path(
        photo.filename or ""
    ).suffix.lower()


    if ext not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:

        return jsonify(
            ok=False,
            error="Photo must be JPG, PNG or WebP.",
        ), 400


    c = db()

    try:

        registration_no = next_player_registration(c)


        safe_name = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            name,
        )[:40]


        if not os.environ.get(
            "CLOUDINARY_CLOUD_NAME"
        ):

            raise RuntimeError(
                "Cloudinary is not configured."
            )


        # ----------------------------------------------------
        # UPLOAD PHOTO TO CLOUDINARY
        # ----------------------------------------------------

        upload_result = cloudinary.uploader.upload(
            photo,
            folder="upl/players",
            public_id=(
                f"{registration_no}_{safe_name}"
            ),
            resource_type="image",
        )


        photo_url = upload_result[
            "secure_url"
        ]


        # ----------------------------------------------------
        # SAVE PLAYER
        # ----------------------------------------------------

        c.execute(
            """
            INSERT INTO players (
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
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'Pending'
            )
            """,
            (
                registration_no,
                name,
                age,
                phone,
                email,
                village,
                panchayat,
                role,
                batting,
                bowling,
                photo_url,
            ),
        )


        c.commit()


        return jsonify(
            ok=True,
            registration_no=registration_no,
        )


    except psycopg.IntegrityError:

        c.rollback()

        return jsonify(
            ok=False,
            error=(
                "This phone number or e-mail "
                "is already registered."
            ),
        ), 409


    except Exception as e:

        c.rollback()

        print(
            "PLAYER REGISTRATION ERROR:",
            repr(e),
        )

        return jsonify(
            ok=False,
            error="Registration failed. Please try again.",
        ), 500


    finally:

        c.close()


# ============================================================
# TEAM REGISTRATION / INTEREST PAGE
# ============================================================

@app.get("/team-registration")
def team_registration():

    return render_template(
        "team_registration.html"
    )


# ============================================================
# TEAM INTEREST API
# ============================================================

@app.post("/api/team-interest")
def team_interest():

    f = request.form


    team_name = f.get(
        "team_name",
        "",
    ).strip()

    contact_name = f.get(
        "contact_name",
        "",
    ).strip()

    phone = re.sub(
        r"\D",
        "",
        f.get("phone", ""),
    )

    email = f.get(
        "email",
        "",
    ).strip().lower()

    village = f.get(
        "village",
        "",
    ).strip()

    panchayat = f.get(
        "panchayat",
        "",
    ).strip()


    if not all([
        team_name,
        contact_name,
        phone,
        email,
        village,
        panchayat,
    ]):

        return jsonify(
            ok=False,
            error="Please complete all required fields.",
        ), 400


    if len(phone) != 10:

        return jsonify(
            ok=False,
            error="Phone number must be 10 digits.",
        ), 400


    if panchayat not in PANCHAYATS:

        return jsonify(
            ok=False,
            error="Invalid panchayat selection.",
        ), 400


    c = db()

    try:

        interest_no = next_team_interest(c)


        c.execute(
            """
            INSERT INTO team_interests (
                interest_no,
                team_name,
                contact_name,
                phone,
                email,
                village,
                gram_panchayat,
                registration_fee,
                interest_charge,
                payment_status,
                status
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                5000,
                100,
                'Pending',
                'Interested'
            )
            """,
            (
                interest_no,
                team_name,
                contact_name,
                phone,
                email,
                village,
                panchayat,
            ),
        )


        c.commit()


        return jsonify(
            ok=True,
            interest_no=interest_no,
            message=(
                "Thank you for showing interest. "
                "Our UPL Organising Committee will "
                "contact you soon if a team slot is available."
            ),
        )


    except Exception as e:

        c.rollback()

        print(
            "TEAM INTEREST ERROR:",
            repr(e),
        )

        return jsonify(
            ok=False,
            error="Unable to submit your interest right now.",
        ), 500


    finally:

        c.close()


# ============================================================
# PUBLIC TEAMS
# ============================================================

@app.get("/teams")
def teams():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM teams
            ORDER BY name
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "teams.html",
        teams=rows,
    )


# ============================================================
# PUBLIC PLAYERS
# ============================================================

@app.get("/players")
def players():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM players
            WHERE status = 'Approved'
            ORDER BY full_name
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "players.html",
        players=rows,
    )


# ============================================================
# PUBLIC FIXTURES
# ============================================================

@app.get("/fixtures")
def fixtures():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM fixtures
            ORDER BY match_date, match_time, match_no
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "fixtures.html",
        fixtures=rows,
    )


# ============================================================
# PUBLIC POINTS TABLE
# ============================================================

@app.get("/points-table")
def pointstable():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM points_table
            ORDER BY
                points DESC,
                nrr DESC,
                team_name
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "points.html",
        points=rows,
    )


# ============================================================
# PUBLIC NEWS
# ============================================================

@app.get("/news")
def news():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM news
            WHERE published = 1
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "news.html",
        news=rows,
    )


# ============================================================
# PUBLIC GALLERY
# ============================================================

@app.get("/gallery")
def gallery():

    c = db()

    try:

        rows = c.execute(
            """
            SELECT *
            FROM gallery
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        c.close()


    return render_template(
        "gallery.html",
        gallery=rows,
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.get("/admin/login")
def admin_login():

    return render_template(
        "login.html"
    )


@app.post("/admin/login")
def admin_login_post():

    username = request.form.get(
        "username",
        "",
    ).strip()

    password = request.form.get(
        "password",
        "",
    )


    c = db()

    try:

        row = c.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    finally:

        c.close()


    if row and check_password_hash(
        row["password_hash"],
        password,
    ):

        session["admin"] = True

        return redirect("/admin")


    return render_template(
        "login.html",
        error="Invalid username or password.",
    ), 401


@app.get("/admin/logout")
def logout():

    session.clear()

    return redirect(
        "/admin/login"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.get("/admin")
@admin_required
def admin():

    c = db()

    try:

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


        news_rows = c.execute(
            """
            SELECT *
         
