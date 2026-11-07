#!/usr/bin/env python3
"""Construit adnames.js : code OACI -> nom de l'aérodrome (eAIP France, section AD 1.3)
et code OACI -> position (lat, lon) du point de référence (base libre OurAirports)."""
import csv, io, json, os, re, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_zones import SITE, dossier_airac, get, texte

SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adnames.js')


def lire(contenu):
    out = {}
    for tr in re.finditer(r'<tr\b[^>]*>(.*?)</tr>', contenu, re.S | re.I):
        cells = [texte(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', tr.group(1), re.S | re.I)]
        if len(cells) > 1 and re.fullmatch(r'[A-Z]{2}[A-Z0-9]{2}', cells[0]) and cells[1]:
            out[cells[0]] = cells[1]
    return out


POS_URL = 'https://davidmegginson.github.io/ourairports-data/airports.csv'


def positions():
    """{'LFKG': [42.0534, 9.4002], ...} pour les aérodromes et héliports français (LF..)."""
    try:
        brut = get(POS_URL).decode('utf-8', 'replace')
    except Exception as e:
        print('Positions : téléchargement impossible (%s).' % e)
        return {}
    out = {}
    for r in csv.DictReader(io.StringIO(brut)):
        code = (r.get('gps_code') or r.get('ident') or '').strip().upper()
        if len(code) == 4 and code.startswith('LF'):
            try:
                out[code] = [round(float(r['latitude_deg']), 4), round(float(r['longitude_deg']), 4)]
            except Exception:
                pass
    return out


def anciennes_positions():
    try:
        t = open(SORTIE, encoding='utf-8').read()
        m = re.search(r'window\.TRI_ADPOS=(\{.*?\});', t, re.S)
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


def main():
    nom, airac = dossier_airac()
    url = '%s/media/dvd/%s/FRANCE/AIRAC-%s/html/eAIP/FR-AD-1.3-fr-FR.html' % (SITE, nom, airac)
    noms = lire(get(url).decode('utf-8', 'replace'))
    if len(noms) < 200:
        sys.exit('Résultat suspect (%d aérodromes) : adnames.js n\'est pas modifié.' % len(noms))
    pos = positions()
    if len(pos) < 200:
        pos = anciennes_positions() or pos
    with open(SORTIE, 'w', encoding='utf-8') as f:
        f.write('window.TRI_AD=' + json.dumps(noms, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + ';\n')
        f.write('window.TRI_ADPOS=' + json.dumps(pos, separators=(',', ':'), sort_keys=True) + ';\n')
    print('%d aérodromes (AIRAC %s), %d positions.' % (len(noms), airac, len(pos)))


if __name__ == '__main__':
    main()
