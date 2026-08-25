
import os
import psycopg
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ["DATABASE_URL"]

with psycopg.connect(DATABASE_URL) as c:
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            registration_no TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            age INTEGER NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            village TEXT NOT NULL,
            gram_panchayat TEXT NOT NULL,
            primary_role TEXT NOT NULL,
            batting_style TEXT,
            bowling_style TEXT,
            photo_path TEXT,
            status TEXT DEFAULT 'Pending'
        );

        CREATE TABLE IF NOT EXISTS teams (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS fixtures (
            id SERIAL PRIMARY KEY,
            match_no TEXT,
            team1 TEXT,
            team2 TEXT,
            match_date TEXT,
            match_time TEXT,
            venue TEXT,
            status TEXT,
            result_text TEXT
        );

        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS points_table (
            id SERIAL PRIMARY KEY,
            team_name TEXT UNIQUE NOT NULL,
            played INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0,
            lost INTEGER DEFAULT 0,
            tied INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            nrr DOUBLE PRECISION DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS gallery (
            id SERIAL PRIMARY KEY,
            title TEXT,
            image_path TEXT
        );
    """)

    user = os.environ.get("UPL_ADMIN_USER", "admin")
    password = os.environ.get("UPL_ADMIN_PASSWORD")

    if not password:
        raise SystemExit("Set UPL_ADMIN_PASSWORD first.")

    c.execute("""
        INSERT INTO admins(username, password_hash)
        VALUES (%s, %s)
        ON CONFLICT(username)
        DO UPDATE SET password_hash = EXCLUDED.password_hash
    """, (user, generate_password_hash(password)))

    c.commit()

print("PostgreSQL database and admin account configured.")
