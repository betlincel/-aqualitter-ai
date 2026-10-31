/* Plain JavaScript/Leaflet. Location functions are exported for controlled tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root.document) root.addEventListener('DOMContentLoaded', () => api.init(root));
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const LOW_ACCURACY_M = 100;
  function createState() { return { candidate: null, confirmed: false, error: '', busy: false, request: 0 }; }
  function validCoordinate(lat, lng) {
    return Number.isFinite(lat) && Number.isFinite(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
  }
  function replaceCandidate(state, candidate) {
    state.candidate = candidate; state.confirmed = false; state.error = ''; state.busy = false;
  }
  function selectGps(state, position) {
    const c = position.coords;
    if (!c || !validCoordinate(c.latitude, c.longitude) || !Number.isFinite(c.accuracy) || c.accuracy < 0 ||
        !Number.isFinite(position.timestamp) || !Number.isFinite(new Date(position.timestamp).getTime())) {
      state.candidate = null; state.confirmed = false; state.busy = false;
      state.error = 'GPS geçerli koordinat, doğruluk veya zaman bilgisi döndürmedi. Haritadan nokta seçin.'; return;
    }
    replaceCandidate(state, {latitude:c.latitude, longitude:c.longitude, accuracy_m:c.accuracy,
      captured_at:new Date(position.timestamp).toISOString(), location_source:'browser_geolocation'});
  }
  function selectManual(state, lat, lng, now = Date.now()) {
    if (!validCoordinate(lat, lng)) throw new Error('Geçersiz harita koordinatı.');
    state.request++; // A late GPS callback must not replace an explicit map click.
    replaceCandidate(state, {latitude:lat, longitude:lng, accuracy_m:null,
      captured_at:new Date(now).toISOString(), location_source:'manual_map'});
  }
  function confirmLocation(state, lowAccuracyAcknowledged) {
    if (!state.candidate || state.busy) throw new Error('Önce konum seçin.');
    if (state.candidate.accuracy_m > LOW_ACCURACY_M && !lowAccuracyAcknowledged)
      throw new Error('Düşük GPS doğruluğu uyarısını onaylayın veya haritadan yeni bir nokta seçin.');
    state.confirmed = true; state.error = '';
  }
  function requestGps(state, env, changed) {
    state.request++; const request = state.request;
    state.candidate = null; state.confirmed = false; state.error = '';
    if (!env.isSecureContext) { state.busy = false; state.error = 'GPS için HTTPS gerekir (yerel geliştirmede localhost kullanılabilir). Haritadan manuel nokta seçebilirsiniz.'; changed(); return; }
    if (!env.navigator.geolocation) { state.busy = false; state.error = 'Bu tarayıcı konum hizmetini desteklemiyor. Haritadan nokta seçin.'; changed(); return; }
    state.busy = true; changed();
    try { env.navigator.geolocation.getCurrentPosition(position => {
      if (request !== state.request) return;
      selectGps(state, position); changed();
    }, error => {
      if (request !== state.request) return;
      state.busy = false;
      const messages = {1:'Konum izni verilmedi. İzni tarayıcı ayarlarından değiştirebilir veya haritadan manuel nokta seçebilirsiniz.',
        2:'GPS konumu alınamadı. Haritadan manuel nokta seçin.', 3:'GPS isteği zaman aşımına uğradı. Tekrar deneyin veya haritadan manuel nokta seçin.'};
      state.error = messages[error.code] || 'Konum alınamadı. Haritadan manuel nokta seçin.'; changed();
    }, {enableHighAccuracy:true, maximumAge:0, timeout:15000}); }
    catch (_) { state.busy = false; state.error = 'Tarayıcı konum isteğini başlatamadı. HTTPS ve tarayıcı izinlerini kontrol edin veya haritadan nokta seçin.'; changed(); }
  }
  function confirmedPayload(state) {
    if (!state.confirmed || !state.candidate) throw new Error('Haritadaki konumu önce onaylayın.');
    return {...state.candidate, location_confirmed:true};
  }
  function init(env) {
    const $ = id => env.document.getElementById(id), state = createState();
    let map = null, marker = null, circle = null, ready = false, sending = false, submitted = false;
    let lastCandidate = null;
    try {
      map = env.L.map('map').setView([41.045, 39.75], 11);
      // CARTO's public basemap is API-key-free and includes the required OSM
      // attribution. A tile error must never disable GPS or manual selection.
      const tiles = env.L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {maxZoom:20,
        subdomains:'abcd',
        attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}).addTo(map);
      if (tiles && typeof tiles.on === 'function') tiles.on('tileerror', () => {
        const warning = $('map-error');
        warning.hidden = false;
        warning.textContent = 'Harita döşemeleri yüklenemedi. GPS koordinatı ve manuel nokta seçimi yine kullanılabilir; konum otomatik olarak taşınmaz.';
      });
      map.on('click', e => { if (sending || submitted) return; selectManual(state, e.latlng.lat, e.latlng.lng); render(); });
    } catch (_) { $('map-error').hidden = false; }
    function render() {
      const c = state.candidate;
      if (c !== lastCandidate) { $('accuracy-ack').checked = false; lastCandidate = c; }
      if (marker) { marker.remove(); marker = null; }
      if (circle) { circle.remove(); circle = null; }
      $('coordinates').hidden = !c;
      if (c) {
        $('latlng').textContent = `${c.latitude.toFixed(6)}, ${c.longitude.toFixed(6)}`;
        $('source').textContent = c.location_source === 'manual_map' ? 'Haritada manuel seçim' : 'Tarayıcı geolocation';
        $('accuracy').textContent = c.accuracy_m === null ? 'Bilinmiyor (manuel seçim)' : `${c.accuracy_m.toFixed(1)} m (garanti değildir)`;
        $('captured').textContent = c.captured_at;
        $('time-label').textContent = c.location_source === 'manual_map' ? 'Manuel seçim zamanı (UTC)' : 'GPS ölçüm zamanı (UTC)';
        if (map) {
          marker = env.L.marker([c.latitude, c.longitude]).addTo(map).bindPopup(state.confirmed ? 'Onaylanan konum' : 'Geçici seçim · onay bekliyor');
          if (c.accuracy_m !== null) circle = env.L.circle([c.latitude, c.longitude], {radius:c.accuracy_m,color:'#25a475'}).addTo(map);
        }
      }
      $('accuracy-warning').hidden = !c || c.accuracy_m === null || c.accuracy_m <= LOW_ACCURACY_M;
      $('location-status').className = state.error ? 'error' : '';
      $('location-status').textContent = state.error || (state.busy ? 'GPS konumu bekleniyor…' : c ? 'İşaretçiyi kontrol edin ve konumu onaylayın.' : 'Konum seçilmedi. Haritaya tıklayabilir veya Konumumu kullan düğmesine basabilirsiniz.');
      $('confirmed').textContent = state.confirmed ? 'Konum onaylandı. Yeni GPS isteği veya harita tıklaması onayı sıfırlar.' : '';
      $('gps').disabled = state.busy || sending || submitted;
      $('manual').disabled = sending || submitted;
      $('confirm').disabled = !c || !map || state.busy || sending || submitted;
      $('submit').disabled = !ready || !state.confirmed || !$('photo').files.length || sending || submitted;
    }
    $('gps').addEventListener('click', () => requestGps(state, env, () => {
      render();
      if (state.candidate && map) map.setView([state.candidate.latitude,state.candidate.longitude], 15);
    }));
    $('manual').addEventListener('click', () => { $('map').focus(); $('location-status').textContent = 'Konum seçmek için haritada bir noktaya tıklayın.'; });
    $('confirm').addEventListener('click', () => { try { confirmLocation(state, $('accuracy-ack').checked); } catch (error) { state.error = error.message; } render(); });
    $('photo').addEventListener('change', render);
    $('new-report').addEventListener('click', () => env.location.reload());
    $('submit').addEventListener('click', async () => {
      if (sending || submitted) return;
      try {
        const file = $('photo').files[0];
        if (!file || file.size > 5 * 1024 * 1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) throw new Error('JPEG, PNG veya WebP; en fazla 5 MiB fotoğraf seçin.');
        const payload = {...confirmedPayload(state), note:$('note').value};
        sending = true; render(); $('submit-status').textContent = 'Fotoğraf yükleniyor ve bildirim kaydediliyor…';
        payload.photo_base64 = await new Promise((resolve,reject) => { const reader = new env.FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('Fotoğraf okunamadı.')); reader.readAsDataURL(file); });
        const response = await env.fetch('/api/reports', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Bildirim kaydedilemedi.');
        submitted = true;
        $('submit-status').textContent = `Bildirim inceleme bekliyor (pending_review). Referans: ${result.report_id}`;
        $('submit-status').className = 'success'; $('new-report').hidden = false;
      } catch (error) { $('submit-status').textContent = error.message || 'Gönderim tamamlanamadı; bağlantıyı kontrol edin.'; $('submit-status').className = 'error'; }
      finally { sending = false; render(); }
    });
    env.fetch('/api/config').then(r => r.json()).then(config => { ready = config.ready === true;
      $('setup').textContent = ready ? 'Anonim gönderim yapılandırması var. Supabase şema/bucket/RLS kurulumu gönderimde denetlenir.' : config.message;
      $('setup').className = ready ? 'success' : 'error'; render();
    }).catch(() => { $('setup').textContent = 'Sunucu yapılandırması kontrol edilemedi. Sayfayı yeniden açın veya yöneticinize bildirin.'; render(); });
    render();
  }
  return {LOW_ACCURACY_M,createState,selectGps,selectManual,requestGps,confirmLocation,confirmedPayload,init};
});
