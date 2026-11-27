# Demo çekiminden önce sistemi aynı temiz duruma getirir. Her çekimden önce çalıştırın.
#
#   powershell -ExecutionPolicy Bypass -File .\demo\demo-hazirla.ps1
#
# - Fatura kayıtlarını, hataları ve asistanın sohbet geçmişini siler.
# - Onay bekleyen eski yürütmeleri iptal eder; eski onay linkleri çalışmaz.
# - Tedarikçi listesini kurar: ABC Gıda kayıtlı, Deniz Ambalaj kayıtlı DEĞİL.
# - Asistanın soracağı geçmişi ekler: Ekim-Kasım 2026'da onaylanmış 6 fatura.
#
# Google Sheets tablosunu bu betik temizlemez: başlık satırı kalacak şekilde
# eski satırları elle silin.
#
# Tüm şirketler, vergi numaraları ve tutarlar uydurmadır.

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)

# Windows PowerShell 5.1, bir programa borulanan metni ASCII gönderir: Türkçe
# harfler veritabanına '?' olarak yazılırdı. Boru ve konsol UTF-8 olsun.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $OutputEncoding

$sql = @'
BEGIN;

-- Onay bekleyen eski fatura yürütmeleri: linkleri artık hiçbir kaydı değiştirmez.
UPDATE public.execution_entity
   SET status = 'canceled', "waitTill" = NULL, "stoppedAt" = now()
 WHERE status = 'waiting' AND "workflowId" = 'FaturaIsleme0001';

TRUNCATE fatura.belgeler, fatura.hatalar, fatura.tedarikciler RESTART IDENTITY;

DO $$ BEGIN
  IF to_regclass('public.asistan_sohbetleri') IS NOT NULL THEN
    TRUNCATE public.asistan_sohbetleri RESTART IDENTITY;
  END IF;
END $$;

INSERT INTO fatura.tedarikciler (vergi_no, unvan) VALUES
  ('1234567890', 'ABC Gıda Sanayi ve Ticaret A.Ş.'),
  ('2345678901', 'Ege Temizlik Ürünleri A.Ş.'),
  ('3456789012', 'Anadolu Lojistik Ltd. Şti.');

INSERT INTO fatura.belgeler
  (alinma, kaynak, dosya_adi, firma, vergi_no, fatura_no, fatura_tarihi,
   ara_toplam, kdv, toplam, yontem, durum, nedenler, karar_veren, karar_zamani)
VALUES
  ('2026-10-08 09:14+03', 'gmail', 'ABC2026000297715.pdf', 'ABC Gıda Sanayi ve Ticaret A.Ş.', '1234567890',
   'ABC2026000297715', '2026-10-08', 4250, 850, 5100, 'e5', 'otomatik_onay', '[]', NULL, NULL),
  ('2026-10-15 11:02+03', 'gmail', 'EGE2026000088412.pdf', 'Ege Temizlik Ürünleri A.Ş.', '2345678901',
   'EGE2026000088412', '2026-10-15', 2150, 430, 2580, 'e5', 'otomatik_onay', '[]', NULL, NULL),
  ('2026-10-27 16:40+03', 'gmail', 'ABC2026000305248.pdf', 'ABC Gıda Sanayi ve Ticaret A.Ş.', '1234567890',
   'ABC2026000305248', '2026-10-27', 6000, 1200, 7200, 'e5', 'otomatik_onay', '[]', NULL, NULL),
  ('2026-11-03 10:21+03', 'gmail', 'ANL2026000156390.pdf', 'Anadolu Lojistik Ltd. Şti.', '3456789012',
   'ANL2026000156390', '2026-11-03', 12500, 2500, 15000, 'e5', 'onaylandi',
   '["Toplam 15000, otomatik onay limitini (10000) aşıyor"]', 'onay linki', '2026-11-03 14:05+03'),
  ('2026-11-12 08:57+03', 'gmail', 'ABC2026000311907.pdf', 'ABC Gıda Sanayi ve Ticaret A.Ş.', '1234567890',
   'ABC2026000311907', '2026-11-12', 5500, 1100, 6600, 'e5', 'otomatik_onay', '[]', NULL, NULL),
  ('2026-11-18 13:33+03', 'gmail', 'EGE2026000091276.pdf', 'Ege Temizlik Ürünleri A.Ş.', '2345678901',
   'EGE2026000091276', '2026-11-18', 1875, 375, 2250, 'e5', 'otomatik_onay', '[]', NULL, NULL);

COMMIT;
'@

$sql | docker compose exec -T postgres psql -U otomasyon -d otomasyon -v ON_ERROR_STOP=1 -q
if ($LASTEXITCODE -ne 0) { throw 'Demo verisi hazırlanamadı (servisler açık mı? docker compose ps)' }

docker compose exec -T postgres psql -U otomasyon -d otomasyon -c "SELECT id, firma, fatura_no, fatura_tarihi, toplam, durum FROM fatura.belgeler ORDER BY id"

Write-Host ''
Write-Host 'Demo hazır. Çekimde gönderilecek faturalar: demo\faturalar\'
Write-Host '  1-abc-gida-otomatik-onay.pdf     -> otomatik onay, Sheets''e satır'
Write-Host '  2-deniz-ambalaj-onay-gerekli.pdf -> Telegram''a onay mesajı (tedarikçi kayıtsız)'
Write-Host '  3-abc-gida-limit-ustu.pdf        -> Telegram''a onay mesajı (10.000 TL limiti)'
Write-Host 'Google Sheets''teki eski satırları silmeyi unutmayın.'
