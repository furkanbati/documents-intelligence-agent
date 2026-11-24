"""workflows/*.json dosyalarını üretir.

n8n workflow JSON'u, Code node'larının JavaScript'ini kaçışlı tek satır olarak
tutar; elle düzenlemesi zordur. Akışı burada okunur halde tutup
`python scripts/build_workflows.py` ile yeniden üretiyoruz. n8n arayüzünde
yaptığınız değişiklikleri kalıcı kılmak isterseniz arayüzden export edin ve
bu betiği kullanmayı bırakın; ikisi birden kaynak olmasın.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "workflows"

PG = {"postgres": {"id": "pgBelgeler000001", "name": "Postgres (belgeler)"}}
TG = {"telegramApi": {"id": "telegramBot00001", "name": "Telegram bot"}}
# kurulum.ps1, .env'deki FATURA_API_KEY ve ASISTAN_SIFRE ile oluşturur.
API_ANAHTARI = {"httpHeaderAuth": {"id": "faturaApiAnahtar", "name": "Fatura API anahtarı"}}
ASISTAN_GIRISI = {"httpBasicAuth": {"id": "asistanGirisi0001", "name": "Asistan girişi"}}

FATURA_ID = "FaturaIsleme0001"
HATA_ID = "HataBildirim0099"
GMAIL_ID = "GmailFatura00002"
ASISTAN_ID = "FaturaAsistani03"


def node(name, type_, version, position, parameters, **extra):
    return {"parameters": parameters, "name": name, "type": type_, "typeVersion": version,
            "position": list(position), "id": f"{name}".replace(" ", "-").lower(), **extra}


def code(name, position, js, per_item=True, **extra):
    params = {"jsCode": js.strip() + "\n"}
    if per_item:
        params["mode"] = "runOnceForEachItem"
    return node(name, "n8n-nodes-base.code", 2, position, params, **extra)


def sql(name, position, query, replacements=None, **extra):
    options = {"queryReplacement": replacements} if replacements else {}
    return node(name, "n8n-nodes-base.postgres", 2.5, position,
                {"operation": "executeQuery", "query": query.strip(), "options": options},
                credentials=PG, **extra)


def if_(name, position, left, operation, right=None, type_="string"):
    condition = {"id": name, "leftValue": left, "operator": {"type": type_, "operation": operation}}
    if right is not None:
        condition["rightValue"] = right
    else:
        condition["operator"]["singleValue"] = True
    return node(name, "n8n-nodes-base.if", 2.2, position, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                                   "version": 2},
                       "conditions": [condition], "combinator": "and"},
        "options": {}})


def connect(*pairs):
    """(kaynak, hedef) veya (kaynak, çıkış, hedef) -> n8n connections."""

    out = {}
    for pair in pairs:
        source, index, target = pair if len(pair) == 3 else (pair[0], 0, pair[1])
        outputs = out.setdefault(source, {"main": []})["main"]
        while len(outputs) <= index:
            outputs.append([])
        outputs[index].append({"node": target, "type": "main", "index": 0})
    return out


def workflow(id_, name, nodes, connections, error_workflow=None, active=False):
    settings = {"executionOrder": "v1", "timezone": "Europe/Istanbul",
                "saveDataSuccessExecution": "all", "saveManualExecutions": True}
    if error_workflow:
        settings["errorWorkflow"] = error_workflow
    return {"id": id_, "name": name, "active": active, "nodes": nodes,
            "connections": connections, "settings": settings, "pinData": {}, "tags": []}


# --- 01 Fatura işleme ------------------------------------------------------

HAZIRLA = r"""
// ---- Ayarlar: müşteriye göre burayı değiştirin ----
const AYARLAR = {
  // '' = extractor'ın varsayılanı; 'accurate' (OpenAI) veya 'private' (yerel)
  profil: '',
  belge_turu: 'invoice',
  // Bu tutarın üstündeki faturalar her zaman onaya düşer.
  oto_onay_limiti: 10000,
  // Onay mesajlarının gideceği Telegram sohbeti (README, "Telegram").
  telegram_chat_id: '',
};

