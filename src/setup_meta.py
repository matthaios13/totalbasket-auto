"""ΜΙΑ φορά: σύνδεση Instagram @totalbasketgr + Σελίδας Facebook Totalbasket.gr.
Παίρνει το μόνιμο token της Σελίδας από το Instagram Report (data/meta-tokens.json), ελέγχει ότι
μπορεί να ανεβάζει, και το βάζει στα GitHub secrets ΧΩΡΙΣ να εμφανιστεί πουθενά.

  python src/setup_meta.py
"""
import json
import shutil
import subprocess
from pathlib import Path

import requests

PAGE_ID = "101259165246257"
IG_ID = "17841445457808335"
REPO = "matthaios13/totalbasket-auto"
G = "https://graph.facebook.com/v23.0"

tok = json.load(open(Path.home() / "Documents/Instagram Report/data/meta-tokens.json"))[IG_ID]
me = requests.get(f"{G}/me", params={"fields": "id,name", "access_token": tok}, timeout=30).json()
if me.get("id") != PAGE_ID:
    raise SystemExit(f"✗ Το token δεν είναι της Σελίδας Totalbasket.gr: {me}")
ig = requests.get(f"{G}/{IG_ID}", params={"fields": "username", "access_token": tok}, timeout=30).json()
d = requests.get(f"{G}/debug_token", params={"input_token": tok, "access_token": tok}, timeout=30).json().get("data", {})
need = {"instagram_content_publish", "pages_manage_posts"}
if not need <= set(d.get("scopes", [])):
    raise SystemExit(f"✗ Λείπουν δικαιώματα: {need - set(d.get('scopes', []))}")
print(f"✓ Σελίδα: {me['name']} · Instagram: @{ig.get('username')} · " + ("δεν λήγει" if not d.get("expires_at") else "⚠️ λήγει"))

gh = shutil.which("gh") or str(Path.home() / ".local/bin/gh")
for k, v in {"IG_ACCESS_TOKEN": tok, "FB_PAGE_TOKEN": tok, "IG_USER_ID": IG_ID}.items():
    subprocess.run([gh, "secret", "set", k, "--repo", REPO], input=v, text=True, check=True, capture_output=True)
    print(f"✓ {k} αποθηκεύτηκε στο GitHub")
subprocess.run([gh, "variable", "set", "FB_PAGE_ID", "--repo", REPO, "--body", PAGE_ID], check=True, capture_output=True)
print("✓ FB_PAGE_ID αποθηκεύτηκε στο GitHub")
