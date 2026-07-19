# Etude marche achat/revente automobile Belgique 2024-2026

Date de verification: 2026-07-19

## Synthese executable

Le marche belge de l'occasion reste structurellement favorable a l'achat/revente rapide:

- 2024: 727 650 voitures d'occasion immatriculees en Belgique, +5,6% selon TRAXIO/FEBIAC.
- 2025: marche encore tres haut. Les sources publiques divergent selon le perimetre: environ 679 662 voitures particulieres d'occasion citees par AutoScout24, et 734 165 vehicules d'occasion cites par TRAXIO/Belga/BX1.
- La demande reste dominee par les particuliers, autour de 90% des immatriculations d'occasion.
- Essence majoritaire: environ 55-61% selon source/periode. Diesel recule fortement mais reste vendable sur les modeles economiques et premium si Euro 6 et kilometrage coherent.
- Prix moyens en baisse/stabilisation depuis 2023: TRAXIO cite environ -7,5% en 2024; AutoScout24 cite 23 348 EUR de prix moyen en novembre 2024 et 26 572 EUR de prix moyen annonce en 2025.
- Les modeles les plus liquides restent constants: VW Golf, VW Polo, Opel Corsa, BMW Serie 3, BMW Serie 1.

Conclusion operationnelle: le bot doit privilegier les modeles a forte rotation, prix public inferieur au marche, historique Car-Pass coherent, Euro 6 recommande, et faible risque mecanique. La marge brute realiste est generalement de 800 a 2 500 EUR sur les voitures de grande diffusion; elle peut depasser 3 000 EUR sur premium/sportives, mais avec risque de frais nettement plus eleve.

## Sources principales utilisees

- TRAXIO, bilan occasion 2024: 727 650 occasions, +5,6%, prix en baisse, top modeles Golf/Polo/Corsa/BMW.
- FEBIAC, analyse marche 2024: 1 175 927 immatriculations totales, 448 277 neuves et 727 650 occasions; essence 55,1% des occasions, diesel 30,6%, hybrides 10%+.
- Car-Pass 2024: 849 860 documents, moyenne 9,4 ans et 106 021 km; fraude compteur 0,11% domestique.
- Car-Pass 2025: 855 169 documents, moyenne 9,8 ans et 107 127 km; budget moyen acheteur 12 160 EUR, moitie sous 10 000 EUR.
- 2ememain 2024: plus de 2 millions d'annonces auto, prix moyen 15 234 EUR, Golf modele le plus vu, Volkswagen marque la plus consultee.
- AutoScout24 2024/2025: prix moyens par periode, stabilisation et ecart particuliers/professionnels; particulier environ 18 006 EUR en 2025.
- SPF Mobilite open data: source officielle pour immatriculations par marque/modele, statut neuf/usage, carburant, Euro.
- LEZ Bruxelles officielle: diesel minimum Euro 6, essence/CNG/LPG minimum Euro 3 pour circuler sans amende.
- LEZ Anvers/Gand officielles: diesel Euro 5/6 admis, essence Euro 2+ admis; verifier toujours la norme Euro sur certificat d'immatriculation/COC/Car-Pass.
- ADAC Pannenstatistik 2024/2026: base comparative de fiabilite/pannes sur modeles europeens.

## Limites

Les plateformes AutoScout24, 2ememain, Gocar, LeParking, Mobile.de et Facebook Marketplace ne publient pas toutes des donnees completes par modele incluant prix net de transaction, delai de vente reel et marge apres revente. Les prix et marges par modele dans le JSON sont donc des estimations business a calibrer avec les scans reels du bot:

- prix_min/prix_max: fourchette d'achat cible, pas cote officielle.
- marge_estimee: marge brute realiste avant frais imprevisibles.
- delai_revente_jours: vitesse estimee si prix coherent et annonce propre.
- score_liquidite: combine volume d'immatriculations, vues/recherches publiques, presence sur plateformes.
- score_risque: 0 = faible risque, 100 = risque tres eleve.

## Systeme de notation

