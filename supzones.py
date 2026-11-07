#!/usr/bin/env python3
"""Construit supzones.js : contours des zones créées par les SUP AIP (ZRT, ZDT, TSA, R, D...).
Lit les PDF du dossier supaip/. Ne relit que les PDF nouveaux."""
import json, math, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_zones import polygones, cercle, rayon_nm

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, 'supaip')
SORTIE = os.path.join(ICI, 'supzones.js')
VERSION = 8  # à augmenter quand la lecture est améliorée : tout est relu
RE_FICHIER = re.compile(r'SUP-AIP-(\d+)-(\d{4})\.pdf$')

# ---------- liens avec l'AIP : positions d'aérodromes, radiales, renvois vers des zones publiées ----------
_CACHE = {}


def _js(nom, var):
    """Lit window.<var>={...}; dans un fichier .js voisin (zones.js, adnames.js)."""
    if (nom, var) in _CACHE:
        return _CACHE[(nom, var)]
    val = {}
    try:
        t = open(os.path.join(ICI, nom), encoding='utf-8').read()
        m = re.search(r'window\.%s=(\{.*?\});?\s*(?:\n|$)' % var, t, re.S)
        val = json.loads(m.group(1)) if m else {}
    except Exception:
        val = {}
    _CACHE[(nom, var)] = val
    return val


def pos_ad(code):
    p = _js('adnames.js', 'TRI_ADPOS').get(code.upper())
    return tuple(p) if p else None


def _dms(lat, lon):
    def f(v, pos, neg, deg):
        h = pos if v >= 0 else neg
        v = abs(v)
        d = int(v)
        m = int((v - d) * 60)
        s = round(((v - d) * 60 - m) * 60, 1)
        if s >= 60:
            s = 0.0
            m += 1
        return '%0*d°%02d\'%04.1f"%s' % (deg, d, m, s, h)
    return '%s %s' % (f(lat, 'N', 'S', 2), f(lon, 'E', 'W', 3))


def point_rdl(code, cap, nm):
    a = pos_ad(code)
    if not a:
        return None
    b = math.radians(cap)
    k = math.cos(math.radians(a[0]))
    return (a[0] + nm * math.cos(b) / 60, a[1] + nm * math.sin(b) / (60 * k))


def substituer(t):
    """Remplace « RDL 145/4NM LFKG » et « centré sur LFOA ARP » par des coordonnées lisibles par le lecteur de contours."""
    def rdl(m):
        u = (m.group(3) or 'NM').upper()
        d = float(m.group(2).replace(',', '.')) / (1.852 if u == 'KM' else 1)
        p = point_rdl(m.group(4), float(m.group(1)), d)
        return _dms(*p) if p else m.group(0)
    t = re.sub(r"(?:RDL|radial|R)\s*(\d{1,3})\s*°?\s*/\s*(\d+(?:[.,]\d+)?)\s*(NM|KM)?\s*(?:de\s+l['’]?\s*ARP\s+(?:de\s+)?|ARP\s+|de\s+|du\s+)?(LF[A-Z]{2})\b", rdl, t, flags=re.I)

    def centre(m):
        p = pos_ad(m.group(2))
        return m.group(1) + _dms(*p) if p else m.group(0)
    t = re.sub(r"(centr[ée]e?\s+sur\s+(?:le\s+point\s+|l['’]\s*ARP\s+(?:de\s+)?)?)(?:ARP\s+)?(LF[A-Z]{2})(?:\s+ARP)?\b(?![\s,]*\d)", centre, t, flags=re.I)
    return t


def _norm(x):
    import unicodedata
    x = unicodedata.normalize('NFD', x.upper())
    return re.sub(r'[^A-Z0-9]+', ' ', ''.join(c for c in x if unicodedata.category(c) != 'Mn')).strip()


