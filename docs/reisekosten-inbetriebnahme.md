# Inbetriebnahme — was vor, beim und nach dem Deploy zu tun ist

Stand 15.08.2026. Zielsystem: axessio.de (Frappe Cloud, v15).

## Vor dem Deploy — bereits erledigt

| Was | Stand |
|---|---|
| Expense Claim Types `Verpflegungsmehraufwand` (6664 / 6674) und `Kilometerpauschale` (6663 / 6673), je Gesellschaft | angelegt |
| `Business Trip Settings`: 0,30 €/km, beide Typen verknüpft | gesetzt |
| Konto 3720 als *Payable* markiert, als Verbindlichkeitskonto je Gesellschaft hinterlegt (axessio Unternehmensgruppe, Hausverwaltung, Hotel Baden-Baden) | gesetzt |
| Mitarbeiterdatensätze: Alexander, Maximilian, Christina und Philipp bei **allen 17 Gesellschaften** (68 Datensätze) | angelegt |
| Bezeichnungen `Inhaber` / `Mitarbeiter` (Stiftungen) | angelegt |
| Mitarbeiter-Benennung auf Nummernkreis `HR-EMP-` umgestellt | erledigt |
| Ask-ALYF-Skill „axessio – Reisekosten & Spesenabrechnung" | angelegt |
| Feature-Datensatz FEAT-15684 | angelegt |

Die Benennung musste umgestellt werden, weil ERPNext bei „Voller Name" keinen zweiten
Mitarbeiter gleichen Namens zulässt — bei 17 Gesellschaften je Person geht das nicht anders.
Bestehende Datensätze behalten ihren Namen.

## Beim Deploy

1. Fork `AlexanderF123/erpnext_germany`, Branch `feature/reisekosten-ki` (oder nach dem Merge
   `version-15-hotfix`) als App-Quelle in Frappe Cloud hinterlegen.
2. `bench migrate` läuft mit dem Deploy: es entstehen die DocTypes `Business Trip Distance`,
   `Employee Vehicle` und `Business Trip Intake`, die neuen Felder an `Business Trip Journey`
   und `Business Trip Settings` — und die geänderten Vorgabewerte der Tageszeilen.
3. Danach einmal `bench --site axessio.de run-tests --app erpnext_germany` — die Tests sind
   geschrieben, aber im Entwicklungscontainer nie gelaufen (dort gibt es keine Site).

## Nach dem Deploy — Restarbeiten

### 1. Standard-Region setzen

`Business Trip Settings` → **Standard-Region** = „Deutschland". Ohne sie fragt die Erfassung bei
jeder Inlandsreise nach der Region.

### 2. Fahrzeuge anlegen

`Employee Vehicle`, je Person **einmal** (die Suche läuft über die Person, nicht über den
einzelnen Mitarbeiterdatensatz):

| Person | Fahrzeug | Kennzeichen | Eigentum | Art |
|---|---|---|---|---|
| Alexander Finkeißen | Jaguar XF Sportbrake | HD-AX90 | Privat | Pkw |
| Alexander Finkeißen | BMW 120 | HD-PJ70 | Privat | Pkw |
| Alexander Finkeißen | Jaguar XKR | HD-XK88 | Privat | Pkw |
| Christina Finkeißen | Jaguar XF Sportbrake | HD-AX90 | Privat | Pkw |
| Christina Finkeißen | BMW 120 | HD-PJ70 | Privat | Pkw |
| Christina Finkeißen | Jaguar XKR | HD-XK88 | Privat | Pkw |

Alle sechs als Pkw — damit gilt durchgehend der Satz von 0,30 €/km. Je Person **ein**
Standardfahrzeug markieren, sonst fragt die Erfassung bei jeder Fahrt nach, welches es war.

### 3. IBAN eintragen

