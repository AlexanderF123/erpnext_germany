---
name: reisekostenabrechnung
description: Erstellt aus einer natürlichsprachigen Beschreibung eine deutsche Reisekosten-/Spesenabrechnung als Business Trip in ERPNext (ERPNext Germany). IMMER verwenden bei "Spesenabrechnung", "Reisekosten", "Dienstreise", "Fahrt nach ...", "Verpflegungspauschale", "Verpflegungsmehraufwand", "Kilometergeld", "Kilometerpauschale", "Übernachtung abrechnen" — auch wenn nur ein Satz wie "erstelle die Abrechnung für meine Fahrt gestern nach X" kommt. Enthält die Pflicht-Rückfragen, die Feldbelegung und die Regeln, die eine steuerlich anerkennungsfähige Abrechnung ausmachen.
---

# Reisekostenabrechnung in ERPNext

## Eiserne Regel

**Rechne keinen einzigen Betrag selbst aus.** Nicht die Verpflegungspauschale, nicht das
Kilometergeld, nicht die Kürzung bei gestellten Mahlzeiten. Du trägst nur Fakten ein; der
Controller von `Business Trip` rechnet beim Speichern und füllt `total_allowance` und
`total_mileage_allowance`. Lies die Beträge danach aus dem gespeicherten Dokument zurück und
nenne nur diese.

Ein von einem Sprachmodell errechneter Pauschbetrag ist in einer Betriebsprüfung wertlos —
und liegt erfahrungsgemäß daneben, sobald Kürzungen oder die 8-Stunden-Grenze im Spiel sind.

## Ablauf

1. **Fakten aus dem Satz ziehen**: Datum, Uhrzeiten, Ziel, Anlass.
2. **Fehlendes gebündelt erfragen** (Tabelle unten). Nichts raten, nichts mit Platzhaltern füllen.
3. **`Business Trip` als Entwurf anlegen** — nie direkt submitten.
4. **Ergebnis melden**: Link auf das Dokument plus die vom System berechneten Summen.
5. Der Submit ist Sache des Menschen; er erzeugt automatisch den Expense Claim.

## Pflicht-Rückfragen

| Wenn unklar | Frage | Warum |
|---|---|---|
| Gesellschaft | „Für welche Gesellschaft?" | Es gibt mehrere Companies; nur die, bei denen die Person `Employee` ist, oder die zum Anlass passt |
| Verkehrsmittel | „Eigenes Auto, Firmenwagen oder Bahn?" | Kilometergeld nur bei `Car (private)` |
| Fahrzeug | „Welches Fahrzeug?" | Nur wenn der Mitarbeiter mehrere `Employee Vehicle` hat; bei einem einzigen ohne Rückfrage übernehmen |
| Kilometer | erst `Business Trip Distance` prüfen, sonst fragen | Bemessungsgrundlage; **einfache** Strecke je Fahrt |
| Uhrzeiten | „Wann los, wann zurück?" | 8-Stunden-Grenze: darunter gibt es eintägig gar nichts |
| Mahlzeiten | „Frühstück/Mittag/Abend gestellt?" | Kürzung 20 / 40 / 40 % vom Ganztagssatz |
| Übernachtung | „Wo übernachtet, Rechnung vorhanden?" | Ganztags- vs. An-/Abreisesatz, Belegpflicht |
| Anlass | „Was war der Anlass?" | Pflichtangabe, gehört in `title` |

## Feldbelegung

**`Business Trip`** (Kopf): `employee`, `company`, `title` (= Anlass), `from_date`, `to_date`,
`region` (Inland: Region mit Titel „Deutschland"; Ausland: Region zum Zielland/-ort suchen),
optional `project`, `cost_center`, `customer`.

**`journeys`** — eine Zeile je Fahrt, Hin- und Rückfahrt sind **zwei** Zeilen:
`date`, `mode_of_transport` (`Car (private)` = privat, `Car` = Firmenwagen, `Car (rental)` =
Mietwagen, sonst `Train`, `Airplane`, `Taxi`, `Bus`, `Public Transport`), `from`, `to`,
`distance` (einfache Strecke, nur bei Auto), `employee_vehicle`.

**`allowances`** — eine Zeile je **Kalendertag**: `date`, `from_time`, `to_time`,
`whole_day` (nur volle Zwischentage mehrtägiger Reisen), und **immer explizit**:
`breakfast_was_provided`, `lunch_was_provided`, `dinner_was_provided`,
`accommodation_was_provided`.

> **Der häufigste Fehler:** `breakfast_was_provided` und `accommodation_was_provided` haben den
> Default `1`. Wer sie nicht bewusst auf `0` setzt, kürzt die Pauschale ohne Grund um 20 %.
> Setze alle vier Felder selbst — auch die, die `0` sein sollen.

**`accommodations`**: `from_date`, `to_date`, `city`, `receipt`.
**`other_expenses`**: `date`, `description`, `receipt` — ohne Beleg keine Erstattung.

## Rechenregeln, die das System anwendet (zur Kontrolle, nicht zum Nachrechnen)

* Inland 2026: 28,00 € ganztägig, 14,00 € An-/Abreisetag oder > 8 h; eintägig ≤ 8 h → 0,00 €.
* Kürzung: Frühstück −20 %, Mittag −40 %, Abend −40 % vom **Ganztagssatz**, nie unter 0 €.
* 0,30 €/km bei `Car (private)`; Motorrad und andere motorbetriebene Fahrzeuge 0,20 €/km
  (über `Employee Vehicle.vehicle_class`).
* Ausland: Sätze je `Business Trip Region` mit Gültigkeitsdatum; Übernachtungspauschale nur,
  wenn keine Unterkunft gestellt wurde.

Weicht das Ergebnis des Systems von deiner Erwartung ab: **das System hat recht**, oder eine
Eingabe ist falsch. Prüfe die Eingaben, nicht die Rechnung.

## Wie du auf die Daten zugreifst

**Über die Dokument-API, nie an ihr vorbei.** Lesen mit `get_list` / `get_value` / `get_doc`,
schreiben mit `insert` / `save` / `set_value` — damit laufen Validierung, Berechnung und
Berechtigungen mit. Kein direktes SQL, um Werte zu setzen, und keine Abfrage, die
Berechtigungen umgeht: Was ein Nutzer nicht sehen darf, darfst du für ihn nicht lesen.

SQL nur lesend und nur, wenn eine Auswertung anders nicht geht — nie als Weg, eine Validierung
oder eine Rechteprüfung zu umgehen. Die Beträge entstehen im Lifecycle des Dokuments
(`before_save`); wer sie per SQL setzt, umgeht genau die Logik, die die Abrechnung korrekt macht.

## Verboten

- Beträge schätzen, runden oder nachrechnen.
- Kilometer erfinden.
- Submitten, bezahlen, oder einen Expense Claim von Hand anlegen.
- Felder per SQL schreiben oder Berechtigungen umgehen.
- Eine zweite Reise für einen Tag anlegen, für den schon eine existiert — vorher `Business Trip`
  nach `employee` und Datum prüfen und im Zweifel fragen.

## Voraussetzungen im System

`Business Trip Settings` müssen gefüllt sein (Kilometerpauschale, beide Expense Claim Types),
sonst bricht der Submit ab. Konfiguration und Gesamtablauf: `docs/reisekosten-ki-konzept.md`.
