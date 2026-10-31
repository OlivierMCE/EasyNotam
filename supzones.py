#!/usr/bin/env python3
"""Construit supzones.js : contours des zones créées par les SUP AIP (ZRT, ZDT, TSA, R, D...).
Lit les PDF du dossier supaip/. Ne relit que les PDF nouveaux."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_zones import polygones

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, 'supaip')
SORTIE = os.path.join(ICI, 'supzones.js')
VERSION = 4  # à augmenter quand la lecture est améliorée : tout est relu
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


COORD_MOT = re.compile(r"\d+\s*°")


def zones_tableau(chemin):
    """SUP où les zones sont dans un tableau (nom à gauche, coordonnées dans une colonne) : lecture par positions."""
    try:
        import pdfplumber
    except Exception:
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'pdfplumber'], check=True)
            import pdfplumber
        except Exception as e:
            print('  pdfplumber indisponible:', e)
            return []
    from build_zones import RE_TOKEN, vertex, rayon_nm, arc, cercle
    out = []
    with pdfplumber.open(chemin) as pdf:
        for page in pdf.pages:
            mots = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            cm = [m for m in mots if COORD_MOT.search(m['text'])]
            if len(cm) < 3 or max(m['x1'] for m in cm) - min(m['x0'] for m in cm) > 140 or min(m['x0'] for m in cm) < 90:
                continue
            x0 = min(m['x0'] for m in cm) - 3
            x1 = max(m['x1'] for m in cm) + 25
            col = sorted([m for m in mots if m['x0'] >= x0 and m['x1'] <= x1], key=lambda m: (round(m['top']), m['x0']))
            texte, offs = '', []
            for m in col:
                offs.append((len(texte), m['top']))
                texte += m['text'] + ' '
            def haut(pos):
                y = offs[0][1]
                for o, top in offs:
                    if o <= pos: y = top
                return y
            # noms : mots à gauche de la colonne des coordonnées
            gauche = sorted([m for m in mots if m['x1'] < x0 + 3 and m['top'] > cm[0]['top'] - 40 and not re.match(r'^(Page|FR|©|SIA|SUP|AIP|Date)', m['text'])], key=lambda m: (round(m['top']), m['x0']))
            lignes = []
            for m in gauche:
                if lignes and abs(lignes[-1]['top'] - m['top']) < 3:
                    lignes[-1]['t'] += ' ' + m['text']
                else:
                    lignes.append({'top': m['top'], 't': m['text']})
            noms = []
            for l in lignes:
                if noms and l['top'] - noms[-1]['bas'] < 14 and not re.match(r'^(ZRT|ZDT|TSA|TRA|ZIT|[A-Z]{1,3}\s?\d)', l['t']):
                    noms[-1]['t'] += ' ' + l['t']; noms[-1]['bas'] = l['top']
                else:
                    noms.append({'t': l['t'], 'haut': l['top'], 'bas': l['top']})
            def quel(y):
                if not noms:
                    return 0
                return min(range(len(noms)), key=lambda i: abs((noms[i]['haut'] + noms[i]['bas']) / 2 - y))
            polys, pts, ys, grp, attente = [], [], [], None, None
            def vider():
                nonlocal pts, ys, grp
                if len(pts) >= 4 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
                    pts = pts[:-1]
                if len(pts) >= 3:
                    polys.append((pts, ys, grp))
                pts, ys, grp = [], [], None
            for m in RE_TOKEN.finditer(texte):
                y = haut(m.start()); g = quel(y)
                if m.group('circ'):
                    vider(); polys.append((cercle(vertex(m.group('cc')), rayon_nm(m.group('cr'), m.group('cu'))), [y], g))
                elif m.group('arc'):
                    attente = (vertex(m.group('ac')), m.group('dir').lower() == 'horaire')
                else:
                    if grp is not None and g != grp:
                        vider(); attente = None
                    v = vertex(m.group('v'))
                    if attente and pts:
                        pts += arc(pts[-1], v, attente[0], attente[1])
                    attente = None
                    pts.append(v); ys.append(y); grp = g
            vider()
            for p, y, g in polys:
                nom = noms[g]['t'] if noms else ''
                out.append({'n': nom[:80], 'p': [[[round(a, 4), round(b, 4)] for a, b in p]]})
    return out


def meilleur(chemin):
    best = []
    cand = [zones_du_texte(t) for t in textes_pdf(chemin)]
    try:
        cand.append(zones_tableau(chemin))
    except Exception as e:
        print('  tableau:', e)
    for z in cand:
        if sum(len(o['p']) for o in z) > sum(len(o['p']) for o in best):
            best = z
    # on ajoute les zones trouvées par les autres méthodes et absentes du meilleur résultat
    connus = {tuple(p[0]) for o in best for p in o['p']}
    for z in cand:
        if z is best:
            continue
        for o in z:
            neufs = [p for p in o['p'] if tuple(p[0]) not in connus]
            if neufs and len(neufs) == len(o['p']):
                best.append(o)
                connus |= {tuple(p[0]) for p in neufs}
    return best


def zones_du_texte(t):
    t = re.sub(r'\s+', ' ', t.replace('\xa0', ' '))
    t = re.sub(r'Page \d+/\d+ FR ©? ?SIA SUP AIP \d+/\d+ Date de publication : \d+ \w+ \d{4}', ' ', t)
    morceaux = re.split(r'LIMITES LAT[ÉE]RALES', t, flags=re.I)
    out = []
    dernier = ''
    for i in range(1, len(morceaux)):
        avant = morceaux[i - 1][-300:]
        j = [m.end() for m in re.finditer(r'ET VERTICALES|ET LAT[ÉE]RALES|(?:AMSL|AGL|ASFC|GND|SFC|FL\s*\d+)(?=\s)', avant, re.I)]
        nom = (avant[j[-1]:] if j else avant[-60:]).strip(' -:/')
        nom = re.split(r'Date de publication\s*:\s*\d+ \w+ \d{4}', nom)[-1].strip(' -:/')
        nom = re.sub(r'^(?:Page \d+/\d+\s*)?(?:FR\s*)?©?\s*(?:SIA\s*)?', '', nom).strip()
        nom = re.sub(r'\s*\(ERNIP[^)]*\)', '', nom).strip()[:80]
        if not j or re.search(r'exclusion|conserve|statut|AIP ENR', nom, re.I) or '°' in nom:
            nom = dernier
        dernier = nom
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
