"""Ρετρό μπάσκετ για το Total Basket: διαβάζει τους τίτλους των καναλιών-πηγών και διαλέγει ματς.

Χωρίς AI: ομάδες, σκορ και σεζόν βγαίνουν ΜΟΝΟ από τον τίτλο του βίντεο με σταθερούς κανόνες.
Αν κάτι δεν διαβάζεται με σιγουριά, το βίντεο απλώς δεν χρησιμοποιείται.

Κρατάμε: κλιπ ≤ max_seconds, με σκορ μπάσκετ (και τα δύο 35–160), με τουλάχιστον μία ελληνική ομάδα
(ή την Εθνική), έως τη σεζόν newest_season. Όχι: Α2/Β' Εθνική, φιλικά, τουρνουά, μικρές ηλικίες, γυναικεία.
Εναλλαγή: τελικός → ντέρμπι → Ευρώπη → πρωτάθλημα → ντέρμπι → Ευρώπη → Εθνική, από όλες τις ομάδες
και όλες τις δεκαετίες (πρώτα ό,τι έχει ανέβει λιγότερο).
"""
import json
import random
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path

import yt_dlp

# ---------------------------------------------------------------- ομάδες
# κανονικό όνομα (κεφαλαία) ← παραλλαγές όπως γράφονται στους τίτλους (χωρίς τόνους, κεφαλαία)
GREEK = {
    "ΠΑΝΑΘΗΝΑΪΚΟΣ": ["ΠΑΝΑΘΗΝΑΙΚΟΣ", "ΠΑΟ", "PANATHINAIKOS", "PANATHINAIKOS ATHENS", "PAO"],
    "ΟΛΥΜΠΙΑΚΟΣ": ["ΟΛΥΜΠΙΑΚΟΣ", "ΟΣΦΠ", "OLYMPIACOS", "OLYMPIAKOS", "OLYMPIACOS PIRAEUS"],
    "ΑΕΚ": ["ΑΕΚ", "AEK", "AEK ATHENS", "A.E.K."],
    "ΠΑΟΚ": ["ΠΑΟΚ", "PAOK", "P.A.O.K.", "PAOK THESSALONIKI"],
    "ΑΡΗΣ": ["ΑΡΗΣ", "ΑΡΗΣ Θ.", "ΑΡΗΣ ΘΕΣΣΑΛΟΝΙΚΗΣ", "ARIS", "ARIS THESSALONIKI", "ARIS BC"],
    "ΠΑΝΙΩΝΙΟΣ": ["ΠΑΝΙΩΝΙΟΣ", "PANIONIOS"], "ΜΑΡΟΥΣΙ": ["ΜΑΡΟΥΣΙ", "MAROUSSI", "MAROUSI"],
    "ΠΕΡΙΣΤΕΡΙ": ["ΠΕΡΙΣΤΕΡΙ", "PERISTERI"], "ΗΡΑΚΛΗΣ": ["ΗΡΑΚΛΗΣ", "ΗΡΑΚΛΗΣ Θ.", "IRAKLIS"],
    "ΠΑΝΕΛΛΗΝΙΟΣ": ["ΠΑΝΕΛΛΗΝΙΟΣ", "PANELLINIOS"], "ΙΩΝΙΚΟΣ ΝΙΚΑΙΑΣ": ["ΙΩΝΙΚΟΣ", "ΙΩΝΙΚΟΣ ΝΙΚΑΙΑΣ", "IONIKOS"],
    "ΚΟΛΟΣΣΟΣ ΡΟΔΟΥ": ["ΚΟΛΟΣΣΟΣ", "ΚΟΛΟΣΣΟΣ Ρ.", "KOLOSSOS"], "ΑΠΟΛΛΩΝ ΠΑΤΡΑΣ": ["ΑΠΟΛΛΩΝ Π.", "ΑΠΟΛΛΩΝ ΠΑΤΡΩΝ", "ΑΠΟΛΛΩΝ ΠΑΤΡΑΣ"],
    "ΣΠΟΡΤΙΓΚ": ["ΣΠΟΡΤΙΓΚ", "SPORTING"], "ΠΑΓΚΡΑΤΙ": ["ΠΑΓΚΡΑΤΙ"], "ΔΑΦΝΗ": ["ΔΑΦΝΗ"],
    "ΗΦΑΙΣΤΟΣ": ["ΗΦΑΙΣΤΟΣ"], "ΡΕΘΥΜΝΟ": ["ΡΕΘΥΜΝΟ", "RETHYMNO"], "ΛΑΡΙΣΑ": ["ΛΑΡΙΣΑ", "LARISA"],
    "ΤΡΙΚΑΛΑ": ["ΤΡΙΚΑΛΑ", "TRIKALA"], "ΚΑΟΔ": ["ΚΑΟΔ", "KAOD"], "ΚΑΒΑΛΑ": ["ΚΑΒΑΛΑ", "KAVALA"],
    "ΑΙΓΑΛΕΩ": ["ΑΙΓΑΛΕΩ"], "ΠΑΠΑΓΟΥ": ["ΠΑΠΑΓΟΥ"], "ΜΑΚΕΔΟΝΙΚΟΣ": ["ΜΑΚΕΔΟΝΙΚΟΣ"], "ΗΛΥΣΙΑΚΟΣ": ["ΗΛΥΣΙΑΚΟΣ"],
    "ΕΣΠΕΡΟΣ ΚΑΛΛΙΘΕΑΣ": ["ΕΣΠΕΡΟΣ", "ΕΣΠΕΡΟΣ Κ."], "ΦΑΡΟΣ ΚΕΡΑΤΣΙΝΙΟΥ": ["ΦΑΡΟΣ", "ΦΑΡΟΣ ΚΕΡ."],
    "ΠΕΙΡΑΙΚΟΣ": ["ΠΕΙΡΑΙΚΟΣ"], "ΚΗΦΙΣΙΑ": ["ΚΗΦΙΣΙΑ", "KIFISIA"], "ΠΡΟΜΗΘΕΑΣ": ["ΠΡΟΜΗΘΕΑΣ", "PROMITHEAS"],
    "ΕΛΛΑΔΑ": ["ΕΛΛΑΔΑ", "ΕΘΝΙΚΗ ΕΛΛΑΔΟΣ", "ΕΘΝΙΚΗ ΕΛΛΑΔΑΣ", "GREECE", "HELLAS"],
}
BIG = {"ΠΑΝΑΘΗΝΑΪΚΟΣ", "ΟΛΥΜΠΙΑΚΟΣ", "ΑΕΚ", "ΠΑΟΚ", "ΑΡΗΣ"}
# Γνωστοί ξένοι αντίπαλοι: ελληνική απόδοση (οι υπόλοιποι μένουν όπως γράφονται)
FOREIGN = {
    "ΡΕΑΛ ΜΑΔΡΙΤΗΣ": ["REAL MADRID", "ΡΕΑΛ", "ΡΕΑΛ Μ.", "ΡΕΑΛ ΜΑΔΡΙΤΗΣ"], "ΜΠΑΡΤΣΕΛΟΝΑ": ["BARCELONA", "ΜΠΑΡΤΣΕΛΟΝΑ", "FC BARCELONA"],
    "ΤΣΣΚΑ ΜΟΣΧΑΣ": ["CSKA MOSCOW", "ΤΣΣΚΑ ΜΟΣΧΑΣ"], "ΜΑΚΑΜΠΙ ΤΕΛ ΑΒΙΒ": ["MACCABI TEL AVIV", "ΜΑΚΑΜΠΙ ΤΕΛ ΑΒΙΒ"],
    "ΦΕΝΕΡΜΠΑΧΤΣΕ": ["FENERBAHCE", "FENERBAHCE ULKER", "FENERBAHCE/ULKER", "ΦΕΝΕΡΜΠΑΧΤΣΕ"], "ΠΑΡΤΙΖΑΝ": ["PARTIZAN", "ΠΑΡΤΙΖΑΝ"],
    "ΓΙΟΥΓΚΟΠΛΑΣΤΙΚΑ": ["JUGOPLASTIKA", "ΓΙΟΥΓΚΟΠΛΑΣΤΙΚΑ"], "ΤΣΙΜΠΟΝΑ": ["CIBONA", "ΤΣΙΜΠΟΝΑ"], "ΜΠΕΝΕΤΟΝ": ["BENETTON", "BENETTON TREVISO", "ΜΠΕΝΕΤΟΝ"],
    "ΒΙΡΤΟΥΣ ΜΠΟΛΟΝΙΑ": ["VIRTUS", "KINDER BOLOGNA", "VIRTUS BOLOGNA", "KINDER"], "ΠΑΝΑΘΗΝΑΪΚΟΣ": [],
    "ΜΟΝΤΕΠΑΣΚΙ ΣΙΕΝΑ": ["MONTEPASCHI", "MONTEPASCHI SIENA", "SIENA"], "ΜΠΑΓΙΕΡΝ": ["BAYERN", "BAYERN MUNICH"],
    "ΕΦΕΣ": ["EFES", "ANADOLU EFES", "EFES PILSEN"], "ΖΑΛΓΚΙΡΙΣ": ["ZALGIRIS", "ZALGIRIS KAUNAS", "ΖΑΛΓΚΙΡΙΣ"],
    "ΕΡΥΘΡΟΣ ΑΣΤΕΡΑΣ": ["CRVENA ZVEZDA", "RED STAR", "ΕΡΥΘΡΟΣ ΑΣΤΕΡΑΣ"], "ΣΑΡΑΓΟΣΑ": ["ZARAGOZA", "CAI ZARAGOZA", "ΣΑΡΑΓΟΣΑ"],
    "ΣΤΕΦΑΝΕΛ ΤΡΙΕΣΤΕ": ["STEFANEL TRIESTE", "STEFANEL"], "ΣΚΑΒΟΛΙΝΙ ΠΕΖΑΡΟ": ["SCAVOLINI", "SCAVOLINI PESARO"],
    "ΤΡΕΪΣΕΡ ΜΙΛΑΝΟ": ["TRACER", "TRACER MILANO"], "ΧΟΥΒΕΝΤΟΥΤ": ["JOVENTUT", "JOVENTUT BADALONA"],
    "ΟΛΙΜΠΙΑ ΛΙΟΥΜΠΛΙΑΝΑ": ["OLIMPIJA", "OLIMPIJA LJUBLJANA", "SMELT OLIMPIJA", "ΟΛΙΜΠΙΑ ΛΙΟΥΜΠΛΙΑΝΑ"],
    "ΛΙΜΟΖ": ["LIMOGES", "ΛΙΜΟΖ"], "ΒΙΛΑΟΥΡΜΠΑΝΕ": ["VILLEURBANNE", "ASVEL"], "ΜΠΟΥΝΤΟΥΤΣΝΟΣΤ": ["BUDUCNOST"],
    "ΓΚΑΛΑΤΑΣΑΡΑΪ": ["GALATASARAY"], "ΒΙΤΟΡΙΑ": ["TAU", "TAU CERAMICA", "BASKONIA", "VITORIA"], "ΧΙΜΚΙ": ["KHIMKI"],
    "ΟΥΝΙΚΑΧΑ": ["UNICAJA"], "ΕΣΣΔ": ["U.S.S.R", "U.S.S.R.", "USSR", "ΣΟΒΙΕΤΙΚΗ ΕΝΩΣΗ", "ΕΣΣΔ"],
    "ΣΙΜΕΝΤΑΛ ΜΙΛΑΝΟ": ["SIMMENTHAL", "ΣΙΜΕΝΤΑΛ ΜΙΛΑΝΟ", "ΣΙΜΕΝΤΑΛ"], "ΕΦΕΣ ΠΙΛΣΕΝ": ["ΕΦΕΣ ΠΙΛΣΕΝ", "ΕΦΕΣ"], "ΒΑΛΕΝΘΙΑ": ["VALENCIA"], "ΜΙΛΑΝΟ": ["MILANO", "OLIMPIA MILANO", "ARMANI MILANO"],
}
FRIENDLY_OR_MINOR = re.compile(r"\bA2\b|\bΑ2\b|Β[΄'’]? ?ΕΘΝ|Γ[΄'’]? ?ΕΘΝ|ΦΙΛΙΚ|FRIENDLY|ΤΟΥΡΝΟΥΑ|TOURNAMENT|ΤΟΥΡΝΟΥΑΣ|ΕΦΗΒ|ΠΑΙΔ|"
                               r"ΝΕΑΝΙΔ|ΓΥΝΑΙΚ|WOMEN|JUNIOR|U\d\d|ALL ?STAR|ΑΛΛ ?ΣΤΑΡ|TRIBUTE|3X3|ΒΕΤΕΡΑΝ|LEGENDS")
