# Ablesungen, Korrekturen und Home-Assistant-Statistiken

## Festgelegtes Konzept

Die Historie ist die fachliche Datenbasis für Karten und Intervallkennzahlen. Ablesungen
behalten IDs, Notizen und Zeitpunkte. Ein Datensatz `kind: replacement` beendet den alten
Zähler mit `old_reading` und beginnt den neuen mit `reading`. Beide gelten zum selben
Zeitpunkt. Fehlende Werte bleiben `null`; ein davon abhängiges Intervall ist unbekannt.
Eine Wechselgrenze kann bearbeitet, aber nicht versehentlich gelöscht werden.

Speicherformat: bestehende Listen `electricity` und `gas` bleiben erhalten, ergänzt um
`_schema: 2` und `_statistics`. Die HA-Store-Version bleibt 1, da das Format additiv ist.
Unbekannte Metadaten bleiben erhalten. Alte Datensätze ohne `kind` sind Ablesungen.
Alte fallende/ungültige Intervalle bleiben sichtbar und werden als unvollständig markiert.
Kartenkonfiguration und Dashboard-Speicher werden nicht migriert oder überschrieben.
Nach einem Upgrade mit Wechseln nicht ohne Datensicherung auf v1.1.4 zurückwechseln:
die alte Version versteht Wechselgrenzen und den Statistikfortschreibungsstand nicht.

### Sensoren und Recorder

Die bisherigen Entity-IDs, Einheiten und `total_increasing`-Klassen bleiben bestehen.
Der Zustand von `strom_stand`, `gas_stand` und `gas_energie_stand` ist künftig ein
**gespeicherter Fortschreibungsstand**. Beim ersten Laden wird er aus dem bisherigen
letzten Stand initialisiert, beim Gas-Energiesensor mit den dann konfigurierten Faktoren.
Der reale Stand steht in den Karten und im Attribut `physical_reading` des Standsensors.

- Neue chronologisch späteste Ablesung: nur das neue, bekannte Intervall addieren.
- Neuer Wechsel: alten Endstand minus letzten alten Stand addieren; neuer Anfangsstand
  ist ausschließlich die Grundlage des nächsten Intervalls.
- Nachtrag, Bearbeitung, Löschen: Historie neu berechnen, veröffentlichte Summen einfrieren.
  Eine Korrektur der aktuellen Grundlage übernimmt den korrigierten Stand für künftige
  Intervalle. Ein nach vorn verschobener Datensatz wird ebenfalls nur als neue Grundlage
  verwendet, ohne Verbrauch aus der Korrektur zu veröffentlichen.
- Gelöschte letzte Ablesung: die zuletzt veröffentlichte Grundlage und Zeitgrenze bleiben
  intern erhalten, damit der folgende Eintrag bereits gemeldeten Verbrauch nicht doppelt zählt.
  Ein später nachgetragener Wechsel ersetzt diese Grundlage durch das neue Zählersegment;
  auch dabei wird keine Differenz zwischen verschiedenen physischen Zählern gebucht.
  Ist der nächste Stand darunter, bleibt das nicht berechenbare Intervall ungebucht und
  der nächste Stand wird die neue Grundlage. Das Attribut `statistics_corrections` ist wahr.
- Einträge bis zur zuletzt veröffentlichten Zeitgrenze buchen nichts rückwirkend nach.
- Fehlende Wechselstände: bekannte Teilintervalle zählen, unbekannte Teile nicht. Späteres
  Vervollständigen repariert die Kartenhistorie, bucht aber keine HA-Historie nach.
- Neustart: dieselben gespeicherten Summen und Grundlagen laden, keine Neuberechnung
  der Statistiksumme aus der geänderten Historie.
- Gas-Energie: bereits veröffentlichte kWh bleiben unverändert; nur neue Intervalle werden
  mit den aktuellen Faktoren umgerechnet. Dies ist **keine historische Faktorverwaltung**.

Damit können Kartenverbrauch und HA-Energieauswertung nach Korrekturen voneinander
abweichen. Bestehende Statistikfehler bleiben bestehen. Es gibt keinen Recorder-Import,
keine Löschung/Überschreibung von Statistiken und keine geschätzte Verteilung auf Tage.
HA ordnet neue Verbrauchszuwächse seiner Erfassungszeit zu, nicht dem historischen
Ableseintervall. Änderungen kurz vor einem Recorder-Zyklus können zusammengefasst werden.

