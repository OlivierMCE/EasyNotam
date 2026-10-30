#!/usr/bin/env python3
"""Met à jour le dossier supaip/ avec les SUP AIP métropole en vigueur publiés par le SIA.
- télécharge ceux qui manquent (SUP-AIP-NNN-AAAA.pdf)
- supprime ceux qui ne figurent plus sur la page du SIA
Aucune bibliothèque externe n'est nécessaire."""
import html, os, re, sys, time, urllib.request

BASE = 'https://www.sia.aviation-civile.gouv.fr'
LISTE = BASE + '/documents/supaip/aip/id/6'
DOSSIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'supaip')
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TriNotam-maj/1.0)'}


def get(url, tentatives=4):
    for i in range(tentatives):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:
            if i == tentatives - 1:
                raise
            print('  nouvel essai (%s)' % e)
            time.sleep(3 * (i + 1))


def lire_liste(page):
    """Renvoie {'238-2026': url_pdf, ...} d'après le tableau de la page du SIA."""
    out = {}
    for ligne in re.split(r'(?i)<tr\b', page)[1:]:
        lien = re.search(r'href="([^"]*/documents/download/[^"]+)"', ligne)
        if not lien:
            continue
        texte = html.unescape(re.sub(r'<[^>]+>', ' ', ligne))
        num = re.search(r'(?<!\d)(\d{1,3})\s*/\s*(\d{4})(?!\d)', texte)
        if not num:
            continue
        cle = '%s-%s' % (num.group(1).zfill(3), num.group(2))
        url = lien.group(1)
        out.setdefault(cle, url if url.startswith('http') else BASE + url)
    return out


def main():
    page = get(LISTE).decode('utf-8', 'replace')
    liste = lire_liste(page)
    print('%d SUP AIP trouvés sur la page du SIA' % len(liste))
    if len(liste) < 20:
        sys.exit('Liste suspecte (trop courte) : rien n\'est modifié.')
    os.makedirs(DOSSIER, exist_ok=True)
    presents = {f[8:-4] for f in os.listdir(DOSSIER) if re.fullmatch(r'SUP-AIP-\d{3}-\d{4}\.pdf', f)}
    ajouts = sorted(set(liste) - presents)
    retraits = sorted(presents - set(liste))
    erreurs = 0
    for cle in ajouts:
        try:
            data = get(liste[cle])
            if not data.startswith(b'%PDF'):
                raise ValueError('ce n\'est pas un PDF')
            with open(os.path.join(DOSSIER, 'SUP-AIP-%s.pdf' % cle), 'wb') as f:
                f.write(data)
            print('+ SUP AIP %s (%d Ko)' % (cle.replace('-', '/'), len(data) // 1024))
        except Exception as e:
            erreurs += 1
            print('! SUP AIP %s : %s' % (cle.replace('-', '/'), e))
    for cle in retraits:
        os.remove(os.path.join(DOSSIER, 'SUP-AIP-%s.pdf' % cle))
        print('- SUP AIP %s (n\'est plus en vigueur)' % cle.replace('-', '/'))
    print('Terminé : %d ajouté(s), %d retiré(s), %d erreur(s).' % (len(ajouts) - erreurs, len(retraits), erreurs))
    if erreurs:
        sys.exit(1)


if __name__ == '__main__':
    main()
