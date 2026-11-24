-- Belge kayıtları. n8n kendi tablolarını public şemasında tutar; bunlar ayrı.

CREATE SCHEMA IF NOT EXISTS fatura;

-- Bilinen tedarikçiler. Listede olmayan vergi numarası manuel onaya düşer.
CREATE TABLE fatura.tedarikciler (
    vergi_no    TEXT PRIMARY KEY,
    unvan       TEXT NOT NULL,
    eklenme     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- İşlenen her belge bir satır. Durumlar:
--   otomatik_onay  tüm kontroller geçti, insan bakmadı
--   onay_bekliyor  bir kontrol takıldı, onay linki gönderildi
--   onaylandi / reddedildi  bir kişi karar verdi
CREATE TABLE fatura.belgeler (
    id             BIGSERIAL PRIMARY KEY,
    alinma         TIMESTAMPTZ NOT NULL DEFAULT now(),
    kaynak         TEXT,           -- webhook, gmail, telegram ...
    dosya_adi      TEXT,
    firma          TEXT,
    vergi_no       TEXT,
    fatura_no      TEXT,
    fatura_tarihi  DATE,
    ara_toplam     NUMERIC(14, 2),
    kdv            NUMERIC(14, 2),
    toplam         NUMERIC(14, 2),
    yontem         TEXT,           -- extractor'ın kullandığı motor (e2, e3, e5, xml ...)
    durum          TEXT NOT NULL,
    nedenler       JSONB NOT NULL DEFAULT '[]',
    onay_linki     TEXT,
    karar_veren    TEXT,
    karar_zamani   TIMESTAMPTZ,
    ham_sonuc      JSONB,
    CONSTRAINT durum_gecerli CHECK (
        durum IN ('otomatik_onay', 'onay_bekliyor', 'onaylandi', 'reddedildi'))
);

CREATE INDEX belgeler_mukerrer ON fatura.belgeler (vergi_no, fatura_no);
CREATE INDEX belgeler_durum ON fatura.belgeler (durum);

-- Hata workflow'unun kayıtları.
CREATE TABLE fatura.hatalar (
    id          BIGSERIAL PRIMARY KEY,
    zaman       TIMESTAMPTZ NOT NULL DEFAULT now(),
    workflow    TEXT,
    node        TEXT,
    mesaj       TEXT,
    yurutme_url TEXT
);
