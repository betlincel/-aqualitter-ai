# AquaLitter teslim noktası — 31 Ekim 2026

Görüntü analizi, kullanıcı incelemesi, konum/gözlem kayıtları, gerçek Natural Earth maskesiyle denetlenen altı noktalı deniz rota demosu ve tahmini yakıt/egzoz CO₂ hesabı mevcut. Son değişiklik, `design/stitch` görsel referansının **beş bölümlü yerel Streamlit arayüzüne uyarlanmasıdır**. Rota algoritması, kara denetimi ve 1 km tampon korunmuştur.

## Ayrı vatandaş GPS prototipi — feature/citizen-gps-reports

Bu çalışma teslim commit'i `5f18592` üzerinden açılan **feature/citizen-gps-reports** dalındadır. Aşağıdaki vatandaş prototipi dosyaları ve yönetici menüsü değişiklikleri commit/push edilmeden çalışma ağacında bırakılır. `kahveotagii` teslimindeki görüntü analizi, hesap modülleri, rota algoritması ve yerel kullanıcı gözlem dosyası değiştirilmemiştir.

- `citizen_app.py`: Ayrı standart Python HTTP sunucusu, varsayılan localhost:8502. `/api/config` sadece hazır/kurulum durumunu, `/api/reports` yalnızca gönderimi işler. Kimlik bilgisi, payload veya koordinat loglamaz; CORS açmaz; aynı origin JSON, gövde boyutu ve zaman aşımı denetimleri uygular. HTTPS ters proxy arkasından üst düzey sayfa olarak açılmalıdır.
- `citizen_reports.py`: Yerel `.streamlit/secrets.toml` okur; yalnızca publishable veya JWT rolü `anon` olan anahtarı kabul eder, service/secret anahtarı kullanmaz veya dosyaya yazmaz. Ayarlar istemciye gönderilmez. Konum/onay/zaman/not/fotoğraf doğrulaması, bellek içinde EXIF'siz JPEG hazırlama, yeni Storage nesnesi ve `return=minimal` ile `pending_review` metadata INSERT'i yapar. Fotoğraflar yerel diske yazılmaz.
- `citizen_web/`: Düz HTML/CSS/JS + Leaflet. Otomatik GPS çağrısı yok; **Konumumu kullan** düğmesi tarayıcı iznini tetikler. Konum geçici işaretçi/çember ve enlem-boylam/doğruluk/zamanla gösterilir, kullanıcı onaylar. GPS düşük doğruluk (100 m üzeri) için ek kabul gerekir. İzin reddi/hata/timeout sonrası harita seçimi sunulur; manuel seçim doğruluğu `null` ve zamanı seçim anıdır. Yeni seçim önceki onayı sıfırlar; koordinat taşınmaz/denize snap edilmez. GPS ve HTTPS sınırlamaları ekranda görünür.
- `supabase/schema.sql`: Yeni tablo, özel bucket, anonim yalnızca INSERT ve `pending_review` politikası; halka açık okuma/listeleme, güncelleme ve silme yok. Storage restrictive guard kuralları başka geniş politikaların bu bucket'ı açmasını önler. Mevcut citizen_reports tablosu varsa transaction durur; DROP/temizleme yapmayın. `check_access.sql` salt okunur kurulum kontrolüdür.
- `tests/test_citizen_reports.py`, `tests/citizen_gps.test.js`: Sunucu/config/transport ve kontrollü GPS/DOM/Leaflet bağlama testleri. Gerçek telefon veya canlı Supabase doğrulaması değildir.

### Kullanıcının yapacağı manuel adım

Yerel anonim Supabase yapılandırması bulundu; gerçek değerler terminale veya bu belgelere yazılmadı. Dashboard → SQL Editor'da önce **supabase/schema.sql**, sonra **supabase/check_access.sql** çalıştırın. Sonuçlarda RLS=true, can_submit=true, listele/güncelle/sil=false ve bucket public=false beklenir. Ardından kendi fotoğrafınızla tek bir gerçek gönderim yapıp Dashboard'da özel fotoğraf ve `pending_review` metadata kaydını doğrulayın. Bu canlı SQL/RLS/yükleme adımı henüz yapılmadı.

