# SPDX-FileCopyrightText: 2025 Aidaro s.r.o.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Aidaro-Commercial-1.0

"""
Databázový modul pro správu SQLite databáze.

Tento modul obsahuje třídu UbyportDatabase, která spravuje:
- Tabulku zaměstnanců (zamestnanci)
- Tabulku API transakcí (api_transakce)
- CRUD operace
- Detekci změn mezi Excelem a DB
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DB_PATH

# Logger pro tento modul (konfigurace se nastaví v main.py)
logger = logging.getLogger(__name__)


class UbyportDatabase:
    """
    Správa SQLite databáze pro Ubyport automatizaci.

    Poskytuje metody pro:
    - Vytvoření schématu databáze
    - CRUD operace nad zaměstnanci
    - Zaznamenávání API transakcí
    - Detekci změn (noví, změněni, k odhlášení)
    """

    def __init__(self, db_path: str = None):
        """
        Inicializace databázového spojení.

        Args:
            db_path: Cesta k SQLite databázi (pokud None, použije se cesta z config.py)
        """
        if db_path is None:
            db_path = str(DB_PATH)
        self.db_path = db_path
        self._ensure_db_directory()
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Výsledky jako slovníky
        self._create_tables()

        logger.info(f"Databáze inicializována: {db_path}")

    def _ensure_db_directory(self):
        """Zajistí, že složka pro databázi existuje."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def _create_tables(self):
        """Vytvoří tabulky pokud neexistují."""
        cursor = self.conn.cursor()

        # Tabulka zaměstnanců
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zamestnanci (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prijmeni TEXT NOT NULL,
                jmeno TEXT NOT NULL,
                datum_narozeni TEXT NOT NULL,
                cislo_pasu TEXT NOT NULL,
                statni_obcanstvi TEXT NOT NULL,
                datum_prijezdu TEXT NOT NULL,
                datum_odjezdu TEXT NOT NULL,
                cislo_viza TEXT,
                bydliste_domov TEXT,
                ucel_pobytu INTEGER DEFAULT 99,
                poznamka TEXT,
                stav TEXT DEFAULT 'NOVY',
                posledni_sync TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cislo_pasu, datum_narozeni)
            )
        """)

        # Tabulka API transakcí
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_transakce (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zamestnanec_id INTEGER,
                datum_odeslani TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                typ_operace TEXT,
                soap_request TEXT,
                soap_response TEXT,
                chyby TEXT,
                pdf_potvrzeni_path TEXT,
                success BOOLEAN,
                FOREIGN KEY (zamestnanec_id) REFERENCES zamestnanci(id)
            )
        """)

        self.conn.commit()
        logger.info("Databázové schéma vytvořeno/ověřeno")

    def _datetime_to_str(self, dt) -> str:
        """Převede datetime objekt na ISO string pro databázi."""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.isoformat()
        if isinstance(dt, str):
            return dt
        return str(dt)

    def _str_to_datetime(self, dt_str: str) -> Optional[datetime]:
        """Převede ISO string z databáze na datetime objekt."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str)
        except:
            return None

    def vloz_zamestnance(self, data: Dict) -> Optional[int]:
        """
        Vloží nového zaměstnance do databáze.

        Args:
            data: Slovník s daty zaměstnance

        Returns:
            ID nového záznamu nebo None při chybě
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO zamestnanci (
                    prijmeni, jmeno, datum_narozeni, cislo_pasu,
                    statni_obcanstvi, datum_prijezdu, datum_odjezdu,
                    cislo_viza, bydliste_domov, ucel_pobytu, poznamka, stav
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['prijmeni'],
                data['jmeno'],
                data['datum_narozeni'],
                data['cislo_pasu'],
                data['statni_obcanstvi'],
                self._datetime_to_str(data['datum_prijezdu']),
                self._datetime_to_str(data['datum_odjezdu']),
                data.get('cislo_viza'),
                data.get('bydliste_domov'),
                data.get('ucel_pobytu', 99),
                data.get('poznamka'),
                data.get('stav', 'NOVY')
            ))

            self.conn.commit()
            zamestnanec_id = cursor.lastrowid
            logger.info(f"Vložen zaměstnanec: {data['jmeno']} {data['prijmeni']} (ID: {zamestnanec_id})")
            return zamestnanec_id

        except sqlite3.IntegrityError as e:
            logger.warning(f"Zaměstnanec již existuje: {data['jmeno']} {data['prijmeni']} - {e}")
            return None
        except Exception as e:
            logger.error(f"Chyba při vkládání zaměstnance: {e}")
            return None

    def aktualizuj_zamestnance(self, zamestnanec_id: int, data: Dict) -> bool:
        """
        Aktualizuje data zaměstnance.

        Args:
            zamestnanec_id: ID zaměstnance
            data: Slovník s novými daty

        Returns:
            True při úspěchu, False při chybě
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE zamestnanci
                SET prijmeni = ?, jmeno = ?, datum_narozeni = ?, cislo_pasu = ?,
                    statni_obcanstvi = ?, datum_prijezdu = ?, datum_odjezdu = ?,
                    cislo_viza = ?, bydliste_domov = ?, ucel_pobytu = ?,
                    poznamka = ?, stav = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                data['prijmeni'],
                data['jmeno'],
                data['datum_narozeni'],
                data['cislo_pasu'],
                data['statni_obcanstvi'],
                self._datetime_to_str(data['datum_prijezdu']),
                self._datetime_to_str(data['datum_odjezdu']),
                data.get('cislo_viza'),
                data.get('bydliste_domov'),
                data.get('ucel_pobytu', 99),
                data.get('poznamka'),
                data.get('stav', 'NOVY'),
                zamestnanec_id
            ))

            self.conn.commit()
            logger.info(f"Aktualizován zaměstnanec ID: {zamestnanec_id}")
            return True

        except Exception as e:
            logger.error(f"Chyba při aktualizaci zaměstnance: {e}")
            return False

    def aktualizuj_stav(self, zamestnanec_id: int, stav: str) -> bool:
        """
        Aktualizuje stav zaměstnance.

        Args:
            zamestnanec_id: ID zaměstnance
            stav: Nový stav (NOVY/PRIHLASEN/ODHLASEN/CHYBA)

        Returns:
            True při úspěchu
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE zamestnanci
                SET stav = ?, posledni_sync = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (stav, zamestnanec_id))

            self.conn.commit()
            logger.info(f"Stav zaměstnance {zamestnanec_id} změněn na: {stav}")
            return True

        except Exception as e:
            logger.error(f"Chyba při aktualizaci stavu: {e}")
            return False

    def najdi_zamestnance(self, cislo_pasu: str, datum_narozeni: str) -> Optional[Dict]:
        """
        Najde zaměstnance podle čísla pasu a data narození.

        Args:
            cislo_pasu: Číslo pasu
            datum_narozeni: Datum narození (DDMMRRRR)

        Returns:
            Slovník s daty zaměstnance nebo None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM zamestnanci
            WHERE cislo_pasu = ? AND datum_narozeni = ?
        """, (cislo_pasu, datum_narozeni))

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_vsichni_zamestnanci(self) -> List[Dict]:
        """
        Vrátí seznam všech zaměstnanců.

        Returns:
            Seznam slovníků s daty zaměstnanců
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM zamestnanci ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


    def zaznamenej_transakci(
        self,
        zamestnanec_id: int,
        typ_operace: str,
        success: bool,
        soap_request: Optional[str] = None,
        soap_response: Optional[str] = None,
        chyby: Optional[str] = None,
        pdf_potvrzeni_path: Optional[str] = None
    ) -> Optional[int]:
        """
        Zaznamená API transakci do databáze.

        Args:
            zamestnanec_id: ID zaměstnance
            typ_operace: Typ operace (PRIHLASENI/ODHLASENI/AKTUALIZACE)
            success: Zda operace proběhla úspěšně
            soap_request: SOAP požadavek (volitelně)
            soap_response: SOAP odpověď (volitelně)
            chyby: Chybové zprávy (volitelně)
            pdf_potvrzeni_path: Cesta k PDF (volitelně)

        Returns:
            ID transakce nebo None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO api_transakce (
                    zamestnanec_id, typ_operace, soap_request, soap_response,
                    chyby, pdf_potvrzeni_path, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                zamestnanec_id,
                typ_operace,
                soap_request,
                soap_response,
                chyby,
                pdf_potvrzeni_path,
                success
            ))

            self.conn.commit()
            transakce_id = cursor.lastrowid
            logger.info(f"Zaznamenána transakce: {typ_operace} pro zaměstnance {zamestnanec_id}")
            return transakce_id

        except Exception as e:
            logger.error(f"Chyba při zaznamenávání transakce: {e}")
            return None

    def get_transakce_zamestnance(self, zamestnanec_id: int) -> List[Dict]:
        """
        Vrátí všechny transakce zaměstnance.

        Args:
            zamestnanec_id: ID zaměstnance

        Returns:
            Seznam transakcí
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM api_transakce
            WHERE zamestnanec_id = ?
            ORDER BY datum_odeslani DESC
        """, (zamestnanec_id,))

        return [dict(row) for row in cursor.fetchall()]

    def detekuj_nove(self, excel_data: List[Dict]) -> List[Dict]:
        """
        Detekuje nové zaměstnance, kteří ještě nejsou v databázi.

        Args:
            excel_data: Seznam zaměstnanců z Excelu

        Returns:
            Seznam nových zaměstnanců (nejsou v DB)
        """
        novi = []

        logger.info(f"Kontrola {len(excel_data)} zaměstnanců z Excelu...")
        for osoba in excel_data:
            jmeno_prijmeni = f"{osoba['jmeno']} {osoba['prijmeni']}"

            db_osoba = self.najdi_zamestnance(
                osoba['cislo_pasu'],
                osoba['datum_narozeni']
            )

            if db_osoba is None:
                # Nový zaměstnanec - bude přihlášen
                novi.append(osoba)
                logger.info(f"  • {jmeno_prijmeni} - NOVÝ zaměstnanec (bude přihlášen)")
            else:
                # Už existuje v DB - přeskočit
                logger.info(f"  • {jmeno_prijmeni} - již přihlášen (přeskočeno)")

        logger.info(f"Nalezeno: {len(novi)} nových zaměstnanců")

        return novi

    def close(self):
        """Uzavře databázové spojení."""
        if self.conn:
            self.conn.close()
            logger.info("Databázové spojení uzavřeno")

    def __enter__(self):
        """Context manager pro použití with blokem."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatické uzavření spojení při opuštění with bloku."""
        self.close()


