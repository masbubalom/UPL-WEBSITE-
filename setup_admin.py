
from pathlib import Path
import sqlite3, os
from werkzeug.security import generate_password_hash

BASE=Path(__file__).resolve().parent
DB=BASE/"upl.db"
user=os.environ.get("UPL_ADMIN_USER","admin")
password=os.environ.get("UPL_ADMIN_PASSWORD")
if not password:
    raise SystemExit("Set UPL_ADMIN_PASSWORD first.")
c=sqlite3.connect(DB)
c.execute("INSERT INTO admins(username,password_hash) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",
          (user,generate_password_hash(password)))
c.commit(); c.close()
print("Admin account configured for:", user)
