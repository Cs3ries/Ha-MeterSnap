# 📸 MeterSnap – Foto-Zählerstandserfassung & Energieabrechnung für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Cs3ries/Ha-MeterSnap/releases/tag/v1.1.0)
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
  * **Ohne KI (Manuelle Erfassung)**: Komplett offline ohne externe Server. Zählerstände selbst tippen, Beweisfotos bleiben im Archiv sicher gespeichert.
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
* 🖼️ **Beweisfoto-Archiv**:
  * Jedes Foto wird dauerhaft mit Zeitstempel und Zählerstand gespeichert. Ein Klick auf die Miniaturansicht öffnet das Foto in voller Auflösung (perfekt als Nachweis bei der Jahresablesung!).
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

* Alle Zählerstände, Messwerte, Kostenberechnungen und Bilddateien verbleiben **vollständig lokal** auf deinem Home-Assistant-System (unter `/config/meter_snap/`).
* **Bei lokaler KI (Ollama) oder manueller Erfassung:** Es verlässt zu keinem Zeitpunkt ein Byte dein lokales Heimnetzwerk.
* **Bei Cloud-Diensten (OpenRouter, Gemini, OpenAI):** Das Foto wird ausschließlich bei einem Scan-Vorgang über eine verschlüsselte HTTPS-Verbindung an die gewählte API übermittelt, um die Ziffern auszulesen. Es werden keinerlei persönliche Nutzerdaten übertragen.