const binary = $input.item.binary || {};
const anahtarlar = Object.keys(binary);
if (!anahtarlar.length) {
  throw new Error("İstekte dosya yok: multipart/form-data ile 'file' alanında gönderin.");
}
const dosya = binary[anahtarlar[0]];
const body = $json.body || {};

return {
  json: {
    kaynak: body.kaynak || 'webhook',
    dosya_adi: dosya.fileName || anahtarlar[0],
    ayarlar: AYARLAR,
  },
  binary: { belge: dosya },
};
"""

KONTROL = r"""
// Extractor'ın sonucunu bir kayda çevirir ve kendi kontrollerini ekler.
const hazirla = $('Hazırla').item.json;
const r = $json;
const n = r.normalized || {};
const f = r.fields || {};
const ETIKET = { company: 'Firma', tax_id: 'Vergi no', invoice_number: 'Fatura no',
                 date: 'Tarih', subtotal: 'Ara toplam', tax: 'KDV', total: 'Toplam' };
const NOT = { 'not found': 'okunamadı', 'not a recognisable date': 'tarih olarak okunamadı',
              'not an amount': 'tutar olarak okunamadı' };

const nedenler = new Set();
for (const [alan, not] of Object.entries(r.review || {})) {
  nedenler.add(`${ETIKET[alan] || alan}: ${NOT[not] || not}`);
}
// Extractor'ın kendi kapısı (kalem toplamları vb.). Alan notları yukarıda.
if (r.gate && !r.gate.accepted) {
  for (const neden of r.gate.reasons || []) {
    if (!Object.keys(ETIKET).some(alan => neden.startsWith(alan + ' '))) {
      nedenler.add(`Extractor kontrolü: ${neden}`);
    }
  }
}

const sayi = v => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? null : Number(v);
const ara = sayi(n.subtotal), kdv = sayi(n.tax), toplam = sayi(n.total);
if (ara !== null && kdv !== null && toplam !== null && Math.abs(ara + kdv - toplam) > 0.05) {
  nedenler.add(`Tutarlar tutmuyor: ${ara} + ${kdv} ≠ ${toplam}`);
}
const limit = hazirla.ayarlar.oto_onay_limiti;
if (toplam !== null && toplam > limit) {
  nedenler.add(`Toplam ${toplam}, otomatik onay limitini (${limit}) aşıyor`);
}

const temiz = v => (v || '').toString().trim() || null;
const vergi_no = (f.tax_id || '').replace(/[^0-9A-Za-z]/g, '') || null;
const tarih = /^\d{4}-\d{2}-\d{2}$/.test(n.date || '') ? n.date : null;

// Satır kutuları büyük ve kayıtta işe yaramaz.
const { lines, field_lines, ...ham } = r;

return {
  json: {
    kayit: {
      kaynak: hazirla.kaynak,
      dosya_adi: hazirla.dosya_adi,
      firma: temiz(f.company),
      vergi_no,
      fatura_no: temiz(f.invoice_number),
      fatura_tarihi: tarih,
      ara_toplam: ara,
      kdv,
      toplam,
      yontem: r.method || null,
    },
    nedenler: [...nedenler],
    ham,
  },
};
"""

KARAR = r"""
// Tedarikçi ve mükerrer kontrolünün sonucunu ekler, durumu belirler.
const k = $('Kontrol et').item.json;
const nedenler = [...k.nedenler];

if (!$json.tedarikci) {
  nedenler.push(k.kayit.vergi_no
    ? `Tedarikçi kayıtlı değil (vergi no ${k.kayit.vergi_no})`
    : 'Vergi numarası okunamadı, tedarikçi doğrulanamadı');
}
if (Number($json.mukerrer) > 0) {
  nedenler.push(`Mükerrer olabilir: aynı vergi no ve fatura no ile ${$json.mukerrer} kayıt var`);
}

