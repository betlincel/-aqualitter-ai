# AquaLitter çalışma devri — 30 Ekim 2026

Görüntü analizi, kullanıcı incelemesi, konum/gözlem kayıtları ve gerçek Natural Earth maskesiyle denetlenen altı noktalı deniz rota demosu mevcut. Son ekleme, başarılı rota sonuçlarından **tahmini dizel yakıtı ve egzoz CO₂ karşılaştırmasıdır**. Rota algoritması, kara denetimi ve 1 km tampon bu eklemede değiştirilmedi.

## Çalıştırma

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Yerel model `models/grounding-dino-tiny`, kara verisi `data/ne_10m_land.zip` altında olmalı. `.venv`, model, ZIP ve kullanıcı kayıtları Git dışında tutulur. `EcoPrune` klasörüne dokunmayın. Dal `kahveotagii`, origin `https://github.com/betlincel/-aqualitter-ai.git`; push yapılmadı. Önceden kalan değişiklikler dahil çalışma ağacı henüz commit edilmemiştir.

## Yakıt ve CO₂ yöntemi

- `fuel_estimates.py`: km / 1.852 → deniz mili; deniz mili × L/deniz mili → yakıt L; yakıt × kg CO₂/L → kg CO₂. Ara değerler yuvarlanmaz. Fark mevcut − önerilen olarak hesaplanır.
- [US EPA 2025, 15 Ocak, Tablo 2 sayfa 2](https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf#page=2): Diesel Fuel = 10,21 kg CO₂/ABD galonu. [NIST Handbook 130 (2025), VI §2.6.1](https://www.nist.gov/document/2025-nist-handbook-130-vi): ABD galonu = 3,785411784 L. Katsayı kodda bölünür: yaklaşık 2,6971966545766954 kg CO₂/L.
- Yalnızca petrol kökenli dizelin doğrudan yanma CO₂'si. Yaşam döngüsü, CH₄/N₂O ve CO₂e dahil değil. Genel yakıt katsayısı tekneye özgü ölçüm olarak sunulmaz.
- `app.py` yalnızca başarılı rota dalında tüketim alanını ve metodolojiyi gösterir. Tüketim başlangıçta boş; hazır varsayım yok. Girilen değer iki rotada sabittir. Hız, akıntı, yük ve toplama tüketimi modellenmez.
- Sonuçlar saklanmaz. Tüketim/rota değişince yeniden hesaplanır; boş/geçersiz tüketim, rota hatası veya ziyaret seçimi kaldırıldığında eski tahminler gösterilmez. Sonlu, pozitif tüketim ve katsayı; sonlu, negatif olmayan mesafe gerekir. Taşma hata olarak gösterilir.

## Denenenler

Beş hesap testi ve gerçek yerel ZIP ile tam Streamlit AppTest akışı geçti. Kontroller: birimler, tam hassasiyet, eşit rotalarda sıfır fark, geçersiz girdiler, değişen tüketimin yenilenmesi ve hata/boş rota sonrası sonuçların kaldırılması. Yeni yakıt arayüzü gerçek tarayıcıda henüz doğrulanmadı. Önceki altı noktalı rota mesafeleri kullanıcı tarafından tarayıcıda doğrulanmıştı.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_fuel_estimates.py"
.\.venv\Scripts\python.exe tests\verify_fuel_streamlit.py
```

Batı→batı, F→B→D→A→C→E mevcut sıra: 64,37911378355338 km; önerilen F→E→D→C→B→A: 39,22031396657271 km. **2 L/deniz mili yalnızca senaryo varsayımı** ile 69,52 / 42,35 L ve 187,52 / 114,24 kg CO₂; fark 27,17 L ve 73,28 kg CO₂. Sabit tasarruf yüzdesi yok.

Kullanıcı gözlem dosyası test verisi olarak değiştirilmedi. SHA256: `af163a7b8685c3559329a5590edf67936fe0c9f8110d8e42c9ae57fdd1d83875`. Gerçek ZIP SHA256: `e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc`. Natural Earth genelleştirilmiş 1:10.000.000 veridir; tamponla yapılan kontrol seyir güvenliği doğrulaması değildir. Nesne sayısı atık kg'sine dönüştürülmez.
