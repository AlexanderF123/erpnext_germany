# Die Skills — was die KI wissen muss, und warum

Zwei Kanäle bedienen dieselbe Fachlogik: **Ask ALYF** (Chat im Desk) und **Claude** (MCP /
Claude Code). Damit beide gleich arbeiten, tragen sie denselben Regelsatz.

* **Claude**: `.claude/skills/reisekostenabrechnung/SKILL.md` in diesem Repository — reist mit
  dem Code, wird bei jeder Reisekosten-Frage automatisch geladen.
* **Ask ALYF**: DocType `Ask ALYF Skill`, Titel „axessio – Reisekosten & Spesenabrechnung".
  Achtung: Wenn der System-Prompt der Instanz das Laden von Skills unterbindet (bei axessio
  steht dort „Rufe das Tool `read_skill` NICHT auf"), muss der Regelsatz stattdessen in den
  System-Prompt — sonst liegt der Skill da und wird nie gelesen.

Beide Fassungen sind bewusst **kurz**. Alles, was Regel ist, steckt im Server; der Skill sagt
nur, wie man mit ihm umgeht.

---

## Die eine Regel, aus der alles andere folgt

> **Die KI ermittelt Fakten. Der Server rechnet.**

Ein Sprachmodell, das eine Verpflegungspauschale „ausrechnet", produziert eine Zahl, die
plausibel aussieht und in einer Betriebsprüfung nichts wert ist — niemand kann sie herleiten,
und bei Kürzungen oder der 8-Stunden-Grenze liegt sie regelmäßig daneben. Deshalb trägt die KI
ausschließlich Sachverhalte ein (Ort, Zeit, Anlass, Verkehrsmittel, gestellte Mahlzeiten), und
jeder Betrag entsteht deterministisch in Python aus Regionstabelle, Einstellungen und
Entfernungstabelle.

Das ist keine Vorsichtsmaßnahme gegen schlechte Modelle, sondern eine Frage der Beweisbarkeit:
Was der Server gerechnet hat, lässt sich Zeile für Zeile nachvollziehen — auch in drei Jahren,
auch von jemandem, der nie mit der KI gesprochen hat.

## Warum die Rückfragen im Server stehen und nicht im Prompt

Der naheliegende Weg wäre gewesen, den Fragenkatalog in den Skill zu schreiben. Dagegen sprechen
drei Dinge:

1. **Zwei Kanäle, eine Wahrheit.** Ask ALYF und Claude würden sonst zwei Kataloge pflegen, die
   auseinanderlaufen, sobald einer geändert wird.
2. **Modellwechsel.** Der Katalog überlebt jeden Wechsel des Sprachmodells, weil er nicht im
   Prompt lebt.
3. **Prüfbarkeit.** Eine Regel im Python-Code hat Tests. Eine Regel im Prompt hat Hoffnung.

Deshalb liefert `Business Trip Intake` die Fragen selbst: `open_questions` enthält je Zeile
`feldname: Frage`. Die KI liest, fragt, trägt die Antwort in genau dieses Feld ein und speichert.

## Die Verbesserungen im Einzelnen — und was sie verhindern

### Entfernungstabelle (`Business Trip Distance`)

*Verhindert:* getippte Kilometer. Jede Zahl, die ein Mensch bei jeder Fahrt neu eingibt, ist eine
Zahl, die falsch sein kann — und bei wiederkehrenden Fahrten fällt eine Abweichung niemandem auf.

Die Strecke wird einmal hinterlegt und danach vom Formular selbst eingetragen. Gespeichert wird
die **einfache** Strecke, weil die Berechnung Hin- und Rückfahrt als zwei Zeilen erwartet — wer
hier die Gesamtstrecke hinterlegt, verdoppelt unbemerkt die Erstattung. Ein von Hand
eingetragener Wert wird nie überschrieben; ein automatisch eingetragener dagegen schon, sobald
sich die Strecke ändert, sonst blieben die Kilometer der vorherigen Fahrt stehen.

### Fahrzeuge je Mitarbeiter (`Employee Vehicle`)

*Verhindert:* die Frage „mit welchem Auto denn?", die in einer Betriebsprüfung niemand mehr
beantworten kann, und einen falschen Satz je Kilometer.

Wer zwei Privatwagen hat, konnte bisher nur „Car (private)" ankreuzen. Jetzt hängt am Fahrzeug
auch der Satz: Motorräder und andere motorbetriebene Fahrzeuge werden mit 0,20 €/km statt
0,30 €/km erstattet. Drei Fälle brechen ab, statt still falsch zu rechnen: ein Fahrzeug eines
anderen Mitarbeiters, ein deaktiviertes Fahrzeug, und ein Firmen- oder Mietwagen, für den
„Car (private)" gewählt wurde — dafür gibt es kein Kilometergeld.

### Keine gestellten Mahlzeiten mehr per Vorgabe

*Verhindert:* eine stille Kürzung um 20 %.

`breakfast_was_provided` und `accommodation_was_provided` standen im Auslieferungszustand auf
„gestellt". Wer eine Tageszeile anlegte, ohne die Häkchen anzufassen, verlor 20 % des
Ganztagssatzes — ohne Fehlermeldung, ohne Hinweis, in jeder einzelnen Abrechnung. Die Vorgaben
stehen jetzt auf „nicht gestellt", und der Generator setzt **alle vier Felder immer explizit**.

Im Zweifel wird gefragt: `meals_confirmed` trennt „nein" von „noch nicht gefragt". Eine
unbeantwortete Frage darf nicht zur Antwort werden.

### Erfassung mit Rückfragen (`Business Trip Intake`)

*Verhindert:* geratene Werte und den Zwang, den Fragenkatalog auswendig zu können.

Die KI legt an, was sie aus dem Satz ziehen konnte — leere Felder bleiben leer. Der Server
leitet ab, was ableitbar ist (Mitarbeiter, Gesellschaft, Region, bekannte Strecke, einziges
Fahrzeug), fragt nach dem Rest und zeigt in `calculation_preview`, was herauskäme. Die Vorschau
entsteht, indem eine Dienstreise im Arbeitsspeicher gebaut und die **echte** Berechnung darauf
ausgeführt wird — keine zweite Rechenlogik, die später auseinanderläuft.

Erzeugt wird die Dienstreise erst, wenn keine Frage mehr offen ist, und immer nur als
**Entwurf**. Der Submit — und damit die Buchung — bleibt beim Menschen.

### Mitarbeiter je Gesellschaft

*Verhindert:* eine Abrechnung, die beim Buchen auffliegt.

Wer für mehrere Gesellschaften unterwegs ist, hat je Gesellschaft einen Mitarbeiterdatensatz,
aber die Benutzerkennung darf nur an einem hängen. Ohne Zuordnung würde die Erfassung den
Mitarbeiter der falschen Gesellschaft nehmen und der Expense Claim beim Submit abgewiesen.
Die Erfassung sucht deshalb zur gewählten Gesellschaft den passenden Datensatz derselben Person
— und fragt, wenn es keinen gibt.

## Was die KI nie tut

- Beträge schätzen, runden oder nachrechnen
- Kilometer erfinden
- Submitten, bezahlen oder einen Expense Claim von Hand anlegen
- Felder per SQL schreiben oder Berechtigungen umgehen
- `meals_confirmed` setzen, ohne gefragt zu haben
- Eine zweite Reise für einen Tag anlegen, für den schon eine existiert

## Zugriff über die Dokument-API

Gelesen wird mit `get_list` / `get_value` / `get_doc`, geschrieben mit `insert` / `save` /
`set_value`. Nur so laufen Validierung, Berechnung und Berechtigungen mit. SQL bleibt lesenden
Auswertungen vorbehalten und ist nie ein Weg, eine Rechteprüfung zu umgehen: Was ein Nutzer
nicht sehen darf, liest die KI auch nicht für ihn.

Dieselbe Regel gilt im Code. Die aufrufbaren Methoden lesen über `get_list` und liefern nur, was
der Aufrufer sehen darf; die Einstellungen kommen aus dem gecachten Single-Doc. Die eine
bewusst nicht permission-gefilterte Abfrage (`get_vehicles`) ist an Ort und Stelle begründet:
Prüfer und Buchhaltung müssen eine fremde Reise speichern können.