```powershell
.\.venv\Scripts\python.exe citizen_app.py --host 127.0.0.1 --port 8502
```

Üretim yolunda `citizen_app.py` Supabase URL ve anonim/publishable anahtarı yalnızca
`SUPABASE_URL`, `SUPABASE_ANON_KEY` veya `SUPABASE_PUBLISHABLE_KEY` ortam değişkenlerinden
okur; Streamlit secrets dosyasını ve service-role anahtarını kullanmaz. Platform portu
`PORT` ile verilebilir; örnek: `\.venv\Scripts\python.exe citizen_app.py --host 0.0.0.0`.

QR içine bu ayrı sunucuya yönlenen, sayfa ve `/api/*` uçları aynı origin altında olan HTTPS URL'sini koyun. Proxy `Host` başlığını korumalı, `Permissions-Policy` geolocation'ı engellememelidir; iframe kullanmayın. Telefonda bilgisayarın localhost'u açılamaz, LAN HTTP üzerinden GPS beklenmemelidir. HTTPS yayın/tünel ve QR üretimi otomatik kurulmadı. Yapılandırma yoksa sayfa kurulum mesajıyla gönderimi kapatır. Ana uygulama ayrı olarak 8501'de çalışır.

32 Python testi (mevcut 22 + yeni 10), 8 Node kontrollü GPS/DOM testi ve mevcut rota/yakıt/gezinme AppTest scriptleri geçti. Rota 64,37911378355338 / 39,22031396657271 km olarak kaldı. Kullanıcı kayıt SHA256 özeti teslim başlangıcındaki `480c1345c5625b361a9dab892e0063e91f9db1aa4574ac64ff81ed1d6d014971` ile aynı. `node --test` bu komut ortamında child-process EPERM verdi; aynı testler alt süreç açmadan `node tests/citizen_gps.test.js` ile geçti. Başarılı kontroller gereksiz tekrarlanmadı.

Sınırlar: Supabase Storage ve metadata INSERT'i atomik değildir. Fotoğraf yüklenip kayıt başarısızsa sahte başarı verilmez; referans kimliğiyle yönetici kontrolü istenir, yetim fotoğrafı yönetici temizler. Anonim silme veya ayrıcalıklı anahtar açılmaz. Kamuya açılmadan önce oran/kötüye kullanım kontrolü gerekir; konum sahteciliği ve GPS doğruluğu garanti edilemez. Ana uygulamaya otomatik aktarım/moderasyon arayüzü kapsamda yoktur.

### Sonraki kontrollü genişletme — yönetici vatandaş bildirimleri

Bu dalda `citizen_admin.py` ve `app.py` içindeki **Vatandaş Bildirimleri** bölümü eklendi. Sunucu tarafı yönetici anahtarıyla `pending_review` kayıtlarını ve özel bucket fotoğraflarını okur; **Görüntü analizine aktar** düğmesi fotoğrafı mevcut Streamlit oturumuna geçirir. Ana yerel gözlem dosyasına otomatik kopyalama, konum taşıma veya denize snap yapılmaz. `[supabase] url` ve `SUPABASE_SERVICE_ROLE_KEY` yoksa bölüm açık kurulum mesajı verir. Yönetici anahtarı yalnız Streamlit sürecinde kalır.

Vatandaş Leaflet döşemesi API anahtarı istemeyen CARTO basemap'ine ve OSM/CARTO attribution'ına geçirildi. `tileerror` durumunda yalnız uyarı gösterilir; GPS ve manuel nokta seçimi çalışmaya devam eder. Tarayıcıdaki gerçek `pending_review` kaydının yönetici bölümünde görünmesi, bu çalışma ortamında service-role anahtarı olmadığı için canlı olarak tekrar edilmedi; Dashboard'da yalnızca sunucu yöneticisi anahtarını ekledikten sonra **Vatandaş Bildirimleri → Pending bildirimleri yenile** ile kontrol edin.

