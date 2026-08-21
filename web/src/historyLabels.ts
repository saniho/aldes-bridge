export interface KeyMeta {
  family: string
  label: string
}

export const FAMILY_ORDER = [
  'Températures',
  'Consignes & limites',
  'Pressions',
  'Eau chaude (ECS)',
  'Modes & état',
  'Énergie & tarifs',
  'Ventilation & débits d’air',
  'Zones (10) — indicateurs',
  'Zones (12) — répartition',
  'Système & connexion',
  'Divers / non documenté',
] as const

export const FALLBACK_FAMILY = 'Divers / non documenté'

const EXACT: Record<string, KeyMeta> = {
  // Températures
  Text: { family: 'Températures', label: 'Température extérieure (°C)' },
  TAin: { family: 'Températures', label: 'Température air entrée (°C)' },
  TAHL: { family: 'Températures', label: 'Température échangeur air — bas (°C)' },
  TAHU: { family: 'Températures', label: 'Température échangeur air — haut (°C)' },
  TEHG: { family: 'Températures', label: 'Température échangeur — gaz (°C)' },
  TEHL: { family: 'Températures', label: 'Température échangeur — liquide (°C)' },
  TEHU: { family: 'Températures', label: 'Température échangeur — haut (°C)' },
  THGa: { family: 'Températures', label: 'Température gaine d’air (°C)' },
  TUeH: { family: 'Températures', label: 'Température unité extérieure (°C)' },

  // Consignes & limites
  CMaST: { family: 'Consignes & limites', label: 'Consigne max — chauffage (°C)' },
  CMiST: { family: 'Consignes & limites', label: 'Consigne min — chauffage (°C)' },
  FMaST: { family: 'Consignes & limites', label: 'Consigne max — froid (°C)' },
  FMiST: { family: 'Consignes & limites', label: 'Consigne min — froid (°C)' },

  // Pressions
  PreH: { family: 'Pressions', label: 'Pression haute circuit (×0,1 bar)' },
  dHi: { family: 'Pressions', label: 'Delta pression — haut' },
  dLo: { family: 'Pressions', label: 'Delta pression — bas' },

  // Eau chaude sanitaire
  TBBa: { family: 'Eau chaude (ECS)', label: 'Ballon ECS — bas (°C)' },
  TBHa: { family: 'Eau chaude (ECS)', label: 'Ballon ECS — haut (°C)' },
  NED: { family: 'Eau chaude (ECS)', label: 'Niveau ECS (%)' },
  BECS: { family: 'Eau chaude (ECS)', label: 'Besoin ECS (état)' },
  AntiL: { family: 'Eau chaude (ECS)', label: 'Protection anti-légionelles' },

  // Modes & état
  UAM: { family: 'Modes & état', label: 'Mode air (indice)' },
  UDM: { family: 'Modes & état', label: 'Mode eau (indice)' },
  NpiH: { family: 'Modes & état', label: 'Nombre de personnes (réglage)' },
  Dvac: { family: 'Modes & état', label: 'Début vacances (epoch)' },
  Fvac: { family: 'Modes & état', label: 'Fin vacances (epoch)' },
  MfAc: { family: 'Modes & état', label: 'Mode fonctionnement — air' },
  MfEc: { family: 'Modes & état', label: 'Mode fonctionnement — eau' },
  ApA1: { family: 'Modes & état', label: 'Appoint air 1' },
  ApA2: { family: 'Modes & état', label: 'Appoint air 2' },
  ApE: { family: 'Modes & état', label: 'Appoint électrique — eau' },
  HPC: { family: 'Modes & état', label: 'Haute pression compresseur (état)' },

  // Énergie & tarifs
  Pno: { family: 'Énergie & tarifs', label: 'Tarif kWh — normal' },
  Pint: { family: 'Énergie & tarifs', label: 'Tarif kWh — intermédiaire' },
  Pkof: { family: 'Énergie & tarifs', label: 'Tarif kWh — creux' },
  Vsec: { family: 'Énergie & tarifs', label: 'Compteur électrique (non documenté)' },
  EPVe: { family: 'Énergie & tarifs', label: 'Énergie (non documenté)' },
  CFrC: { family: 'Énergie & tarifs', label: 'Compteur froid (non documenté)' },
  RFrC: { family: 'Énergie & tarifs', label: 'Compteur froid (non documenté)' },
  CVeI: { family: 'Énergie & tarifs', label: 'Consommation (non documenté)' },
  Cena: { family: 'Énergie & tarifs', label: 'Consommation énergie (non documenté)' },
  EcF: { family: 'Énergie & tarifs', label: 'Économie (non documenté)' },
  Rec: { family: 'Énergie & tarifs', label: 'Récupération (non documenté)' },
  Sec: { family: 'Énergie & tarifs', label: 'Secondaire (non documenté)' },

  // Ventilation & débits d'air
  RVeI: { family: 'Ventilation & débits d’air', label: 'Vitesse rotation ventilateur (tr/min)' },
  Dno: { family: 'Ventilation & débits d’air', label: 'Débit d’air — nominal (m³/h)' },
  Dma: { family: 'Ventilation & débits d’air', label: 'Débit d’air — maximum (m³/h)' },
  Dint: { family: 'Ventilation & débits d’air', label: 'Débit d’air — intermédiaire (m³/h)' },
  DLN: { family: 'Ventilation & débits d’air', label: 'Débit d’air — faible nuit (m³/h)' },
  DPLe: { family: 'Ventilation & débits d’air', label: 'Débit d’air — plein (m³/h)' },
  DmCO: { family: 'Ventilation & débits d’air', label: 'Débit d’air — max CO₂ (m³/h)' },
  Dkof: { family: 'Ventilation & débits d’air', label: 'Débit d’air — hors gel (m³/h)' },

  // Système & connexion
  Vers_UC: { family: 'Système & connexion', label: 'Version unité centrale' },
  box: { family: 'Système & connexion', label: 'Connexion box (état)' },
  cloud: { family: 'Système & connexion', label: 'Connexion cloud Aldes (état)' },
  TyI: { family: 'Système & connexion', label: 'Type d’installation' },
  TyM: { family: 'Système & connexion', label: 'Type de machine' },
  IId: { family: 'Système & connexion', label: 'Identifiant installation' },
  NbO: { family: 'Système & connexion', label: 'Nombre d’ouvertures (compteur)' },
  NbME: { family: 'Système & connexion', label: 'Nombre de modes éco' },
  dt: { family: 'Système & connexion', label: 'Horodatage dernier relevé (epoch)' },
  Ddef: { family: 'Système & connexion', label: 'Compteur dégivrage' },
  Defr: { family: 'Système & connexion', label: 'Défaut circuit froid (état)' },
  Dev: { family: 'Système & connexion', label: 'État (non documenté)' },

  // Divers / non documenté
  AVG: { family: 'Divers / non documenté', label: 'Non documenté' },
  AVL: { family: 'Divers / non documenté', label: 'Non documenté' },
  CVG: { family: 'Divers / non documenté', label: 'Non documenté' },
  CVL: { family: 'Divers / non documenté', label: 'Non documenté' },
  NoOS: { family: 'Divers / non documenté', label: 'Non documenté' },
  HiOS: { family: 'Divers / non documenté', label: 'Non documenté' },
  OOT: { family: 'Divers / non documenté', label: 'Non documenté' },
  OCT: { family: 'Divers / non documenté', label: 'Non documenté' },
}