const durum = nedenler.length ? 'onay_bekliyor' : 'otomatik_onay';
// Bu yürütme, Wait node'unda bu adres çağrılana kadar bekler.
const base = $execution.resumeUrl;
const ek = base.includes('?') ? '&' : '?';

return {
  json: {
    ...k.kayit,
    durum,
    nedenler,
    onay_linki: durum === 'onay_bekliyor' ? base : null,
    linkler: durum === 'onay_bekliyor'
      ? { onayla: `${base}${ek}karar=onay`, reddet: `${base}${ek}karar=red` }
      : null,
    ham: k.ham,
  },
};
"""

KAYIT_EKLE = """
INSERT INTO fatura.belgeler
    (kaynak, dosya_adi, firma, vergi_no, fatura_no, fatura_tarihi,
     ara_toplam, kdv, toplam, yontem, durum, nedenler, onay_linki, ham_sonuc)
VALUES ($1, $2, $3, $4, $5, $6::date, $7::numeric, $8::numeric, $9::numeric,
        $10, $11, $12::jsonb, $13, $14::jsonb)
RETURNING *;
"""

KAYIT_PARAMS = ("={{ [$json.kaynak, $json.dosya_adi, $json.firma, $json.vergi_no, $json.fatura_no, "
                "$json.fatura_tarihi, $json.ara_toplam, $json.kdv, $json.toplam, $json.yontem, "
                "$json.durum, JSON.stringify($json.nedenler), $json.onay_linki, "
                "JSON.stringify($json.ham)] }}")

ONAY_MESAJI = r"""
const b = $json;
const linkler = $('Karar ver').item.json.linkler;
const metin = [
  `🧾 Onay bekleyen fatura #${b.id}`,
  `Firma: ${b.firma ?? '-'}`,
  `Fatura no: ${b.fatura_no ?? '-'}`,
  `Tarih: ${b.fatura_tarihi ? String(b.fatura_tarihi).slice(0, 10) : '-'}`,
  `Toplam: ${b.toplam ?? '-'}`,
  '',
  'Neden onaya düştü:',
  ...b.nedenler.map(n => `• ${n}`),
  '',
  `✅ Onayla: ${linkler.onayla}`,
  `❌ Reddet: ${linkler.reddet}`,
].join('\n');

return { json: { ...b, chat_id: $('Hazırla').item.json.ayarlar.telegram_chat_id, metin } };
"""

KARARI_OKU = r"""
// Onay linkinden gelen karar. Süre dolduysa sorgu yoktur, kayıt bekler.
const karar = ($json.query || {}).karar;
const durum = karar === 'onay' ? 'onaylandi' : karar === 'red' ? 'reddedildi' : '';
return { json: { id: $('Kayıt ekle').item.json.id, durum, karar_veren: durum ? 'onay linki' : null } };
"""

SHEETS_SATIRI = r"""
const b = $json;
return {
  json: {
    'Kayıt': b.id,
    'Fatura Tarihi': b.fatura_tarihi ? String(b.fatura_tarihi).slice(0, 10) : '',
    'Firma': b.firma ?? '',
    'Vergi No': b.vergi_no ?? '',
    'Fatura No': b.fatura_no ?? '',
    'Ara Toplam': b.ara_toplam ?? '',
    'KDV': b.kdv ?? '',
    'Toplam': b.toplam ?? '',
    'Durum': b.durum,
    'Kaynak': b.kaynak ?? '',
  },
};
"""

KARAR_SAYFASI = (
    '=<!doctype html><html lang="tr"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Fatura kararı</title></head>'
    '<body style="font-family:system-ui,sans-serif;padding:2rem;max-width:32rem;margin:auto">'
    "<h2>Fatura #{{ $json.id }} {{ $json.durum === 'onaylandi' ? 'onaylandı ✅' : 'reddedildi ❌' }}</h2>"
    "<p>Karar kaydedildi. Bu sayfayı kapatabilirsiniz.</p></body></html>"
)


def fatura_isleme():
    nodes = [
        node("Fatura geldi", "n8n-nodes-base.webhook", 2, (0, 300), {
            "httpMethod": "POST", "path": "fatura", "authentication": "headerAuth",
            "responseMode": "responseNode", "options": {}},
            credentials=API_ANAHTARI, webhookId="fatura-isleme-webhook",
            notes="X-API-Key başlığı olmayan istekler reddedilir (.env: FATURA_API_KEY)."),
        code("Hazırla", (220, 300), HAZIRLA),
        node("Alanları çıkar", "n8n-nodes-base.httpRequest", 4.2, (440, 300), {
            "method": "POST",
            "url": "http://extractor:8000/extract",
            "sendBody": True,
            "contentType": "multipart-form-data",
            "bodyParameters": {"parameters": [
                {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "belge"},
                {"name": "doctype", "value": "={{ $json.ayarlar.belge_turu }}"},
                {"name": "profile", "value": "={{ $json.ayarlar.profil }}"},
            ]},
            "options": {"timeout": 300000},
        }, retryOnFail=True, maxTries=2, waitBetweenTries=5000),
        code("Kontrol et", (660, 300), KONTROL),
        sql("Tedarikçi ve mükerrer", (880, 300), """