Der MCP-Zugang sperrt das Feld `iban` („restricted field"), deshalb von Hand am
Mitarbeiterdatensatz:

| Person | IBAN | Bank |
|---|---|---|
| Alexander Finkeißen | `DE79200411110679723700` (comdirect Giro) | comdirect bank |
| Christina Finkeißen | `DE79200411110679723700` (dasselbe comdirect-Konto) | comdirect bank |
| Maximilian Finkeißen | `DE02670923000033108982` (Volksbank Kurpfalz) | bereits gesetzt |

Die Bankbezeichnung ist bei allen neuen Datensätzen schon eingetragen; es fehlt nur die IBAN.
Für die Erstattung genügt sie auf dem Datensatz der zahlenden Gesellschaft. Philipps Bankdaten
liegen nicht im System — bei Bedarf nachtragen.

### 4. Entfernungstabelle füllen

Startpunkt einheitlich **„Heidelberg, Büro"** (Sofienstraße 6-10, 69115 Heidelberg), Ziel = der
Objektname. Einzutragen ist die **einfache** Strecke inklusive der 7,5 km für Parkplatzsuche.

Routing-Dienste sind aus der Entwicklungsumgebung gesperrt (Nominatim, OSRM und ADAC laufen
alle in den Egress-Filter). Die Werte unten stammen deshalb aus veröffentlichten
Streckenangaben zwischen den Stadtzentren, gerundet auf ganze Kilometer — das Feld `distance`
ist ganzzahlig, die 7,5 km ergeben daher einen Rundungsschritt.

| Ziel (Stadt) | Fahrstrecke lt. Quelle | + 7,5 km | einzutragen | Objekte |
|---|---|---|---|---|
| Mannheim | 21 km | 28,5 | **29** | 10 Objekte (Hebelstr., Augustaanlage 13 + 50, I7, D6, A3, Kaiserring, Gluckstr., Ifflandstr., Käfertaler Str.) |
| Ludwigshafen | 23 km | 30,5 | **31** | 12 Objekte (Knollstr. 1/3/19, Saarlandstr. 135–141, Pestalozzistr. 2–10, Garagen) |
| Bruchsal | 37 km | 44,5 | **45** | Hildastraße 1 |
| Darmstadt | 57 km | 64,5 | **65** | 6 Objekte (Wilhelminenstr., Karlstr., Osannstr., Magdalenenstr. 9 + 11c, Heidenreichstr.) |
| Kirchheimbolanden | 78 km | 85,5 | **86** | Albrecht-Dürer-Str., Eisenberg Plakatwand |
| Baden-Baden | 90 km | 97,5 | **98** | Ooser Bahnhofstraße 6 |

Quellen: luftlinie.org, ADAC Maps, entfernungsrechnerkm.com, routenplaner.cc (abgerufen
15.08.2026). Die Angaben streuen je Quelle um ein bis drei Kilometer; genommen wurde jeweils
der mittlere Wert.

**Heidelberg innerorts — hier fehlt eine belastbare Quelle:**

| Objekt | Vorschlag | Anmerkung |
|---|---|---|
| HD Sofienstraße (H-103) | — | Das ist das Büro selbst; eine Fahrt dorthin ist keine Dienstreise |
| HD Lutherstraße 25a (H-102) | 2 + 7,5 → **10** | geschätzt |
| HD Bergstraße 29b (H-104) | 3 + 7,5 → **11** | geschätzt |
| HD Schloss-Wolfsbrunnenweg 62 (H-101) | 4 + 7,5 → **12** | geschätzt |
| HD Kranichweg 35-37 (H-105) | 6 + 7,5 → **14** | geschätzt |

Diese vier sind **Schätzungen**, keine recherchierten Werte — innerorts liefert keine
Streckendatenbank Haus-zu-Haus-Werte. Bitte einmal mit dem Navi gegenprüfen; danach stehen sie
dauerhaft.

### 5. Testreise

Den Beispielsatz durchspielen und bis zur Buchung führen:

> „Erstelle die Spesenabrechnung für meine Fahrt heute 8 bis 17 Uhr nach Baden-Baden wegen
> Bauvorhaben Baden-Baden."

Erwartung: Rückfragen nach Gesellschaft, Verkehrsmittel und Mahlzeiten; danach 14,00 €
Verpflegung plus Kilometergeld, Entwurf, Submit, Expense Claim, Zahlung.

## Offen, unabhängig vom Deploy

* **Gegenkonto für die Unternehmer-Gesellschaften** (Christina Finkeißen Rechtsanwältin, MPF
  Immobilien KG): Die Erstattung gehört dort nicht auf ein Lohnkonto, sondern auf ein
  Privat-/Gesellschafterverrechnungskonto — Entscheidung des Steuerberaters.
* **Einordnung zweier Gesellschaften prüfen**: *Brilu-Stiftung Immobilienverwaltung & Co. KG*
  ist als KG mit „Inhaber" angelegt, obwohl der Name eine Stiftung nennt. Und bei den
  Einzelunternehmen der jeweils anderen Person steht „Mitarbeiter" statt „Inhaber".
* **Print Format** „Reisekostenabrechnung" und die Anbindung ans Automation Run Log.
* **Server-Script-Fehler**: „Assign Leave" (Before Save auf Employee) bricht mit
  `'>' not supported between instances of 'NoneType' and 'int'` ab, sobald
  `custom_working_days_per_week` leer ist. Alle neuen Datensätze wurden deshalb mit 0 angelegt.
  Das Script sollte den Leerfall abfangen.
