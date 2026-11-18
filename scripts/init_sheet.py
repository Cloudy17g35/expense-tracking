"""Przygotowuje arkusz (zakładki, nagłówki, formuły). Szczegóły: bot/sheet_setup.py.

Uruchamiane z GitHub Actions: Actions → Init sheet → Run workflow.
"""

import json
import logging
import os
import sys

import gspread

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.sheet_setup import setup_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SA_JSON"]))
    setup_all(client.open_by_key(os.environ["SHEET_ID"]))
    logging.info("Gotowe.")


if __name__ == "__main__":
    main()