def refs_aip(t):
    """« Identiques à celles de la zone LF-R 124 », « … de la TMA BÂLE » : on reprend le contour publié à l'AIP."""
    if not re.search(r'identiques?|publi[ée]e?s?\s+(?:à|a)\s+l.AIP|voir\s+AIP|AIP\s+(?:France\s+)?ENR', t, re.I):
        return []
    zs = _js('zones.js', 'TRI_ZONES')
    zs = zs.get('z', []) if isinstance(zs, dict) else []
    if not zs:
        return []
    par_cle = {z['k']: z for z in zs}
    out, vus = [], set()

    def ajoute(z):
        if z['k'] not in vus:
            vus.add(z['k'])
            out.append(z)
    for m in re.finditer(r'LF[\s-]*(R|D|P|TRA|TSA|CBA)[\s-]*(\d{1,4})\s*([A-Z]{0,2}\d?)(?![A-Za-z0-9])', t):
        tete, lettres = m.group(1) + m.group(2), m.group(3).upper()
        if tete + lettres in par_cle:
            ajoute(par_cle[tete + lettres])
        elif lettres == '' or not any(k.startswith(tete + lettres) for k in par_cle):
            for k, z in par_cle.items():
                if k == tete or (k.startswith(tete) and re.fullmatch(r'[A-Z]{1,2}\d?', k[len(tete):])):
                    ajoute(z)
    for m in re.finditer(r'\b(TMA|CTA)\s+([A-ZÀ-Ý][A-ZÀ-Ý\' -]{2,24}?)(?=\s*(?:[.,;(]|$|\d|publi|et\b|\n))', t):
        base = _norm(m.group(1) + ' ' + m.group(2))
        for z in zs:
            if _norm(z.get('b') or z.get('n') or '') == base:
                ajoute(z)
    polys = []
    for z in out:
        polys += z['p']
    return polys


def polys_ou_ref(t):
    p = polygones(substituer(t))
    return p or [[(a, b) for a, b in q] for q in refs_aip(t)]



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


def _centre(p):
    return (sum(a for a, b in p) / len(p), sum(b for a, b in p) / len(p))


def _proche(p, liste):
    """Vrai si le contour p double un contour de la liste (même centre à 0,02° près et même taille à 15 % près)."""
    c = _centre(p)
    et = max(max(a for a, b in p) - min(a for a, b in p), max(b for a, b in p) - min(b for a, b in p))
    return any(abs(c[0] - v[0]) < 0.02 and abs(c[1] - v[1]) < 0.02 and abs(et - v[2]) <= 0.15 * max(et, v[2], 1e-6) for v in liste)


def _sig(p):
    c = _centre(p)
    return (c[0], c[1], max(max(a for a, b in p) - min(a for a, b in p), max(b for a, b in p) - min(b for a, b in p)))


def meilleur(chemin):
    best = []
    cand = []
    try:
        cand.append(zones_positions(chemin))
    except Exception as e:
        print('  positions:', e)
    cand += [zones_du_texte(t) for t in textes_pdf(chemin)]
    try:
        cand.append(zones_colonnes(chemin))
    except Exception as e:
        print('  colonnes:', e)
    try:
        cand.append(zones_tableau(chemin))
    except Exception as e:
        print('  tableau:', e)
    # on écarte les « zones » dont le nom est un mot de description (arc, cercle, limites…) : lecture ratée
    cand = [[o for o in z if not re.match(r'\s*(arc|cercle|limites?|lat[ée]rales?)\b', o['n'], re.I)] for z in cand]

    def score(z):
        return (sum(len(o['p']) for o in z), len(z), -sum(len(o['n']) for o in z), sum(len(p) for o in z for p in o['p']))
    for z in cand:
        if score(z) > score(best):
            best = z
    # on ajoute les zones trouvées par les autres méthodes et absentes du meilleur résultat
    connus = [_sig(p) for o in best for p in o['p']]
    sommets = {tuple(p[0]) for o in best for p in o['p']}
    for z in cand:
        if z is best:
            continue
        for o in z:
            neufs = [p for p in o['p'] if tuple(p[0]) not in sommets and not _proche(p, connus)]
            if neufs and len(neufs) == len(o['p']):
                best.append(o)
                connus += [_sig(p) for p in neufs]
                sommets |= {tuple(p[0]) for p in neufs}
    if len(best) == 1 and not best[0]['n'].strip():
        try:
            t = subprocess.run(['pdftotext', '-layout', chemin, '-'], capture_output=True, text=True).stdout
            m = re.search(r"\b((?:ZRT|ZDT|ZIT|TSA|TRA)(?:/(?:ZRT|ZDT))?\s+['‘’\"][^'‘’\"\n]{2,40}['‘’\"])", t)
            if m:
                best[0]['n'] = m.group(1).strip()
        except Exception:
            pass
    return best