COMP = [  # (λέξη στον τίτλο, ελληνική απόδοση, είναι τελικός)
    (r"FINAL ?FOUR|F4\b|ΦΑΪΝΑΛ|ΦΑΙΝΑΛ", "Final Four", True),
    (r"ΗΜΙΤΕΛΙΚ|SEMI ?FINAL", "Ημιτελικός", False),
    (r"ΤΕΛΙΚΟΣ ΚΥΠΕΛΛΟΥ ΚΥΠΕΛΛΟΥΧΩΝ|CUP WINNERS.*FINAL|SAPORTA.*FINAL", "Τελικός Κυπέλλου Κυπελλούχων", True),
    (r"KORAC.*FINAL|ΤΕΛΙΚΟΣ.*KORAC|ΤΕΛΙΚΟΣ.*ΚΟΡΑΤΣ", "Τελικός Κόρατς", True),
    (r"ΤΕΛΙΚΟΣ ΚΥΠΕΛΛΟΥ", "Τελικός Κυπέλλου Ελλάδας", True),
    (r"\bFINAL\b|ΤΕΛΙΚΟΣ", "Τελικός", True),
    (r"EUROLEAGUE|ΕΥΡΩΛΙΓΚΑ|CHAMPIONS CUP|ΚΥΠΕΛΛΟ ΠΡΩΤΑΘΛΗΤΡΙΩΝ", "EuroLeague / Κύπελλο Πρωταθλητριών", False),
    (r"SAPORTA|CUP WINNERS|ΚΥΠΕΛΛΟΥΧΩΝ", "Κύπελλο Κυπελλούχων", False),
    (r"KORAC|ΚΟΡΑΤΣ", "Κύπελλο Κόρατς", False),
    (r"EUROCUP|ULEB", "EuroCup", False),
    (r"EUROBASKET|ΕΥΡΩΜΠΑΣΚΕΤ", "Ευρωμπάσκετ", False),
    (r"MUNDOBASKET|ΜΟΥΝΤΟΜΠΑΣΚΕΤ|WORLD CUP|ΠΑΓΚΟΣΜΙΟ", "Μουντομπάσκετ", False),
    (r"ΚΥΠΕΛΛΟ|CUP\b", "Κύπελλο Ελλάδας", False),
    (r"PLAY ?OFF|ΠΛΕΪ ?ΟΦ", "Playoffs", False),
]
LATIN = str.maketrans("ABEZHIKMNOPTYX", "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ")


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").upper())
    s = unicodedata.normalize("NFC", "".join(c for c in s if not unicodedata.combining(c)))
    return re.sub(r"\s+", " ", s.replace("–", "-").replace("—", "-")).strip()


