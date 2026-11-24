// Uji UI form di jsdom (dijalankan oleh tests/test_form_salin.py). Argumen: URL dasar server, tanggal, jam.
// Keluaran: satu baris JSON {salin1x: {...}, ...}. Memerlukan paket npm 'jsdom' (npm install jsdom).
const { JSDOM } = require("jsdom");
const [base, tanggal, jam] = process.argv.slice(2);
const tunggu = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const dom = await JSDOM.fromURL(`${base}/form/${tanggal}/${jam}`, {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, base), o); w.confirm = () => true; w.scrollTo = () => {}; },
  });
  const w = dom.window, D = w.document;
  for (let i = 0; i < 80 && !(D.querySelector("#f_ww") && D.querySelector("#temuan") && !/memuat/.test(D.querySelector("#temuan").textContent)); i++) await tunggu(100);
  const nilai = () => { const o = {}; D.querySelectorAll("[data-k]").forEach(e => { if (e.value !== "") o[e.dataset.k] = e.value; }); return o; };
  const awal = nilai();
  D.querySelector("#salin").click();
  await tunggu(2500);
  const sesudah1 = nilai();
  const terkunci = [...D.querySelectorAll("[data-k]")].filter(e => e.disabled).map(e => e.dataset.k);
  const hidden = [...D.querySelectorAll(".f[hidden]")].map(e => e.dataset.w);
  const ie = D.querySelector("#f_penguapan_ie");
  const urutan = [...D.querySelectorAll("section.bag-penguapan [data-k]")].map(e => e.dataset.k);
  const bagianTanah = D.querySelector("#f_land_cond") && D.querySelector("#f_land_cond").closest("section").className;
  console.log(JSON.stringify({ awal, sesudah1, terkunci, hidden, ie: (ie && ie.options) ? [...ie.options].map(o => o.value + "|" + o.textContent) : null, urutan, bagianTanah }));
  w.close();
})().catch(e => { console.error(String(e)); process.exit(2); });
