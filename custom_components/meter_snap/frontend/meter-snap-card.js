/**
 * MeterSnap Lovelace Custom Card
 * Version 1.0.11
 * 
 * Ermöglicht Foto-Aufnahme (Smartphone-Kamera), Ziffernerkennung via KI,
 * Bestätigungsdialog, Historientabelle und Kostenrechnung für Strom und Gas.
 */

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
    this._previewModalImage = null;
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;

    // Initial fetch once hass is available
    if (!oldHass && hass) {
      this._fetchData();
    }
  }

  setConfig(config) {
    this._config = {
      title: 'MeterSnap',
      default_meter: 'electricity',
      ...config,
    };
    if (config.default_meter) {
      this._meterType = config.default_meter;
    }
    this._render();
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig() {
    return {
      title: 'MeterSnap',
      default_meter: 'electricity'
    };
  }

  async _fetchData() {
    if (!this._hass) return;

    try {
      const resp = await this._callApi('GET', `/api/meter_snap/reading?meter_type=${this._meterType}`);
      if (resp && resp.success) {
        this._readings = resp.readings || [];
        this._kpis = resp.kpis || {};
      }
    } catch (err) {
      console.warn('MeterSnap: Fehler beim Laden der Daten:', err);
    }
    this._render();
  }

  async _callApi(method, path, body = null, isFormData = false) {
    const headers = {};
    const token = this._hass?.auth?.data?.access_token || this._hass?.auth?.accessToken;
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const options = {
      method,
      headers,
    };

    if (body) {
      if (isFormData) {
        options.body = body;
      } else {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
      }
    }

    const res = await fetch(path, options);
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`API Error (${res.status}): ${txt}`);
    }
    return await res.json();
  }

  _setMeterType(type) {
    if (this._meterType !== type) {
      this._meterType = type;
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
      const script = document.createElement('script');
      script.src = '/meter_snap_frontend/heic2any.min.js';
      script.onload = () => resolve(window.heic2any);
      script.onerror = () => {
        // Fallback to CDN if local static asset fails
        console.warn('MeterSnap: Lokales heic2any nicht erreichbar, lade von CDN...');
        const cdnScript = document.createElement('script');
        cdnScript.src = 'https://cdn.jsdelivr.net/npm/heic2any@0.0.4/dist/heic2any.min.js';
        cdnScript.onload = () => resolve(window.heic2any);
        cdnScript.onerror = (e) => reject(new Error('HEIC-Konverter konnte nicht geladen werden'));
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

  async _handleFileSelected(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    this._loading = true;
    this._statusMessage = 'Bereite Foto vor...';
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
            });
            const jpegBlob = Array.isArray(converted) ? converted[0] : converted;
            const newName = (file.name || 'meter').replace(/\.hei[cf]$/i, '.jpg');
            fileToProcess = new File([jpegBlob], newName, { type: 'image/jpeg' });
          }
        } catch (heicErr) {
          console.warn('MeterSnap: HEIC-Konvertierung per heic2any fehlgeschlagen:', heicErr);
        }
      }

      this._statusMessage = 'KI liest Zählerstand aus dem Foto...';
      this._render();

      // 1. Extract photo capture date & time from EXIF / file (strips GPS/serials later in canvas)
      photoDateTime = await this._extractPhotoDateTime(file);

      // 2. Compress and resize image to JPEG (strips all GPS / device metadata!)
      base64Image = await this._compressImage(fileToProcess);
      if (!base64Image) {
        throw new Error('Datei konnte nicht geladen werden.');
      }

      const resp = await this._callApi('POST', '/api/meter_snap/scan', {
        image: base64Image,
        meter_type: this._meterType,
      });

      if (!resp || !resp.success) {
        throw new Error(resp?.error || 'Zählerstand konnte nicht erkannt werden.');
      }

      // Open confirmation dialog with the original photo timestamp
      this._pendingScan = {
        reading: resp.reading !== undefined ? resp.reading : '',
        unit: resp.unit || (this._meterType === 'electricity' ? 'kWh' : 'm³'),
        confidence: resp.confidence || 'high',
        details: resp.details || '',
        image: base64Image,
        timestamp: photoDateTime,
        notes: 'Erfasst via Foto',
      };
    } catch (err) {
      alert(`Hinweis: ${err.message}\nDu kannst den Stand auch manuell eintragen.`);
      const nowStr = new Date().toISOString().slice(0, 16);
      this._pendingScan = {
        reading: '',
        unit: this._meterType === 'electricity' ? 'kWh' : 'm³',
        confidence: 'manual',
        details: 'Manuelle Eingabe',
        image: base64Image || null,
        timestamp: photoDateTime || nowStr,
        notes: '',
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
      reading: '',
      unit: this._meterType === 'electricity' ? 'kWh' : 'm³',
      confidence: 'manual',
      details: 'Manuelle Eingabe',
      image: null,
      timestamp: nowStr,
      notes: '',
    };
    this._render();
  }

  async _savePendingScan() {
    if (!this._pendingScan) return;

    const inputVal = this.shadowRoot.getElementById('confirmReadingInput')?.value;
    const timeVal = this.shadowRoot.getElementById('confirmTimeInput')?.value;
    const notesVal = this.shadowRoot.getElementById('confirmNotesInput')?.value;

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
        meter_type: this._meterType,
        reading: readingNum,
        timestamp: isoTimestamp,
        image_base64: this._pendingScan.image || null,
        notes: notesVal || '',
      };

      const resp = await this._callApi('POST', '/api/meter_snap/reading', payload);
      if (resp && resp.success) {
        this._pendingScan = null;
        await this._fetchData();
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
    this._pendingScan = null;
    this._render();
  }

  async _deleteEntry(id) {
    if (!confirm('Möchtest du diese Ablesung wirklich löschen?')) return;

    try {
      await this._callApi('DELETE', `/api/meter_snap/reading?meter_type=${this._meterType}&id=${id}`);
      await this._fetchData();
    } catch (err) {
      alert(`Fehler beim Löschen: ${err.message}`);
    }
  }

  _openImageModal(imgFile) {
    this._previewModalImage = `/api/meter_snap/image/${imgFile}`;
    this._render();
  }

  _closeImageModal() {
    this._previewModalImage = null;
    this._render();
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

  _render() {
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
        .thumb {
          width: 36px;
          height: 36px;
          object-fit: cover;
          border-radius: 4px;
          cursor: pointer;
          border: 1px solid #ddd;
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
        .lightbox-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(0,0,0,0.85);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
        }
        .lightbox-img {
          max-width: 90vw;
          max-height: 85vh;
          border-radius: 8px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }
        .lightbox-close {
          position: absolute;
          top: 20px;
          right: 20px;
          color: #fff;
          font-size: 2rem;
          cursor: pointer;
          background: none;
          border: none;
        }
      </style>

      <ha-card>
        <!-- Header & Tabs -->
        <div class="header">
          <div class="title-row">
            <img src="/meter_snap_frontend/icon.png" class="title-logo" alt="MeterSnap" onerror="this.style.display='none'" />
            <span>${this._config.title || 'MeterSnap'}</span>
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
              <span class="badge badge-green">${this._pendingScan.details || 'Erkannt'}</span>
            </div>
            <div class="modal-body">
              ${this._pendingScan.image ? `
                <img src="${this._pendingScan.image}" class="modal-img-preview" alt="Zähler Vorschau" />
              ` : ''}
              <div class="modal-form">
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
            <input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif,image/*" capture="environment" class="file-input" id="cameraInput" />
            <button class="btn-capture" id="btnCapture">
              📸 Foto aufnehmen / hochladen
            </button>
            <button class="btn-manual" id="btnManual">
              ✏️ Manuell
            </button>
          </div>
        ` : ''}

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
                  <th>Foto</th>
                  <th>Stand (${unit})</th>
                  <th>Verbrauch</th>
                  <th>Kosten</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${this._readings.map(r => `
                  <tr>
                    <td>${this._formatDate(r.timestamp)}</td>
                    <td>
                      ${r.image_file ? `
                        <img src="/api/meter_snap/image/${r.image_file}" class="thumb" data-img="${r.image_file}" title="Vergrößern" />
                      ` : '-'}
                    </td>
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
          `}
        </div>

        <!-- Lightbox Zoom Modal -->
        ${this._previewModalImage ? `
          <div class="lightbox-backdrop" id="lightbox">
            <button class="lightbox-close" id="lightboxClose">&times;</button>
            <img src="${this._previewModalImage}" class="lightbox-img" alt="Zählerfoto Großansicht" />
          </div>
        ` : ''}
      </ha-card>
    `;

    this._attachEventListeners();
  }

  _attachEventListeners() {
    const root = this.shadowRoot;

    // Tabs
    root.getElementById('tabElec')?.addEventListener('click', () => this._setMeterType('electricity'));
    root.getElementById('tabGas')?.addEventListener('click', () => this._setMeterType('gas'));

    // Camera Trigger
    const fileInput = root.getElementById('cameraInput');
    root.getElementById('btnCapture')?.addEventListener('click', () => {
      fileInput?.click();
    });
    fileInput?.addEventListener('change', (e) => this._handleFileSelected(e));

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

    // Thumbnails Zoom
    root.querySelectorAll('.thumb').forEach(img => {
      img.addEventListener('click', () => {
        const file = img.getAttribute('data-img');
        if (file) this._openImageModal(file);
      });
    });

    // Lightbox Close
    root.getElementById('lightbox')?.addEventListener('click', () => this._closeImageModal());
    root.getElementById('lightboxClose')?.addEventListener('click', () => this._closeImageModal());
  }
}

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
  '%c METERSNAP CARD %c Version 1.0.11 geladen ',
  'color: white; background: #03a9f4; font-weight: 700;',
  'color: #03a9f4; background: white; font-weight: 700;'
);