SELECT
    (SELECT unvan FROM fatura.tedarikciler WHERE vergi_no = $1::text) AS tedarikci,
    (SELECT count(*) FROM fatura.belgeler
      WHERE vergi_no = $1::text AND fatura_no = $2::text AND durum <> 'reddedildi')::int AS mukerrer;
""", "={{ [$json.kayit.vergi_no, $json.kayit.fatura_no] }}"),
        code("Karar ver", (1100, 300), KARAR),
        sql("Kayıt ekle", (1320, 300), KAYIT_EKLE, KAYIT_PARAMS),
        node("Yanıtla", "n8n-nodes-base.respondToWebhook", 1.1, (1540, 300), {
            "respondWith": "json",
            "responseBody": "={{ { id: $json.id, durum: $json.durum, nedenler: $json.nedenler, "
                            "firma: $json.firma, fatura_no: $json.fatura_no, toplam: $json.toplam, "
                            "linkler: $('Karar ver').item.json.linkler } }}",
            "options": {}}),
        if_("Onay gerekli mi?", (1760, 300), "={{ $json.durum }}", "equals", "onay_bekliyor"),
        code("Onay mesajı", (1980, 180), ONAY_MESAJI),
        node("Telegram'a gönder", "n8n-nodes-base.telegram", 1.2, (2200, 180), {
            "chatId": "={{ $json.chat_id }}", "text": "={{ $json.metin }}",
            "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True}},
            credentials=TG, disabled=True,
            notes="Telegram kimlik bilgisini ekleyip Hazırla'da telegram_chat_id'yi doldurunca açın."),
        node("Karar bekle", "n8n-nodes-base.wait", 1.1, (2420, 180), {
            "resume": "webhook", "httpMethod": "GET", "responseMode": "responseNode",
            "limitWaitTime": True, "limitType": "afterTimeInterval",
            "resumeAmount": 7, "resumeUnit": "days", "options": {}},
            webhookId="fatura-karar-bekle"),
        code("Kararı oku", (2640, 180), KARARI_OKU),
        if_("Karar verildi mi?", (2860, 180), "={{ $json.durum }}", "notEmpty"),
        sql("Kararı kaydet", (3080, 100), """
UPDATE fatura.belgeler
   SET durum = $2::text, karar_veren = $3::text, karar_zamani = now()
 WHERE id = $1::bigint AND durum = 'onay_bekliyor'
