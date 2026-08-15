# Inbetriebnahme — was vor, beim und nach dem Deploy zu tun ist

Stand 15.08.2026. Zielsystem: axessio.de (Frappe Cloud, v15).

## Vor dem Deploy — bereits erledigt

| Was | Stand |
|---|---|
| Expense Claim Types `Verpflegungsmehraufwand` (6664 / 6674) und `Kilometerpauschale` (6663 / 6673), je Gesellschaft | angelegt |
| `Business Trip Settings`: 0,30 €/km, beide Typen verknüpft | gesetzt |
| Konto 3720 als *Payable* markiert, als Verbindlichkeitskonto je Gesellschaft hinterlegt (axessio Unternehmensgruppe, Hausverwaltung, Hotel Baden-Baden) | gesetzt |
| Mitarbeiterdatensätze: Alexander und Maximilian bei allen 17 Gesellschaften, Christina bei ihrer Kanzlei | angelegt |
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
| Alexander Finkeißen | (Bezeichnung ergänzen) | HD-AX90 | Privat | Pkw |
| Alexander Finkeißen | (Bezeichnung ergänzen) | HD-PJ70 | Privat | Pkw |
| Alexander Finkeißen | (Bezeichnung ergänzen) | HD-XK88 | Privat | Pkw |
| Christina Finkeißen | dieselben drei Kennzeichen | | Privat | Pkw |

Eines davon als **Standardfahrzeug** markieren — dann fragt die Erfassung nicht jedes Mal nach.
Sind es Motorräder oder andere motorbetriebene Fahrzeuge, die Fahrzeugart entsprechend setzen:
davon hängt der Satz ab (0,20 statt 0,30 €/km).

### 3. IBAN eintragen

Der MCP-Zugang sperrt das Feld `iban` („restricted field"), deshalb von Hand am
Mitarbeiterdatensatz:

| Person | IBAN | Bank |
|---|---|---|
| Alexander Finkeißen | `DE79200411110679723700` (comdirect Giro) | comdirect bank |
| Christina Finkeißen | zu bestätigen — im System liegt **kein** comdirect-Konto auf ihren Namen | |
| Maximilian Finkeißen | `DE02670923000033108982` (Volksbank Kurpfalz) | bereits gesetzt |

Die Bankbezeichnung ist bei allen neuen Datensätzen schon eingetragen; es fehlt nur die IBAN.
Für die Erstattung genügt sie auf dem Datensatz der zahlenden Gesellschaft.

### 4. Entfernungstabelle füllen

`Business Trip Distance`, Startpunkt einheitlich schreiben (Vorschlag: **„Heidelberg, Büro"**),
Ziel = Objektname wie unten. Einzutragen ist die **einfache** Strecke; auf jede kommen laut
Vorgabe **+7,5 km** für Parkplatzsuche.

**Die Kilometer fehlen noch, und ich trage sie nicht geraten ein.** Routing-Dienste sind aus
diesem Container nicht erreichbar (Proxy blockt Nominatim und OSRM), und eine erfundene
Entfernung ist genau das, was diese Lösung überall sonst verhindert. Sobald die Werte vorliegen
— aus dem Navi, aus Google Maps oder als Freigabe eines Routing-Dienstes — sind die Zeilen in
einem Zug angelegt.

Die 37 Objekte (ohne die beiden Abrechnungsgruppen und das Demo-Objekt):

| Stadt | Objekte |
|---|---|
| Heidelberg | Schloss-Wolfsbrunnenweg 62 · Lutherstraße 25a · Sofienstraße · Bergstraße 29b · Kranichweg 35-37 |
| Darmstadt | Wilhelminenstraße 50 · Karlstraße 85 · Osannstraße 4 · Magdalenenstraße 9/9a/9b · Magdalenenstraße 11c · Heidenreichstraße 40+40A |
| Mannheim | Hebelstraße 1 · Augustaanlage 50 · I7, 15 · D6, 2 · A3, 2 · Kaiserring 8-16 · Gluckstraße 6 · Augustaanlage 13 · Ifflandstraße 2-6 · Käfertaler Straße 39-41 |
| Ludwigshafen | Knollstraße 1 · Knollstraße 3 · Knollstraße 19 · Saarlandstraße 135 · 137 · 139 · 141 · Pestalozzistraße 2 · 6 · 8 · 10 · Garagen/Stellplätze |
| Kirchheimbolanden | Albrecht-Dürer-Straße 14-16 · Eisenberg Plakatwand |
| Bruchsal | Hildastraße 1 |
| Baden-Baden | Ooser Bahnhofstraße 6 |

Innerhalb einer Stadt unterscheiden sich die Strecken oft nur um ein bis zwei Kilometer — ein
Wert je Stadt plus Korrektur bei Ausreißern reicht in der Praxis, solange er belegbar ist.

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
