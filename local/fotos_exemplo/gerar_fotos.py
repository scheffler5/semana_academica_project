"""Gera as fotos ilustrativas dos produtos de exemplo (já geradas e versionadas nesta pasta).

Uso (precisa do Playwright):  python local/fotos_exemplo/gerar_fotos.py local/fotos_exemplo
Arte: Twemoji (CC-BY 4.0) sobre fundo em degradê. Ver LICENCA.md.
"""
import sys, asyncio
from playwright.async_api import async_playwright
OUT = sys.argv[1]
ITEMS = [
    ("NB-001", "1f4bb", "#dbeafe", "#93c5fd"), ("MS-002", "1f5b1", "#ede9fe", "#c4b5fd"),
    ("TC-003", "2328", "#e0e7ff", "#a5b4fc"), ("MN-004", "1f5a5", "#cffafe", "#67e8f9"),
    ("CB-005", "1f50c", "#fef3c7", "#fcd34d"), ("HD-006", "1f3a7", "#fce7f3", "#f9a8d4"),
    ("PD-007", "1f4be", "#dcfce7", "#86efac"), ("SS-008", "1f4bd", "#e2e8f0", "#94a3b8"),
    ("WC-009", "1f4f7", "#ffedd5", "#fdba74"), ("CD-010", "1fa91", "#f5f5f4", "#d6d3d1"),
]
HTML = """<html><body style="margin:0;width:800px;height:600px;display:grid;place-items:center;
background:radial-gradient(circle at 30% 25%, {a}, {b});font-family:-apple-system">
<div style="position:absolute;width:420px;height:80px;bottom:150px;border-radius:50%;background:rgba(0,0,0,.12);filter:blur(18px)"></div>
<img src="https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/{e}.svg" style="width:300px;height:300px;filter:drop-shadow(0 24px 30px rgba(0,0,0,.25));position:relative">
</body></html>"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 800, "height": 600})
        for sku, e, a, c in ITEMS:
            await pg.set_content(HTML.format(a=a, b=c, e=e), wait_until="networkidle")
            await pg.screenshot(path=f"{OUT}/{sku}.jpg", type="jpeg", quality=82)
        await b.close()
asyncio.run(main())
