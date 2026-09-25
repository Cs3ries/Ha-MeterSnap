// Run with NODE_PATH pointing to a Playwright installation: node tests/test_card.cjs
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<style>body { margin: 8px; --primary-text-color:#222; --secondary-text-color:#666; --card-background-color:white; --divider-color:#ddd; --primary-color:#03a9f4; }</style>');
    await page.addScriptTag({path: path.resolve('custom_components/meter_snap/frontend/meter-snap-card.js')});
    const result = await page.evaluate(async () => {
      const check = (value, message) => { if (!value) throw new Error(message); };
      const apiCard = document.createElement('meter-snap-card');
      const apiCalls = [];
      const apiResult = {success:true};
      apiCard._hass = {
        get auth() { throw new Error('Must not read private auth fields'); },
        async callApi(...args) { apiCalls.push(args); return apiResult; }
      };
      const originalFetch = window.fetch;
      window.fetch = () => { throw new Error('Must not send raw fetch'); };
      try {
        const payload = {reading:123, meter_type:'electricity'};
        check(await apiCard._callApi('GET', '/api/meter_snap/reading?meter_type=electricity') === apiResult, 'API response');
        await apiCard._callApi('POST', '/api/meter_snap/reading', payload);
        await apiCard._callApi('POST', '/api/meter_snap/scan', {image:'data:image/jpeg;base64,test'});
        await apiCard._callApi('DELETE', '/api/meter_snap/reading?meter_type=gas&id=123');
        check(apiCalls[0][1] === 'meter_snap/reading?meter_type=electricity', 'strip API prefix and preserve query');
        check(apiCalls[1][0] === 'POST' && apiCalls[1][2] === payload, 'pass JSON object unchanged');
        check(apiCalls[2][1] === 'meter_snap/scan' && apiCalls[3][0] === 'DELETE', 'scan and delete use HA');
        const denied = {status_code:401, message:'Unauthorized'};
        apiCard._hass.callApi = async () => { throw denied; };
        let caught;
        try { await apiCard._callApi('GET', '/api/meter_snap/reading'); } catch (error) { caught = error; }
        check(caught === denied, 'propagate authentication failure without fallback');
        apiCard._hass = {};
        caught = null;
        try { await apiCard._callApi('GET', '/api/meter_snap/reading'); } catch (error) { caught = error; }
        check(caught instanceof Error, 'missing connection fails without request');
      } finally { window.fetch = originalFetch; }
      const card = document.createElement('meter-snap-card');
      card.setConfig({type:'custom:meter-snap-card', title:'<img src=x onerror=alert(1)>'});
      card._readings = Array.from({length: 500}, (_,i) => ({id:String(i), timestamp:'2026-09-22T12:00:00Z', reading:500-i, consumption:1, cost:0.3}));
      document.body.append(card); card._render();
      check(card.shadowRoot.querySelectorAll('tbody tr').length === 5, 'history bounded');
      check(card.shadowRoot.querySelector('.title-row span').textContent.startsWith('<img'), 'title escaped');
      card.shadowRoot.querySelector('#nextPage').click();
      check(card.shadowRoot.querySelector('tbody b').textContent === '495', 'next page');
      card._page = 99; card._readings = card._readings.slice(0,6); card._render();
      check(card._page === 1 && card.shadowRoot.querySelectorAll('tbody tr').length === 1, 'page clamped after deletion');
      card.setConfig({meter:'gas', sections:['history','kpis'], metrics:['cost'], compact:true});
      check(!card.shadowRoot.querySelector('.header'), 'hidden section');
      check(card._meterType === 'gas', 'fixed meter');
      check(card.shadowRoot.querySelectorAll('.kpi-card').length === 1, 'metric selection');
      check(card.shadowRoot.querySelector('ha-card').children[1].className === 'table-container', 'section order');
      const editor = document.createElement('meter-snap-card-editor');
      editor.setConfig({type:'custom:meter-snap-card'}); document.body.append(editor);
      let updated; editor.addEventListener('config-changed', e => updated = e.detail.config);
      editor.shadowRoot.querySelector('[data-list="sections"][value="history"]').click();
      check(!updated.sections.includes('history'), 'editor visibility');
      editor.shadowRoot.querySelector('[data-field="sections"][data-key="kpis"][data-step="-1"]').click();
      check(updated.sections[0] === 'kpis', 'editor reorder');
      const editorOrder = field => [...editor.shadowRoot.querySelectorAll(`[data-list="${field}"]`)].map(input => input.value).join(',');
      for (const [field, key] of [['sections','kpis'], ['metrics','reading']]) {
        const before = editorOrder(field);
        editor.shadowRoot.querySelector(`[data-list="${field}"][value="${key}"]`).click();
        check(editorOrder(field) === before, 'unchecking keeps editor order');
        editor.setConfig(JSON.parse(JSON.stringify(updated)));
        check(editorOrder(field) === before, 'hidden position survives config reload');
        editor.shadowRoot.querySelector(`[data-list="${field}"][value="${key}"]`).click();
        check(editorOrder(field) === before && updated[field][0] === key, 'rechecking restores original position');
      }
      editor.shadowRoot.querySelector('[data-field="sections"][data-key="history"][data-step="-1"]').click();
      check(updated.sections_order.indexOf('history') === 2 && !updated.sections.includes('history'), 'disabled item can move without becoming visible');
      for (const meter of ['gas', 'electricity', 'switchable']) {
        const select = editor.shadowRoot.querySelector('#meter');
        select.value = meter; select.dispatchEvent(new Event('change'));
        const meterCard = document.createElement('meter-snap-card');
        meterCard.setConfig({...updated, sections:['header','kpis']});
        check(meterCard._meterType === (meter === 'gas' ? 'gas' : 'electricity'), 'editor meter selection applied');
        check(Boolean(meterCard.shadowRoot.querySelector('.tabs')) === (meter === 'switchable'), 'only both mode shows meter tabs');
      }
      const restored = document.createElement('meter-snap-card'); restored.setConfig(JSON.parse(JSON.stringify(updated)));
      check(!restored.shadowRoot.querySelector('.table-container'), 'config roundtrip');
      const second = document.createElement('meter-snap-card'); second.setConfig({}); document.body.append(second);
      let calls = 0;
      for (const c of [card, second]) { c._hass = {}; c._callApi = async () => { calls++; return {success:true,readings:[],kpis:{current_reading:123}}; }; }
      window.dispatchEvent(new Event('meter-snap-data-changed'));
      await new Promise(resolve => setTimeout(resolve, 0));
      check(calls === 2 && second._kpis.current_reading === 123, 'synchronize cards');
      second._openManualEntry();
      const input = second.shadowRoot.querySelector('#confirmReadingInput'); input.value = '987';
      await second._fetchData();
      check(second.shadowRoot.querySelector('#confirmReadingInput') === input && input.value === '987', 'preserve input during refresh');
      second._pendingScan = null;
      const pending = [];
      second._callApi = () => new Promise(resolve => pending.push(resolve));
      const oldRequest = second._fetchData(); const newRequest = second._fetchData();
      pending[1]({success:true, readings:[], kpis:{current_reading:200}}); await newRequest;
      pending[0]({success:true, readings:[], kpis:{current_reading:100}}); await oldRequest;
      check(second._kpis.current_reading === 200, 'ignore stale response');
      card.remove(); second.remove(); editor.remove();
      const bothSelect = editor.shadowRoot.querySelector('#meter');
      bothSelect.value = 'both'; bothSelect.dispatchEvent(new Event('change'));
      check(updated.meter === 'both', 'editor supports simultaneous meters');
      const both = document.createElement('meter-snap-card');
      both.setConfig({...updated, sections:['header','kpis','capture','history'], metrics:['reading']});
      document.body.append(both);
      const requestedMeters = [];
      const ha = {callApi: async (_method, url) => {
        const gas = url.includes('meter_type=gas'); requestedMeters.push(url);
        return {success:true, kpis:{current_reading: gas ? 700 : 12000}, readings:Array.from({length:7}, (_,i) => ({id:String(i),reading:(gas ? 700 : 12000)-i,timestamp:'2026-09-22T12:00:00Z',consumption:1,cost:1}))};
      }};
      both.hass = ha;
      await new Promise(resolve => setTimeout(resolve, 0));
      const meters = [...both.shadowRoot.querySelectorAll('meter-snap-card')];
      check(meters.length === 2 && meters[0]._kpis.current_reading === 12000 && meters[1]._kpis.current_reading === 700, 'both meter values loaded independently');
      check(requestedMeters.length === 2 && !requestedMeters.some(url => url.includes('meter_type=both')), 'one valid request per meter');
      check(meters.every(card => !card.shadowRoot.querySelector('.tabs')), 'no redundant switches in both mode');
      meters[0].shadowRoot.querySelector('#nextPage').click();
      check(meters[0]._page === 1 && meters[1]._page === 0, 'independent history pages');
      meters[1]._openManualEntry();
      const gasInput = meters[1].shadowRoot.querySelector('#confirmReadingInput'); gasInput.value = '777';
      both.hass = {...ha}; window.dispatchEvent(new Event('meter-snap-data-changed'));
      await new Promise(resolve => setTimeout(resolve, 0));
      check(meters[1].shadowRoot.querySelector('#confirmReadingInput') === gasInput && gasInput.value === '777', 'both mode preserves active input');
      check(both.shadowRoot.querySelector('.meters').scrollWidth <= both.clientWidth, 'both mode fits mobile');
      both.setConfig({meter:'gas'});
      check(!both.shadowRoot.querySelector('meter-snap-card') && meters.every(card => !card.isConnected), 'mode change disconnects children');
      both.remove();

      // New reading workflows use the same API, dialog and synchronization event.
      check(meterSnapAge('2026-03-08T12:00:00', new Date('2026-03-09T11:00:00')) === 1, 'calendar days across DST');
      check(meterSnapAge('2026-01-01T23:59:00', new Date('2026-01-02T00:01:00')) === 1, 'calendar midnight');
      check(meterSnapAge(null) === null && meterSnapAge('bad') === null, 'missing freshness');
      const editCard = document.createElement('meter-snap-card');
      editCard.setConfig({sections:['history','kpis'], meter:'electricity'});
      editCard._hass = {language:'en'};
      editCard._readings = [{id:'edit', timestamp:'2026-01-01T12:34:56.789Z', reading:100, notes:'<unsafe "note">', consumption:null, cost:null, incomplete:true}];
      editCard._kpis = {current_reading:null,last_cost:null,projected_monthly_cost:null};
      document.body.append(editCard); editCard._render();
      check(editCard.shadowRoot.textContent.includes('Incomplete'), 'incomplete in English');
      editCard.shadowRoot.querySelector('.btn-edit').click();
      check(editCard.shadowRoot.querySelector('#confirmNotesInput').value === '<unsafe "note">', 'escaped editing note');
      check(editCard.shadowRoot.querySelector('#confirmTimeInput').value === meterSnapLocalTime('2026-01-01T12:34:56Z'), 'local time including seconds');
      check(editCard.shadowRoot.querySelector('#btnSwitchGas').disabled, 'editing cannot move meters');
      const setInput = (id,value) => { const input = editCard.shadowRoot.getElementById(id); input.value=value; input.dispatchEvent(new Event('input')); };
      setInput('confirmReadingInput','105'); setInput('confirmNotesInput','corrected');
      const sent = []; const oldConfirm = window.confirm; const oldAlert = window.alert;
      let confirmed = false;
      window.confirm = () => confirmed;
      window.alert = message => { throw new Error(message); };
      editCard._fetchData = async () => {};
      editCard._callApi = async (method,url,payload) => {
        sent.push(payload);
        return payload.confirmation ? {success:true} : {warning:true, confirmation:'token', warnings:[{from:'2026-01-01',to:'2026-01-02',consumption:105,days:1,daily_rate:105,limit:100}]};
      };
      await editCard._savePendingScan();
      check(sent.length === 1 && editCard._pendingScan, 'cancel warning keeps draft unsaved');
      check(editCard.shadowRoot.querySelector('#confirmReadingInput').value === '105', 'warning preserves changed value');
      confirmed = true; await editCard._savePendingScan();
      check(sent.length === 3 && sent[2].confirmation === 'token' && sent[2].id === 'edit' && sent[2].notes === 'corrected' && sent[2].timestamp === '2026-01-01T12:34:56.789Z', 'explicit confirmed correction');
      check(!editCard._pendingScan, 'success closes draft');
      editCard._openReplacement();
      check(editCard.shadowRoot.querySelector('#confirmOldInput'), 'replacement form');
      setInput('confirmTimeInput', '2026-01-02T12:00:00');
      editCard._callApi = async (method,url,payload) => { sent.push(payload); return {success:true}; };
      await editCard._savePendingScan();
      check(sent.at(-1).kind === 'replacement' && sent.at(-1).reading === null && sent.at(-1).old_reading === null, 'unknown replacement readings remain null');
      window.confirm = oldConfirm; window.alert = oldAlert;
      check(editor.shadowRoot.querySelector('[data-list="metrics"][value="freshness"]'), 'freshness in visual editor');
      editCard.remove();

      const preview = document.createElement('meter-snap-card');
      preview.setConfig({title:'Mein Strom',meter:'electricity',compact:true});
      preview._kpis = {current_reading:12450,last_consumption:210,last_cost:78,projected_monthly_cost:82};
      preview._readings = Array.from({length:12}, (_,i) => ({id:String(i),timestamp:'2026-09-22T12:00:00Z',reading:12450-i*210,consumption:210,cost:78}));
      document.body.append(preview); preview._render();
      return 'authenticated API delegation, pagination, configuration, editor, synchronization, draft preservation, request races, editing, replacement, warnings and freshness passed';
    });
    await page.screenshot({path:'/tmp/meter-snap-mobile.png', fullPage:true});
    await page.evaluate(() => {
      if (document.documentElement.scrollWidth > window.innerWidth) throw new Error('mobile page overflow');
      const editor = document.createElement('meter-snap-card-editor');
      editor.setConfig({type:'custom:meter-snap-card', meter:'gas', sections:['kpis','capture']});
      document.body.replaceChildren(editor);
    });
    await page.screenshot({path:'/tmp/meter-snap-editor.png', fullPage:true});
    await page.evaluate(() => {
      const card = document.createElement('meter-snap-card');
      card.setConfig({meter:'both', title:'Strom & Gas', sections:['header','kpis'], metrics:['reading','consumption']});
      document.body.replaceChildren(card);
      [...card.shadowRoot.querySelectorAll('meter-snap-card')].forEach((child, index) => {
        child._kpis = {current_reading:index ? 700 : 12000, last_consumption:index ? 25 : 210}; child._render();
      });
    });
    await page.screenshot({path:'/tmp/meter-snap-both-mobile.png',fullPage:true});
    await page.setViewportSize({width:1000,height:700});
    await page.screenshot({path:'/tmp/meter-snap-both-desktop.png',fullPage:true});
    assert.deepEqual(errors, []);
    console.log(result);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
