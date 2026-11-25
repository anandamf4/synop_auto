# -*- coding: utf-8 -*-
"""core/status.py - [rev 36] status ringan dari bot/web untuk panel (data/status_bot.json). Selalu best-effort: galat tak pernah menjatuhkan bot."""
import datetime as dt
import json
import os
import tempfile

from core.paths import ROOT

BERKAS = ROOT / "data" / "status_bot.json"


def baca():
    try:
        return json.loads(BERKAS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def tulis(kunci, **nilai):
    """Gabungkan {kunci: {..., waktu}} ke berkas status (tulis atomik)."""
    try:
        d = baca()
        d[kunci] = dict(nilai, waktu=dt.datetime.now().isoformat(timespec="seconds"))
        BERKAS.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(BERKAS.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, BERKAS)
    except Exception:
        pass
