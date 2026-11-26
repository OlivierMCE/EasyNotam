/* Écran de connexion EasyBrief : compte (e-mail + mot de passe), invitation, 1 à 2 appareils par compte.
   Les règles côté serveur sont dans firestore.rules ; ici, c'est l'interface et la vérification à chaque ouverture. */
const CFG = window.EB_AUTH && window.EB_AUTH.firebase;
const MAX = (window.EB_AUTH && window.EB_AUTH.maxAppareils) || 2;
const V = 'https://www.gstatic.com/firebasejs/10.12.2/';
const $ = id => document.getElementById(id);
const html = document.documentElement;

if (!CFG || !CFG.apiKey) { html.classList.remove('verrou'); }       // pas encore configuré : l'appli reste ouverte
else (async () => {
  const msg = (t, ok) => { const m = $('porte-msg'); m.textContent = t || ''; m.className = ok ? 'ok' : ''; };
  const ouvrir = email => { html.classList.remove('verrou'); $('compte-mail').textContent = email || ''; $('compte').hidden = false;
    try { localStorage.setItem('eb_ok', JSON.stringify({ t: Date.now(), e: email })); } catch (e) {} };
  const fermer = t => { html.classList.add('verrou'); $('compte').hidden = true; msg(t); try { localStorage.removeItem('eb_ok'); } catch (e) {} };

  let A, F, auth, db;
  try {
    const [app, au, fs] = await Promise.all([import(V + 'firebase-app.js'), import(V + 'firebase-auth.js'), import(V + 'firebase-firestore.js')]);
    A = au; F = fs;
    const a = app.initializeApp(CFG); auth = A.getAuth(a); db = F.getFirestore(a);
  } catch (e) {
    // hors ligne : on laisse entrer si la dernière vérification date de moins de 48 h
    let ok = null; try { ok = JSON.parse(localStorage.getItem('eb_ok') || 'null'); } catch (e2) {}
    if (ok && Date.now() - ok.t < 48 * 3600e3) { ouvrir(ok.e); return; }
    msg('Connexion impossible (réseau). Réessayez en ligne.'); $('porte-go').textContent = 'Réessayer'; $('porte-form').onsubmit = ev => { ev.preventDefault(); location.reload(); }; return;
  }

  const idAppareil = () => { let d = localStorage.getItem('eb_dev'); if (!d) { d = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()); localStorage.setItem('eb_dev', d); } return d; };
  const nomAppareil = () => { const u = navigator.userAgent; const t = /iPhone/.test(u) ? 'iPhone' : /iPad/.test(u) ? 'iPad' : /Android/.test(u) ? 'Android' : /Mac/.test(u) ? (navigator.maxTouchPoints > 1 ? 'iPad' : 'Mac') : /Windows/.test(u) ? 'Windows' : 'Appareil'; return t; };

  // vérifie que le compte est autorisé et que cet appareil a droit d'entrer
  async function verifier(user) {
    const ref = F.doc(db, 'users', user.uid);
    let snap;
    try { snap = await F.getDoc(ref); } catch (e) { return { ok: false, t: 'Accès refusé (compte non autorisé ou supprimé).' }; }
    if (!snap.exists()) return { ok: false, t: 'Ce compte n’est plus autorisé. Contactez l’administrateur.' };
    const d = snap.data();
    if (d.actif === false) return { ok: false, t: 'Ce compte est suspendu. Contactez l’administrateur.' };
    const id = idAppareil(), devs = d.devices || {};
    if (devs[id]) return { ok: true };
    if (Object.keys(devs).length >= MAX) return { ok: false, t: `Ce compte est déjà utilisé sur ${MAX} appareils. Demandez à l’administrateur de libérer une place.` };
    try { await F.updateDoc(ref, { ['devices.' + id]: { nom: nomAppareil(), ajout: Date.now() } }); } catch (e) { return { ok: false, t: 'Impossible d’enregistrer cet appareil.' }; }
    return { ok: true };
  }

  async function controle(user) {
    const r = await verifier(user);
    if (r.ok) { ouvrir(user.email); return true; }
    await A.signOut(auth); fermer(r.t); return false;
  }

  let creation = false;
  A.onAuthStateChanged(auth, user => { if (creation) return; if (user) controle(user); else { html.classList.add('verrou'); $('compte').hidden = true; } });
  // revérification régulière : un compte supprimé perd l'accès à la prochaine ouverture ou dans les 5 minutes
  const recheck = () => { if (auth.currentUser) verifier(auth.currentUser).then(r => { if (!r.ok) A.signOut(auth).then(() => fermer(r.t)); }); };
  setInterval(recheck, 5 * 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) recheck(); });

  // onglets Connexion / Créer un compte
  let mode = 'connexion';
  const setMode = m => { mode = m; $('porte').dataset.mode = m;
    $('t-conn').setAttribute('aria-selected', m === 'connexion'); $('t-crea').setAttribute('aria-selected', m === 'creation');
    $('porte-go').textContent = m === 'connexion' ? 'Se connecter' : 'Créer mon compte'; msg(''); };
  $('t-conn').onclick = () => setMode('connexion'); $('t-crea').onclick = () => setMode('creation');

  const traduire = e => ({
    'auth/invalid-credential': 'E-mail ou mot de passe incorrect.', 'auth/wrong-password': 'E-mail ou mot de passe incorrect.',
    'auth/user-not-found': 'E-mail ou mot de passe incorrect.', 'auth/email-already-in-use': 'Un compte existe déjà avec cet e-mail. Utilisez « Se connecter ».',
    'auth/weak-password': 'Mot de passe trop court (6 caractères minimum).', 'auth/invalid-email': 'Adresse e-mail invalide.',
    'auth/too-many-requests': 'Trop d’essais. Réessayez dans quelques minutes.', 'auth/network-request-failed': 'Réseau indisponible.'
  }[e && e.code] || 'Une erreur est survenue (' + ((e && e.code) || 'inconnue') + ').');

  $('porte-form').onsubmit = async ev => {
    ev.preventDefault();
    const email = $('p-mail').value.trim(), mdp = $('p-mdp').value, code = $('p-code').value.trim().toUpperCase();
    const go = $('porte-go'); go.disabled = true; msg('');
    try {
      if (mode === 'connexion') {
        await A.signInWithEmailAndPassword(auth, email, mdp);        // onAuthStateChanged fait le reste
      } else {
        if (!code) { msg('Entrez votre code d’invitation.'); return; }
        creation = true;
        const cred = await A.createUserWithEmailAndPassword(auth, email, mdp);
        try {
          const batch = F.writeBatch(db), id = idAppareil();
          batch.update(F.doc(db, 'invites', code), { used: true, usedBy: cred.user.uid, usedAt: Date.now() });
          batch.set(F.doc(db, 'users', cred.user.uid), { email, actif: true, code, created: Date.now(), devices: { [id]: { nom: nomAppareil(), ajout: Date.now() } } });
          await batch.commit();
          creation = false; await controle(cred.user);
        } catch (e) {                                                  // code faux ou déjà utilisé : on annule la création du compte
          try { await cred.user.delete(); } catch (e2) { await A.signOut(auth); }
          creation = false; msg('Code d’invitation invalide ou déjà utilisé.'); return;
        }
      }
    } catch (e) { creation = false; msg(traduire(e)); }
    finally { creation = false; go.disabled = false; }
  };
  $('porte-oubli').onclick = async () => {
    const email = $('p-mail').value.trim(); if (!email) { msg('Entrez d’abord votre e-mail.'); return; }
    try { await A.sendPasswordResetEmail(auth, email); msg('E-mail de réinitialisation envoyé.', true); } catch (e) { msg(traduire(e)); }
  };
  $('compte-sortie').onclick = () => A.signOut(auth).then(() => fermer(''));
})();
