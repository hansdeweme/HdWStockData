"""Prepare a reviewable 500-icon selection; copying is a separate operation."""
import csv
from pathlib import Path
import pandas as pd

source = Path(r'D:\Coding\forecast\gui\ticker_icons')
icons = {p.stem.upper(): p for p in source.glob('*.png')}
popular = '''AAPL MSFT NVDA AMZN GOOG GOOGL META TSLA AVGO AMD INTC MU TSM
ASML ARM QCOM PLTR ORCL CRM ADBE CRWD PANW NET SNOW DDOG SHOP UBER ABNB
COIN MSTR HOOD SOFI PYPL SQ XYZ AFRM UPST RKLB ASTS IONQ RGTI QBTS
RIVN LCID NIO XPEV LI BABA JD PDD BIDU BILI TCEHY MELI SE NU GRAB
DKNG RBLX U PATH AI SOUN BBAI HIMS RXRX TEM CRSP NTLA BEAM MRNA BNTX
GME AMC MARA RIOT CLSK IREN WULF CIFR SMCI DELL HPE VRT APP TTD
ROKU SPOT NFLX DIS WBD PINS SNAP ZM DOCU TWLO OKTA ZS MDB CFLT
F GM RACE TM HMC STLA NKE LULU SBUX CMG CAVA CELH BROS CHWY
CVNA CAR CCL RCL NCLH DAL UAL AAL LUV BA GE RTX LMT NOC
XOM CVX OXY COP SLB FSLR ENPH SEDG RUN BE PLUG FCEL CCJ UEC
WMT COST TGT HD LOW KO PEP MCD JNJ PFE LLY NVO UNH CVS
JPM BAC C WFC GS MS V MA AXP BRK.B BRK.A SCHW BLK BX
T VZ TMUS IBM CSCO AMAT LRCX KLAC TXN ADI NXPI ON MRVL
DUOL FUBO OPEN ACHR JOBY WING WIX ETSY EBAY YETI CROX'''.split()
large = pd.read_html('icon_selection_source.html')[0]
sp500 = pd.read_html('icon_selection_sp500.html')[0]
selected = {}
# Avoid old artwork for known reused tickers in this historical collection.
excluded = {'COR', 'VG'}
aliases = {'BRK.B': 'BRKB', 'BRK.A': 'BRKA'}

def add(symbol, basis):
    if symbol in selected or symbol in excluded:
        return
    path = icons.get(symbol) or icons.get(aliases.get(symbol, ''))
    if path:
        selected[symbol] = {'ticker': symbol, 'source_file': str(path),
                            'destination_file': symbol + '.png', 'basis': basis}

for symbol in popular:
    add(symbol, 'Widely followed showcase selection')
for symbol in large['Symbol']:
    add(symbol, 'Largest companies by market capitalization')
for symbol in sp500['Symbol']:
    add(symbol, 'S&P 500 constituent, source list order')
rows = list(selected.values())[:500]
assert len(rows) == 500, f'Only {len(rows)} matches'
with open('stock_icons_selection.csv', 'w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
size = sum(Path(row['source_file']).stat().st_size for row in rows)
total = sum(path.stat().st_size for path in icons.values())
print(f'Selected {len(rows)} icons: {size / 1024 / 1024:.2f} MiB; original {len(icons)} icons: {total / 1024 / 1024:.2f} MiB')
from collections import Counter
print(dict(Counter(row['basis'] for row in rows)))