RETURNING *;
""", "={{ [$json.id, $json.durum, $json.karar_veren] }}"),
        node("Karar sayfası", "n8n-nodes-base.respondToWebhook", 1.1, (3300, 100), {
            "respondWith": "text", "responseBody": KARAR_SAYFASI,
            "options": {"responseHeaders": {"entries": [
                {"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}}),
        if_("Onaylandı mı?", (3520, 100), "={{ $json.durum }}", "equals", "onaylandi"),
        code("Sheets satırı", (3740, 400), SHEETS_SATIRI),
        node("Google Sheets'e yaz", "n8n-nodes-base.googleSheets", 4.5, (3960, 400), {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "url", "value": ""},
            "sheetName": {"__rl": True, "mode": "name", "value": "Faturalar"},
            "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [],
                        "schema": []},
            "options": {}},
            disabled=True,
            notes="Google kimlik bilgisini ve tablo adresini girip açın. Tabloda 'Faturalar' sayfası "
                  "ve Sheets satırı node'undaki başlıklar olmalı."),
    ]
    connections = connect(
        ("Fatura geldi", "Hazırla"),
        ("Hazırla", "Alanları çıkar"),
        ("Alanları çıkar", "Kontrol et"),
        ("Kontrol et", "Tedarikçi ve mükerrer"),
        ("Tedarikçi ve mükerrer", "Karar ver"),
        ("Karar ver", "Kayıt ekle"),
        ("Kayıt ekle", "Yanıtla"),
        ("Yanıtla", "Onay gerekli mi?"),
        ("Onay gerekli mi?", 0, "Onay mesajı"),
        ("Onay gerekli mi?", 1, "Sheets satırı"),
        ("Onay mesajı", "Telegram'a gönder"),
        ("Telegram'a gönder", "Karar bekle"),
        ("Karar bekle", "Kararı oku"),
        ("Kararı oku", "Karar verildi mi?"),
        ("Karar verildi mi?", 0, "Kararı kaydet"),
        ("Kararı kaydet", "Karar sayfası"),
        ("Karar sayfası", "Onaylandı mı?"),
        ("Onaylandı mı?", 0, "Sheets satırı"),
        ("Sheets satırı", "Google Sheets'e yaz"),
    )
    return workflow(FATURA_ID, "01 Fatura işleme", nodes, connections, error_workflow=HATA_ID)


# --- 02 Gmail -> fatura işleme ----------------------------------------------

GMAIL_EKLER = r"""
// Her ek ayrı bir belge olur; yalnızca PDF, XML ve görseller.
const UZANTILAR = /\.(pdf|xml|png|jpe?g|webp|tiff?)$/i;
const cikti = [];
for (const item of $input.all()) {
  const gonderen = item.json.from?.text || item.json.from?.value?.[0]?.address || '';
  for (const [anahtar, dosya] of Object.entries(item.binary || {})) {
    if (!UZANTILAR.test(dosya.fileName || '')) continue;
    cikti.push({ json: { kaynak: 'gmail', gonderen, konu: item.json.subject || '' },
                 binary: { belge: dosya } });
  }
}
return cikti;
"""


def gmail():
    nodes = [
        node("Yeni e-posta", "n8n-nodes-base.gmailTrigger", 1.2, (0, 300), {
            "pollTimes": {"item": [{"mode": "everyMinute"}]},
            "simple": False,
            "filters": {"q": "has:attachment -in:chats", "readStatus": "unread"},
            "options": {"downloadAttachments": True, "dataPropertyAttachmentsPrefixName": "ek_"}},
            credentials={"gmailOAuth2": {"id": "gmailHesap000001", "name": "Gmail hesabı"}}),
        code("Ekleri ayır", (220, 300), GMAIL_EKLER, per_item=False),
        node("Fatura işlemeye gönder", "n8n-nodes-base.httpRequest", 4.2, (440, 300), {
            "method": "POST",
            "url": "http://localhost:5678/webhook/fatura",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "contentType": "multipart-form-data",
            "bodyParameters": {"parameters": [
                {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "belge"},
                {"name": "kaynak", "value": "gmail"},
            ]},
            "options": {"timeout": 300000}}, credentials=API_ANAHTARI),
    ]
    connections = connect(("Yeni e-posta", "Ekleri ayır"), ("Ekleri ayır", "Fatura işlemeye gönder"))
    return workflow(GMAIL_ID, "02 Gmail eki → fatura işleme", nodes, connections, error_workflow=HATA_ID)


# --- 99 Hata bildirimi -------------------------------------------------------

HATA_OZETI = r"""
const e = $json.execution || {};
const mesaj = e.error?.message || 'Bilinmeyen hata';
const node = e.lastNodeExecuted || e.error?.node?.name || '';
const workflow = $json.workflow?.name || '';
return {
  json: {
    workflow, node, mesaj, url: e.url || null,
    metin: `⚠️ ${workflow} hata verdi\nNode: ${node}\n${mesaj}${e.url ? `\n${e.url}` : ''}`,
    chat_id: '',  // Hata mesajlarının gideceği Telegram sohbeti
  },
};
"""


def hata():
    nodes = [
        node("Hata oldu", "n8n-nodes-base.errorTrigger", 1, (0, 300), {}),
        code("Hata özeti", (220, 300), HATA_OZETI),
        sql("Hatayı kaydet", (440, 300), """