RE_DMS = re.compile(r"(\d{1,3})\s*°\s*(\d{1,2})\s*['’′]\s*(\d{1,2}(?:[.,]\d+)?)?\s*(?:\"|”|″|''|’’|′′)?\s*([NSEWO])\b")


def zones_colonnes(chemin):
    """Mise en page en colonnes (ex. 4 zones côte à côte : noms sur une ligne, puis « CERCLE DE 2 NM… »,
    les latitudes sur une ligne et les longitudes sur la suivante)."""
    t = subprocess.run(['pdftotext', '-layout', chemin, '-'], capture_output=True, text=True).stdout
    lignes = t.split('\n')
    out = []
    i = 0
    while i < len(lignes) - 1:
        suiv = ''
        j = i + 1
        while j < len(lignes) and not lignes[j].strip():
            j += 1
        if j < len(lignes):
            suiv = lignes[j]
        k = len(re.findall(r'LIMITES LAT[ÉE]RALES', suiv, re.I))
        noms = [n.strip() for n in re.split(r'\s{2,}', lignes[i].strip()) if n.strip()]
        if k >= 2 and len(noms) == k and not re.search(r'LIMITES', lignes[i], re.I):
            bloc = []
            m = j + 1
            while m < len(lignes) and not re.search(r'LIMITES VERTICALES', lignes[m], re.I):
                bloc.append(lignes[m])
                m += 1
            txt = '\n'.join(bloc)
            rays = re.findall(r'CERCLE\s+DE\s+(\d+(?:[.,]\d+)?)\s*(NM|KM|M)\b', txt, re.I)
            lats, lons = [], []
            for mm in RE_DMS.finditer(txt):
                v = int(mm.group(1)) + int(mm.group(2)) / 60 + float((mm.group(3) or '0').replace(',', '.')) / 3600
                h = mm.group(4).upper()
                if h in 'NS':
                    lats.append(-v if h == 'S' else v)
                else:
                    lons.append(-v if h in 'WO' else v)
            if len(lats) == k and len(lons) == k and rays:
                for n in range(k):
                    r = rayon_nm(*rays[n if len(rays) == k else 0])
                    p = cercle((lats[n], lons[n]), r)
                    out.append({'n': noms[n][:80], 'p': [[[round(a, 4), round(b, 4)] for a, b in p]]})
            i = m
        i += 1
    return out


