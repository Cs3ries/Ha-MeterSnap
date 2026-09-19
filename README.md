# 📸 MeterSnap – Foto-Zählerstandserfassung & Energieabrechnung für Home Assistant

**MeterSnap** ist eine native Home Assistant Custom Integration mit maßgeschneiderter Dashboard-Karte (Lovelace Card). Sie ermöglicht es dir, Zählerstände von **Strom- und Gaszählern** per Smartphone-Foto oder Bild-Upload automatisch per KI auszulesen, in einer Historientabelle zu archivieren und deinen Verbrauch sowie deine Kosten minutengenau anhand deiner echten Vertragskonditionen zu berechnen.

---

## ✨ Features

* 📸 **Foto-Upload & Kamera-Direktzugriff**: Öffnet auf dem Smartphone mit einem Klick die Kamera.
* 🤖 **Vision-KI Ziffernerkennung**: 
  * Erkennt Ziffern auf analogen Rollenzählwerken (schwarze Hauptziffern und rote Nachkommastellen).
  * Erkennt Ziffern auf digitalen LCD-Displays (sucht gezielt nach dem Bezugscode `1.8.0`).
  * Unterstützt **Google Gemini** (empfohlen: extrem schnell, praktisch kostenlos) sowie **OpenAI GPT-4o-mini** oder lokale Vision-Server (Ollama).
* 🔍 **Sofort-Vorschau & Korrektur-Dialog**: Du siehst das Foto direkt neben der erkannten Zahl und kannst sie vor dem Speichern mit einem Fingertipp anpassen.
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
* 🖼️ **Beweisfoto-Archiv**:
  * Jedes Foto wird dauerhaft mit Zeitstempel gespeichert. Ein Klick auf die Miniaturansicht öffnet das Foto in voller Auflösung (perfekt als Nachweis bei der Jahresablesung!).
* 🌿 **Home Assistant Energy Dashboard**:
  * Erstellt native Entitäten (`sensor.meter_snap_strom_stand`, `sensor.meter_snap_gas_stand`) mit `state_class: total_increasing`, die direkt im offiziellen HA Energie-Dashboard hinterlegt werden können.

---

## 🛠️ Installation

### Methode 1: Manuell (Direkt kopieren)
1. Kopiere den Ordner `custom_components/meter_snap` in dein Home Assistant `config/custom_components/` Verzeichnis:
   ```
   /config/custom_components/meter_snap/
   ```
2. Starte Home Assistant neu:
   * *Einstellungen* $\rightarrow$ *System* $\rightarrow$ *Neu starten*.
3. Gehe zu *Einstellungen* $\rightarrow$ *Geräte & Dienste* $\rightarrow$ *Integration hinzufügen*.
4. Suche nach **MeterSnap** und folge dem Einrichtungsassistenten.

### Methode 2: Über HACS
1. Öffne HACS in Home Assistant.
2. Gehe auf *Integrationen* $\rightarrow$ *Benutzerdefinierte Repositories*.
3. Füge dieses Repository als Kategorie **Integration** hinzu.
4. Klicke auf Installieren und starte Home Assistant neu.

---

## ⚙️ Konfiguration (Config Flow)

Im Einrichtungsassistenten legst du deine Werte fest (kann jederzeit unter *Einstellungen $\rightarrow$ Geräte & Dienste $\rightarrow$ MeterSnap $\rightarrow$ Konfigurieren* angepasst werden):

### 1. Wähle deinen KI-Dienst
* **OpenRouter**: Zugriff auf moderne Vision-Modelle (inkl. kostenloser `:free`-Modelle mit automatischer Modellauswahl).
* **Lokale KI / Custom**: Verbindung zu lokalem Ollama, LocalAI oder vLLM ohne Cloud.
* **Google Gemini**: Direkte Anbindung per Google AI Studio API-Key.
* **OpenAI**: Direkte Anbindung per OpenAI Platform API-Key.
* **Ohne KI (Manuelle Erfassung)**: Komplett offline ohne KI – Zählerstände direkt manuell im Dashboard erfassen (Fotos bleiben zur Beweissicherung archiviert).

### 2. Stromvertrag
* **Stromzähler aktivieren**: Ja / Nein
* **Arbeitspreis (€/kWh)**: z. B. `0.32`
* **Grundpreis (€/Monat)**: z. B. `12.00`
* **Monatlicher Abschlag (€)**: z. B. `90.00`

### 3. Gasvertrag
* **Gaszähler aktivieren**: Ja / Nein
* **Arbeitspreis (€/kWh)**: z. B. `0.10`
* **Grundpreis (€/Monat)**: z. B. `10.00`
* **Monatlicher Abschlag (€)**: z. B. `110.00`
* **Brennwert (kWh/m³)**: z. B. `11.2` (steht auf deiner Gasrechnung)
* **Zustandszahl Z**: z. B. `0.95` (steht auf deiner Gasrechnung)

---

## 📱 Dashboard-Karte (Lovelace Card) einrichten

MeterSnap registriert die Karte automatisch.

1. Öffne dein Home Assistant Dashboard.
2. Klicke oben rechts auf das Stift-Symbol (**Dashboard bearbeiten**) $\rightarrow$ **Karte hinzufügen**.
3. Wähle **Manuell** (ganz unten) und füge folgenden YAML-Code ein:

```yaml
type: custom:meter-snap-card
title: Zählerstand & Verbrauch
default_meter: electricity
```

*(Optional: Falls Home Assistant die Resource nicht automatisch lädt, trage unter Einstellungen $\rightarrow$ Dashboards $\rightarrow$ Ressourcen folgende URL ein: `/meter_snap_frontend/meter-snap-card.js` als JavaScript-Modul).*

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
Alle Zählerstände, Berechnungen und Bilddateien verbleiben lokal auf deinem Home-Assistant-System (unter `/config/meter_snap/`). Beim Foto-Scan wird lediglich das Zählerfoto über eine verschlüsselte HTTPS-Verbindung an die gewählte Vision-API (Gemini/OpenAI) übertragen, um die Ziffern auszulesen.
