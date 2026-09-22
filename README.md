# 📸 MeterSnap – Foto-Zählerstandserfassung & Energieabrechnung für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![version](https://img.shields.io/badge/version-1.1.4--b3-orange.svg)](https://github.com/Cs3ries/Ha-MeterSnap/releases/tag/v1.1.4-b3)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.1%2B-blue.svg)](https://www.home-assistant.io/)

**MeterSnap** ist eine native Home Assistant Custom Integration mit maßgeschneiderter Dashboard-Karte (Lovelace Card). Sie ermöglicht es dir, Zählerstände von **Strom- und Gaszählern** per Smartphone-Foto oder Bild-Upload automatisch per KI auszulesen (oder komplett offline manuell einzutragen), in einer Historientabelle zu archivieren und deinen Verbrauch sowie deine Kosten minutengenau anhand deiner echten Vertragskonditionen zu berechnen.

---

## ✨ Features

* 📸 **Foto-Upload & Kamera-Direktzugriff**: Öffnet auf dem Smartphone mit einem Klick die Kamera oder Fotogalerie.
* 🧠 **Smart Universal Scan & Zählertyp-Erkennung**:
  * Erkennt Ziffern auf analogen Rollenzählwerken (schwarze Hauptziffern und rote Nachkommastellen).
  * Erkennt Ziffern auf digitalen LCD-Displays (sucht gezielt nach dem Bezugscode `1.8.0`).
  * Erkennt automatisch, ob es sich um einen **Strom- oder Gaszähler** handelt.
* 🤖 **Flexible KI-Anbindung & Modellauswahl**:
  * **OpenRouter**: Zugriff auf hunderte Vision-Modelle. Inklusive dynamischer Modellauswahl mit **kostenlosen Modellen (`:free`) direkt an oberster Stelle**!
  * **Lokale KI / Custom**: 100% lokale Bilderkennung mit Ollama (z.B. LLaVA, Qwen2-VL), LocalAI oder vLLM ohne Cloud.
  * **Google Gemini**: Direkte Anbindung per Google AI Studio API-Schlüssel.
  * **OpenAI**: Direkte Anbindung per OpenAI Platform API-Schlüssel (z.B. GPT-4o-mini).
  * **Ohne KI (Manuelle Erfassung)**: Komplett offline ohne externe Server. Zählerstände selbst eintippen.
* 📦 **Batch-Upload**: Mehrere Zählerfotos auf einmal hochladen und nacheinander prüfen und speichern.
* 🍏 **Automatische iPhone HEIC-Konvertierung**: Lädt iPhone-Fotos (HEIC/HEIF) direkt hoch und konvertiert sie serverseitig verlustfrei in JPEG.
* 🔍 **Sofort-Vorschau & Korrektur-Dialog**: Du siehst das Foto direkt neben der erkannten Zahl und kannst sie vor dem Speichern mit einem Fingertipp prüfen oder korrigieren.
* ⚡ **Strom-Kostenberechnung**: 
  * Berechnung von Verbrauch ($\Delta \text{kWh}$), Zeitraum in Tagen und Durchschnittsverbrauch/Tag.
  * Automatische Aufteilung in **Arbeitspreis** (€/kWh) und anteiligen **Grundpreis** (€/Monat).
* 🔥 **Gas-Kostenberechnung (inkl. $m^3 \rightarrow \text{kWh}$ Umrechnung)**:
  * Gaszähler erfassen das Volumen in $m^3$.
  * MeterSnap rechnet mit **Brennwert** und **Zustandszahl (Z-Zahl)** von deiner Gasrechnung exakt in Kilowattstunden ($\text{kWh}$) und Euro um:
    $$\text{Energie in kWh} = \text{Verbrauch in } m^3 \times \text{Brennwert} \times \text{Z-Zahl}$$
* 📊 **Abschlags-Prognose (Ampel)**:
  * Rechnet deinen aktuellen Tagesverbrauch auf den Monat hoch.
  * Zeigt an, ob dein monatlicher Abschlag ausreicht oder ob eine Nachzahlung droht.
* 🖼️ **Datenschutzfreundliche Foto-Prüfung (Kein Festspeicher-Ballast)**:
  * Das Zählerfoto wird direkt im Browser-Bestätigungsdialog neben dem erkannten Wert angezeigt, damit du das Originalfoto vor dem Speichern in Ruhe vergleichen kannst. Nach der Bestätigung wird das Foto verworfen und belegt keinen dauerhaften Speicherplatz in Home Assistant.