INSERT INTO fatura.hatalar (workflow, node, mesaj, yurutme_url)
VALUES ($1, $2, $3, $4) RETURNING id;
""", "={{ [$json.workflow, $json.node, $json.mesaj, $json.url] }}"),
        node("Telegram'a bildir", "n8n-nodes-base.telegram", 1.2, (660, 300), {
            "chatId": "={{ $('Hata özeti').item.json.chat_id }}",
            "text": "={{ $('Hata özeti').item.json.metin }}",
            "additionalFields": {"appendAttribution": False}},
            credentials=TG, disabled=True,
            notes="Telegram kimlik bilgisini ekleyip Hata özeti'nde chat_id'yi doldurunca açın."),
    ]
    connections = connect(("Hata oldu", "Hata özeti"), ("Hata özeti", "Hatayı kaydet"),
                          ("Hatayı kaydet", "Telegram'a bildir"))
    return workflow(HATA_ID, "99 Hata bildirimi", nodes, connections)


# --- 03 Fatura asistanı (soru-cevap) ----------------------------------------

OLLAMA = {"ollamaApi": {"id": "ollamaYerel00001", "name": "Ollama (yerel)"}}

SISTEM_MESAJI = """=Sen XYZ Market muhasebe biriminin fatura asistanısın. Bugünün tarihi {{ $now.toFormat('yyyy-MM-dd') }}.

Araçların:
- fatura_toplami: tedarikçi ve duruma göre fatura adedi ve toplam tutar. "Ne kadar", "toplam", "kaç fatura" soruları için.
- fatura_listesi: faturaları tek tek listeler (numara, tarih, tutar, durum). Belirli faturaları görmek için.
- dokuman_sor: sözleşmeler ve şirket politikaları (vade, fiyatlar, onay yetkileri, ödeme günleri, iade). Bu konularda önce bu aracı kullan.

