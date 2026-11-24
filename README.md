# Documents Intelligence Agent

E-posta, webhook veya Telegram'dan gelen faturaları okuyan, kontrol eden,
şüpheli olanları onaya gönderen ve sonucu kaydeden bir **n8n** otomasyonu.

Okuma ve kontrol işi mevcut servislerde kalır, n8n bunları birbirine bağlar:

| Parça | Görevi |
|---|---|
| **n8n** | Tetikleyiciler, akış, onay mesajları, Google Sheets |
| **[scanned-doc-extractor](https://github.com/furkanbati/scanned-doc-extractor)** | PDF, görsel veya e-Fatura XML'den alanları çıkarır |
| **[enterprise-rag-assistant](https://github.com/furkanbati/enterprise-rag-assistant)** | Sözleşme ve politika belgelerinden kaynaklı cevap |
| **Postgres** | Belge kayıtları, tedarikçi listesi, hatalar, sohbet hafızası (ve n8n'in kendi verisi) |
| **Ollama** | Yerel modeller: asistan, RAG ve extractor'ın gizli modu |

## Akış

```
Webhook /fatura ─┐
Gmail eki ───────┤ (02, kimlik bilgisi eklenince)
                 ▼
          Hazırla ──► Alanları çıkar (extractor) ──► Kontrol et
                                                        │  eksik alan, KDV tutarlılığı,
                                                        │  tutar limiti, extractor kapısı
                                                        ▼
                           Tedarikçi ve mükerrer (Postgres) ──► Karar ver ──► Kayıt ekle ──► Yanıtla
                                                                                              │
                         ┌─────────────── onay gerekli mi? ───────────────────────────────────┘
                         │ evet                                       │ hayır (otomatik_onay)
                         ▼                                            ▼
        Onay mesajı ─► Telegram ─► Karar bekle (link)           Sheets satırı ─► Google Sheets
                                          │
                       Kararı kaydet ─► Karar sayfası ─► onaylandıysa ─► Sheets satırı
```

Bir fatura **otomatik onaylanır** ancak tüm kontrollerden geçerse: alanlar
okunmuş, ara toplam + KDV = toplam, toplam limitin altında, tedarikçi
`fatura.tedarikciler` listesinde ve aynı vergi no + fatura no daha önce gelmemiş.
Biri bile takılırsa kayıt `onay_bekliyor` olur ve nedenleriyle birlikte
onay/red linkleri gönderilir. Linkler n8n tarafından imzalanır ve 7 gün geçerlidir.

Her hata `99 Hata bildirimi` workflow'una düşer, `fatura.hatalar` tablosuna yazılır
ve (açıldığında) Telegram'a bildirilir.

## Kurulum

Gerekenler: Docker Desktop ve git. Extractor ve RAG servisleri kaynak koddan
build edildiği için üç repo aynı klasörde yan yana olmalı:

```powershell
git clone https://github.com/furkanbati/documents-intelligence-agent.git
```

```powershell
git clone https://github.com/furkanbati/scanned-doc-extractor.git
```

```powershell
git clone https://github.com/furkanbati/enterprise-rag-assistant.git
```

```powershell
cd documents-intelligence-agent
```

```powershell
powershell -ExecutionPolicy Bypass -File .\kurulum.ps1
```

İlk kurulumda imajlar build edilir ve modeller indirilir (asistan modeli
yaklaşık 3 GB). Bu birkaç dakikadan uzun sürebilir.

Betik sırasıyla şunları yapar:

1. `.env` yoksa oluşturur; boş gizli değerleri (veritabanı şifresi, şifreleme
   anahtarı, fatura API anahtarı, asistan şifresi) rastgele üretir. Dolu
   değerlere dokunmaz.
2. `docker compose up -d --build` ile servisleri başlatır.
3. Kimlik bilgilerini ve `workflows/` klasörünü n8n'e yükler.
4. Fatura, asistan ve hata workflow'larını yayınlar.
5. Asistan modelini hazırlar ve örnek belgeleri RAG'e yükler.

Ardından http://localhost:5678 adresini açıp yönetici hesabını oluşturun.
Betiği tekrar çalıştırmak güvenlidir; workflow'ları dosyadaki haliyle yeniden yükler.

## Erişim ve güvenlik

| Giriş noktası | Koruma |
|---|---|
| Fatura webhook'u (`/webhook/fatura`) | `X-API-Key` başlığı zorunlu (`.env`: `FATURA_API_KEY`); yoksa 403 |
| Asistan sohbet sayfası | Tarayıcı kullanıcı adı/şifre sorar (`ASISTAN_KULLANICI`, varsayılan `muhasebe`; `ASISTAN_SIFRE`) |
| Onay/red linkleri | n8n tarafından imzalı, 7 gün geçerli, tek kullanımlık |
| n8n arayüzü | n8n'in kendi yönetici hesabı |

Fatura gönderen her sistem (Gmail workflow'u, ERP, form) bu anahtarı kullanır.
Anahtar veya şifreyi değiştirmek için `.env`'de değeri değiştirip
`kurulum.ps1`'i tekrar çalıştırın.

Portlar yalnızca bu bilgisayara (`127.0.0.1`) açıktır. Sunucuya kurarken önüne
HTTPS veren bir reverse proxy (ör. Caddy) koyun; bu korumalar şifreli bağlantı
olmadan yeterli değildir.

> Türkçe Windows notu: PowerShell'in `-match` operatörü Türkçe sistemde `I`
> harfini `ı` ile eşleştirmeye çalışır ve `FATURA_API_KEY` gibi adları bulamaz.
> `kurulum.ps1` bu yüzden `-cmatch` kullanır; betiği değiştirirken buna dikkat edin.

## Deneme

`ornekler/` klasöründe iki uydurma e-Fatura var (aynı tedarikçi, farklı fatura no).

Önce anahtarı `.env`'den alın (aynı PowerShell penceresinde kalır):

```powershell
$key = ((Select-String -Path .env -Pattern '^FATURA_API_KEY=' -CaseSensitive).Line -split '=', 2)[1]
```

```powershell
curl.exe -H "X-API-Key: $key" -F file=@ornekler/efatura-153.xml http://localhost:5678/webhook/fatura
```

Tedarikçi henüz kayıtlı olmadığı için yanıt `onay_bekliyor` olur ve içinde
`linkler.onayla` / `linkler.reddet` adresleri bulunur. Birini tarayıcıda açın.
Sonra tedarikçiyi ekleyip diğer faturayı gönderin, bu sefer `otomatik_onay` gelir:

```powershell
docker compose exec postgres psql -U otomasyon -d otomasyon -c "insert into fatura.tedarikciler values ('1234567890', 'ABC Gıda Sanayi ve Ticaret A.Ş.')"
```

```powershell
curl.exe -H "X-API-Key: $key" -F file=@ornekler/efatura-154.xml http://localhost:5678/webhook/fatura
```

Kayıtları görmek için:

```powershell
docker compose exec postgres psql -U otomasyon -d otomasyon -c "select id, durum, firma, fatura_no, toplam, nedenler from fatura.belgeler order by id"
```

PDF ve görseller de aynı adrese gönderilir. Okuma modu `Hazırla` node'undaki
`profil` ayarından seçilir: `accurate` (OpenAI, `.env`'de `OPENAI_API_KEY`
gerekir), `private` (yerel model) veya boş (extractor seçer).

## Fatura asistanı (03)

Faturalar ve şirket belgeleri hakkında Türkçe soru-cevap. Sohbet sayfası:
http://localhost:5678/webhook/fatura-asistani/chat (kullanıcı adı ve şifre `.env`'de;
Telegram bağlanınca bot da aynı asistana gider).

Asistan bir n8n **AI Agent** node'udur ve üç aracı vardır:

| Araç | Ne yapar |
|---|---|
| `fatura_toplami` | Firma ve duruma göre fatura adedi ve toplam tutar |
| `fatura_listesi` | Faturaları tek tek listeler (numara, tarih, tutar, durum, onay nedeni) |
| `dokuman_sor` | Soruyu RAG servisine iletir: sözleşmeler, ödeme ve onay politikası |

Veritabanı araçları **sabit, parametreli SQL** çalıştırır. Model yalnızca firma,
tarih aralığı ve durum filtrelerini doldurur, SQL yazamaz; veri değiştiremez ve
uydurma bir sorgu çalıştıramaz. Sohbet geçmişi Postgres'te
(`asistan_sohbetleri`) tutulur; takip soruları ("bu tutar için kim onaylar?")
önceki cevabı bilir.

Örnek sorular (test edildi, CPU'da 11–70 sn):

- "ABC Gıda'dan onaylanmış faturaların toplam tutarı ne kadar?"
- "Onay bekleyen faturalar hangileri ve neden bekliyorlar?"
- "ABC Gıda ile anlaşmamızda ödeme vadesi ve erken ödeme indirimi nedir?"
- "Geçen ay Migros'a ne kadar ödedik?" (kayıt yoksa bulunamadığını söyler)
- "ABC Gıda sözleşmesinde ayçiçek yağının birim fiyatı ne kadar?" (tablodan: 1.900 TL)
- "5.353 TL'lik bir faturayı kim onaylar?" (politikadaki onay yetkileri tablosundan)

Şirket belgeleri `ornekler/belgeler/` klasöründen kurulumda bir kez yüklenir.
Müşterinin belgelerini eklemek için dosyayı bu klasöre koyup `kurulum.ps1`'i
tekrar çalıştırın (PDF, Word, HTML, Markdown, metin).

**Tablolar:** Markdown, Word ve HTML tabloları aranabilir. PDF tabloları için
`.env`'e `RAG_TABLE_STRUCTURE=true` yazın (Docling TableFormer, ilk kullanımda
yaklaşık 360 MB indirir, yükleme yavaşlar) ve belgeleri yeniden yükleyin.
Müşteri belgeleri çoğunlukla PDF olduğu için kurulumda bunu açmayı düşünün.

### Hız

Asistan CPU'da `qwen3.5:4b` ile çalışır. Ollama varsayılan olarak her çekirdeğe
bir thread açar; performans ve verimlilik çekirdeklerini karıştıran işlemcilerde
(bu makinede Intel Core Ultra 5 225H) üretim **0,35 token/sn**'ye düştü ve bir
soru 7 dakika sürdü. 8 thread ile **16 token/sn**'ye çıktı ve aynı soru 18 saniyeye
indi. Kurulum bu yüzden `qwen3.5-asistan` adında, thread sayısı ayarlı bir model
takma adı oluşturur; asistan ve RAG bunu kullanır. Başka bir makinede
`.env`'deki `OLLAMA_NUM_THREAD` değerini (genelde performans çekirdeği sayısı ile
toplam çekirdek sayısı arası) deneyip kurulumu tekrar çalıştırın.

Konteyneri `cpuset` ile çekirdeklere sabitlemek işe yaramadı (0,2 token/sn):
sanal çekirdek numaraları yavaş çekirdeklere denk gelebiliyor.

### OpenAI ile çalıştırmak

Daha hızlı ve çok adımlı sorularda daha isabetli cevap için: n8n'de asistan
workflow'unda **Model** node'unu silip yerine *OpenAI Chat Model* ekleyin ve
OpenAI kimlik bilgisi tanımlayın. RAG'in de OpenAI kullanması için `.env`'e
`OPENAI_API_KEY` ve `RAG_LLM_PROVIDER=openai` yazıp `docker compose up -d` çalıştırın.
Belgeler müşterinin sunucusundan çıkmamalıysa yerel modelde kalın.

## Müşteriye göre ayarlar

`01 Fatura işleme` içindeki **Hazırla** node'unun başında:

- `oto_onay_limiti`: bu tutarın üstündeki faturalar her zaman onaya düşer
- `telegram_chat_id`: onay mesajlarının gideceği sohbet
- `profil`, `belge_turu`: extractor'a iletilir

## Telegram, Gmail ve Google Sheets'i açmak

Bu node'lar kimlik bilgisi gerektirdiği için kapalı (disabled) gelir. Kapalıyken
akış onları atlayıp devam eder.

1. **Telegram:** @BotFather'dan bir bot oluşturun. n8n'de *Credentials → Telegram API*
   ekleyin, adı `Telegram bot` olsun. Asistanın Telegram'dan çalışması için
   `03 Fatura asistanı` içindeki *Telegram mesajı* ve *Telegram'a yanıt* node'larını açın;
   Telegram tetikleyicisi https adresi ister, bu yüzden `PUBLIC_URL` gerekir. Bota bir mesaj atın,
   `https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden `chat.id` değerini alın ve
   Hazırla'daki `telegram_chat_id` alanına yazın. Ardından *Telegram'a gönder* node'unu açın.
   Linklerin telefondan da çalışması için n8n dışarıdan erişilebilir olmalı:
   bir Cloudflare Tunnel veya ngrok adresini `.env`'deki `PUBLIC_URL`'e yazıp
   `docker compose up -d` çalıştırın.
2. **Google Sheets:** *Credentials → Google Sheets OAuth2* ekleyin. İçinde `Faturalar`
   sayfası olan bir tablo açın ve ilk satıra *Sheets satırı* node'undaki başlıkları yazın
   (`Kayıt, Fatura Tarihi, Firma, Vergi No, Fatura No, Ara Toplam, KDV, Toplam, Durum, Kaynak`).
   Tablo adresini *Google Sheets'e yaz* node'una girip node'u açın.
3. **Gmail:** *Credentials → Gmail OAuth2* ekleyin, `02 Gmail eki → fatura işleme`
   workflow'unda seçin ve yayınlayın. Okunmamış, ekli e-postaların PDF, XML ve görsel
   ekleri tek tek fatura işlemeye gönderilir.

Değişikliklerden sonra workflow'u n8n'de **Publish** edin.

## Workflow'ları düzenlemek

`workflows/*.json` dosyaları `scripts/build_workflows.py` tarafından üretilir:

```powershell
python scripts/build_workflows.py
```

Bu yol, kodu okunur halde tutmak ve sürüm kontrolüne koymak için var. n8n arayüzünde
değişiklik yapıp onu kalıcı kılmak isterseniz workflow'u arayüzden export edip
`workflows/` klasörüne yazın; o noktadan sonra betiği kullanmayın. Aynı workflow'un
iki kaynağı olmasın.

## Lisans

[MIT](LICENSE)

## Sonraki adımlar

- Telegram'a fotoğrafı atılan faturanın doğrudan işlenmesi
- Linux sunucu kurulumu: `kurulum.sh`, HTTPS (Caddy), yedekleme
- Demo videosu