* 🌿 **Home Assistant Energy Dashboard**:
  * Erstellt native Entitäten (`sensor.meter_snap_strom_stand`, `sensor.meter_snap_gas_stand`, `sensor.meter_snap_gas_energie_stand`) mit `state_class: total_increasing`, die direkt im offiziellen HA Energie-Dashboard hinterlegt werden können.

---

## 🛠️ Installation

### Methode 1: Über HACS (Empfohlen)
1. Öffne **HACS** in Home Assistant.
2. Gehe auf die drei Punkte oben rechts $\rightarrow$ **Benutzerdefinierte Repositories** *(Custom repositories)*.
3. Füge folgende URL hinzu:
   ```
   https://github.com/Cs3ries/Ha-MeterSnap
   ```
   * Kategorie: **Integration**
4. Klicke auf **Hinzufügen** und danach auf **Herunterladen**.
5. Starte Home Assistant neu (*Einstellungen* $\rightarrow$ *System* $\rightarrow$ *Neu starten*).

### Methode 2: Manuell
1. Kopiere den Ordner `custom_components/meter_snap` in dein Home Assistant `config/custom_components/` Verzeichnis:
   ```
   /config/custom_components/meter_snap/
   ```
2. Starte Home Assistant neu.

---

## ⚙️ Konfiguration (Geführter Einrichtungsassistent)

Gehe nach dem Neustart auf **Einstellungen** $\rightarrow$ **Geräte & Dienste** $\rightarrow$ **Integration hinzufügen** und wähle **MeterSnap**.

Der neue Assistent führt dich Schritt für Schritt durch das Setup:

### Schritt 1: Wähle deinen KI-Dienst
* **OpenRouter**:
  * API-Key eingeben (optional für Free-Modelle).
  * Im nächsten Schritt Modell aus dem Dropdown wählen – **kostenlose Modelle (`:free`) stehen ganz oben!**
* **Lokale KI / Benutzerdefiniert**:
  * Für rein lokale Server (z.B. Ollama auf `http://localhost:11434/v1/chat/completions`, Modell `llava`).
  * API-Schlüssel kann bei lokalen Instanzen leer bleiben.
