"""
generate_raw_data.py
---------------------
Genera un dataset grezzo e VOLUTAMENTE sporco, per simulare un export reale
da un sistema POS (punto vendita) di un negozio di abbigliamento sportivo.

Problemi iniettati di proposito (quelli che un vero export POS presenta):
- prezzi con formato misto ("49.99", "49,99€", "")
- date in formati diversi (ISO, europeo, timestamp)
- email/clienti duplicati con casing diverso
- righe duplicate esatte
- valori nulli su campi non sempre obbligatori
- quantità negative (resi) mischiate a vendite
- categorie con refusi ("Scarpe", "scarpe ", "SCARPE")

Questo è il punto di ingresso del livello BRONZE: dati grezzi, as-is,
nessuna pulizia.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "bronze" / "pos_transactions_raw.csv"

PRODUCTS = [
    ("SKU-1001", "Scarpe running Pegasus", "Scarpe", 119.99),
    ("SKU-1002", "Scarpe running Pegasus", "scarpe ", 119.99),  # refuso categoria voluto
    ("SKU-1003", "Felpa tech fleece", "Abbigliamento", 69.99),
    ("SKU-1004", "T-shirt dri-fit", "Abbigliamento", 24.99),
    ("SKU-1005", "Pantaloncini running", "Abbigliamento", 34.99),
    ("SKU-1006", "Zaino sportivo", "Accessori", 44.99),
    ("SKU-1007", "Calzini tecnici (3 paia)", "Accessori", 14.99),
    ("SKU-1008", "Scarpe basket Air", "SCARPE", 149.99),  # refuso categoria voluto
    ("SKU-1009", "Giacca a vento", "Abbigliamento", 89.99),
    ("SKU-1010", "Cappellino", "Accessori", 19.99),
]

STORES = ["Marcianise", "Caserta", "Napoli Centro", "Napoli Vomero"]

PAYMENT_METHODS = ["carta", "contanti", "Carta", "CONTANTI", "bancomat", ""]

CUSTOMER_EMAILS = [
    "mario.rossi@email.com", "Mario.Rossi@email.com",  # stesso cliente, casing diverso
    "giulia.bianchi@email.com", "", None,
    "luca.verdi@email.com", "LUCA.VERDI@email.com",
    "anna.neri@email.com", "sara.gialli@email.com",
    None, "", "paolo.blu@email.com",
]


def random_date_messy(start, end):
    """Genera una data in uno tra tre formati diversi, come farebbe
    un export reale fatto da sistemi POS differenti nei vari negozi."""
    delta = end - start
    random_dt = start + timedelta(
        days=random.randint(0, delta.days),
        hours=random.randint(8, 21),
        minutes=random.randint(0, 59),
    )
    fmt_choice = random.choice(["iso", "eu", "ts"])
    if fmt_choice == "iso":
        return random_dt.strftime("%Y-%m-%d %H:%M:%S")
    elif fmt_choice == "eu":
        return random_dt.strftime("%d/%m/%Y %H:%M")
    else:
        return str(int(random_dt.timestamp()))


def messy_price(base_price):
    """Restituisce il prezzo in uno tra più formati sporchi, o vuoto."""
    roll = random.random()
    if roll < 0.03:
        return ""  # prezzo mancante
    elif roll < 0.15:
        return f"{base_price:.2f}".replace(".", ",") + "€"
    elif roll < 0.25:
        return f"{base_price:.2f}€"
    else:
        return f"{base_price:.2f}"


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1)
    end = datetime(2026, 9, 30)

    rows = []
    header = [
        "transaction_id", "sku", "product_name", "category", "store",
        "quantity", "unit_price", "payment_method", "customer_email",
        "transaction_date",
    ]

    transaction_counter = 1
    for _ in range(6000):
        sku, name, category, base_price = random.choice(PRODUCTS)
        store = random.choice(STORES)

        # l'80% sono vendite normali, il resto resi (quantità negativa)
        is_return = random.random() < 0.05
        quantity = -random.randint(1, 2) if is_return else random.randint(1, 3)

        row = [
            f"TX{transaction_counter:06d}",
            sku,
            name,
            category,
            store,
            quantity,
            messy_price(base_price),
            random.choice(PAYMENT_METHODS),
            random.choice(CUSTOMER_EMAILS),
            random_date_messy(start, end),
        ]
        rows.append(row)
        transaction_counter += 1

        # ~2% di righe duplicate esatte, come capita per doppio invio POS
        if random.random() < 0.02:
            rows.append(row.copy())

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Generate {len(rows)} righe grezze in {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
