// workflows/*.json'u bu kuruluma göre doldurur; kurulum.ps1, n8n konteynerinde çalıştırır.
//
//   node render-workflows.js <girdi klasörü> <çıktı klasörü> <kimlik bilgileri.json>
//
// - __TELEGRAM_CHAT_ID__ ve __GOOGLE_SHEET_URL__ yer tutucularını ortam
//   değişkenlerinden (TELEGRAM_CHAT_ID, GOOGLE_SHEET_URL) doldurur.
// - Node'ları n8n'de var olan kimlik bilgilerine bağlar: önce aynı kimlikliye,
//   yoksa aynı türdeki ilk kimlik bilgisine. Google hesapları n8n arayüzünde
//   oluşturulur ve rastgele kimlik alır; kurulum tekrar çalışınca bağlantı
//   böylece kopmaz.
// - Kapalı gelen entegrasyon node'larını, ihtiyaç duydukları her şey varsa açar.
// - Son satırda yayınlanabilecek isteğe bağlı workflow'ları yazar (READY=...).

const fs = require('fs');
const path = require('path');

const [input, output, credentialsFile] = process.argv.slice(2);
const credentials = JSON.parse(fs.readFileSync(credentialsFile, 'utf8'));
const values = {
  __TELEGRAM_CHAT_ID__: (process.env.TELEGRAM_CHAT_ID || '').trim(),
  __GOOGLE_SHEET_URL__: (process.env.GOOGLE_SHEET_URL || '').trim(),
};

// Node adı -> açılması için gerekenler.
const ENABLE = {
  "Telegram'a gönder": { credential: 'telegramApi', value: '__TELEGRAM_CHAT_ID__' },
  "Telegram'a bildir": { credential: 'telegramApi', value: '__TELEGRAM_CHAT_ID__' },
  "Google Sheets'e yaz": { credential: 'googleSheetsOAuth2Api', value: '__GOOGLE_SHEET_URL__' },
};
// Yalnızca kimlik bilgisi varsa yayınlanan workflow'lar.
const OPTIONAL = { GmailFatura00002: 'gmailOAuth2' };

function link(type, current) {
  const same = credentials.find((c) => c.id === current.id && c.type === type);
  const any = credentials.find((c) => c.type === type);
  const found = same || any;
  return found ? { id: found.id, name: found.name } : null;
}

fs.mkdirSync(output, { recursive: true });
const ready = [];
const report = [];

for (const file of fs.readdirSync(input).filter((f) => f.endsWith('.json'))) {
  let text = fs.readFileSync(path.join(input, file), 'utf8');
  for (const [placeholder, value] of Object.entries(values)) {
    // JSON içinde bir dizgenin parçası: kaçış gerekebilir.
    text = text.split(placeholder).join(JSON.stringify(value).slice(1, -1));
  }
  const workflow = JSON.parse(text);

  for (const node of workflow.nodes) {
    for (const [type, current] of Object.entries(node.credentials || {})) {
      const found = link(type, current);
      if (found) node.credentials[type] = found;
    }
    const rule = ENABLE[node.name];
    if (rule) {
      const ok = Boolean(link(rule.credential, {}) && values[rule.value]);
      if (ok) delete node.disabled;
      report.push(`${workflow.name} / ${node.name}: ${ok ? 'açık' : 'kapalı'}`);
    }
  }

  const needs = OPTIONAL[workflow.id];
  if (needs && credentials.some((c) => c.type === needs)) ready.push(workflow.id);

  fs.writeFileSync(path.join(output, file), JSON.stringify(workflow, null, 2));
}

for (const line of report) console.log(line);
console.log(`READY=${ready.join(',')}`);