* **Google Gemini**:
  * Direkte Key-Eingabe (erhältlich im Google AI Studio unter [aistudio.google.com](https://aistudio.google.com/)).
* **OpenAI**:
  * Direkte Key-Eingabe (aus dem Dashboard unter [platform.openai.com](https://platform.openai.com/api-keys)).
* **Ohne KI (Manuelle Erfassung)**:
  * 100% offline. Zählerstände selbst eintippen, keine externen Server.

### Schritt 2: Stromvertrag
* **Stromzähler aktivieren**: Ja / Nein
* **Arbeitspreis (€/kWh)**: z. B. `0.32`
* **Grundpreis (€/Monat)**: z. B. `12.00`
* **Monatlicher Abschlag (€)**: z. B. `90.00`

### Schritt 3: Gasvertrag
* **Gaszähler aktivieren**: Ja / Nein
* **Arbeitspreis (€/kWh)**: z. B. `0.10`
* **Grundpreis (€/Monat)**: z. B. `10.00`
* **Monatlicher Abschlag (€)**: z. B. `110.00`
* **Brennwert (kWh/m³)**: z. B. `11.2` (steht auf deiner Gasrechnung)
* **Zustandszahl Z**: z. B. `0.95` (steht auf deiner Gasrechnung)

> [!TIP]
> Alle Einstellungen können jederzeit nachträglich unter *Einstellungen $\rightarrow$ Geräte & Dienste $\rightarrow$ MeterSnap $\rightarrow$ Konfigurieren* modular und getrennt angepasst werden!

---

## Eigenes Energie-Dashboard mit Foto-Upload (optional, ab v1.1.4-b3)

Am Ende der Ersteinrichtung kannst du **MeterSnap-Energie-Dashboard anlegen / anzeigen** aktivieren. Bei einer bestehenden Installation findest du dieselbe Option unter **Einstellungen → Geräte & Dienste → MeterSnap → Konfigurieren → Energie-Dashboard & Foto-Upload**.

Die zusätzliche Seite **MeterSnap Energie** erscheint in der Seitenleiste unter `/meter-snap-energy`. Sie kombiniert die Foto-/manuelle Erfassung mit den offiziellen HA-Energiekarten und deren Datumsauswahl. Beim ersten Anlegen werden die aktivierten Strom-/Gaszähler berücksichtigt.

Die Diagramme verwenden die bereits eingerichteten HA-Energiequellen. Falls diese noch fehlen, führt ein Link zu den Energieeinstellungen. MeterSnap ändert die Energiequellen nicht automatisch. Einzelne Fotoablesungen liefern keinen gemessenen Tagesverlauf; alte Ablesungen werden nicht nachträglich in die HA-Energiestatistik verteilt.

Die Seite wird von der Integration verwaltet: Ein-/Ausblenden erfolgt über die obige Option, nicht über die Liste manuell angelegter Dashboards. Die Karten selbst kannst du über **Dashboard bearbeiten** anpassen. Deine Änderungen bleiben bei Neustarts, Updates und Aus-/Einschalten der Option erhalten. Auch bei geänderten Zählereinstellungen wird ein bestehendes Layout nicht überschrieben; passe dessen Karten bei Bedarf selbst an. Die eingebaute Energie-Seite bleibt erhalten.

Ist `/meter-snap-energy` bereits belegt, wird nichts überschrieben. Eine HA-Benachrichtigung weist auf das Problem hin; nach Freigabe der Adresse die Integration neu laden. Bei manuell verwalteten YAML-Ressourcen muss die MeterSnap-Kartenressource weiterhin wie unten beschrieben eingetragen sein.

---

## 📱 Dashboard-Karte (Lovelace Card) einrichten

MeterSnap registriert die Karte automatisch in Home Assistant.

1. Öffne dein Home Assistant Dashboard.
2. Klicke oben rechts auf das Stift-Symbol (**Dashboard bearbeiten**) $\rightarrow$ **Karte hinzufügen**.
3. Wähle **Manuell** (ganz unten) und füge folgenden YAML-Code ein:

```yaml
type: custom:meter-snap-card
title: Zählerstand & Verbrauch
default_meter: electricity
```

**Automatisch ab v1.1.2:** Bei über die Oberfläche verwalteten Dashboard-Ressourcen registriert MeterSnap die Karte beim Start selbst. Bestehende lokale Einträge für `meter-snap-card.js` werden auf die aktuelle Versions-URL umgestellt und doppelte Einträge zusammengeführt. Nach einem Update Home Assistant neu starten und die Dashboard-Seite neu laden. Die Karte selbst platzierst du weiterhin im gewünschten Dashboard.

**YAML-Ressourcen:** Diese bleiben manuell verwaltet. Verwende `/meter_snap_frontend/meter-snap-card.js?v=1.1.2` mit `type: module` und aktualisiere die Versionsangabe nach Updates. MeterSnap verändert keine YAML-Dateien.

---

## Authentifizierung ab v1.1.4-b1

Die Karte verwendet für Lesen, Speichern, Löschen und Foto-Scans den Home-Assistant-Aufruf `hass.callApi`. Die bisherige manuelle Tokenübernahme entfällt. Dadurch übernimmt Home Assistant die Authentifizierung einschließlich Token-Erneuerung. Nach dem Update Home Assistant neu starten und alle geöffneten Dashboard-Seiten neu laden, damit keine alte Kartenversion weiter Anfragen sendet.

## Modulare Karten ab v1.1.4-b1

**Neu in v1.1.4-b2:** Strom und Gas lassen sich gleichzeitig anzeigen. Abgewählte Bereiche und Kennzahlen behalten ihre Reihenfolge, auch nach Speichern und erneutem Aktivieren.

Unter **Dashboard bearbeiten → Karte hinzufügen → MeterSnap Card** steht ein visueller Editor bereit. Für bestehende Karten öffne **Bearbeiten** und gegebenenfalls **Visuellen Editor anzeigen**.

- **Bereiche:** Titel/Zählerauswahl, Kennzahlen, Erfassung und Historie einzeln einblenden und mit den Pfeilen sortieren. Abgewählte Bereiche und Kennzahlen behalten ihre Position im Editor und erscheinen beim erneuten Anwählen wieder an derselben Stelle. Nur die Pfeiltasten ändern die Reihenfolge.
- **Kennzahlen:** Stand, Verbrauch, Kosten und Monatsprognose einzeln auswählen und sortieren.
- **Zähleranzeige:** Nur Strom, nur Gas, beide mit Umschalter oder beide gleichzeitig. Bei gleichzeitiger Anzeige stehen die Zähler je nach Kartenbreite neben- oder untereinander, mit eigener Erfassung und eigener Historienseite. Beim Umschalten lässt sich der Startzähler festlegen.
- **Historie:** Standardmäßig fünf Ablesungen pro Seite, einstellbar von 1 bis 50. Zurück/Weiter öffnet weitere Einträge.
- **Kompakt:** Reduzierte Abstände für kleine Karten. Farben orientieren sich am HA-Theme.

Jede Karteninstanz speichert ihre eigene Darstellung in der Dashboard-Konfiguration. Füge beispielsweise eine Stromübersicht und eine separate Historienkarte hinzu. Änderungen an Ablesungen aktualisieren andere Karten auf derselben Seite sofort; weitere geöffnete Seiten laden spätestens nach etwa 30 Sekunden neue Daten, solange sie sichtbar sind. Laufende Eingaben werden dabei nicht überschrieben.

Bestehende Konfigurationen mit `title` und `default_meter` funktionieren weiterhin; die Historie wird jetzt seitenweise angezeigt. Die Karten werden auf normalen, bearbeitbaren Dashboards platziert. Die eingebaute Energie-Seite bezieht weiterhin die Sensorwerte.

Optionales YAML-Beispiel einer kompakten Stromkarte:

```yaml
type: custom:meter-snap-card
title: Mein Strom
meter: electricity
compact: true
sections:
  - header
  - kpis
  - capture
metrics:
  - reading
  - consumption
history_page_size: 5
```

`meter: both` zeigt Strom und Gas gleichzeitig; `meter: switchable` verwendet den Umschalter. `sections_order` und `metrics_order` speichern die vollständige Reihenfolge einschließlich abgewählter Elemente.

Eine separate Historie verwendet `sections: [header, history]`. Ohne `sections` oder `metrics` werden alle jeweiligen Bausteine angezeigt. Eine leere Liste blendet sie vollständig aus. Bei umschaltbaren Karten liegt die Zählerauswahl im Titelbereich.

Nach dem Update Home Assistant neu starten und die Dashboard-Seite neu laden. Bei manuell verwalteten YAML-Ressourcen die URL auf `/meter_snap_frontend/meter-snap-card.js?v=1.1.4-b3` aktualisieren.

---

## 📈 Einbindung ins Home Assistant Energy Dashboard

1. Gehe in Home Assistant auf **Einstellungen** $\rightarrow$ **Dashboards** $\rightarrow$ **Energie**.
2. **Stromnetz (Netzverbrauch)**:
   * Klicke auf *Verbrauch hinzufügen*.
   * Wähle den Sensor: `sensor.meter_snap_strom_stand`.
3. **Gasnetz**:
   * Klicke auf *Gasquelle hinzufügen*.
   * Wähle den Sensor: `sensor.meter_snap_gas_stand` (in $m^3$) oder `sensor.meter_snap_gas_energie_stand` (in $\text{kWh}$).

---

## 🔒 Datenschutz & Speicherung

**Update-Hinweis für v1.1.2:** Beim Start werden bereits gespeicherte Fotos unter `/config/meter_snap/images` gelöscht und ihre Verknüpfungen aus den Messwerten entfernt. Benötigte Beweisfotos vor dem Update separat sichern. Zählerstände bleiben erhalten.

* Alle Zählerstände, Messwerte und Kostenberechnungen verbleiben **vollständig lokal** auf deinem Home-Assistant-System (unter `.storage`). Es werden **keine Zählerfotos dauerhaft auf der Festplatte gespeichert** – dies spart wertvollen Speicherplatz und schützt deine Privatsphäre.
* **Bei lokaler KI (Ollama) oder manueller Erfassung:** Es verlässt zu keinem Zeitpunkt ein Byte dein lokales Heimnetzwerk.
* **Bei Cloud-Diensten (OpenRouter, Gemini, OpenAI):** Das Foto wird ausschließlich bei einem Scan-Vorgang über eine verschlüsselte HTTPS-Verbindung an die gewählte API übermittelt, um die Ziffern auszulesen. Es werden keinerlei persönliche Nutzerdaten übertragen.


## Icon in Home Assistant und HACS

Ab Home Assistant 2026.3 werden die mitgelieferten Bilder unter `custom_components/meter_snap/brand/` für die Integrationsanzeige verwendet. Nach dem Update Home Assistant neu starten und die Oberfläche neu laden. Ältere HA-Versionen unterstützen diese lokalen Brand-Bilder nicht.

Die Icon-Anzeige in der HACS-Liste hängt zusätzlich von HACS ab: [HACS-Issue #5223](https://github.com/hacs/integration/issues/5223) beschreibt fehlende lokale Brand-Icons. Die Dateien im MeterSnap-Repository allein beheben diesen HACS-Fehler nicht.
