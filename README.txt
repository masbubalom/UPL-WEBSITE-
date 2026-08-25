UPL 2025 COMPLETE WEBSITE
==========================

Included:
- Professional UPL homepage
- Player registration form
- SQLite database
- Player photo uploads
- Duplicate phone/email protection
- Conditional Batter/Bowler/All-Rounder fields
- Gram Panchayat dropdown with all 9 names
- Admin login
- Approve / Reject player registrations
- Teams management
- Fixtures management
- Points table management
- News / announcement management
- Gallery upload
- Public Teams / Players / Fixtures / Points / News / Gallery pages

QUICK START (local computer)
----------------------------
1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Install:
   pip install -r requirements.txt

4. Set admin password:
   Windows PowerShell:
     $env:UPL_ADMIN_PASSWORD="YOUR_STRONG_PASSWORD"
   macOS/Linux:
     export UPL_ADMIN_PASSWORD="YOUR_STRONG_PASSWORD"

   Optional:
     $env:UPL_ADMIN_USER="admin"
     $env:UPL_SECRET_KEY="LONG_RANDOM_SECRET"

5. Create/update admin:
   python setup_admin.py

6. Start:
   python app.py

7. Open:
   http://127.0.0.1:5000/
   Registration:
   http://127.0.0.1:5000/registration
   Admin:
   http://127.0.0.1:5000/admin/login

IMPORTANT FOR PUBLIC LAUNCH
---------------------------
The website needs a real server/hosting that supports Python/Flask and persistent storage.
Use HTTPS and a strong admin password. Do not expose the SQLite database file publicly.
Back up upl.db and uploads/.
For a production deployment, use a proper WSGI server and persistent disk.

UPL INFORMATION CURRENTLY SET
-----------------------------
Venue: Uttar Lakshmipur High School
Player registration: September
Matches: October and November
Prize details: To be announced
Rules: To be announced
Facebook: https://www.facebook.com/share/1H6PF4UPKz/