Kurallar:
- Rakamları ve fatura bilgilerini yalnızca araç sonuçlarından ver; asla tahmin etme veya uydurma.
- Sonuçlardaki durumlar: otomatik_onay (sistem onayladı) ve onaylandi (bir kişi onayladı) ikisi de onaylanmış faturadır; onay_bekliyor bekleyen, reddedildi reddedilmiş faturadır. Onaylanmış faturalar sorulunca durum filtresine "onaylanan" ver.
- "Geçen ay", "bu yıl" gibi ifadeleri bugünün tarihine göre YYYY-AA-GG aralığına çevir.
- Tutarlar TL'dir. Cevabı kısa ve Türkçe ver. Belgeden gelen bilgide belgenin adını söyle.
- Araçlar bir şey bulamazsa bunu açıkça söyle."""

FIRMA = "$fromAI('firma', 'Firma adı veya bir parçası; tüm firmalar için boş bırak', 'string', '')"
BASLANGIC = "$fromAI('baslangic', 'Fatura tarihi başlangıcı, YYYY-AA-GG; sınır yoksa boş', 'string', '')"
BITIS = "$fromAI('bitis', 'Fatura tarihi bitişi, YYYY-AA-GG; sınır yoksa boş', 'string', '')"
# Model iş dilinde seçer: "onaylanan" iki onay türünü birden kapsar. Tek tek
# durumlarla model "onaylanmış" sorusunda yalnızca birini filtreliyordu.
DURUM = ("$fromAI('durum', 'Yalnızca bu durumdakiler: onaylanan (otomatik veya elle onaylanmış), "
         "onay_bekliyor, reddedildi; hepsi için boş', 'string', '')")
# Boş metin NULLIF ile NULL olur: Postgres OR'un iki yanını da değerlendirebilir,
# ''::date ise hata verir.
FILTRE = """
WHERE (NULLIF($1::text, '') IS NULL OR firma ILIKE '%' || $1::text || '%')
  AND (NULLIF($2::text, '') IS NULL OR fatura_tarihi >= NULLIF($2::text, '')::date)
  AND (NULLIF($3::text, '') IS NULL OR fatura_tarihi <= NULLIF($3::text, '')::date)
  AND (NULLIF($4::text, '') IS NULL OR durum = $4::text
       OR ($4::text = 'onaylanan' AND durum IN ('otomatik_onay', 'onaylandi')))"""
FILTRE_PARAMS = f"={{{{ [{FIRMA}, {BASLANGIC}, {BITIS}, {DURUM}] }}}}"

TELEGRAM_GIRDISI = r"""
const m = $json.message || {};
return { json: { chatInput: m.text || '', sessionId: `telegram-${m.chat?.id}`, chat_id: m.chat?.id } };
"""


def arac_sql(name, position, description, query):
    return node(name, "n8n-nodes-base.postgresTool", 2.5, position, {
        "descriptionType": "manual", "toolDescription": description,
        "operation": "executeQuery", "query": query.strip(),
        "options": {"queryReplacement": FILTRE_PARAMS}}, credentials=PG)


def asistan():
    nodes = [
        node("Sohbet", "@n8n/n8n-nodes-langchain.chatTrigger", 1.5, (0, 200), {
            "public": True, "mode": "hostedChat", "authentication": "basicAuth",
            "options": {"title": "Fatura Asistanı", "subtitle": "Faturalar, sözleşmeler ve ödeme politikası",
                        "inputPlaceholder": "Sorunuzu yazın...", "responseMode": "lastNode"}},
            credentials=ASISTAN_GIRISI, webhookId="fatura-asistani",
            notes="Tarayıcı kullanıcı adı ve şifre sorar (.env: ASISTAN_KULLANICI, ASISTAN_SIFRE)."),
        node("Telegram mesajı", "n8n-nodes-base.telegramTrigger", 1.2, (0, 420), {
            "updates": ["message"], "additionalFields": {}},
            credentials=TG, disabled=True, webhookId="fatura-asistani-telegram",
            notes="Telegram kimlik bilgisini ekleyince açın; bota yazılan mesajlar asistana gelir."),
        code("Telegram girdisi", (220, 420), TELEGRAM_GIRDISI),
        node("Asistan", "@n8n/n8n-nodes-langchain.agent", 3.1, (480, 300), {
            "promptType": "define", "text": "={{ $json.chatInput }}",
            "options": {"systemMessage": SISTEM_MESAJI, "maxIterations": 6, "enableStreaming": False}}),
        node("Model", "@n8n/n8n-nodes-langchain.lmChatOllama", 1, (300, 560), {
            # qwen3.5:4b + makineye uygun thread sayısı; kurulum.ps1 oluşturur.
            "model": "qwen3.5-asistan",
            "options": {"think": False, "temperature": 0.1, "numCtx": 8192, "keepAlive": "30m"}},
            credentials=OLLAMA,
            notes="Daha hızlı ve isabetli cevap için OpenAI Chat Model node'uyla değiştirilebilir (README)."),
        node("Sohbet hafızası", "@n8n/n8n-nodes-langchain.memoryPostgresChat", 1.4, (460, 560), {
            "sessionIdType": "customKey", "sessionKey": "={{ $json.sessionId }}",
            "tableName": "asistan_sohbetleri", "contextWindowLength": 6}, credentials=PG),
        arac_sql("fatura_toplami", (620, 560),
                 "Faturaların firma ve duruma göre adedini ve toplam tutarını (TL) verir. Filtreler isteğe bağlıdır.",
                 f"""