def _greekify(s):
    """Λατινικά γράμματα-σωσίες μέσα σε ελληνική λέξη (π.χ. 'ΣΚΑBΟΛΙΝΙ') → ελληνικά."""
    return " ".join(w.translate(LATIN) if re.search("[Α-Ω]", w) else w for w in s.split())


def _team(raw):
    """(όνομα για εμφάνιση, ελληνική ομάδα ή None). None όταν δεν μοιάζει με όνομα ομάδας."""
    n = _greekify(_norm(raw)).strip(" .:-|,")
    n = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()
    n = n.rsplit("(", 1)[-1].strip(" .:-|,")
    if not n or len(n) > 32 or re.search(r"\d{3,}", n):
        return None, None
    for name, alts in GREEK.items():
        if n == name or n in alts or any(n.startswith(a + " ") for a in alts if len(a) >= 4):
            return name, name
    for name, alts in FOREIGN.items():
        if n in alts or n == name:   # ξένες ομάδες: ΜΟΝΟ ακριβές όνομα (π.χ. ΤΣΣΚΑ Σόφιας ≠ ΤΣΣΚΑ Μόσχας)
            return name, None
    if len(n.split()) > 4:
        return None, None
    if re.search("[Α-Ω]", n) and not re.search("[A-Z]", n):
        return n, "GR:" + n          # άγνωστη ελληνική ομάδα (π.χ. ΙΚΑΡΟΣ ΧΑΛΚΙΔΑΣ)
    return n, None


