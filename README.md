# AquaLitter

Yeşil Gelecek Hackathonu için görüntülerden deniz/kıyı atığı gözlemleri oluşturma, haritalama ve temizlik tekneleri için rota/etki karşılaştırması hedefleniyor. Bu ilk teknik adım yalnızca tek görüntüde nesne tespit akışını doğrulamaya yöneliktir. Kara ulaşımı planlaması bu ürün kapsamına dahil değildir.

## Görüntü analizi denemesi

Arayüz, tek bir fotoğrafta aday kutuları üretmek için **Grounding DINO Tiny** kullanır. Bu, genel amaçlı, açık kelimeli bir nesne tespit modelidir; atık veya kıyı fotoğraflarına özel eğitilmemiştir. Aranan İngilizce ifadeler: `plastic bottle`, `plastic bag`, `beverage can`, `paper cup`, `food wrapper`, `litter`. Bunlar modelin sabit sınıf listesi değildir; kullanıcı isteminden eşleşen metinlerdir. Sonuçlar atık tespit başarım kanıtı veya doğruluk garantisi sayılmaz. Kullanıcı görüntüdeki adayları doğrulamalıdır.

Resmî [Hugging Face model kartı ve dosyaları](https://huggingface.co/IDEA-Research/grounding-dino-tiny) Apache-2.0 lisansı bildiriyor; resmî [GroundingDINO kod deposu](https://github.com/IDEA-Research/GroundingDINO) da Apache-2.0 lisanslıdır. Model deposunda yaklaşık 689 MB `model.safetensors` ve işlemci/tokenizer yapılandırma dosyaları vardır. Aynı ağırlığın `pytorch_model.bin` kopyası da depoda bulunur; aşağıdaki indirme yalnızca `safetensors` dosyasını alır. Ücretli servis veya API anahtarı kullanılmaz.

### Model dosyalarını indirme

Uygulama modeli yalnızca şu yerel klasörden ve ağ isteği yapmadan yükler: `models/grounding-dino-tiny`. Normal Windows PowerShell'de depo köküne geçip Hugging Face'in desteklenen CLI indirme komutunu bir kez çalıştırın:

```powershell
.\.venv\Scripts\hf.exe download IDEA-Research/grounding-dino-tiny --local-dir models/grounding-dino-tiny --include "*.json" "*.txt" model.safetensors --exclude pytorch_model.bin
```

İşlem bittikten sonra klasörde en az şu dosyaları doğrulayın: `config.json`, `model.safetensors`, `preprocessor_config.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.txt`. İndirme yarıda kesilirse Hugging Face komutunu kullanıcı normal ağ erişiminde yeniden çalıştırabilir; uygulama eksik dosyaları “tespit yok” olarak göstermez. TLS/güvenlik denetimlerini kapatmayın ve ayna kullanmayın.

Codex komut ortamındaki önceki indirme denemesi `HTTP_PROXY`/`HTTPS_PROXY` değişkenlerinin `http://127.0.0.1:9` proxy bağlantısı `WinError 10061` ile reddedildiği için tamamlanamamıştı. Kullanıcı modeli daha sonra resmî yöntemle `models/grounding-dino-tiny` klasörüne indirdi; bu klasör ve ağırlıklar Git dışında kalır.

### İlk örnek ve test durumu

`data/sample_coco_000000039769.jpg`, model kartındaki örnek akışla ilişkili COCO val2017 kedi/uzaktan kumanda görüntüsüdür; görsel COCO'nun [CC BY 4.0 kullanım koşullarına](https://cocodataset.org/#termsofuse) tabidir. Model 30 Ekim 2026'da yerel CPU'da yüklendi ve örnek üzerinde teknik inference tamamlandı. Uygulamanın atık istemi 640×480 görüntüde `plastic bag` için 0.3169 puanlı bir aday kutu döndürdü (piksel kutusu: `7, 45, 224, 139`); bu, kedi/uzaktan kumanda fotoğrafındaki yanlış eşleşmedir ve genel model sınırlamasını gösterir. Model kartındaki `a cat. a remote control.` kontrol istemi dört kutu döndürdü. Bu örnek kıyı fotoğrafı veya atık başarım testi değildir. Gerçek kıyı fotoğrafı testi bekliyor.

Uygulama dosya okuma, model yükleme ve inference hatalarını ayrı gösterir. “Bu görüntüde modelin kapsamına giren atık tespit edilmedi” metni yalnızca model başarıyla yüklendikten ve inference tamamlandıktan sonra sıfır sonuç dönmesi halinde gösterilir. Fotoğraftan konum, kilogram, gerçek alan (m²) veya doğrulanmamış kirlilik yüzdesi üretilmez. Kullanıcı yüklemeleri diske kaydedilmez; gözlem konumu kullanıcı tarafından ayrıca seçilir.

### İnsan incelemesi ve sonraki aşama kaydı

Ham model ifadeleri ve her ham kutu ayrı tabloda korunur. Yalnızca özgün görüntü piksel koordinatları tamamen aynı olan kutular inceleme için tek aday grubunda gösterilir; gruptaki bütün model ifade varyantları seçilebilir. Farklı koordinatlı adaylar sınıf adına veya kutu örtüşmesine göre bastırılmaz/birleştirilmez. Kullanıcı her adayı `Bekliyor`, `Onayla` ya da `Reddet` olarak işaretler; yalnızca onaylananlar “Kullanıcı tarafından onaylanan tespitler” bölümüne kaydedilir.

Onaylı tespitler tek fotoğraf başına tek gözlem kaydında gruplanır. Kararlar aynı fotoğrafta tekrar kaydedilirse yeni nokta açılmaz; onaylı nesne listesi var olan gözlemde güncellenir. Eski düz tespit kayıtları fotoğraf SHA-256 özetiyle birleştirilir; bilinmeyen tarih, konum ve kayıt türü boş/belirsiz kalır.

## Konum ve kirlilik gözlem haritası

Harita Trabzon kıyılarına odaklanır. Kullanıcı kaydı `Gerçek gözlem` veya `Senaryo` olarak sınıflandırır; tarih girer ve konumu haritada tıklayarak ya da enlem-boylam yazarak belirtir. Koordinatlar aralık dışındaysa kaydetme reddedilir. Tarihin kaynağı kullanıcı girdisi, konum kaynağı ise `map_click` veya `manual_coordinates` olarak saklanır. Fotoğrafın piksel kutuları hiçbir aşamada coğrafi koordinat sayılmaz.

Harita tıklama etkileşimi MIT lisanslı [streamlit-folium](https://github.com/randyzwitch/streamlit-folium) bileşenini kullanır; uygulama bağımlılığı `requirements.txt` içinde yer alır. Harita zeminindeki OpenStreetMap döşemeleri tarayıcıdan çevrim içi yüklenir.

Harita gerçek gözlemleri ve senaryo noktalarını katman seçimiyle ayırır. Turuncu sabit örnek noktaları yalnızca harita arayüzünü göstermek için kullanılan açık senaryo verisidir; gerçek kıyı gözlemi değildir. Nokta ayrıntısında onaylı nesne sayısı ve tür dağılımı yer alır; bunlar kg veya fiziksel yoğunluk ölçüsü değildir. Harita döşemelerinin görüntülenmesi için tarayıcıda internet erişimi gerekir.

Kayıtlar fotoğrafı içermeyen yerel `data/confirmed_observations.json` dosyasına yazılır ve uygulamadan JSON olarak indirilebilir. Şema 2 her fotoğraf için tek `observation_id`, tarih, kayıt türü, kullanıcı kaynaklı konum ve bu fotoğrafa bağlı onaylı nesneleri taşır. Dosya `.gitignore` kapsamındaki `data/` klasöründe kalır. Coğrafi koordinat fotoğraftan çıkarılmaz.

## Windows 11 / Python 3.12

PowerShell'i depo klasöründe açın:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ardından yukarıdaki model dosyalarını indirme komutunu çalıştırıp uygulamayı başlatın:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Tarayıcıda Streamlit'in yazdığı yerel adresi açın.

## Sınırlar ve kapsam

- Bu prototipte kıyı/atık verisi üzerinde ölçülmüş başarı iddiası yoktur; genel açık-kelime model yanlış eşleşme yapabilir veya nesneleri kaçırabilir.
- Güven puanı modelin eşleşme puanıdır, doğruluk garantisi değildir.
- Rota planı yalnızca yerel kara maskesiyle doğrulanmış erişilebilir bağlantılarda gösterilir. Kullanıcı tüketim girerse mesafeden tahmini dizel yakıtı ve egzoz CO₂'si hesaplanır; yöntem ve sınırlar aşağıdadır.
- `.venv`, model dosyaları, model önbellekleri ve kullanıcı fotoğrafları Git dışında tutulur.

## Deniz temizligi rota plani

Rota bolumunde kayit turu ayri secilir. Yalnizca konumu ve en az bir onayli tespiti olan gozlemler secilebilir. Gercek ve senaryo kayitlari ayni planda karistirilmaz. Kullanici baslangic/donus noktasini ve mevcut ziyaret sirasini secer; onerilen sira ayni noktalari ve uclari korur. Mesafe ekranda cizilen koridor segmentleri boyunca Haversine ile hesaplanip km ve deniz mili olarak gosterilir. Sabit tasarruf yüzdesi üretilmez; nesne sayısı atık kg'sine dönüştürülmez. Kullanıcı tüketim girerse aşağıdaki mesafe tabanlı yakıt/CO₂ tahmini gösterilir.

### Kiyi verisi ve indirme

Kara kesisimi icin resmi Natural Earth 1:10m kara poligonlari ZIP'i gerekir. Resmi [indirme sayfasi](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/) ve dogrudan dosya adresi: <https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip>. Veri Natural Earth [kullanim kosullarina](https://www.naturalearthdata.com/about/terms-of-use/) gore kamu malidir. Indirme boyutu yaklasik 3.12 MB'dir.

PowerShell'de depo klasorunde ZIP'i su hedefe indirin:

```powershell
New-Item -ItemType Directory -Force .\data | Out-Null
Invoke-WebRequest -Uri "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip" -OutFile ".\data\ne_10m_land.zip"
Get-FileHash ".\data\ne_10m_land.zip" -Algorithm SHA256
```

Uygulama ZIP icindeki WGS84 `.shp` kara poligonunu dogrudan okur; dosyanin yeri `data/ne_10m_land.zip` olmalidir. `data/` Git disinda kalir. Dosya yoksa, bozuksa veya Trabzon sinirinda poligon icermiyorsa rota basarili sayilmaz.

### Cozunurluk ve sinirlar

Veri Trabzon icin 40.98-41.08 derece kuzey, 39.65-39.86 derece dogu calisma sinirinda filtrelenir. Her gozlem noktasi ve cizilecek baglanti kara kesisimi ve 1 km kiyi tamponu acisindan denetlenir. Hazir deniz koridoru, demo tekne noktalariyla secilen gozlemler arasinda 41.045 derece kuzeydeki sabit acik deniz hattini kullanir; koordinatlar tasinmaz. Baglanti denetimden gecmezse nedeni gosterilir. Tekrar gecilen baglantilar kesik cizgi ve yon oklariyla ayrilir.

Natural Earth 1:10m, 1:10,000,000 olcekli genellestirilmis haritacilik verisidir ve tanimi buyuk adalari kapsar. Kucuk kayalik, mendirek veya guncel kiyi degisimlerini garantiyle gostermez. Bu cozumunurluk kiyidaki yakin tekne kullanimi veya seyir guvenligi icin yeterli degildir; 1 km tampon da guvenlik teminati degildir. Katman yalnizca kaba kara/kiyi cakisma elemesi ve prototip senaryo rotalari icindir. OpenStreetMap dosemesi sadece gorsel arka plandir, vektor/rota kaynagi degildir.

Onayli kullanici gozlemleri, gercek ve senaryo ayrimi korunarak aday olur. Nokta kara icindeyse, kiyi tamponundaysa, sinir disindaysa veya koridor baglantilari kara ile kesisiyorsa plan durdurulur ve neden bildirilir; konum tasinmaz. Rota optimizeri en fazla 6 ziyaret noktasini dener. Gerçek deniz haritası, akıntı, sığlık, tekne kısıtları ve navigasyon kapsam dışıdır; tahmini yakıt/CO₂ hesabının varsayımları aşağıdadır.

### Altı noktalı başarılı deniz senaryosu — 30 Ekim 2026

Hazır demo noktaları `marine_routes.py` içinde tek kaynaktan tanımlanır; gözlem haritası ve rota planlayıcısı aynı koordinatları kullanır. Bunlar **temsili senaryo noktalarıdır**, fotoğraftan çıkarılan veya sahada ölçülen konumlar değildir. Demo kayıtlarındaki birer `litter` girdisi de yalnızca senaryo yer tutucusudur; gerçek model çıktısı, onaylanmış fotoğraf tespiti, kg veya yoğunluk ölçümü değildir. Kullanıcının `data/confirmed_observations.json` kayıtları bu güncellemede değiştirilmemiştir.

| Senaryo | Enlem | Boylam |
| --- | ---: | ---: |
| A | 41.0350 | 39.7050 |
| B | 41.0550 | 39.7300 |
| C | 41.0400 | 39.7550 |
| D | 41.0650 | 39.7800 |
| E | 41.0380 | 39.8050 |
| F | 41.0600 | 39.8350 |

Batı tekne noktası `(41.0450, 39.6900)`, doğu tekne noktası `(41.0450, 39.8200)` olarak kalır. Yerel gerçek ZIP ile altı ziyaret ve iki tekne noktası, aralarındaki 28 bağlantının tamamı (56 yönlü geometri) mevcut kara kontrolü ve **1 km tamponuyla** test edilmiştir. Bu denetim, yukarıda açıklanan genelleştirilmiş veri sınırları içinde kaba elemedir; seyir güvenliği onayı değildir. Doğrulanan ZIP SHA256: `e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc`.

Uygulamada `Senaryo` türünü, başlangıç ve dönüş için `batı` noktasını, A–F ziyaretlerinin tümünü ve mevcut sıra olarak **F → B → D → A → C → E** seçin. Bu girdiler için ölçülen sonuç:

| Rota | Ziyaret sırası | km | Deniz mili |
| --- | --- | ---: | ---: |
| Mevcut | F → B → D → A → C → E | 64,3791 | 34,7619 |
| Önerilen | F → E → D → C → B → A | 39,2203 | 21,1773 |

Mesafe farkı **25,1588 km** olarak hesaplanır. Aynı uzunluktaki başka sıralar da olabilir; sonuç yalnızca bu girdiler içindir, sabit tasarruf oranı değildir. İki rota da altı ziyaretin her birini bir kez içerir ve batıya döner. Haritalara gerçekten aktarılan yedişer Folium çizgisinin Haversine toplamları, hesaplanan mesafelerle `1e-9 km` toleransında eşleşmiştir. Önceki geçersiz A konumu `(41.0080, 39.7200)` testte ayrıca tutulur ve kara/kıyı nedeniyle reddedilmeye devam eder.

Tam uygulama `Streamlit AppTest` ile, ilk turda altı ziyaret ve sıra oturum durumuna verilerek çalıştırıldı: ilk tam script turu **7,59 sn**, aynı girdilerle önbellekli tekrar turu **0,63 sn**. İlk süre uygulama içe aktarımlarını, gerçek ZIP'in hazırlanmasını, rota karşılaştırmasını ve iki haritanın üretilmesini içerir. Yüklenme göstergesi başarıda `complete` durumuyla sonlandı. Bu ölçümler kontrollü tam uygulama çalıştırıcısına aittir; tarayıcı ağ/çizim süresi veya görsel tarayıcı doğrulaması olarak sunulmaz.

Doğrulama komutları (yerel gerçek ZIP gereklidir; testler indirme yapmaz):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*routes.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_real_zip_scenario.py"
.\.venv\Scripts\python.exe tests\verify_demo_streamlit.py
```

Gerçek ZIP entegrasyon testleri dosya yoksa açık bir atlama nedeni bildirir; bu durum başarılı kara denetimi sayılmaz. Tam uygulama doğrulama komutu dosyayı zorunlu tutar ve ZIP/kullanıcı kayıt dosyası özetlerinin değişmediğini de denetler. Daha önce açık kalmış Streamlit sürecinde eski modül veya önbellek kullanılıyorsa süreci durdurup aynı `.venv` ile yeniden başlatın.

### Tahmini yakıt ve egzoz CO₂ karşılaştırması

Başarılı rota karşılaştırmasında tekne tüketimi **L/deniz mili** olarak girilir. Alan başlangıçta boştur; hazır tekne tüketimi veya otomatik örnek değer kullanılmaz. İki rotada aynı sabit tüketim varsayılır. Hız, akıntı, yük, bekleme ve atık toplama sırasında tüketim modellenmez. Sonuçlar ölçüm değil tahmindir.

```text
deniz mili = km / 1,852
yakıt (L) = deniz mili × tüketim (L/deniz mili)
CO₂ (kg) = yakıt (L) × emisyon katsayısı (kg CO₂/L)
fark = mevcut − önerilen
```

Katsayı, [US EPA GHG Emission Factors Hub 2025, Tablo 2, sayfa 2](https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf#page=2), **15 Ocak 2025**, `Diesel Fuel` satırındaki **10,21 kg CO₂/ABD galonu** değeridir. [NIST Handbook 130 (2025), VI §2.6.1](https://www.nist.gov/document/2025-nist-handbook-130-vi) dönüşümüyle **1 ABD galonu = 3,785411784 L**; katsayı `10.21 / 3.785411784` olarak, yaklaşık **2,6971966545766954 kg CO₂/L** kullanılır. Bu genel petrol kökenli dizel yakma katsayısı tekneye özgü ölçüm değildir. Kaynak, tarih, birim dönüşümü ve kapsam uygulamanın metodoloji bölümünde de gösterilir.

Kapsam yalnızca doğrudan yakıt yanması/egzoz CO₂'sidir. Yakıtın üretimi ve taşınması gibi yaşam döngüsü emisyonları ile CH₄ ve N₂O dahil değildir; sonuç CO₂e değildir. Hesap mevcut yuvarlanmamış rota mesafelerini ve katsayının tam bölümünü kullanır; yalnızca ekrandaki değerler iki ondalık basamağa yuvarlanır.

**Yalnızca senaryo varsayımı olarak 2 L/deniz mili** girildiğinde, altı noktalı batı→batı örneğinin mevcut rotası 69,52 L / 187,52 kg CO₂; önerilen rotası 42,35 L / 114,24 kg CO₂ olur. Hesaplanan fark 27,17 L / 73,28 kg CO₂'dır. Bu tüketim bir tekne ölçümü değildir ve uygulamaya varsayılan olarak atanmaz.

Tüketim sonlu ve sıfırdan büyük olmalıdır. Boş giriş, geçersiz giriş, sayısal taşma, rota hatası veya ziyaret seçiminin kaldırılması durumunda tahmin gösterilmez. Hesap sonuçları oturumda saklanmaz; her Streamlit turunda o anki başarılı rota ve tüketimden yeniden üretilir. Eşit rotalarda fark sıfırdır; negatif fark varsa işareti korunur.

Doğrulama (30 Ekim 2026): beş hesap testi ile km/deniz mili, litre ve CO₂ dönüşümü, tam hassasiyet, sıfır fark, negatif/boş/sonlu olmayan girdiler ve taşma denetlendi. Gerçek ZIP kullanan tam Streamlit AppTest akışında boş giriş, 2→3 tüketim değişikliği, eşit rota, sıfır giriş, alanın temizlenmesi, rota hatası ve ziyaret kaldırıldığında eski tahminlerin kalmaması geçti. Kullanıcı kayıt dosyasının SHA256 özeti değişmedi. Bu yeni bölüm için gerçek tarayıcı testi yapılmadı.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_fuel_estimates.py"
.\.venv\Scripts\python.exe tests\verify_fuel_streamlit.py
```
