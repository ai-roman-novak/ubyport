# SPDX-FileCopyrightText: 2025 Aidaro s.r.o.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Aidaro-Commercial-1.0

"""
Modul pro export dat z databáze do Excelu.

Vytvoří output Excel soubor s přehledem všech zaměstnanců.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from database import UbyportDatabase
from config import DB_PATH, EXPORT_DIR

logger = logging.getLogger(__name__)


class ExcelExporter:
    """
    Export dat z databáze do Excelu.
    """

    def __init__(self, db_path: str = None):
        """
        Inicializace exporteru.

        Args:
            db_path: Cesta k databázi (pokud None, použije se cesta z config.py)
        """
        if db_path is None:
            db_path = str(DB_PATH)
        self.db_path = db_path

    def export_zamestnance(self, output_path: Optional[str] = None) -> str:
        """
        Exportuje všechny zaměstnance z databáze do Excelu.

        Args:
            output_path: Cesta k výstupnímu souboru (pokud None, vygeneruje se)

        Returns:
            Cesta k vytvořenému souboru
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"data/export_zamestnanci_{timestamp}.xlsx"

        # Připojení k databázi
        with UbyportDatabase(self.db_path) as db:
            # Načtení všech zaměstnanců
            zamestnanci = db.get_vsichni_zamestnanci()

            if not zamestnanci:
                logger.warning("Žádní zaměstnanci k exportu")
                return None

            # Převod na DataFrame
            df = pd.DataFrame(zamestnanci)

            # Výběr sloupců pro export
            export_columns = [
                'id',
                'prijmeni',
                'jmeno',
                'datum_narozeni',
                'cislo_pasu',
                'statni_obcanstvi',
                'datum_prijezdu',
                'datum_odjezdu',
                'cislo_viza',
                'bydliste_domov',
                'ucel_pobytu',
                'poznamka',
                'stav',
                'posledni_sync',
                'created_at',
                'updated_at'
            ]

            # Filtrace existujících sloupců
            available_columns = [col for col in export_columns if col in df.columns]
            df_export = df[available_columns]

            # Přejmenování sloupců na čitelné názvy
            column_names = {
                'id': 'ID',
                'prijmeni': 'Příjmení',
                'jmeno': 'Jméno',
                'datum_narozeni': 'Datum narození',
                'cislo_pasu': 'Číslo pasu',
                'statni_obcanstvi': 'Státní občanství',
                'datum_prijezdu': 'Datum příjezdu',
                'datum_odjezdu': 'Datum odjezdu',
                'cislo_viza': 'Číslo víza',
                'bydliste_domov': 'Bydliště v domovské zemi',
                'ucel_pobytu': 'Účel pobytu',
                'poznamka': 'Poznámka',
                'stav': 'Stav',
                'posledni_sync': 'Poslední synchronizace',
                'created_at': 'Vytvořeno',
                'updated_at': 'Aktualizováno'
            }

            df_export = df_export.rename(columns=column_names)

            # Uložení do Excelu
            df_export.to_excel(output_path, index=False, engine='openpyxl')
            logger.info(f"Export vytvořen: {output_path} ({len(df_export)} záznamů)")

            return output_path

    def export_transakce(self, output_path: Optional[str] = None) -> str:
        """
        Exportuje všechny transakce z databáze do Excelu.

        Args:
            output_path: Cesta k výstupnímu souboru

        Returns:
            Cesta k vytvořenému souboru
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"data/export_transakce_{timestamp}.xlsx"

        # Připojení k databázi
        with UbyportDatabase(self.db_path) as db:
            # Načtení všech zaměstnanců a jejich transakcí
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT
                    t.id,
                    t.datum_odeslani,
                    z.prijmeni || ' ' || z.jmeno as zamestnanec,
                    t.typ_operace,
                    t.success,
                    t.chyby,
                    t.pdf_potvrzeni_path
                FROM api_transakce t
                LEFT JOIN zamestnanci z ON t.zamestnanec_id = z.id
                ORDER BY t.datum_odeslani DESC
            """)

            transakce = []
            for row in cursor.fetchall():
                # Extrahuj jen název souboru z celé cesty
                pdf_path = row[6]
                pdf_name = Path(pdf_path).name if pdf_path else ''

                transakce.append({
                    'ID': row[0],
                    'Datum': row[1],
                    'Zaměstnanec': row[2],
                    'Operace': row[3],
                    'Úspěch': 'Ano' if row[4] else 'Ne',
                    'Chyby': row[5],
                    'PDF': pdf_name
                })

            if not transakce:
                logger.warning("Žádné transakce k exportu")
                return None

            # Převod na DataFrame
            df = pd.DataFrame(transakce)

            # Uložení do Excelu
            df.to_excel(output_path, index=False, engine='openpyxl')
            logger.info(f"Export transakcí vytvořen: {output_path} ({len(df)} záznamů)")

            return output_path

    def export_vse(self, base_path: Optional[str] = None) -> dict:
        """
        Exportuje vše (zaměstnanci + transakce) do jednoho Excel souboru s více listy.

        Args:
            base_path: Základní cesta (bez přípony)

        Returns:
            Dict s cestami k vytvořeným souborům
        """
        if base_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = str(EXPORT_DIR / f"export_kompletni_{timestamp}.xlsx")
        else:
            output_path = base_path if base_path.endswith('.xlsx') else f"{base_path}.xlsx"

        # Složka export se vytváří automaticky v config.py
        # (ensure_directories())

        # Připojení k databázi
        with UbyportDatabase(self.db_path) as db:
            # Načtení zaměstnanců - řazení podle ID vzestupně (staří nahoře, noví dole)
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM zamestnanci ORDER BY id ASC")
            zamestnanci = [dict(row) for row in cursor.fetchall()]
            df_zam = pd.DataFrame(zamestnanci)

            # Přejmenování sloupců
            column_names = {
                'id': 'ID',
                'prijmeni': 'Příjmení',
                'jmeno': 'Jméno',
                'datum_narozeni': 'Datum narození',
                'cislo_pasu': 'Číslo pasu',
                'statni_obcanstvi': 'Státní občanství',
                'datum_prijezdu': 'Datum příjezdu',
                'datum_odjezdu': 'Datum odjezdu',
                'cislo_viza': 'Číslo víza',
                'bydliste_domov': 'Bydliště',
                'ucel_pobytu': 'Účel pobytu',
                'poznamka': 'Poznámka',
                'stav': 'Stav',
                'posledni_sync': 'Poslední sync',
                'created_at': 'Vytvořeno',
                'updated_at': 'Aktualizováno'
            }
            df_zam = df_zam.rename(columns=column_names)

            # Formátování datumů - převod na YYYY-MM-DD formát
            if 'Datum příjezdu' in df_zam.columns:
                df_zam['Datum příjezdu'] = pd.to_datetime(df_zam['Datum příjezdu']).dt.strftime('%Y-%m-%d')
            if 'Datum odjezdu' in df_zam.columns:
                df_zam['Datum odjezdu'] = pd.to_datetime(df_zam['Datum odjezdu']).dt.strftime('%Y-%m-%d')

            # Načtení transakcí
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT
                    t.id,
                    t.datum_odeslani,
                    z.prijmeni || ' ' || z.jmeno as zamestnanec,
                    t.typ_operace,
                    t.success,
                    t.chyby,
                    t.pdf_potvrzeni_path
                FROM api_transakce t
                LEFT JOIN zamestnanci z ON t.zamestnanec_id = z.id
                ORDER BY t.datum_odeslani DESC
            """)

            transakce = []
            for row in cursor.fetchall():
                # Extrahuj jen název souboru z celé cesty
                pdf_path = row[6]
                pdf_name = Path(pdf_path).name if pdf_path else ''

                transakce.append({
                    'ID': row[0],
                    'Datum': row[1],
                    'Zaměstnanec': row[2],
                    'Operace': row[3],
                    'Úspěch': 'Ano' if row[4] else 'Ne',
                    'Chyby': row[5],
                    'PDF': pdf_name
                })

            df_trans = pd.DataFrame(transakce)

            # Vytvoření Excel souboru s více listy
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df_zam.to_excel(writer, sheet_name='People', index=False)
                if not df_trans.empty:
                    df_trans.to_excel(writer, sheet_name='Transakce', index=False)

            logger.info(f"Kompletní export vytvořen: {output_path}")
            logger.info(f"  - People: {len(df_zam)} záznamů")
            logger.info(f"  - Transakce: {len(df_trans)} záznamů")

            return {
                'path': output_path,
                'zamestnanci': len(df_zam),
                'transakce': len(df_trans)
            }

    def export_potvrzeni_policie(self, output_path: Optional[str] = None) -> dict:
        """
        Exportuje POUZE zaměstnance potvrzené policií (stav PRIHLASEN).

        Tento export obsahuje pouze ty zaměstnance, kteří byli úspěšně
        přijati policií a mají stav PRIHLASEN. Vhodné pro vizuální kontrolu
        a další použití ověřených dat.

        Args:
            output_path: Cesta k výstupnímu souboru (pokud None, vygeneruje se)

        Returns:
            Dict s informacemi o exportu (path, počet záznamů)
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = str(EXPORT_DIR / f"potvrzeni_policie_{timestamp}.xlsx")

        # Složka export se vytváří automaticky v config.py
        # (ensure_directories())

        # Připojení k databázi
        with UbyportDatabase(self.db_path) as db:
            # Načtení POUZE zaměstnanců se stavem PRIHLASEN + info o PDF
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT
                    z.id,
                    z.prijmeni,
                    z.jmeno,
                    z.datum_narozeni,
                    z.cislo_pasu,
                    z.statni_obcanstvi,
                    z.datum_prijezdu,
                    z.datum_odjezdu,
                    z.cislo_viza,
                    z.bydliste_domov,
                    z.ucel_pobytu,
                    z.poznamka,
                    z.stav,
                    z.posledni_sync,
                    t.datum_odeslani as datum_potvrzeni,
                    t.pdf_potvrzeni_path
                FROM zamestnanci z
                LEFT JOIN api_transakce t ON z.id = t.zamestnanec_id AND t.success = 1
                WHERE z.stav = 'PRIHLASEN'
                ORDER BY z.id ASC
            """)

            potvrzeni = []
            for row in cursor.fetchall():
                # Extrahuj jen název souboru z celé cesty
                pdf_path = row[15]
                pdf_name = Path(pdf_path).name if pdf_path else ''

                potvrzeni.append({
                    'ID': row[0],
                    'Příjmení': row[1],
                    'Jméno': row[2],
                    'Datum narození': row[3],
                    'Číslo pasu': row[4],
                    'Státní občanství': row[5],
                    'Datum příjezdu': row[6],
                    'Datum odjezdu': row[7],
                    'Číslo víza': row[8] if row[8] else '',
                    'Bydliště': row[9] if row[9] else '',
                    'Účel pobytu': row[10] if row[10] else 99,
                    'Poznámka': row[11] if row[11] else '',
                    'Stav': row[12],
                    'Datum zápisu u policie': row[14] if row[14] else row[13],
                    'PDF potvrzení': pdf_name
                })

            if not potvrzeni:
                logger.warning("Žádní zaměstnanci se stavem PRIHLASEN k exportu")
                return {
                    'path': None,
                    'count': 0
                }

            # Převod na DataFrame
            df = pd.DataFrame(potvrzeni)

            # Formátování datumů - převod na DD.MM.YYYY formát (lidsky čitelný)
            if 'Datum příjezdu' in df.columns:
                df['Datum příjezdu'] = pd.to_datetime(df['Datum příjezdu']).dt.strftime('%d.%m.%Y')
            if 'Datum odjezdu' in df.columns:
                df['Datum odjezdu'] = pd.to_datetime(df['Datum odjezdu']).dt.strftime('%d.%m.%Y')
            if 'Datum zápisu u policie' in df.columns:
                df['Datum zápisu u policie'] = pd.to_datetime(df['Datum zápisu u policie']).dt.strftime('%d.%m.%Y %H:%M')

            # Uložení do Excelu
            df.to_excel(output_path, index=False, engine='openpyxl')

            logger.info(f"Export potvrzení policie vytvořen: {output_path}")
            logger.info(f"  - Počet potvrzených zaměstnanců: {len(df)}")

            return {
                'path': output_path,
                'count': len(df)
            }


if __name__ == "__main__":
    """Test exportu."""
    logging.basicConfig(level=logging.INFO)

    exporter = ExcelExporter()

    print("=" * 60)
    print("EXCEL EXPORT - TEST")
    print("=" * 60)

    # Test exportu všeho
    result = exporter.export_vse()

    print(f"\n[OK] Export vytvořen: {result['path']}")
    print(f"     Zaměstnanců: {result['zamestnanci']}")
    print(f"     Transakcí: {result['transakce']}")

    print("\n" + "=" * 60)