const PATTERNS: Array<{
  re: RegExp
  family: string
  label: (m: RegExpMatchArray) => string
}> = [
  {
    re: /^MT(\d+)$/,
    family: 'Températures',
    label: (m) => `Température zone ${m[1]} (°C)`,
  },
  {
    re: /^UsC(\d+)$/,
    family: 'Consignes & limites',
    label: (m) => `Consigne zone ${m[1]} (°C)`,
  },
  {
    re: /^Cre(\d+)$/,
    family: 'Consignes & limites',
    label: (m) => `Consigne éco zone ${m[1]} (°C)`,
  },
  {
    re: /^OCa(\d+)$/,
    family: 'Zones (10) — indicateurs',
    label: (m) => `Zone ${m[1]} — indicateur ventilation (a)`,
  },
  {
    re: /^OOa(\d+)$/,
    family: 'Zones (10) — indicateurs',
    label: (m) => `Zone ${m[1]} — indicateur ventilation (b)`,
  },
  {
    re: /^Os(\d+)$/,
    family: 'Zones (10) — indicateurs',
    label: (m) => `Zone ${m[1]} — indicateur ventilation (c)`,
  },
  {
    re: /^Cc(C|E|H)(\d+)$/,
    family: 'Zones (12) — répartition',
    label: (m) => `Zone ${m[2]} — indicateur ${m[1]}`,
  },
  {
    re: /^Co(C|E|H)(\d+)$/,
    family: 'Zones (12) — répartition',
    label: (m) => `Zone ${m[2]} — indicateur ${m[1]}`,
  },
]

export function getKeyMeta(key: string): KeyMeta {
  const exact = EXACT[key]
  if (exact) return exact
  for (const p of PATTERNS) {
    const m = key.match(p.re)
    if (m) return { family: p.family, label: p.label(m) }
  }
  return { family: FALLBACK_FAMILY, label: 'Non documenté' }
}