## Çalıştırma

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Yerel model `models/grounding-dino-tiny`, kara verisi `data/ne_10m_land.zip` altında olmalı. `.venv`, model, ZIP, yerel fotoğraflar ve kullanıcı kayıtları Git dışında tutulur. `EcoPrune` klasörüne dokunmayın. Dal `kahveotagii`, origin `https://github.com/betlincel/-aqualitter-ai.git`; teslim bağlantısı: [kahveotagii](https://github.com/betlincel/-aqualitter-ai/tree/kahveotagii). Uyarlama öncesi çalışan proje ve tasarım kaynakları **9d90706** koruma commit'indedir. Bu teslim güncellemesi arayüz dosyalarını, tema ayarını, uyarlanmış testleri ve tarayıcı doğrulama belgelerini aynı dalda kaydeder. Dal/remote değişikliği ve force push kullanılmaz.

## Arayüz ve durum sürekliliği

- `.streamlit/config.toml` koyu lacivert/yeşil yerel temayı, `ui_shell.py` sol menü ve kart stillerini tanımlar. Yeni frontend veya API yok. Stitch HTML'sindeki scriptler, sabit telemetri/sensör/filo sayıları ve sertifikasyon ifadeleri kullanılmaz.
- Menü: Genel Bakış / Görüntü Analizi / Gözlem Haritası / Temizlik Rotası / Çevresel Etki. Sayfalar `app.py` içindeki `render_*_page` fonksiyonlarıdır. Uzun model/kıyı/emisyon yöntemleri ve ham aday ayrıntıları açılır bölümlere taşındı.
- `preserve_ui_values()` etkin olmayan sayfaların açık widget anahtarlarını Streamlit temizliğinden korur. Tetikleyici butonlar ve file-uploader nesneleri buna dahil edilmez. Fotoğraf baytları/adı `active_photo` içinde yalnızca oturumda saklanır; dosya seçici boş görünse de fotoğraf kartı ve analiz geri gelir. `Fotoğrafı kaldır` yeni uploader anahtarıyla seçimi temizler. Restart/yeni oturumda geçici durum sıfırlanır.
- `route_snapshot` yalnızca başarılı plan özetidir; girdi/kayıt/kara verisi/ayarlara bağlı SHA256 imzasıyla kullanılır. Menü geçişi planı korur. Değişen girdi veya kaynakta eski kartlar/tahminler kullanılmaz. Yakıt tahmini saklanmaz, güncel tüketimden hesaplanır.
- Genel Bakış kartları kullanıcı kayıtlarından ve son geçerli hesaptan beslenir; hazır demo sayıları gözlem/nesne kartlarına katılmaz. Hesap yoksa `Henüz hesaplanmadı` görünür. Gerçek/senaryo ve tahmini etiketleri korunur.
- İki rota haritasına aynı birleşik `fit_bounds`, 40 piksel dolgu ve `max_zoom=13` uygulanır; aynı yüksekliktedir. Yön okları bacak başına birdir, ziyaret numaraları büyütülmüştür. Folium geometrileri ve mesafe hesabı korunur.

## Yakıt ve CO₂ yöntemi

- `fuel_estimates.py`: km / 1.852 → deniz mili; deniz mili × L/deniz mili → yakıt L; yakıt × kg CO₂/L → kg CO₂. Ara değerler yuvarlanmaz. Fark mevcut − önerilen olarak hesaplanır.
- [US EPA 2025, 15 Ocak, Tablo 2 sayfa 2](https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf#page=2): Diesel Fuel = 10,21 kg CO₂/ABD galonu. [NIST Handbook 130 (2025), VI §2.6.1](https://www.nist.gov/document/2025-nist-handbook-130-vi): ABD galonu = 3,785411784 L. Katsayı kodda bölünür: yaklaşık 2,6971966545766954 kg CO₂/L.
- Yalnızca petrol kökenli dizelin doğrudan yanma CO₂'si. Yaşam döngüsü, CH₄/N₂O ve CO₂e dahil değil. Genel yakıt katsayısı tekneye özgü ölçüm olarak sunulmaz.
- `app.py` yalnızca güncel başarılı plan varsa Çevresel Etki bölümünde tüketim alanını ve metodolojiyi gösterir. Tüketim başlangıçta boş; hazır varsayım yok. Girilen değer iki rotada sabittir. Hız, akıntı, yük ve toplama tüketimi modellenmez.
- Sonuçlar saklanmaz. Tüketim/rota değişince yeniden hesaplanır; boş/geçersiz tüketim, rota hatası veya ziyaret seçimi kaldırıldığında eski tahminler gösterilmez. Sonlu, pozitif tüketim ve katsayı; sonlu, negatif olmayan mesafe gerekir. Taşma hata olarak gösterilir.

## Denenenler

22 hesap/rota testi ve gerçek yerel ZIP ile tam Streamlit AppTest akışları geçti. Kontroller: birimler, tam hassasiyet, eşit rotalarda sıfır fark, geçersiz girdiler, değişen tüketimin yenilenmesi ve hata/boş rota sonrası sonuçların kaldırılması. İki Folium haritasının 14 çizgi bacağı mesafelerle eşleşiyor, ortak sınırlar tüm noktaları kapsıyor ve oklar tekrar edilmiyor. Beş bölüm arasında fotoğraf/analiz, ret/etiket kararı, iki kontrollü harita tıklaması, tarih, rota ve tüketim korunuyor. Gezinme testi sentetik ve açıkça etiketli test fixture'ı kullanır; yeni inference iddiası yoktur.

### Kullanıcı tarafından gerçek tarayıcıda doğrulanan teslim

31 Ekim 2026 teslimi için kullanıcı, tasarım uyarlamasından sonra şu kontrollerin geçtiğini bildirdi:

- Beş bölümlü arayüz açılıyor ve menüler çalışıyor; model kutuları ve inceleme kartları görünüyor.
- Dört doğru nesne onaylandı; balıktaki yanlış `food wrapper` adayı reddedildi ve ret kararı menüler arasında korundu.
- Gözlem Haritası mevcut dört onaylı nesneli kaydı gösteriyor.
- Altı senaryo noktasının mevcut/önerilen mesafeleri 64,38 / 39,22 km; fark 25,16 km.
- 2 L/deniz mili **senaryo tüketimiyle** mevcut/önerilen yakıt 69,52 / 42,35 L; tahmini doğrudan egzoz CO₂ farkı 73,28 kg.
- Rota ve tahmini CO₂ değerleri Genel Bakış kartlarına doğru taşınıyor.

Önceki yakıt tarayıcı kontrolünde tüketim 2→1 değişince sonuçların yarıya inmesi ve alan temizlenince eski sonuçların kaldırılması da doğrulanmıştı. Bu kullanıcı tarayıcı doğrulamaları, kontrollü AppTest ve sentetik gezinme fixture'ından ayrıdır. Tek kullanıcı fotoğrafındaki sonuçlar genel model başarımı veya bilimsel kirlilik ölçümü olarak sunulmaz. Yeni özellik/algoritma değişikliği bu teslim işinin kapsamı değildir.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe tests\verify_fuel_streamlit.py
.\.venv\Scripts\python.exe tests\verify_demo_streamlit.py
.\.venv\Scripts\python.exe tests\verify_navigation_streamlit.py
```

Batı→batı, F→B→D→A→C→E mevcut sıra: 64,37911378355338 km; önerilen F→E→D→C→B→A: 39,22031396657271 km. **2 L/deniz mili yalnızca senaryo varsayımı** ile 69,52 / 42,35 L ve 187,52 / 114,24 kg CO₂; fark 27,17 L ve 73,28 kg CO₂. Sabit tasarruf yüzdesi yok.

Kullanıcı gözlem dosyası bu teslimde değiştirilmez ve Git'e eklenmez. Kullanıcının son tarayıcı incelemesinden sonraki yerel dosyanın teslim başlangıcı SHA256 özeti: `480c1345c5625b361a9dab892e0063e91f9db1aa4574ac64ff81ed1d6d014971`. Gerçek ZIP SHA256: `e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc`. `.gitignore` bu dosyaları ve model/ortam/yüklemeleri dışarıda tutar; mevcut izlenen dosyalarda bu yerel kaynaklar yoktur. Natural Earth genelleştirilmiş 1:10.000.000 veridir; tamponla yapılan kontrol seyir güvenliği doğrulaması değildir. Nesne sayısı atık kg'sine dönüştürülmez. Yeni kurulum için model ve ZIP'i README'deki resmî adreslerden ayrıca hazırlamak gerekir.