score_total = 25% marge + 25% prix sous marche + 20% vitesse de revente + 20% fiabilite + 10% risque inverse.

Conversion:

- 85-100: ACHETER IMMEDIATEMENT
- 75-84: BONNE AFFAIRE
- 60-74: A NEGOCIER
- 45-59: RISQUE ELEVE
- 0-44: A EVITER

## Top 50 achat/revente Belgique

Voir `business/data/marche_revente_belgique_top50.json`.

## Classements rapides

### Top 10 meilleure marge

1. Golf GTI
2. BMW M135i
3. Audi S3
4. Golf R
5. Mercedes Classe A
6. BMW Serie 3
7. Audi A3
8. Mercedes Classe C
9. Peugeot 3008
10. BMW X1

### Top 10 revente rapide

1. Volkswagen Golf
2. Volkswagen Polo
3. Opel Corsa
4. BMW Serie 1
5. Audi A3
6. Renault Clio
7. Peugeot 208
8. BMW Serie 3
9. Mercedes Classe A
10. Toyota Yaris

### Top 10 fiabilite

1. Toyota Yaris
2. Toyota Corolla
3. Skoda Fabia
4. Skoda Octavia
5. Mazda 3
6. Hyundai i20
7. Kia Ceed
8. Volkswagen Polo
9. Audi A3
10. Peugeot 208

### Top 10 budget sous 10 000 EUR

1. Volkswagen Polo
2. Opel Corsa
3. Renault Clio
4. Ford Fiesta
5. Toyota Yaris
6. Peugeot 208
7. Seat Ibiza
8. Skoda Fabia
9. Citroen C3
10. Volkswagen Golf

### Top 10 budget 10 000-15 000 EUR

1. Volkswagen Golf
2. Audi A3
3. BMW Serie 1
4. Opel Astra
5. Peugeot 308
6. Ford Focus
7. Seat Leon
8. Skoda Octavia
9. Mercedes Classe A
10. Toyota Corolla

### Top 10 budget 15 000-20 000 EUR

1. BMW Serie 3
2. Mercedes Classe A
3. Audi A3
4. BMW X1
5. Volkswagen T-Roc
6. Peugeot 3008
7. Golf GTI
8. Mercedes Classe C
9. Volvo V40
10. Toyota C-HR

### Top 10 a eviter ou acheter seulement tres decote

1. Nissan Qashqai diesel ancien
2. Renault Scenic diesel ancien
3. Ford Kuga diesel ancien
4. Toyota C-HR recent a batterie 12V surveiller
5. Toyota Yaris recente a batterie 12V surveiller
6. BMW 5 diesel fort kilometrage
7. Mercedes Classe E diesel ancien fort kilometrage
8. Audi Q3 diesel fort kilometrage
9. Volkswagen Touran diesel ancien
10. Fiat 500 automatique/Dualogic

### Top diesel

1. BMW 320d Euro 6
2. BMW 118d Euro 6
3. Audi A3 2.0 TDI Euro 6
4. Volkswagen Golf 2.0 TDI Euro 6
5. Skoda Octavia 2.0 TDI Euro 6
6. Peugeot 308 1.5 BlueHDi Euro 6
7. Mercedes A 180d/A 200d Euro 6
8. Volkswagen Passat 2.0 TDI Euro 6
9. Opel Astra 1.6 CDTi Euro 6
10. Seat Leon 2.0 TDI Euro 6

### Top essence

1. Volkswagen Polo 1.0 TSI
2. Volkswagen Golf 1.0/1.5 TSI
3. Peugeot 208 PureTech avec historique courroie/verifications
4. Renault Clio TCe recent
5. Audi A3 1.0/1.4/1.5 TFSI
6. BMW 118i
7. Opel Corsa essence
8. Ford Fiesta EcoBoost avec historique
9. Toyota Yaris essence
10. Seat Ibiza 1.0 TSI

### Top hybride

