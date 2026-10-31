#!/usr/bin/env python3
"""Construit zones.js (contours des zones R, D, P, TRA, TSA, TMA, CTR...) à partir de l'eAIP France du SIA.
Lit les sections ENR 5.1, ENR 5.2 et ENR 2.1. Aucune bibliothèque externe n'est nécessaire."""
import html, json, math, os, re, sys, time, urllib.request

SITE = 'https://www.sia.aviation-civile.gouv.fr'
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zones.js')
SECTIONS = ['FR-ENR-5.1-fr-FR.html', 'FR-ENR-5.2-fr-FR.html', 'FR-ENR-2.1-fr-FR.html']
MOIS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TriNotam-maj/1.0)'}

NUM = r"(\d+)\s*°\s*(\d+)\s*['’′]\s*(\d+(?:[.,]\d+)?)\s*['’\"″”′]{0,2}\s*([NS])\s*[,\-–]?\s*(\d+)\s*°\s*(\d+)\s*['’′]\s*(\d+(?:[.,]\d+)?)\s*['’\"″”′]{0,2}\s*([EWO])"
RE_TOKEN = re.compile(
    r'(?P<circ>cercle de (?P<cr>[\d.,]+)\s*(?P<cu>NM|km|m)\s+de rayon centré sur\s*(?:le point\s*)?(?:[A-Z]{4}\s*ARP\s*)?(?:PSN\s*:?\s*)?(?P<cc>' + NUM + r'))'
    r'|(?P<arc>arc\s+(?P<dir>anti-horaire|horaire)\s+de\s+(?P<ar>[\d.,]+)\s*(?P<au>NM|km|m)\s+de rayon centré sur\s*(?:le point\s*)?(?:[A-Z]{4}\s*ARP\s*)?(?:PSN\s*:?\s*)?(?P<ac>' + NUM + r'))'
    r'|(?P<v>' + NUM + r')', re.I)
RE_V = re.compile(NUM)


def get(url, essais=4):
    for i in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:
            if i == essais - 1:
                raise
            print('  nouvel essai (%s)' % e)
            time.sleep(4 * (i + 1))


def dossier_airac():
    """Nom du dossier eAIP en vigueur et date AIRAC, lus sur la page d'accueil du SIA (sinon calculés)."""
    try:
        page = get(SITE + '/').decode('utf-8', 'replace')
        m = re.search(r'dvd(?:/|%2F)eAIP_(\d{1,2})_([A-Z]{3})_(\d{4})(?:/|%2F)FRANCE', page, re.I)
        if m:
            jj, mmm, aaaa = int(m.group(1)), m.group(2).upper(), int(m.group(3))
            return 'eAIP_%02d_%s_%d' % (jj, mmm, aaaa), '%d-%02d-%02d' % (aaaa, MOIS[mmm], jj)
        print('Dossier eAIP non trouvé sur la page d\'accueil : calcul de la date AIRAC.')
    except Exception as e:
        print('Page d\'accueil illisible (%s) : calcul de la date AIRAC.' % e)
    import datetime
    ref = datetime.date(2026, 10, 29)  # début d'un cycle AIRAC, les cycles durent 28 jours
    n = (datetime.date.today() - ref).days // 28
    d = ref + datetime.timedelta(days=28 * n)
    mois = {v: k for k, v in MOIS.items()}
    return 'eAIP_%02d_%s_%d' % (d.day, mois[d.month], d.year), d.isoformat()


def dms(m, o):
    lat = int(m.group(o + 1)) + int(m.group(o + 2)) / 60 + float(m.group(o + 3).replace(',', '.')) / 3600
    lon = int(m.group(o + 5)) + int(m.group(o + 6)) / 60 + float(m.group(o + 7).replace(',', '.')) / 3600
    return (-lat if m.group(o + 4).upper() == 'S' else lat, -lon if m.group(o + 8).upper() in ('W', 'O') else lon)


def vertex(texte):
    m = RE_V.search(texte)
    return dms(m, 0)


def rayon_nm(val, unite):
    r = float(val.replace(',', '.'))
    u = unite.lower()
    return r / 1.852 if u == 'km' else (r / 1852 if u == 'm' else r)


def arc(p0, p1, c, horaire):
    """Points d'un arc de cercle de p0 à p1 autour de c (sens horaire ou non)."""
    k = math.cos(math.radians(c[0]))
    def xy(p): return ((p[1] - c[1]) * k * 60, (p[0] - c[0]) * 60)
    (x0, y0), (x1, y1) = xy(p0), xy(p1)
    a0, a1 = math.atan2(x0, y0), math.atan2(x1, y1)
    r = (math.hypot(x0, y0) + math.hypot(x1, y1)) / 2
    bal = (a1 - a0) % (2 * math.pi) if horaire else -((a0 - a1) % (2 * math.pi))
    if abs(bal) < 1e-9:
        bal = 2 * math.pi if horaire else -2 * math.pi
    n = max(2, int(abs(math.degrees(bal)) / 5))
    out = []
    for i in range(1, n):
        a = a0 + bal * i / n
        out.append((c[0] + r * math.cos(a) / 60, c[1] + r * math.sin(a) / (60 * k)))
    return out