SCORE = re.compile(r"(?<![\d/.])(\d{2,3})\s*-\s*(\d{2,3})(?![\d/.])")


def _season(t):
    m = re.search(r"(?<!\d)(19[4-9]\d|20[0-2]\d)\s*[-/]\s*(\d{2})(?!\d)", t)
    if m and (int(m[2]) - int(m[1][2:])) % 100 == 1:
        return int(m[1])
    m = re.search(r"\(\D*(\d{2})[/-](\d{2})\)", t)                       # (13/14), (EUROCUP 13/14)
    if m and (int(m[2]) - int(m[1])) % 100 == 1:
        y = int(m[1]); return 2000 + y if y < 40 else 1900 + y
    m = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](19\d{2}|20\d{2}|\d{2})(?!\d)", t)   # ημερομηνία
    if m:
        y = int(m[3]); y = y if y > 100 else (2000 + y if y < 40 else 1900 + y)
        return y if int(m[2]) >= 7 else y - 1
    m = re.search(r"(?<!\d)(19[4-9]\d|20[0-2]\d)(?!\d)", t)
    return -int(m[1]) if m else None      # αρνητικό = ξέρουμε μόνο τη χρονιά


def parse(title, channel=""):
    """Τίτλος → στοιχεία αγώνα, ή None αν δεν διαβάζεται με σιγουριά."""
    t = _norm(title)
    if FRIENDLY_OR_MINOR.search(t) or re.search(r"\s_\s|\s\+\s|&", t):   # κλιπ με δύο ματς → όχι
        return None
    scores = [m for m in SCORE.finditer(t) if 35 <= int(m[1]) <= 160 and 35 <= int(m[2]) <= 160]
    # αγνοούμε «σεζόν» τύπου 88-89 που μοιάζουν με σκορ
    scores = [m for m in scores if not (int(m[2]) - int(m[1]) == 1 and re.search(rf"(19|20){m[1]}", t) is None
                                        and int(m[1]) >= 60 and t[m.end():m.end() + 1] != " " and False)]
    if len(scores) != 1:
        return None
    sm = scores[0]
    s1, s2 = int(sm[1]), int(sm[2])
    if s1 == s2:
        return None
    before, after = t[:sm.start()], t[sm.end():]
    before = re.sub(r"^.*?:\s*", "", before) if ":" in before else before          # «KORAC 1984-85: …»
    before = re.sub(r"\[.*?\]|\(.*?\)", " ", before)
    before = re.sub(r"(?<!\d)(19|20)\d{2}\s*[-/]\s*\d{2}(?!\d)|(?<!\d)(19|20)\d{2}(?!\d)", " ", before)
    before = re.sub(r"\bBASKETBALL\b|\bΜΠΑΣΚΕΤ\b|\bA1\b|\bΑ1\b|\bHIGHLIGHTS\b", " ", before).strip(" |-:")
    parts = re.split(r"\s+VS\.?\s+|\s+-\s+|(?<=[Α-ΩA-Z.])-(?=[Α-ΩA-Z])", before)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return None
    (home, hg), (away, ag) = _team(parts[-2]), _team(parts[-1])
    if not home or not away or home == away or not any(x and not x.startswith("GR:") for x in (hg, ag)) and not (hg and ag):
        return None
    season = _season(t)
    if not season:
        return None
    slabel = str(-season) if season < 0 else f"{season}-{(season + 1) % 100:02d}"
    season = abs(season)
    comp, final = "", False
    for rx, label, is_final in COMP:
        if re.search(rx, t):
            comp, final = label, is_final
            break
    # βαριά ήττα ελληνικής ομάδας από ξένη (>20 πόντους) → όχι για το Total Basket
    if not (hg and ag):
        gr_pts = s1 if hg else s2
        if (s2 if hg else s1) - gr_pts > 20:
            return None
    national = "ΕΛΛΑΔΑ" in (hg, ag)
    euro_comp = re.search(r"EUROLEAGUE|ΕΥΡΩΛΙΓΚΑ|CHAMPIONS|ΠΡΩΤΑΘΛΗΤΡΙΩΝ|ΚΥΠΕΛΛΟΥΧΩΝ|ΚΥΠ\. ?ΚΥΠ|SAPORTA|KORAC|ΚΟΡΑΤΣ|"
                          r"EUROCUP|ULEB|FINAL ?FOUR|F4\b|BCL|FIBA EUROPE", t)
    foreign_word = re.search(r"ΣΟΦΙΑΣ|ΜΟΣΧΑΣ|ΠΡΑΓΑΣ|ΒΕΛΙΓΡΑΔΙΟΥ|ΖΑΓΚΡΕΜΠ|ΜΙΛΑΝΟ|ΜΑΔΡΙΤΗΣ|ΒΑΡΚΕΛΩΝΗΣ|ΤΕΛ ΑΒΙΒ|"
                             r"ΒΟΥΚΟΥΡΕΣΤΙΟΥ|ΙΣΤΑΝΜΠΟΥΛ|ΚΩΝΣΤΑΝΤΙΝΟΥΠΟΛΗΣ|ΚΑΟΥΝΑΣ|ΣΠΛΙΤ|ΒΟΛΟΝΙΑΣ|ΜΠΟΛΟΝΙΑ|ΤΡΕΒΙΖΟ", t)
    if (euro_comp or foreign_word) and not national:
        # η μη «γνωστή» ομάδα είναι ξένη, ακόμα κι αν γράφεται ελληνικά
        if hg and hg.startswith("GR:"):
            hg = None
        if ag and ag.startswith("GR:"):
            ag = None
    if final:
        kind = "final"
    elif national:
        kind = "national"
    elif hg in BIG and ag in BIG:
        kind = "derby"
    elif hg and ag:
        kind = "greek"
    else:
        kind = "euro"
    star = "ΝΙΚΟΣ ΓΚΑΛΗΣ" if re.search(r"GALIS|ΓΚΑΛΗΣ", t) else ""
    return {"home": home, "away": away, "score": f"{s1}-{s2}", "season_start": season,
            "season": slabel, "comp": comp, "final": final, "kind": kind,
            "clubs": [c.replace("GR:", "") for c in (hg, ag) if c], "star": star, "channel": channel}