1. Toyota Yaris Hybrid
2. Toyota Corolla Hybrid
3. Toyota C-HR Hybrid
4. Lexus CT 200h
5. Hyundai Ioniq Hybrid
6. Kia Niro Hybrid
7. Renault Clio E-Tech
8. Honda Jazz Hybrid
9. Toyota Prius
10. Ford Puma mHEV

## 20 meilleurs compromis

Critere: risque faible/moyen, forte demande, revente estimee sous 30 jours, marge brute > 1 000 EUR.

1. Volkswagen Golf
2. Volkswagen Polo
3. Audi A3
4. BMW Serie 1
5. Opel Corsa
6. Renault Clio
7. Peugeot 208
8. Skoda Octavia
9. Seat Leon
10. Ford Fiesta
11. Toyota Yaris
12. Peugeot 308
13. Opel Astra
14. BMW Serie 3
15. Mercedes Classe A
16. Ford Focus
17. Seat Ibiza
18. Skoda Fabia
19. Volkswagen T-Roc
20. Toyota Corolla

## Strategie par capital

### Capital 5 000 EUR

Objectif: petites citadines propres, achat tres selectif, rotation rapide.

- Cibles: Polo, Corsa, Clio, Fiesta, C3, Ibiza, Fabia.
- Eviter: premium ancien, diesel Euro 4 ou moins, automatique fragile, voitures sans Car-Pass coherent.
- Marge cible: 600-1 200 EUR.
- Strategie: une seule voiture a la fois, prix d'achat sous marche d'au moins 15%.

### Capital 10 000 EUR

Objectif: citadines recentes et compactes d'entree.

- Cibles: Golf, Polo, 208, Clio, Yaris, Astra, Focus.
- Marge cible: 900-1 800 EUR.
- Strategie: acheter essence/Euro 6, presentation propre, entretien prouve.

### Capital 15 000 EUR

Objectif: compactes premium et gros volumes.

- Cibles: Audi A3, BMW Serie 1, Mercedes Classe A, Golf, Octavia, Leon.
- Marge cible: 1 200-2 500 EUR.
- Strategie: priorite aux annonces particulieres sous marche, eviter gros frais non documentes.

### Capital 20 000 EUR

Objectif: premium/sportif controle ou SUV tres liquide.

- Cibles: BMW Serie 3, BMW X1, Golf GTI, Audi A3/S3 selectif, Peugeot 3008, T-Roc.
- Marge cible: 1 500-3 500 EUR.
- Strategie: inspection stricte, historique complet, marge de securite mecanique au moins 1 500 EUR.

## Revenus possibles

Hypotheses prudentes:

- Marge brute moyenne basse: 1 000 EUR/vente.
- Marge brute moyenne cible: 1 700 EUR/vente.
- Frais moyens preparation/annonces/transport: 250-600 EUR.
- Marge nette prudente: 700-1 200 EUR/vente.

| Ventes/mois | Net prudent | Net cible |
|---:|---:|---:|
| 1 | 700 EUR | 1 200 EUR |
| 2 | 1 400 EUR | 2 400 EUR |
| 5 | 3 500 EUR | 6 000 EUR |
| 10 | 7 000 EUR | 12 000 EUR |

Point critique: a partir de 5 ventes/mois, l'avantage vient moins de la marge unitaire que du process: sourcing, controle mecanique, photos, publication, suivi prix, rapidite de negotiation.

## Recommandations bot

1. Ne jamais classer une annonce en ACHETER IMMEDIATEMENT si prix inconnu, kilometrage inconnu ou lien non exploitable.
2. Penaliser diesel non Euro 6, sauf achat tres decote hors Bruxelles.
3. Penaliser fortement les modeles premium au-dessus de 180 000 km sans historique complet.
4. Bonifier les modeles top volume: Golf, Polo, Corsa, BMW Serie 1/3, A3, Clio, 208.
5. Integrer Car-Pass comme signal critique: age, kilometrage, rappel ouvert, historique entretien.
6. Garder une marge securite mecanique: 800 EUR citadine, 1 200 EUR compacte, 2 000 EUR premium/sportive.
7. Calibrer automatiquement les prix moyens avec les annonces observees localement par source et par region.