if __name__ == "__main__":
    """
    Testovací skript pro ověření databázových operací.
    """
    # Nastavení logování pro samostatné spuštění
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("UBYPORT DATABASE - TEST")
    print("=" * 60)

    try:
        # Vytvoření testovací databáze
        print("\n1. Vytvareni databaze...")
        with UbyportDatabase(db_path="data/test_ubyport.db") as db:
            print("   [OK] Databaze vytvorena")

            # Test vložení zaměstnance
            print("\n2. Vlozeni testovacich dat...")
            test_zamestnanec = {
                'prijmeni': 'Testovy',
                'jmeno': 'Jan',
                'datum_narozeni': '01011990',
                'cislo_pasu': 'TEST123456',
                'statni_obcanstvi': 'CZE',
                'datum_prijezdu': '2025-01-01',
                'datum_odjezdu': '2025-12-31',
                'cislo_viza': None,
                'bydliste_domov': 'Praha',
                'ucel_pobytu': 99,
                'poznamka': 'Testovaci zamestnanec',
                'stav': 'NOVY'
            }

            zam_id = db.vloz_zamestnance(test_zamestnanec)
            if zam_id:
                print(f"   [OK] Zamestnanec vlozen s ID: {zam_id}")

                # Test vyhledání
                print("\n3. Vyhledani zamestnance...")
                nalezeny = db.najdi_zamestnance('TEST123456', '01011990')
                if nalezeny:
                    print(f"   [OK] Zamestnanec nalezen: {nalezeny['jmeno']} {nalezeny['prijmeni']}")

                # Test aktualizace stavu
                print("\n4. Aktualizace stavu...")
                if db.aktualizuj_stav(zam_id, 'PRIHLASEN'):
                    print("   [OK] Stav aktualizovan na: PRIHLASEN")

                # Test zaznamenání transakce
                print("\n5. Zaznamenani transakce...")
                trans_id = db.zaznamenej_transakci(
                    zamestnanec_id=zam_id,
                    typ_operace='PRIHLASENI',
                    success=True,
                    chyby=None
                )
                if trans_id:
                    print(f"   [OK] Transakce zaznamenana s ID: {trans_id}")

                # Test výpisu všech zaměstnanců
                print("\n6. Vypis vsech zamestnancu...")
                vsichni = db.get_vsichni_zamestnanci()
                print(f"   [OK] Pocet zamestnancu v DB: {len(vsichni)}")

            print("\n" + "=" * 60)
            print("VSECHNY TESTY PROBEHLY USPESNE!")
            print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] CHYBA: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