# ---------------------------------------------------------------- κανάλια / κατάλογος
def _opts():
    o = {"quiet": True, "no_warnings": True, "noprogress": True, "sleep_interval_requests": 1}
    deno = shutil.which("deno") or str(Path(sys.executable).with_name("deno"))
    if Path(deno).exists():
        o["js_runtimes"] = {"deno": {"path": deno}}
    return o


def catalog(cfg, data_dir, max_age_hours=72):
    """Όλοι οι αγώνες από όλα τα κανάλια (cache στο Mac για 3 μέρες)."""
    path = Path(data_dir) / "catalog.json"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        return json.loads(path.read_text())
    src, out = cfg["source"], []
    for key, ch in src["channels"].items():
        try:
            with yt_dlp.YoutubeDL({**_opts(), "extract_flat": True}) as y:
                info = y.extract_info(f"https://www.youtube.com/channel/{ch['id']}/videos", download=False)
        except Exception as e:
            print(f"(κανάλι {key}: {e})")
            continue
        for e in info.get("entries") or []:
            if not e or not e.get("duration") or not 15 <= e["duration"] <= src["max_seconds"]:
                continue
            m = parse(e.get("title"), key)
            if m and m["season_start"] <= src["newest_season"]:
                out.append({"id": e["id"], "title": e["title"], "duration": e["duration"], **m})
    seen, uniq = set(), []
    for c in out:   # ίδιο ματς από δύο κανάλια → μία φορά
        k = (c["home"], c["away"], c["score"], c["season_start"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(uniq, ensure_ascii=False))
    return uniq


PATTERN = ["final", "derby", "euro", "greek", "derby", "euro", "national"]


def pick_next(cfg, used_ids, data_dir):
    cat = catalog(cfg, data_dir)
    by_id = {c["id"]: c for c in cat}
    used = [by_id[i] for i in used_ids if i in by_id]
    used_keys = {(c["home"], c["away"], c["score"], c["season_start"]) for c in used}
    cands = [c for c in cat if c["id"] not in used_ids and (c["home"], c["away"], c["score"], c["season_start"]) not in used_keys]
    if not cands:
        raise RuntimeError("Δεν απέμεινε κατάλληλο ρετρό")
    want = PATTERN[len(used) % len(PATTERN)]
    order = PATTERN[PATTERN.index(want):] + PATTERN[:PATTERN.index(want)]
    club_n, era_n = {}, {}
    for c in used:
        for k in c["clubs"]:
            club_n[k] = club_n.get(k, 0) + 1
        era_n[c["season_start"] // 5] = era_n.get(c["season_start"] // 5, 0) + 1
    for k in order:
        pool = [c for c in cands if c["kind"] == k]
        if not pool:
            continue
        # ομάδα που έχει ανέβει λιγότερο, μετά εποχή που έχει ανέβει λιγότερο
        score = lambda c: (min(club_n.get(x, 0) for x in c["clubs"]), era_n.get(c["season_start"] // 5, 0))
        best = min(score(c) for c in pool)
        choice = random.choice([c for c in pool if score(c) == best])
        break
    print(f"Επιλογή: {choice['title']} [{choice['channel']}] → {choice['kind']}")
    with yt_dlp.YoutubeDL(_opts()) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={choice['id']}", download=False)
    info["match"] = choice
    return info


def download(info, workdir):
    from imageio_ffmpeg import get_ffmpeg_exe
    workdir = Path(workdir)
    opts = {**_opts(), "format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4",
            "ffmpeg_location": get_ffmpeg_exe(), "outtmpl": str(workdir / "%(id)s.%(ext)s"),
            "writethumbnail": True, "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}]}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([info["webpage_url"]])
    return workdir / f"{info['id']}.mp4", workdir / f"{info['id']}.jpg"


# ---------------------------------------------------------------- κείμενα (ουδέτερα: χωρίς άρθρα/γένος)
HOOKS = {
    "final": ["ΤΕΛΙΚΟΣ ΓΙΑ ΤΗΝ ΙΣΤΟΡΙΑ! 🏆", "ΤΟΤΕ ΠΟΥ ΚΡΙΘΗΚΕ ΤΟ ΤΡΟΠΑΙΟ! 🏆", "ΤΕΛΙΚΟΣ ΠΟΥ ΔΕΝ ΞΕΧΝΙΕΤΑΙ! 🔥"],
    "derby": ["ΝΤΕΡΜΠΙ ΑΠΟ ΤΑ ΠΑΛΙΑ! 🔥", "ΤΟ ΝΤΕΡΜΠΙ ΠΟΥ ΔΕΝ ΞΕΧΝΙΕΤΑΙ! 🔥", "ΚΛΑΣΙΚΟ ΝΤΕΡΜΠΙ! 🏀"],
    "euro": ["ΕΥΡΩΠΑΪΚΗ ΒΡΑΔΙΑ! ✨", "ΕΛΛΗΝΙΚΟ ΜΠΑΣΚΕΤ ΣΤΗΝ ΕΥΡΩΠΗ! 🏀", "ΜΕΓΑΛΗ ΒΡΑΔΙΑ ΣΤΗΝ ΕΥΡΩΠΗ! 🔥"],
    "greek": ["ΘΥΜΑΣΑΙ ΑΥΤΟ ΤΟ ΜΑΤΣ; 📼", "ΑΠΟ ΤΟ ΑΡΧΕΙΟ ΤΟΥ ΕΛΛΗΝΙΚΟΥ ΜΠΑΣΚΕΤ! 🏀", "ΡΕΤΡΟ ΜΠΑΣΚΕΤ! 📼"],
    "national": ["Η ΕΘΝΙΚΗ ΣΕ ΜΕΓΑΛΕΣ ΣΤΙΓΜΕΣ! 🇬🇷", "ΓΑΛΑΝΟΛΕΥΚΗ ΑΠΟ ΤΑ ΠΑΛΙΑ! 🇬🇷"],
}
VINTAGE = ["ΣΠΑΝΙΟ ΒΙΝΤΕΟ ΑΠΟ ΤΟ {y}! 📼", "ΘΗΣΑΥΡΟΣ ΑΠΟ ΤΟ {y}! 📼"]
CLOSING = ["Ποιος θυμάται αυτό το ματς; Γράψ' το στα σχόλια! 🏀", "Πού ήσουν τότε; Γράψ' το στα σχόλια! 🏀",
           "Από τις στιγμές που έγραψαν ιστορία στο ελληνικό μπάσκετ! 🏀"]


def generate(info, cfg):
    c = info["match"]
    rnd = random.Random(info["id"])
    match = f"{c['home']} – {c['away']} {c['score']}"
    hooks = list(HOOKS[c["kind"]])
    if c["season_start"] < 1990:
        hooks += [v.format(y=c["season_start"]) for v in VINTAGE]
    if c["star"]:
        hooks.append(f"{c['star']} ΣΕ ΔΡΑΣΗ! ⭐")
    tags = "#totalbasket #shorts #basketball"
    hook = rnd.choice(hooks)
    yt = f"{hook} {match}" if len(hook) + len(match) + len(tags) + 2 <= 100 else match
    lines = [f"🏀 {match}", "", f"📅 {'Σεζόν ' if '-' in c['season'] else ''}{c['season']}"]
    if c["comp"]:
        lines.append(f"🏆 {c['comp']}")
    if c["star"]:
        lines.append(f"⭐ {c['star'].title()}")
    lines += ["", rnd.choice(CLOSING)]
    credit = f"🎥 Πηγή: {cfg['source']['channels'][c['channel']]['credit']}"
    return {
        "overlay_title": f"{c['season']} · {match}",
        "youtube_title": f"{yt} {tags}",
        "full_description": "\n\n".join(["\n".join(lines), credit, cfg["hashtags"]]),
        "confident": True,
    }
