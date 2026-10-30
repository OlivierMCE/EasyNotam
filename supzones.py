#!/usr/bin/env python3
"""Construit supzones.js : contours des zones créées par les SUP AIP (ZRT, ZDT, TSA, R, D...).
Lit les PDF du dossier supaip/. Ne relit que les PDF nouveaux."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_zones import polygones

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, 'supaip')
SORTIE = os.path.join(ICI, 'supzones.js')
VERSION = 2  # à augmenter quand la lecture est améliorée : tout est relu
RE_FICHIER = re.compile(r'SUP-AIP-(\d+)-(\d{4})\.pdf$')


def textes_pdf(chemin):
    """Texte du PDF lu par deux outils différents (on garde le meilleur résultat)."""
    out = []
    try:
        from pypdf import PdfReader
        out.append(' '.join((p.extract_text() or '') for p in PdfReader(chemin).pages))
    except Exception as e:
        print('  pypdf:', e)
    for mode in (['-layout'], []):
        try:
            out.append(subprocess.run(['pdftotext'] + mode + [chemin, '-'], capture_output=True, text=True).stdout)
        except Exception as e:
            print('  pdftotext:', e)
            break
    return out


def meilleur(chemin):
    best = []
    for t in textes_pdf(chemin):
        z = zones_du_texte(t)
        if sum(len(o['p']) for o in z) > sum(len(o['p']) for o in best):
            best = z
    return best


def zones_du_texte(t):
    t = re.sub(r'\s+', ' ', t.replace('\xa0', ' '))
    morceaux = re.split(r'LIMITES LAT[ÉE]RALES', t, flags=re.I)
    out = []
    for i in range(1, len(morceaux)):
        avant = morceaux[i - 1][-300:]
        j = [m.end() for m in re.finditer(r'ET VERTICALES|ET LAT[ÉE]RALES|(?:AMSL|AGL|ASFC|GND|SFC|FL\s*\d+)(?=\s)', avant, re.I)]
        nom = (avant[j[-1]:] if j else avant[-60:]).strip(' -:/')
        nom = re.sub(r'\s*\(ERNIP[^)]*\)', '', nom).strip()[:80]
        bloc = re.split(r'LIMITES VERTICALES', morceaux[i], flags=re.I)[0]
        polys = polygones(bloc)
        if polys:
            out.append({'n': nom, 'p': [[[round(a, 4), round(b, 4)] for a, b in p] for p in polys]})
    return out


def main():
    ancien = {}
    if os.path.exists(SORTIE):
        try:
            ancien = json.loads(open(SORTIE, encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
        except Exception:
            ancien = {}
    if ancien.get('_v') != VERSION:
        ancien = {}
    res = {'_v': VERSION}
    for f in sorted(os.listdir(DOSSIER)) if os.path.isdir(DOSSIER) else []:
        m = RE_FICHIER.search(f)
        if not m:
            continue
        cle = '%s/%s' % (m.group(1).zfill(3), m.group(2))
        if cle in ancien:
            res[cle] = ancien[cle]
            continue
        print('Lecture', f)
        try:
            z = meilleur(os.path.join(DOSSIER, f))
        except Exception as e:
            print('  erreur', e)
            z = []
        res[cle] = z
    if res == ancien and os.path.exists(SORTIE):
        print('supzones.js est déjà à jour.')
        return
    with open(SORTIE, 'w', encoding='utf-8') as f:
        f.write('window.TRI_SUPZ=' + json.dumps(res, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('%d SUP AIP, dont %d avec des contours.' % (len(res) - 1, sum(1 for k, v in res.items() if k != '_v' and v)))


if __name__ == '__main__':
    main()
