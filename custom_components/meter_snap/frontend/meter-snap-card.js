/**
 * MeterSnap Lovelace Custom Card
 * Version 1.1.4-b4
 * 
 * Ermöglicht Foto-Aufnahme (Smartphone-Kamera), Ziffernerkennung via KI,
 * Bestätigungsdialog, Historientabelle und Kostenrechnung für Strom und Gas.
 */

const METER_SNAP_SECTIONS = { header: 'Titel & Zählerauswahl', kpis: 'Kennzahlen', capture: 'Erfassung', history: 'Historie' };
const METER_SNAP_METRICS = { reading: 'Aktueller Stand', consumption: 'Letzter Verbrauch', cost: 'Letzte Kosten', projection: 'Monatsprognose' };
const meterSnapEscape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
function meterSnapConfig(config) {
  const list = (value, allowed) => Array.isArray(value) ? [...new Set(value.filter(key => Object.prototype.hasOwnProperty.call(allowed, key)))] : Object.keys(allowed);
  const sections = list(config.sections, METER_SNAP_SECTIONS);
  const metrics = list(config.metrics, METER_SNAP_METRICS);
  // Remember positions independently of visibility, including disabled items.
  const order = (value, selected, labels) => [...new Set([
    ...(Array.isArray(value) ? list(value, labels) : selected), ...Object.keys(labels)
  ])];
  const sectionOrder = order(config.sections_order, sections, METER_SNAP_SECTIONS);
  const metricOrder = order(config.metrics_order, metrics, METER_SNAP_METRICS);
  return { ...config, title: config.title ?? 'MeterSnap',
    default_meter: config.default_meter === 'gas' ? 'gas' : 'electricity',
    meter: ['electricity', 'gas', 'both'].includes(config.meter) ? config.meter : 'switchable',
    sections: sectionOrder.filter(key => sections.includes(key)),
    metrics: metricOrder.filter(key => metrics.includes(key)),
    sections_order: sectionOrder,
    metrics_order: metricOrder,
    history_page_size: Math.max(1, Math.min(50, Math.trunc(Number(config.history_page_size) || 5))),
    compact: config.compact === true };
}

class MeterSnapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._meterType = 'electricity'; // 'electricity' | 'gas'
    this._readings = [];
    this._kpis = {};
    this._loading = false;
    this._statusMessage = '';
    this._pendingScan = null; // Holds scan result for confirmation
    this._fileQueue = []; // Queue for multi-file batch upload
    this._page = 0;
    this._requestId = 0;
    this._onDataChanged = () => this._fetchData();
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;
    this.shadowRoot.querySelectorAll('meter-snap-card').forEach(card => { card.hass = hass; });

    // Initial fetch once hass is available
    if (!oldHass && hass) {
      this._fetchData();
    }
  }

  connectedCallback() {
    window.addEventListener('meter-snap-data-changed', this._onDataChanged);
    if (this._hass) this._fetchData();
    this._refreshTimer = window.setInterval(() => {
      if (!document.hidden) this._fetchData();
    }, 30000);
  }

  disconnectedCallback() {
    window.removeEventListener('meter-snap-data-changed', this._onDataChanged);
    window.clearInterval(this._refreshTimer);
    this._requestId++;
  }

  setConfig(config) {
    this._config = meterSnapConfig(config);
    this._requestId++;
    this._meterType = ['gas', 'electricity'].includes(this._config.meter) ? this._config.meter : this._config.default_meter;
    this._page = 0;
    this._render();
    if (this._hass) this._fetchData();
  }

  static getConfigElement() { return document.createElement('meter-snap-card-editor'); }

  getCardSize() {
    if (this._config?.meter === 'both') return [...this.shadowRoot.querySelectorAll('meter-snap-card')].reduce((sum, card) => sum + card.getCardSize(), 1);
    return this._config?.sections.reduce((size, section) => size + ({header: 1, kpis: 2, capture: 1, history: 1 + this._config.history_page_size}[section]), 0) || 1;
  }

  static getStubConfig() {
    return {
      title: 'MeterSnap',
      default_meter: 'electricity'
    };
  }

  async _fetchData() {
    if (!this._hass || !this._config || this._config.meter === 'both') return;
    const requestId = ++this._requestId;
    const meterType = this._meterType;
    try {
      const resp = await this._callApi('GET', `/api/meter_snap/reading?meter_type=${meterType}`);
      if (requestId !== this._requestId) return;
      if (resp && resp.success) {
        this._readings = resp.readings || [];
        this._kpis = resp.kpis || {};
      }
    } catch (err) {
      console.warn('MeterSnap: Fehler beim Laden der Daten:', err);
    }
    if (!this._pendingScan && !this._loading) this._render();
  }

  async _callApi(method, path, body) {
    if (typeof this._hass?.callApi !== 'function') {
      throw new Error('Home-Assistant-Verbindung noch nicht bereit. Bitte erneut versuchen.');
    }
    // HA owns authentication and token renewal. callApi adds the /api/ prefix.
    return this._hass.callApi(method, path.replace(/^\/api\//, ''), body);
  }

  _setMeterType(type) {
    if (this._meterType !== type) {
      this._meterType = type;
      this._page = 0;
      this._pendingScan = null;
      this._render();
      this._fetchData();
    }
  }

  _extractPhotoDateTime(file) {
    return new Promise((resolve) => {
      // Fallback to file.lastModified
      const fallbackDate = file.lastModified ? new Date(file.lastModified) : new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const formatLocal = (d) =>
        `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const fallbackStr = formatLocal(fallbackDate);

      // Read first 128KB to extract EXIF DateTimeOriginal if present
      const slice = file.slice(0, 131072);
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const buffer = new Uint8Array(e.target.result);
          let str = '';
          for (let i = 0; i < buffer.length; i++) {
            const code = buffer[i];
            str += (code >= 32 && code <= 126) ? String.fromCharCode(code) : ' ';
          }

          // EXIF standard date format: "YYYY:MM:DD HH:MM:SS"
          const match = str.match(/\b(20[2-9]\d)[:\-](\d{2})[:\-](\d{2})[\sT](\d{2}):(\d{2}):(\d{2})\b/);
          if (match) {
            const [_, year, month, day, hours, minutes] = match;
            resolve(`${year}-${month}-${day}T${hours}:${minutes}`);
            return;
          }
        } catch (err) {
          console.debug('EXIF date extraction fallback:', err);
        }
        resolve(fallbackStr);
      };
      reader.onerror = () => resolve(fallbackStr);
      reader.readAsArrayBuffer(slice);
    });
  }

  _loadHeicConverter() {
    if (window.heic2any) return Promise.resolve(window.heic2any);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error('HEIC-Konverter Timeout - Backend übernimmt'));
      }, 3500);

      const script = document.createElement('script');
      script.src = '/meter_snap_frontend/heic2any.min.js';
      script.onload = () => {
        clearTimeout(timer);
        resolve(window.heic2any);
      };
      script.onerror = () => {
        // Fallback to CDN if local static asset fails
        console.warn('MeterSnap: Lokales heic2any nicht erreichbar, lade von CDN...');
        const cdnScript = document.createElement('script');
        cdnScript.src = 'https://cdn.jsdelivr.net/npm/heic2any@0.0.4/dist/heic2any.min.js';
        cdnScript.onload = () => {
          clearTimeout(timer);
          resolve(window.heic2any);
        };
        cdnScript.onerror = (e) => {
          clearTimeout(timer);
          reject(new Error('HEIC-Konverter konnte nicht geladen werden'));
        };
        document.head.appendChild(cdnScript);
      };
      document.head.appendChild(script);
    });
  }

  async _isHeicFile(file) {
    if (
      file.type === 'image/heic' ||
      file.type === 'image/heif' ||
      /\.hei[cf]$/i.test(file.name || '')
    ) {
      return true;
    }
    try {
      const slice = file.slice(0, 16);
      const buffer = await slice.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      if (bytes.length >= 8) {
        const brand = String.fromCharCode(bytes[4], bytes[5], bytes[6], bytes[7]);
        if (brand === 'ftyp') {
          return true;
        }
      }
    } catch {
      // Ignore
    }
    return false;
  }

  _compressImage(file, maxDimension = 1600, quality = 0.85) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const rawDataUrl = e.target.result;
        const img = new Image();
        img.onload = () => {
          let width = img.width;
          let height = img.height;

          if (width > maxDimension || height > maxDimension) {
            if (width > height) {
              height = Math.round((height * maxDimension) / width);
              width = maxDimension;
            } else {
              width = Math.round((width * maxDimension) / height);
              height = maxDimension;
            }
          }

          try {
            // Drawing on canvas creates a fresh bitmap and completely strips
            // all EXIF metadata (GPS location coordinates, camera serials, device info)
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);
            resolve(canvas.toDataURL('image/jpeg', quality));
          } catch (canvasErr) {
            console.warn('MeterSnap: Canvas compression failed, falling back to original:', canvasErr);
            resolve(rawDataUrl);
          }
        };
        img.onerror = (err) => {
          // In Chromium/Vivaldi or on unsupported formats (HEIC without native decode),
          // do NOT fail the upload! Fallback to the original data URL so the backend can process it.
          console.warn('MeterSnap: Browser image decode failed, falling back to direct upload:', err);
          resolve(rawDataUrl);
        };
        img.src = rawDataUrl;
      };
      reader.onerror = (err) => {
        console.error('MeterSnap: FileReader failed:', err);
        resolve(null);
      };
      reader.readAsDataURL(file);
    });
  }

  async _handleFilesSelected(event) {
    const input = event.target;
    const files = input && input.files ? Array.from(input.files) : [];
    if (input) input.value = ''; // Reset so the exact same file can be re-selected if needed
    if (!files.length) return;

    this._fileQueue = files;
    await this._processNextQueuedFile();
  }

  async _processNextQueuedFile() {
    if (!this._fileQueue || !this._fileQueue.length) {
      this._pendingScan = null;
      this._render();
      return;
    }

    const file = this._fileQueue.shift();
    const remainingCount = this._fileQueue.length;

    this._loading = true;
    this._statusMessage = remainingCount > 0
      ? `Bereite Foto vor (${remainingCount + 1} Fotos in Warteschlange)...`
      : 'Bereite Foto vor...';
    this._render();

    let base64Image = null;
    let photoDateTime = null;

    try {
      let fileToProcess = file;
      const isHeic = await this._isHeicFile(file);

      // Auto-convert iPhone HEIC format to standard JPEG
      if (isHeic) {
        this._statusMessage = 'Konvertiere iPhone HEIC-Foto in JPEG...';
        this._render();
        try {
          await this._loadHeicConverter();
          if (window.heic2any) {
            const converted = await window.heic2any({
              blob: file,
              toType: 'image/jpeg',
              quality: 0.88,
              multiple: false,
            });
            const jpegBlob = Array.isArray(converted) ? converted[0] : converted;
            const newName = (file.name || 'meter').replace(/\.hei[cf]$/i, '.jpg');
            fileToProcess = new File([jpegBlob], newName, { type: 'image/jpeg' });
          }
        } catch (heicErr) {
          console.warn('MeterSnap: HEIC-Konvertierung per heic2any fehlgeschlagen, Backend übernimmt:', heicErr);
        }
      }

      this._statusMessage = 'KI erkennt Zähler und liest Stand...';
      this._render();

      // 1. Extract photo capture date & time from EXIF / file (strips GPS/serials later in canvas)
      photoDateTime = await this._extractPhotoDateTime(file);

      // 2. Compress and resize image to JPEG (strips all GPS / device metadata!)
      base64Image = await this._compressImage(fileToProcess);
      if (!base64Image) {
        throw new Error('Datei konnte nicht geladen werden.');
      }

      // We call with meter_type: 'auto' so AI classifies between electricity and gas!
      const resp = await this._callApi('POST', '/api/meter_snap/scan', {
        image: base64Image,
        meter_type: 'auto',
      });

      if (!resp || !resp.success) {
        throw new Error(resp?.error || 'Zählerstand konnte nicht erkannt werden.');
      }

      // If backend converted HEIC to JPEG, use the converted image
      if (resp.converted_image) {
        base64Image = resp.converted_image;
      }

      const detectedType = resp.meter_type === 'gas' ? 'gas' : 'electricity';
      const detectedUnit = resp.unit || (detectedType === 'electricity' ? 'kWh' : 'm³');

      // Open confirmation dialog with the detected meter type & original photo timestamp
      this._pendingScan = {
        meter_type: detectedType,
        reading: resp.reading !== undefined ? resp.reading : '',
        unit: detectedUnit,
        confidence: resp.confidence || 'high',
        details: resp.details || (detectedType === 'electricity' ? 'Stromzähler erkannt' : 'Gaszähler erkannt'),
        image: base64Image,
        timestamp: photoDateTime,
        notes: 'Erfasst via Smart Scan',
        remainingInQueue: remainingCount,
      };
    } catch (err) {
      alert(`Hinweis: ${err.message}\nDu kannst den Stand auch manuell eintragen.`);
      const nowStr = new Date().toISOString().slice(0, 16);
      const isRawHeic = base64Image && (
        base64Image.startsWith('data:image/heic') ||
        base64Image.startsWith('data:image/heif') ||
        base64Image.startsWith('data:;base64') ||
        base64Image.startsWith('data:application/octet-stream')
      );
      this._pendingScan = {
        meter_type: this._meterType,
        reading: '',
        unit: this._meterType === 'electricity' ? 'kWh' : 'm³',
        confidence: 'manual',
        details: 'Manuelle Eingabe',
        image: isRawHeic ? null : (base64Image || null),
        timestamp: photoDateTime || nowStr,
        notes: '',
        remainingInQueue: remainingCount,
      };
    } finally {
      this._loading = false;
      this._statusMessage = '';
      this._render();
    }
  }

  _openManualEntry() {
    const nowStr = new Date().toISOString().slice(0, 16);
    this._pendingScan = {
      meter_type: this._meterType,
      reading: '',
      unit: this._meterType === 'electricity' ? 'kWh' : 'm³',
      confidence: 'manual',
      details: 'Manuelle Eingabe',
      image: null,
      timestamp: nowStr,
      notes: '',
      remainingInQueue: 0,
    };
    this._render();
  }

  async _savePendingScan() {
    if (!this._pendingScan) return;

    const inputVal = this.shadowRoot.getElementById('confirmReadingInput')?.value;
    const timeVal = this.shadowRoot.getElementById('confirmTimeInput')?.value;
    const notesVal = this.shadowRoot.getElementById('confirmNotesInput')?.value;
    const meterType = this._pendingScan.meter_type || this._meterType;

    const readingNum = parseFloat(inputVal);
    if (isNaN(readingNum) || readingNum < 0) {
      alert('Bitte gib einen gültigen positiven Zählerstand ein.');
      return;
    }

    this._loading = true;
    this._statusMessage = 'Speichere Zählerstand...';
    this._render();

    try {
      let isoTimestamp = new Date().toISOString();
      if (timeVal) {
        isoTimestamp = new Date(timeVal).toISOString();
      }

      const payload = {
        meter_type: meterType,
        reading: readingNum,
        timestamp: isoTimestamp,
        notes: notesVal || '',
      };

      const resp = await this._callApi('POST', '/api/meter_snap/reading', payload);
      if (resp && resp.success) {
        if (this._config.meter === 'switchable') this._meterType = meterType;
        this._page = 0;
        window.dispatchEvent(new Event('meter-snap-data-changed'));
        await this._fetchData();

        if (this._fileQueue && this._fileQueue.length > 0) {
          // Process next photo in batch queue
          await this._processNextQueuedFile();
          return;
        } else {
          this._pendingScan = null;
        }
      } else {
        throw new Error(resp?.error || 'Fehler beim Speichern');
      }
    } catch (err) {
      alert(`Fehler: ${err.message}`);
    } finally {
      this._loading = false;
      this._statusMessage = '';
      this._render();
    }
  }

  _cancelPendingScan() {
    if (this._fileQueue && this._fileQueue.length > 0) {
      if (confirm('Möchtest du zum nächsten Foto in der Warteschlange springen?')) {
        this._processNextQueuedFile();
        return;
      }
      this._fileQueue = [];
    }
    this._pendingScan = null;
    this._render();
  }

  async _deleteEntry(id) {
    if (!confirm('Möchtest du diese Ablesung wirklich löschen?')) return;

    try {
      await this._callApi('DELETE', `/api/meter_snap/reading?meter_type=${this._meterType}&id=${id}`);
      window.dispatchEvent(new Event('meter-snap-data-changed'));
      await this._fetchData();
    } catch (err) {
      alert(`Fehler beim Löschen: ${err.message}`);
    }
  }

  _formatDate(isoStr) {
    if (!isoStr) return '-';
    try {
      const dt = new Date(isoStr);
      return dt.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoStr;
    }
  }

  _renderBoth() {
    // Each meter keeps its own readings, pagination and pending input.
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color); font-family:var(--ha-font-family, sans-serif); }
        .both-title { font-size:1.25rem; font-weight:600; margin:0 0 12px; overflow-wrap:anywhere; }
        .meters { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap:12px; }
        .meter { min-width:0; }
        .meter-label { font-size:1rem; margin:0 0 8px; }
      </style>
      ${this._config.sections.includes('header') && this._config.title ? `<div class="both-title">${meterSnapEscape(this._config.title)}</div>` : ''}
      <div class="meters"></div>`;
    const container = this.shadowRoot.querySelector('.meters');
    for (const [meter, title] of [['electricity', 'Strom'], ['gas', 'Gas']]) {
      const section = document.createElement('section');
      section.className = 'meter';
      section.setAttribute('aria-label', title);
      // Retain a meter label even if the optional card header is hidden.
      if (!this._config.sections.includes('header')) {
        const label = document.createElement('h3');
        label.className = 'meter-label'; label.textContent = title; section.append(label);
      }
      const card = document.createElement('meter-snap-card');
      card.setConfig({...this._config, meter, title});
      section.append(card); container.append(section);
      if (this._hass) card.hass = this._hass;
    }
  }

  _render() {
    if (!this._config) return;
    if (this._config.meter === 'both') { this._renderBoth(); return; }
    const pages = Math.max(1, Math.ceil(this._readings.length / this._config.history_page_size));
    this._page = Math.min(this._page, pages - 1);
    const visibleReadings = this._readings.slice(this._page * this._config.history_page_size, (this._page + 1) * this._config.history_page_size);
    const isElec = this._meterType === 'electricity';
    const unit = isElec ? 'kWh' : 'm³';

    const currentReading = this._kpis.current_reading !== undefined ? this._kpis.current_reading : '-';
    const lastConsumption = this._kpis.last_consumption !== undefined ? this._kpis.last_consumption : '-';
    const lastCost = this._kpis.last_cost !== undefined ? this._kpis.last_cost.toFixed(2) : '-';
    const projCost = this._kpis.projected_monthly_cost !== undefined ? this._kpis.projected_monthly_cost.toFixed(2) : '-';
    const paymentDiff = this._kpis.monthly_payment_diff !== undefined ? this._kpis.monthly_payment_diff : null;

    let diffBadge = '';
    if (paymentDiff !== null) {
      if (paymentDiff >= 0) {
        diffBadge = `<span class="badge badge-green">+${paymentDiff.toFixed(2)} € Guthaben</span>`;
      } else {
        diffBadge = `<span class="badge badge-red">${paymentDiff.toFixed(2)} € Nachzahlung</span>`;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--ha-font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
          color: var(--primary-text-color, #212121);
        }
        ha-card {
          display: block;
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.08));
          background: var(--ha-card-background, var(--card-background-color, #fff));
          position: relative;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 14px;
        }
        .title-row {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 1.25rem;
          font-weight: 600;
        }
        .title-logo {
          width: 32px;
          height: 32px;
          border-radius: 6px;
          object-fit: cover;
          box-shadow: 0 1px 4px rgba(0,0,0,0.15);
        }
        .title-icon {
          font-size: 1.5rem;
        }
        .tabs {
          display: flex;
          background: var(--secondary-background-color, #f0f2f5);
          border-radius: 8px;
          padding: 3px;
          gap: 4px;
        }
        .tab-btn {
          border: none;
          background: transparent;
          padding: 6px 14px;
          border-radius: 6px;
          font-weight: 500;
          font-size: 0.9rem;
          cursor: pointer;
          color: var(--secondary-text-color, #666);
          transition: all 0.2s ease;
        }
        .tab-btn.active {
          background: var(--card-background-color, #fff);
          color: var(--primary-color, #03a9f4);
          box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }
        .kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
          gap: 10px;
          margin-bottom: 16px;
        }
        .kpi-card {
          background: var(--secondary-background-color, #f7f9fa);
          border-radius: 8px;
          padding: 10px 12px;
          display: flex;
          flex-direction: column;
        }
        .kpi-label {
          font-size: 0.75rem;
          color: var(--secondary-text-color, #757575);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }
        .kpi-val {
          font-size: 1.15rem;
          font-weight: 700;
          color: var(--primary-text-color, #212121);
        }
        .kpi-sub {
          font-size: 0.75rem;
          margin-top: 4px;
        }
        .badge {
          display: inline-block;
          font-size: 0.7rem;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
        }
        .badge-green {
          background: #e8f5e9;
          color: #2e7d32;
        }
        .badge-red {
          background: #ffebee;
          color: #c62828;
        }
        .badge-elec {
          background: #e1f5fe;
          color: #0277bd;
        }
        .badge-gas {
          background: #fff3e0;
          color: #ef6c00;
        }
        .type-switch {
          display: flex;
          gap: 8px;
          margin-top: 4px;
        }
        .type-btn {
          flex: 1;
          padding: 8px 10px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px;
          background: var(--secondary-background-color, #f0f2f5);
          cursor: pointer;
          font-weight: 600;
          font-size: 0.88rem;
          color: var(--secondary-text-color, #555);
          transition: all 0.15s ease;
        }
        .type-btn.active {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
          box-shadow: 0 1px 4px rgba(3, 169, 244, 0.3);
        }
        .queue-badge {
          background: #e8f5e9;
          color: #2e7d32;
          font-size: 0.8rem;
          font-weight: 600;
          padding: 4px 8px;
          border-radius: 4px;
          margin-bottom: 10px;
        }
        .action-bar {
          display: flex;
          gap: 10px;
          margin-bottom: 18px;
        }
        .btn-capture {
          flex: 2;
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border: none;
          border-radius: 8px;
          padding: 12px 16px;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: background 0.2s;
        }
        .btn-capture:hover {
          filter: brightness(0.95);
        }
        .btn-smart {
          background: var(--primary-color, #03a9f4);
        }
        .btn-manual {
          flex: 1;
          background: var(--secondary-background-color, #f0f2f5);
          color: var(--primary-text-color, #333);
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          padding: 12px 10px;
          font-size: 0.9rem;
          cursor: pointer;
        }
        .file-input {
          display: none;
        }
        .loading-overlay {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px 10px;
          background: var(--secondary-background-color, #f7f9fa);
          border-radius: 8px;
          margin-bottom: 16px;
        }
        .spinner {
          border: 3px solid rgba(0,0,0,0.1);
          border-top: 3px solid var(--primary-color, #03a9f4);
          border-radius: 50%;
          width: 28px;
          height: 28px;
          animation: spin 1s linear infinite;
          margin-bottom: 10px;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .modal-card {
          background: var(--secondary-background-color, #f9fafb);
          border: 2px solid var(--primary-color, #03a9f4);
          border-radius: 10px;
          padding: 16px;
          margin-bottom: 16px;
        }
        .modal-title {
          font-weight: 600;
          font-size: 1.05rem;
          margin-bottom: 12px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .modal-body {
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
        }
        .modal-img-preview {
          width: 130px;
          height: 130px;
          object-fit: cover;
          border-radius: 8px;
          border: 1px solid #ccc;
        }
        .modal-form {
          flex: 1;
          min-width: 180px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .form-group label {
          font-size: 0.8rem;
          color: var(--secondary-text-color, #666);
          display: block;
          margin-bottom: 2px;
        }
        .form-input {
          width: 100%;
          padding: 8px 10px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px;
          font-size: 1rem;
          box-sizing: border-box;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121);
        }
        .modal-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 14px;
        }
        .btn-confirm {
          background: #2e7d32;
          color: #fff;
          border: none;
          padding: 8px 16px;
          border-radius: 6px;
          font-weight: 600;
          cursor: pointer;
        }
        .btn-cancel {
          background: #757575;
          color: #fff;
          border: none;
          padding: 8px 14px;
          border-radius: 6px;
          cursor: pointer;
        }
        .table-container {
          overflow-x: auto;
          margin-top: 8px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.88rem;
          text-align: left;
        }
        th {
          padding: 8px 6px;
          color: var(--secondary-text-color, #666);
          border-bottom: 2px solid var(--divider-color, #e0e0e0);
          font-weight: 600;
        }
        td {
          padding: 10px 6px;
          border-bottom: 1px solid var(--divider-color, #eee);
          vertical-align: middle;
        }
        .btn-del {
          background: none;
          border: none;
          color: #e53935;
          cursor: pointer;
          font-size: 1rem;
          padding: 4px;
        }
        .empty-state {
          text-align: center;
          padding: 24px 10px;
          color: var(--secondary-text-color, #888);
          font-size: 0.95rem;
        }
      </style>

      <ha-card>
        <style>
          .header { flex-wrap: wrap; gap: 12px; }
          .title-row { min-width: 0; overflow-wrap: anywhere; }
          .pagination { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 12px; }
          .pagination button { color: var(--primary-text-color); background: var(--secondary-background-color); border: 1px solid var(--divider-color); border-radius: 8px; min-height: 40px; cursor: pointer; }
          .pagination button:disabled { opacity: .4; cursor: default; }
          .compact .kpi-card { padding: 8px; }
          .compact .kpi-grid { gap: 6px; margin-bottom: 8px; }
          .compact td { padding: 6px; }
          @media(max-width: 450px) { .action-bar { flex-wrap: wrap; } .modal-body { flex-direction: column; } }
        </style>
        <!-- Header & Tabs -->
        <div class="header">
          <div class="title-row">
            <img src="/meter_snap_frontend/icon.png" class="title-logo" alt="MeterSnap" onerror="this.style.display='none'" />
            <span>${meterSnapEscape(this._config.title)}</span>
          </div>
          <div class="tabs">
            <button class="tab-btn ${isElec ? 'active' : ''}" id="tabElec">⚡ Strom</button>
            <button class="tab-btn ${!isElec ? 'active' : ''}" id="tabGas">🔥 Gas</button>
          </div>
        </div>

        <!-- KPI Grid -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <span class="kpi-label">Aktueller Stand</span>
            <span class="kpi-val">${currentReading} <span style="font-size: 0.8rem; font-weight: 400;">${unit}</span></span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Letzter Verbrauch</span>
            <span class="kpi-val">${lastConsumption} <span style="font-size: 0.8rem; font-weight: 400;">${unit}</span></span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Letzte Kosten</span>
            <span class="kpi-val">${lastCost} €</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Monatsprognose</span>
            <span class="kpi-val">${projCost} €</span>
            <div class="kpi-sub">${diffBadge}</div>
          </div>
        </div>

        <section class="capture-section">
        <!-- Loading Spinner -->
        ${this._loading ? `
          <div class="loading-overlay">
            <div class="spinner"></div>
            <div>${this._statusMessage}</div>
          </div>
        ` : ''}

        <!-- Pending Scan / Confirmation Modal -->
        ${this._pendingScan && !this._loading ? `
          <div class="modal-card">
            <div class="modal-title">
              <span>🔎 Zählerstand prüfen & bestätigen</span>
              <span class="badge ${this._pendingScan.meter_type === 'electricity' ? 'badge-elec' : 'badge-gas'}">
                ${this._pendingScan.meter_type === 'electricity' ? '⚡ Strom' : '🔥 Gas'} • ${this._pendingScan.details || 'Erkannt'}
              </span>
            </div>
            ${this._pendingScan.remainingInQueue > 0 ? `
              <div class="queue-badge">📋 Noch ${this._pendingScan.remainingInQueue} weiteres Foto in der Warteschlange</div>
            ` : ''}
            <div class="modal-body">
              ${this._pendingScan.image ? `
                <img src="${this._pendingScan.image}" class="modal-img-preview" alt="Zähler Vorschau" />
              ` : ''}
              <div class="modal-form">
                <div class="form-group">
                  <label>Zählertyp zuordnen:</label>
                  <div class="type-switch">
                    <button type="button" class="type-btn ${this._pendingScan.meter_type === 'electricity' ? 'active' : ''}" id="btnSwitchElec">⚡ Strom (kWh)</button>
                    <button type="button" class="type-btn ${this._pendingScan.meter_type === 'gas' ? 'active' : ''}" id="btnSwitchGas">🔥 Gas (m³)</button>
                  </div>
                </div>
                <div class="form-group">
                  <label for="confirmReadingInput">Zählerstand (${this._pendingScan.unit}):</label>
                  <input type="number" step="0.001" class="form-input" id="confirmReadingInput" value="${this._pendingScan.reading}" />
                </div>
                <div class="form-group">
                  <label for="confirmTimeInput">Datum & Uhrzeit:</label>
                  <input type="datetime-local" class="form-input" id="confirmTimeInput" value="${this._pendingScan.timestamp}" />
                </div>
                <div class="form-group">
                  <label for="confirmNotesInput">Notiz (optional):</label>
                  <input type="text" class="form-input" id="confirmNotesInput" value="${this._pendingScan.notes}" />
                </div>
              </div>
            </div>
            <div class="modal-actions">
              <button class="btn-cancel" id="btnCancelScan">Abbrechen</button>
              <button class="btn-confirm" id="btnSaveScan">✅ Bestätigen & Speichern</button>
            </div>
          </div>
        ` : ''}

        <!-- Action Buttons -->
        ${!this._pendingScan && !this._loading ? `
          <div class="action-bar">
            <input type="file" accept="image/*,.heic,.HEIC,.heif,.HEIF,.jpg,.jpeg,.JPG,.JPEG,.png,.PNG,.webp,.WEBP,image/heic,image/heif" multiple class="file-input" id="cameraInput" />
            <button class="btn-capture btn-smart" id="btnCapture" title="Zählerfoto aufnehmen oder aus der Galerie wählen (Strom & Gas automatisch erkannt)">
              📸 Zähler scannen (Universal)
            </button>
            <button class="btn-manual" id="btnManual">
              ✏️ Manuell
            </button>
          </div>
        ` : ''}

        </section>
        <!-- History Table -->
        <div class="table-container">
          ${this._readings.length === 0 ? `
            <div class="empty-state">
              Noch keine Ablesungen für ${isElec ? 'den Stromzähler' : 'den Gaszähler'} vorhanden.<br>
              Mache dein erstes Foto!
            </div>
          ` : `
            <table>
              <thead>
                <tr>
                  <th>Datum</th>
                  <th>Stand (${unit})</th>
                  <th>Verbrauch</th>
                  <th>Kosten</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${visibleReadings.map(r => `
                  <tr>
                    <td>${this._formatDate(r.timestamp)}</td>
                    <td><b>${r.reading}</b></td>
                    <td>${r.consumption > 0 ? `+${r.consumption} ${unit}` : '-'}</td>
                    <td>${r.cost > 0 ? `${r.cost.toFixed(2)} €` : '-'}</td>
                    <td>
                      <button class="btn-del" data-id="${r.id}" title="Eintrag löschen">🗑️</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
            <nav class="pagination" aria-label="Ablesungen durchblättern">
              <button id="prevPage" ${this._page === 0 ? 'disabled' : ''} aria-label="Vorherige Seite">← Zurück</button>
              <span aria-live="polite">${this._page + 1} / ${pages} · ${this._readings.length} Ablesungen</span>
              <button id="nextPage" ${this._page >= pages - 1 ? 'disabled' : ''} aria-label="Nächste Seite">Weiter →</button>
            </nav>
          `}
        </div>
      </ha-card>
    `;

    const card = this.shadowRoot.querySelector('ha-card');
    card.classList.toggle('compact', this._config.compact);
    const selectors = { header: '.header', kpis: '.kpi-grid', capture: '.capture-section', history: '.table-container' };
    const sections = Object.fromEntries(Object.entries(selectors).map(([key, selector]) => [key, card.querySelector(selector)]));
    const metrics = [...sections.kpis.children];
    Object.keys(METER_SNAP_METRICS).forEach((key, index) => {
      if (!this._config.metrics.includes(key)) metrics[index].remove();
    });
    this._config.metrics.forEach(key => sections.kpis.append(metrics[Object.keys(METER_SNAP_METRICS).indexOf(key)]));
    Object.values(sections).forEach(section => section.remove());
    this._config.sections.forEach(key => card.append(sections[key]));
    if (this._config.meter !== 'switchable') sections.header.querySelector('.tabs').remove();
    // Keep an active confirmation accessible even if the editor hides capture.
    if ((this._pendingScan || this._loading) && !this._config.sections.includes('capture')) card.append(sections.capture);
    this._attachEventListeners();
  }

  _attachEventListeners() {
    const root = this.shadowRoot;

    root.getElementById('prevPage')?.addEventListener('click', () => { this._page = Math.max(0, this._page - 1); this._render(); });
    root.getElementById('nextPage')?.addEventListener('click', () => { this._page++; this._render(); });
    // Tabs
    root.getElementById('tabElec')?.addEventListener('click', () => this._setMeterType('electricity'));
    root.getElementById('tabGas')?.addEventListener('click', () => this._setMeterType('gas'));

    // Type Switcher inside Confirmation Modal
    root.getElementById('btnSwitchElec')?.addEventListener('click', () => {
      if (this._pendingScan) {
        this._pendingScan.meter_type = 'electricity';
        this._pendingScan.unit = 'kWh';
        this._render();
      }
    });
    root.getElementById('btnSwitchGas')?.addEventListener('click', () => {
      if (this._pendingScan) {
        this._pendingScan.meter_type = 'gas';
        this._pendingScan.unit = 'm³';
        this._render();
      }
    });

    // Camera / File Trigger
    const fileInput = root.getElementById('cameraInput');
    root.getElementById('btnCapture')?.addEventListener('click', () => {
      fileInput?.click();
    });
    fileInput?.addEventListener('change', (e) => this._handleFilesSelected(e));

    // Manual Entry Trigger
    root.getElementById('btnManual')?.addEventListener('click', () => this._openManualEntry());

    // Modal Actions
    root.getElementById('btnSaveScan')?.addEventListener('click', () => this._savePendingScan());
    root.getElementById('btnCancelScan')?.addEventListener('click', () => this._cancelPendingScan());

    // Row Delete
    root.querySelectorAll('.btn-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        if (id) this._deleteEntry(id);
      });
    });
  }
}

class MeterSnapCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({mode: 'open'}); }
  setConfig(config) { this._config = meterSnapConfig(config); this._render(); }
  set hass(hass) { this._hass = hass; }
  _emit() {
    this.dispatchEvent(new CustomEvent('config-changed', {detail: {config: {...this._config}}, bubbles: true, composed: true}));
  }
  _render() {
    if (!this._config) return;
    const cfg = this._config;
    const rows = (field, labels) => cfg[`${field}_order`].map((key, index) => {
      return `<div class="row"><label><input type="checkbox" data-list="${field}" value="${key}" ${cfg[field].includes(key) ? 'checked' : ''}> ${labels[key]}</label>
        <button type="button" data-field="${field}" data-key="${key}" data-step="-1" ${index <= 0 ? 'disabled' : ''} aria-label="${labels[key]} nach oben">↑</button>
        <button type="button" data-field="${field}" data-key="${key}" data-step="1" ${index === cfg[`${field}_order`].length - 1 ? 'disabled' : ''} aria-label="${labels[key]} nach unten">↓</button></div>`;
    }).join('');
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; color:var(--primary-text-color); }
      .field { display:grid; gap:6px; margin: 12px 0; }
      input, select, button { font:inherit; color:var(--primary-text-color); background:var(--card-background-color, white); border:1px solid var(--divider-color, #aaa); border-radius:6px; padding:8px; }
      input[type=checkbox] { accent-color:var(--primary-color); }
      fieldset { border:1px solid var(--divider-color, #aaa); border-radius:8px; margin:16px 0; }
      .row { display:flex; align-items:center; gap:8px; padding:4px 0; } .row label { flex:1; }
      button { min-width:40px; min-height:40px; cursor:pointer; } button:disabled { opacity:.35; cursor:default; }
      p { color:var(--secondary-text-color); font-size:.9em; }
    </style>
    <label class="field">Titel<input id="title" type="text" value="${meterSnapEscape(cfg.title)}"></label>
    <label class="field">Zähleranzeige<select id="meter">
      <option value="electricity">Nur Strom</option><option value="gas">Nur Gas</option><option value="switchable">Beide – mit Umschalter</option><option value="both">Beide – gleichzeitig sichtbar</option>
    </select></label>
    ${cfg.meter === 'switchable' ? '<label class="field">Beim Öffnen anzeigen<select id="default_meter"><option value="electricity">Strom</option><option value="gas">Gas</option></select></label>' : ''}
    ${cfg.meter === 'both' ? '<p>Strom und Gas werden getrennt nebeneinander angezeigt; auf schmalen Karten untereinander. Die ausgewählten Bereiche und Kennzahlen gelten für beide.</p>' : ''}
    <label><input id="compact" type="checkbox" ${cfg.compact ? 'checked' : ''}> Kompakte Darstellung</label>
    <fieldset><legend>Bereiche und Reihenfolge</legend>${rows('sections', METER_SNAP_SECTIONS)}</fieldset>
    ${cfg.meter === 'switchable' && !cfg.sections.includes('header') ? '<p>Ohne Titelbereich wird nur der beim Öffnen gewählte Zähler angezeigt. Für eine feste Zählerkarte oben „Nur Strom“ oder „Nur Gas“ wählen.</p>' : ''}
    <fieldset><legend>Kennzahlen und Reihenfolge</legend>${rows('metrics', METER_SNAP_METRICS)}</fieldset>
    <label class="field">Ablesungen pro Seite (1–50)<input id="history_page_size" type="number" min="1" max="50" step="1" value="${cfg.history_page_size}"></label>
    <p>Jede Karteninstanz hat eigene Einstellungen. Weitere MeterSnap-Karten können separat im Dashboard platziert werden. Farben folgen dem Home-Assistant-Theme.</p>`;
    for (const field of ['meter', 'default_meter']) {
      const el = this.shadowRoot.getElementById(field);
      if (el) el.value = cfg[field];
    }
    for (const field of ['title', 'meter', 'default_meter', 'compact', 'history_page_size']) {
      this.shadowRoot.getElementById(field)?.addEventListener('change', event => {
        if (field === 'history_page_size' && !event.target.checkValidity()) { event.target.reportValidity(); return; }
        this._config = meterSnapConfig({...this._config, [field]: field === 'compact' ? event.target.checked : event.target.value});
        this._emit(); this._render();
      });
    }
    this.shadowRoot.querySelectorAll('[data-list]').forEach(input => input.addEventListener('change', () => {
      const field = input.dataset.list;
      const selected = new Set(this._config[field]);
      if (input.checked) selected.add(input.value); else selected.delete(input.value);
      this._config[field] = this._config[`${field}_order`].filter(key => selected.has(key));
      this._emit(); this._render();
    }));
    this.shadowRoot.querySelectorAll('[data-step]').forEach(button => button.addEventListener('click', () => {
      const field = button.dataset.field;
      const list = [...this._config[`${field}_order`]];
      const index = list.indexOf(button.dataset.key);
      const next = index + Number(button.dataset.step);
      if (index < 0 || next < 0 || next >= list.length) return;
      [list[index], list[next]] = [list[next], list[index]];
      this._config[`${field}_order`] = list;
      this._config[field] = list.filter(key => this._config[field].includes(key));
      this._emit(); this._render();
    }));
  }
}
customElements.define('meter-snap-card-editor', MeterSnapCardEditor);

// Register Custom Element
customElements.define('meter-snap-card', MeterSnapCard);

// Register in Home Assistant Custom Cards List
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'meter-snap-card',
  name: 'MeterSnap Card',
  description: 'Zählerstände für Strom und Gas per Foto erfassen, auswerten und berechnen',
  preview: true,
});

console.info(
  '%c METERSNAP CARD %c Version 1.1.4-b4 geladen ',
  'color: white; background: #03a9f4; font-weight: 700;',
  'color: #03a9f4; background: white; font-weight: 700;'
);