def zones_positions(chemin):
    """Zones présentées côte à côte (2 à 5 colonnes) : on s'appuie sur la position horizontale du texte.
    Chaque colonne = un nom en tête + ses sommets en dessous."""
    t = subprocess.run(['pdftotext', '-layout', chemin, '-'], capture_output=True, text=True).stdout
    lignes = t.split('\n')

    def segs(l):
        return [(m.start(), m.group(0).strip()) for m in re.finditer(r'\S+(?: {1,2}\S+)*', l)]

    out = []
    i = 0
    while i < len(lignes):
        if not re.search(r'LIMITES LAT[ÉE]RALES ET VERTICALES', lignes[i], re.I):
            i += 1
            continue
        j = i + 1
        fin = len(lignes)
        for m in range(j, len(lignes)):
            if re.search(r'LIMITES VERTICALES|ORGANISMES|INFORMATION DES USAGERS', lignes[m], re.I):
                fin = m
                break
        bande = lignes[j:fin]
        # en-têtes : lignes avant la première ligne contenant un sommet, un cercle ou un arc
        premiere = next((k for k, l in enumerate(bande) if re.search(r"°|cercle|arc\s+(?:anti-)?horaire", l, re.I)), len(bande))
        ancres = []
        for l in bande[:premiere]:
            if re.search(r'LIMITES', l, re.I):
                continue
            for x, tx in segs(l):
                if not re.match(r'\(', tx):
                    ancres.append(x)
        cols = []
        for x in sorted(ancres):
            if not cols or x - cols[-1][-1] > 12:
                cols.append([x])
            else:
                cols[-1].append(x)
        starts = [min(c) for c in cols]
        if len(starts) >= 2:
            bornes = [(starts[k] + starts[k + 1]) / 2 for k in range(len(starts) - 1)]
            def col_de(x):
                return sum(1 for b in bornes if x >= b)
            noms = [[] for _ in starts]
            corps = [[] for _ in starts]
            for k, l in enumerate(bande):
                for x, tx in segs(l):
                    c = col_de(x)
                    if k < premiere:
                        if not re.search(r'LIMITES|ERNIP|^\(|^\)', tx, re.I):
                            noms[c].append(tx)
                    else:
                        corps[c].append(tx)
            for c in range(len(starts)):
                polys = polys_ou_ref(' '.join(corps[c]))
                if polys:
                    nom = re.sub(r'\s+', ' ', ' '.join(noms[c])).strip()[:80]
                    out.append({'n': nom, 'p': [[[round(a, 4), round(b, 4)] for a, b in p] for p in polys]})
        i = fin
    return out


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
        polys = polys_ou_ref(bloc)
        if polys:
            out.append({'n': nom, 'p': [[[round(a, 4), round(b, 4)] for a, b in p] for p in polys]})
    return out


MOTS = {'UNE': 1, 'UN': 1, 'DEUX': 2, 'TROIS': 3, 'QUATRE': 4, 'CINQ': 5, 'SIX': 6, 'SEPT': 7, 'HUIT': 8, 'NEUF': 9, 'DIX': 10, 'ONZE': 11, 'DOUZE': 12}


def attendu(chemin):
    """Nombre de zones annoncé dans le titre du SUP AIP (« création de 16 zones… »), ou None."""
    try:
        t = subprocess.run(['pdftotext', '-layout', chemin, '-'], capture_output=True, text=True).stdout
    except Exception:
        return None
    t = re.sub(r'\s+', ' ', t.upper())
    m = re.search(r"CR[ÉE]ATION (?:A TITRE EXP[ÉE]RIMENTAL )?(?:D['’]|DE )\s*(UNE?|\d+|[A-Z]+) (?:NOUVELLES? )?(?:ZONES?|ZRT|ZDT|TSA|TRA|ZIT|ESPACES?)", t)
    if not m:
        return None
    w = m.group(1)
    return int(w) if w.isdigit() else MOTS.get(w)


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
    chk = dict(ancien.get('_chk') or {})
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
        n = sum(len(o['p']) for o in z)
        att = attendu(os.path.join(DOSSIER, f))
        if att and n < att:
            chk[cle] = [n, att]
        else:
            chk.pop(cle, None)
    res['_chk'] = {k: v for k, v in chk.items() if k in res}
    if res == ancien and os.path.exists(SORTIE):
        print('supzones.js est déjà à jour.')
        return
    with open(SORTIE, 'w', encoding='utf-8') as f:
        f.write('window.TRI_SUPZ=' + json.dumps(res, ensure_ascii=False, separators=(',', ':')) + ';\n')
    sups = [k for k in res if k not in ('_v', '_chk')]
    print('%d SUP AIP, dont %d avec des contours.' % (len(sups), sum(1 for k in sups if res[k])))
    with open(os.path.join(ICI, 'supzones_rapport.txt'), 'w', encoding='utf-8') as f:
        f.write('SUP AIP dont les contours sont incomplets (trouvées / annoncées) :\n')
        for k, v in sorted(res['_chk'].items()):
            f.write('  %s : %d / %d\n' % (k, v[0], v[1]))
        f.write('Total : %d\n' % len(res['_chk']))
    print('%d SUP AIP à contours incomplets (voir supzones_rapport.txt).' % len(res['_chk']))


if __name__ == '__main__':
    main()
