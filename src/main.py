"""Αναρτήσεις Total Basket (τρέχει στο GitHub): στις ώρες του config παίρνει το επόμενο έτοιμο ρετρό
από την ουρά (branch "queue", που τη γεμίζει το Mac με το prepare.py) και το ανεβάζει σε
YouTube (Shorts), Instagram (Reels) και Facebook (Reels).

  python src/main.py --check   # γράφει due=true/false (για το workflow)
  python src/main.py           # ανάρτηση αν είναι ώρα
  python src/main.py --force   # ανάρτηση τώρα
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "posted.json"
QUEUE = ROOT / "queue"          # checkout του branch "queue"
LOW_QUEUE = 6


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"posted_ids": [], "log": []}


def save_state(state):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def load_cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def due_slot(cfg, state, now):
    sch = cfg["schedule"]
    done = {e["slot"] for e in state["log"] if e.get("ok")}
    slots = (sch.get("overrides") or {}).get(now.strftime("%Y-%m-%d"), sch["slots"])
    for hhmm in reversed(slots):
        h, m = map(int, hhmm.split(":"))
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = t.strftime("%Y-%m-%d %H:%M")
        if t <= now < t + timedelta(hours=sch["grace_hours"]) and key not in done:
            return key
    return None


def pending(state):
    manifest = QUEUE / "manifest.json"
    if not manifest.exists():
        return []
    posted = set(state["posted_ids"])
    return [i for i in json.loads(manifest.read_text()) if i not in posted]


def public_url(item_id):
    repo = os.environ.get("GITHUB_REPOSITORY", "matthaios13/totalbasket-auto")
    return f"https://raw.githubusercontent.com/{repo}/queue/{item_id}.mp4"


def fetch_video(item_id):
    import tempfile
    import requests
    path = Path(tempfile.mkdtemp()) / f"{item_id}.mp4"
    with requests.get(public_url(item_id), stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return path


def open_issue(title, body):
    if not os.environ.get("GITHUB_ACTIONS"):
        print(title, body)
        return
    subprocess.run(["gh", "issue", "create", "--title", title, "--body", body])


def review_youtube(cfg, state):
    """Ιδιωτικά Shorts που ανέβηκαν πριν από ≥ N λεπτά: αν είναι καθαρά γίνονται δημόσια."""
    pub = cfg["publish"]
    if not pub.get("youtube") or not pub.get("youtube_auto_public"):
        return False
    import publish
    now = datetime.now(ZoneInfo("UTC"))
    min_wait = timedelta(minutes=pub.get("youtube_review_minutes", 30))
    changed = False
    for e in state["log"]:
        if e.get("yt_state") != "pending":
            continue
        uploaded = datetime.fromisoformat(e["yt_uploaded"])
        if now - uploaded < min_wait:
            continue
        try:
            verdict, why = publish.youtube_check(e["yt_id"])
        except Exception as ex:
            print(f"YouTube έλεγχος {e['yt_id']}: σφάλμα {ex}")
            continue
        if verdict == "wait" and now - uploaded < timedelta(hours=48):
            continue
        if verdict == "ok":
            publish.youtube_make_public(e["yt_id"])
            e["yt_state"] = "public"
            print(f"YouTube {e['yt_id']}: καθαρό → ΔΗΜΟΣΙΟ")
        else:
            e["yt_state"], e["yt_reason"] = "held", why
            open_issue(f"YouTube: έμεινε ιδιωτικό — {e['source_title']}",
                       f"Το https://youtube.com/shorts/{e['yt_id']} δεν έγινε δημόσιο.\nΛόγος: {why}")
            print(f"YouTube {e['yt_id']}: ΚΡΑΤΙΕΤΑΙ ιδιωτικό ({why})")
        changed = True
    return changed


def notify_low_queue(left):
    if left > LOW_QUEUE or not os.environ.get("GITHUB_ACTIONS"):
        return
    title = "Total Basket: η ουρά βίντεο αδειάζει — άνοιξε το Mac"
    found = subprocess.run(["gh", "issue", "list", "--state", "open", "--search", title, "--json", "number"],
                           capture_output=True, text=True).stdout
    if found.strip() in ("", "[]"):
        subprocess.run(["gh", "issue", "create", "--title", title, "--body",
                        f"Έχουν μείνει {left} έτοιμα βίντεο. Άνοιξε το Mac για να ετοιμάσει καινούρια."])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--review-now", action="store_true")
    ap.add_argument("--youtube-check", action="store_true")
    ap.add_argument("--facebook-check", action="store_true")
    args = ap.parse_args()

    cfg, state = load_cfg(), load_state()
    if args.youtube_check:
        import publish
        print("Συνδεδεμένο κανάλι YouTube:", publish.youtube_channel())
        return
    if args.facebook_check:
        import publish
        print("Facebook:", publish.facebook_check())
        return
    if args.review or args.review_now:
        if args.review_now:
            cfg["publish"]["youtube_review_minutes"] = 0
        if review_youtube(cfg, state):
            save_state(state)
        return

    now = datetime.now(ZoneInfo(cfg["schedule"]["timezone"]))
    slot = due_slot(cfg, state, now) if cfg.get("active") else None
    if args.force:
        slot = slot or now.strftime("%Y-%m-%d %H:%M") + " (manual)"
    if args.check:
        print(f"due={'true' if slot else 'false'}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"due={'true' if slot else 'false'}\n")
        return
    if not slot:
        print(f"{now:%H:%M} — δεν είναι ώρα ανάρτησης (ή active: false).")
        return

    queue = pending(state)
    if not queue:
        notify_low_queue(0)
        sys.exit("Η ουρά είναι άδεια — δεν υπάρχει έτοιμο βίντεο.")
    item_id = queue[0]
    meta = json.loads((QUEUE / f"{item_id}.json").read_text())
    video_url = public_url(item_id)
    print(f"[{slot}] {meta['source_title']} → {meta['youtube_title']}")

    import publish
    entry = {"slot": slot, "source_id": item_id, "source_title": meta["source_title"],
             "title": meta["youtube_title"], "ok": False}
    errors, pub = [], cfg["publish"]
    text = f"{meta['youtube_title'].replace(' #shorts', '')}\n\n{meta['full_description']}"
    if pub.get("youtube"):
        try:
            yt_id = publish.youtube_upload(fetch_video(item_id), meta["youtube_title"], meta["full_description"],
                                           privacy="private", paid_promotion=pub.get("youtube_paid_promotion", False))
            entry.update(youtube=f"https://youtube.com/shorts/{yt_id}", yt_id=yt_id,
                         yt_uploaded=datetime.now(ZoneInfo("UTC")).isoformat(),
                         yt_state="pending" if pub.get("youtube_auto_public") else "private")
            print("YouTube (ιδιωτικό):", entry["youtube"])
        except Exception as e:
            errors.append(f"YouTube: {e}")
    if pub.get("instagram"):
        try:
            entry["instagram"] = publish.instagram_upload(video_url, text)
            print("Instagram:", entry["instagram"])
        except Exception as e:
            errors.append(f"Instagram: {e}")
    if pub.get("instagram_story"):
        try:
            entry["story"] = publish.instagram_upload(video_url, "", story=True)
            print("Instagram Story:", entry["story"])
        except Exception as e:
            errors.append(f"Instagram Story: {e}")
    if pub.get("facebook"):
        try:
            entry["facebook"] = publish.facebook_reel_upload(video_url, text)
            print("Facebook:", entry["facebook"])
        except Exception as e:
            errors.append(f"Facebook: {e}")

    entry["ok"] = bool(entry.get("youtube") or entry.get("instagram") or entry.get("facebook"))
    entry["errors"] = errors
    if entry["ok"]:
        state["posted_ids"].append(item_id)
    state["log"].append(entry)
    save_state(state)
    notify_low_queue(len(queue) - (1 if entry["ok"] else 0))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
