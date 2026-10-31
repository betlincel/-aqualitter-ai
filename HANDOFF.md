# AquaLitter teslim noktası — 31 Ekim 2026

Görüntü analizi, kullanıcı incelemesi, konum/gözlem kayıtları, gerçek Natural Earth maskesiyle denetlenen altı noktalı deniz rota demosu ve tahmini yakıt/egzoz CO₂ hesabı mevcut. Son değişiklik, `design/stitch` görsel referansının **beş bölümlü yerel Streamlit arayüzüne uyarlanmasıdır**. Rota algoritması, kara denetimi ve 1 km tampon korunmuştur.

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