Grundlage: [HA Sensor entity](https://developers.home-assistant.io/docs/core/entity/sensor/),
insbesondere die Reset-Semantik von `total_increasing`.

### Plausibilität

Eindeutige Zeitpunkte werden nach UTC-Normalisierung geprüft. Naive Zeitpunkte behalten
zur Kompatibilität ihre bisherige UTC-Bedeutung; die Karte sendet Zeitpunkte mit Zeitzone.
Vorgänger und Nachfolger müssen zum jeweiligen physischen Zähler passen. Sinkende Werte
werden abgewiesen, niemals als Nullverbrauch gerechnet. Bei beschädigten Altbeständen
werden nur die von einer Änderung betroffenen Intervalle validiert, damit Reparaturen
schrittweise möglich bleiben.

Eine Warnung erscheint oberhalb des größeren Werts aus 100 kWh/Tag (Strom) bzw.
30 m³/Tag (Gas) und dem Fünffachen des Median-Tagesverbrauchs vorhandener gültiger
Vergleichsintervalle. Das ist eine konservative Heuristik, keine technische Zählergrenze.
Die Warnung nennt Intervall, Verbrauch, Tagesrate und Schwelle; Bestätigung gilt nur für
den geprüften Datenstand. Auch kurze Intervalle werden mit ihrer tatsächlichen Dauer geprüft.

## Lokal automatisiert

`python3 -m unittest discover -s tests -v`

Die Tests verwenden echte Coordinator-/Berechnungslogik und einen HA-Store-Testadapter.
Geprüft werden ungültige Zahlen/Zeitpunkte, identische Zeitpunkte mit anderen Zeitzonen,
chronologische Nachträge, Bearbeitung beider Nachbarintervalle, mehrere Wechsel,
unvollständige Wechsel, Migration ohne Verlust, Warnbestätigung, konkurrierende
Schreibvorgänge, Fehler beim Speichern, Neustart und Statistikfortschreibung.
Die bisherigen Onboarding-, Ressourcen- und Dashboard-Erhaltungstests bleiben enthalten.

`NODE_PATH=<Pfad zu node_modules> node tests/test_card.cjs`

Optional `PLAYWRIGHT_EXECUTABLE_PATH` auf einen installierten Chromium-Testbrowser setzen.
Browserprüfungen umfassen bestehende Kartenregressionen, Bearbeitung, Notiz-Escaping,
lokale Zeitdarstellung, Abbruch/Bestätigung einer Warnung, unvollständige Wechsel,
Aktualität mit Kalenderdatumwechsel und Auswahl im visuellen Editor.

## Noch offen: reale Home-Assistant-Integration

Hier steht keine laufende HA-Testinstanz bereit. Store-Adapter und Browser-Mocks bestätigen
**nicht** Recorder, Langzeitstatistiken oder das echte Energie-Dashboard.
Folgende Schritte auf einer separaten HA-Testinstanz durchführen; produktive Statistiken
nicht löschen. Vorher `.storage/meter_snap_data`, Integration und Dashboard sichern.

1. v1.1.4 mit Testablesungen Strom 1000 (Tag 1), 1030 (Tag 4) betreiben; Sensorzustand,
   `statistic_id`, `state` und `sum` festhalten. Mindestens einen Recorder-Zyklus abwarten.
   Karten individuell konfigurieren und das optionale Dashboard verändern.
2. Lokalen Entwicklungsstand installieren, HA neu starten, Browserressource neu laden.
   Prüfen: IDs/Notizen unverändert, Sensor 1030, keine neue Statistik-ID, keine veränderten
   alten Statistikzeilen, Kartenreihenfolge und Dashboard-Anpassungen erhalten.
3. 1010 (Tag 2) nachtragen: lokale Intervalle 10/20, Sensor weiterhin 1030. Letzte Ablesung
   auf 1025 korrigieren: lokale Intervalle 10/15, Sensor weiterhin 1030. Nach Recorder-Zyklus
   darf weder Reset noch künstlicher Verbrauch erscheinen.
4. 1035 (Tag 5) neu erfassen: Sensor 1040, also ausschließlich +10. Warten, `sum`-Differenz
   kontrollieren. Neu starten und gleichen Zustand/gleiche Statistiksumme kontrollieren.
5. Letzten Eintrag löschen: Sensor bleibt 1040. 1040 (Tag 6) neu erfassen: Sensor 1045,
   ausschließlich +5. Historie und lokale Kosten werden dagegen aus verbliebenen Einträgen
   neu berechnet. Historischen Eintrag ebenfalls löschen und Recorder prüfen.
6. Wechsel Tag 7 mit altem Endstand 1050, neuem Anfangsstand 5 erfassen: Sensor 1055
   (+10). Neuer Stand 12 (Tag 8): Sensor 1062 (+7). Kein Reset und keine Differenz 1050→5.
   Wechselzeitpunkt/Endstand bearbeiten und prüfen, dass nur die lokale Historie korrigiert wird.
7. Weiteren Wechsel mit leerem End-/Anfangsstand erfassen: Unvollständigkeit sichtbar,
   keine erfundenen Intervalle. Folgende Ablesung wird Grundlage, erst das nächste bekannte
   Intervall erhöht die Summe. Wechsel vervollständigen: lokale Historie repariert,
   keine rückwirkende Buchung in HA.
8. Entsprechende Folge für Gas durchführen: m³-Sensor und kWh-Sensor mit ihren jeweiligen
   Faktoren vergleichen; keinen Sprung des gesamten kWh-Stands nach Optionsänderung erwarten.
9. In Entwicklerwerkzeuge → Statistik und im eingebauten sowie zusätzlichen Energie-Dashboard
   nach einem vollständigen Stundenzyklus prüfen: bestehende Daten erhalten, nur neue
   Zuwächse zur Erfassungszeit. Datumsauswahl darf keine erfundene historische Verteilung zeigen.
10. Zwei Karten und zwei Tabs öffnen: Bearbeiten/Löschen/Wechsel synchronisieren sich; fremde
    Änderungen schließen offene Eingaben nicht. Große Tagesrate abbrechen und dann bewusst
    bestätigen. Zweite Karte zwischen Warnung und Bestätigung ändern: erneute Prüfung erwarten.
11. Deutsch/Englisch, Mobilansicht, „heute“, keine Ablesung und Mitternachtswechsel prüfen;
    Aktualitätsanzeige aus-/einblenden und anordnen. Aktualisierung erfolgt bei sichtbarer Karte
    mit dem bestehenden 30-Sekunden-Abruf. Kalenderdatum folgt der Browser-Zeitzone.
