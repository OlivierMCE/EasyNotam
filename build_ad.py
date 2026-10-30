#!/usr/bin/env python3
"""Construit adnames.js : code OACI -> nom de l'aérodrome (eAIP France, section AD 1.3)."""
import json, os, re, sys
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


def main():
    nom, airac = dossier_airac()
    url = '%s/media/dvd/%s/FRANCE/AIRAC-%s/html/eAIP/FR-AD-1.3-fr-FR.html' % (SITE, nom, airac)
    noms = lire(get(url).decode('utf-8', 'replace'))
    if len(noms) < 200:
        sys.exit('Résultat suspect (%d aérodromes) : adnames.js n\'est pas modifié.' % len(noms))
    with open(SORTIE, 'w', encoding='utf-8') as f:
        f.write('window.TRI_AD=' + json.dumps(noms, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + ';\n')
    print('%d aérodromes (AIRAC %s).' % (len(noms), airac))


if __name__ == '__main__':
    main()