def cercle(c, r_nm):
    k = math.cos(math.radians(c[0]))
    return [(c[0] + r_nm * math.cos(2 * math.pi * i / 48) / 60, c[1] + r_nm * math.sin(2 * math.pi * i / 48) / (60 * k)) for i in range(48)]


def polygones(geo):
    """Texte des limites latérales -> liste de polygones [(lat, lon), ...]."""
    polys, pts, attente = [], [], None
    for m in RE_TOKEN.finditer(geo):
        if m.group('circ'):
            polys.append(cercle(vertex(m.group('cc')), rayon_nm(m.group('cr'), m.group('cu'))))
        elif m.group('arc'):
            attente = (vertex(m.group('ac')), m.group('dir').lower() == 'horaire')
        else:
            v = vertex(m.group('v'))
            if attente and pts:
                pts += arc(pts[-1], v, attente[0], attente[1])
            attente = None
            pts.append(v)
            if len(pts) >= 4 and abs(pts[0][0] - v[0]) < 1e-9 and abs(pts[0][1] - v[1]) < 1e-9:
                polys.append(pts[:-1])
                pts = []
    if len(pts) >= 3:
        polys.append(pts)
    return [p for p in polys if len(p) >= 3]


def texte(cell):
    t = re.sub(r'<[^>]+>', ' ', cell)
    return re.sub(r'\s+', ' ', html.unescape(t).replace('\xa0', ' ')).strip()


RE_NOM_LF = re.compile(r'^LF[\s-]*([A-Z]{1,4})\s*(\d+(?:\.\d+)?)\s*([A-Z]\d?)?\b')


def cle_et_type(nom):
    m = RE_NOM_LF.match(nom)
    if m:
        return (m.group(1) + m.group(2) + (m.group(3) or '')).upper(), m.group(1).upper()
    return re.sub(r'[^A-Z0-9]', '', nom.upper()), nom.split(' ')[0].upper()


def base(nom):
    b = re.sub(r'\s+partie\s*\d+.*$', '', nom, flags=re.I)
    return re.sub(r'\s+', ' ', b).strip().upper()


def lire_section(contenu, zones):
    courant = ''
    for tr in re.finditer(r'<tr\b[^>]*>(.*?)</tr>', contenu, re.S | re.I):
        cells = re.findall(r'<td\b[^>]*>(.*?)</td>', tr.group(1), re.S | re.I)
        if not cells:
            continue
        t = texte(cells[0])
        iv = re.search(r'\d+\s*°\s*\d+\s*\'|cercle de', t)
        if not iv:
            if len(t) < 90 and RE_NOM_LF.match(t):
                courant = t
            continue
        nom = t[:iv.start()].strip(' -') or courant
        if not nom or re.match(r'^(FIR|UIR)\b', nom):
            continue
        polys = polygones(t[iv.start():])
        if not polys:
            continue
        cle, typ = cle_et_type(nom)
        vert = texte(cells[1]) if len(cells) > 1 else ''
        vert = re.sub(r'\s*-{3,}\s*', ' / ', vert)
        z = zones.setdefault(cle, {'k': cle, 'n': nom, 't': typ, 'b': base(nom), 'v': vert, 'p': []})
        z['p'] += [[[round(a, 4), round(b, 4)] for a, b in p] for p in polys]


def main():
    nom, airac = dossier_airac()
    if os.path.exists(SORTIE):
        if ('"airac":"%s"' % airac) in open(SORTIE, encoding='utf-8').read(400):
            print('zones.js est déjà à jour (AIRAC %s).' % airac)
            return
    zones = {}
    for f in SECTIONS:
        url = '%s/media/dvd/%s/FRANCE/AIRAC-%s/html/eAIP/%s' % (SITE, nom, airac, f)
        print('Lecture de', f)
        lire_section(get(url).decode('utf-8', 'replace'), zones)
    if len(zones) < 300:
        sys.exit('Résultat suspect (%d zones seulement) : zones.js n\'est pas modifié.' % len(zones))
    data = {'airac': airac, 'z': sorted(zones.values(), key=lambda z: z['k'])}
    with open(SORTIE, 'w', encoding='utf-8') as f:
        f.write('window.TRI_ZONES=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('%d zones enregistrées (AIRAC %s).' % (len(zones), airac))


if __name__ == '__main__':
    main()