SELECT firma, durum, count(*)::int AS adet, sum(toplam) AS toplam_tl
  FROM fatura.belgeler{FILTRE}
 GROUP BY firma, durum
 ORDER BY firma, durum;"""),
        arac_sql("fatura_listesi", (780, 560),
                 "Faturaları tek tek listeler (en yeni 20). Filtreler isteğe bağlıdır.",
                 f"""
SELECT id, firma, fatura_no, fatura_tarihi, toplam AS toplam_tl, durum, nedenler
  FROM fatura.belgeler{FILTRE}
 ORDER BY fatura_tarihi DESC NULLS LAST, id DESC
 LIMIT 20;"""),
        node("dokuman_sor", "n8n-nodes-base.httpRequestTool", 4.2, (940, 560), {
            "toolDescription": "Şirket belgelerine (tedarikçi sözleşmeleri, ödeme ve onay politikası) "
                               "soru sorar; kaynaklı bir cevap döner.",
            "method": "POST", "url": "http://rag:8000/chat",
            "sendBody": True, "contentType": "json", "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ question: $fromAI('soru', 'Belgelere sorulacak soru, "
                        "Türkçe ve tam cümle', 'string') }) }}",
            "options": {"timeout": 300000}}),
        if_("Telegram'dan mı?", (840, 300), "={{ $('Telegram girdisi').isExecuted }}", "true",
            None, type_="boolean"),
        node("Telegram'a yanıt", "n8n-nodes-base.telegram", 1.2, (1060, 220), {
            "chatId": "={{ $('Telegram girdisi').item.json.chat_id }}", "text": "={{ $json.output }}",
            "additionalFields": {"appendAttribution": False}},
            credentials=TG, disabled=True, notes="Telegram mesajı node'uyla birlikte açın."),
    ]
    connections = connect(
        ("Sohbet", "Asistan"),
        ("Telegram mesajı", "Telegram girdisi"),
        ("Telegram girdisi", "Asistan"),
        ("Asistan", "Telegram'dan mı?"),
        ("Telegram'dan mı?", 0, "Telegram'a yanıt"),
    )
    for source, kind in [("Model", "ai_languageModel"), ("Sohbet hafızası", "ai_memory"),
                         ("fatura_toplami", "ai_tool"), ("fatura_listesi", "ai_tool"),
                         ("dokuman_sor", "ai_tool")]:
        connections[source] = {kind: [[{"node": "Asistan", "type": kind, "index": 0}]]}
    return workflow(ASISTAN_ID, "03 Fatura asistanı", nodes, connections, error_workflow=HATA_ID)


def main():
    OUT.mkdir(exist_ok=True)
    for name, wf in [("01-fatura-isleme", fatura_isleme()), ("02-gmail-fatura", gmail()),
                     ("03-fatura-asistani", asistan()), ("99-hata-bildirimi", hata())]:
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"yazıldı: {path.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
