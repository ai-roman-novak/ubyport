# SPDX-FileCopyrightText: 2025 Aidaro s.r.o.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Aidaro-Commercial-1.0

"""
Modul pro čtení a validaci dat z Excel souborů.

Tento modul obsahuje třídu ExcelReader, která:
- Načítá data zaměstnanců z Excel souboru
- Validuje formáty a povinná pole
- Konvertuje data do správného formátu pro databázi a API
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Logger pro tento modul (konfigurace se nastaví v main.py)
logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Vlastní výjimka pro validační chyby."""
    pass


class ExcelReader:
    """
    Čtení a validace Excel souborů se zaměstnanci.

    Očekávaná struktura Excelu:
    - Příjmení (povinné)
    - Jméno (povinné)
    - Datum narození (povinné) - DDMMRRRR
    - Číslo pasu (povinné)
    - Státní občanství (povinné) - 3písmenný kód
    - Datum příjezdu (povinné)
    - Datum odjezdu (povinné)
    - Číslo víza (nepovinné)
    - Bydliště v domovské zemi (nepovinné)
    - Účel pobytu (nepovinné) - číslo 00-99
    - Poznámka (nepovinné)
    """

    # Mapování názvů sloupců (různé varianty)
    COLUMN_MAPPING = {
        'prijmeni': ['Příjmení', 'prijmeni', 'PRIJMENI', 'Surname'],
        'jmeno': ['Jméno', 'jmeno', 'JMENO', 'Name'],
        'datum_narozeni': ['Datum narození', 'datum_narozeni', 'DATUM_NAROZENI', 'Birth Date', 'Date of Birth'],
        'cislo_pasu': ['Číslo pasu', 'cislo_pasu', 'CISLO_PASU', 'Passport Number', 'Passport', 'Číslo pasu'],
        'statni_obcanstvi': ['Státní občanství', 'statni_obcanstvi', 'STATNI_OBCANSTVI', 'Nationality', 'Občanství'],
        'datum_prijezdu': ['Datum příjezdu', 'datum_prijezdu', 'DATUM_PRIJEZDU', 'Arrival Date', 'Check-in', 'Ubytování od kdy'],
        'datum_odjezdu': ['Datum odjezdu', 'datum_odjezdu', 'DATUM_ODJEZDU', 'Departure Date', 'Check-out', 'Ubytování do kdy'],
        'cislo_viza': ['Číslo víza', 'cislo_viza', 'CISLO_VIZA', 'Visa Number'],
        'bydliste_domov': ['Bydliště v domovské zemi', 'bydliste_domov', 'BYDLISTE_DOMOV', 'Home Address', 'Adresa ubytování'],
        'ucel_pobytu': ['Účel pobytu', 'ucel_pobytu', 'UCEL_POBYTU', 'Purpose of Stay'],
        'poznamka': ['Poznámka', 'poznamka', 'POZNAMKA', 'Note', 'Notes']
    }

    def __init__(self, excel_path: str):
        """
        Inicializace Excel čtečky.

        Args:
            excel_path: Cesta k Excel souboru
        """
        self.excel_path = Path(excel_path)
        self.df = None
        self.errors = []
        logger.info(f"ExcelReader inicializován pro: {excel_path}")

    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalizuje názvy sloupců podle COLUMN_MAPPING.

        Args:
            df: DataFrame s originálními názvy

        Returns:
            DataFrame s normalizovanými názvy
        """
        column_rename = {}

        for standard_name, variants in self.COLUMN_MAPPING.items():
            for col in df.columns:
                if col in variants:
                    column_rename[col] = standard_name
                    break

        if column_rename:
            df = df.rename(columns=column_rename)
            logger.info(f"Normalizovány názvy sloupců: {list(column_rename.keys())}")

        return df

    def _validate_required_columns(self, df: pd.DataFrame) -> bool:
        """
        Zkontroluje, zda jsou přítomny všechny povinné sloupce.

        Args:
            df: DataFrame k validaci

        Returns:
            True pokud jsou všechny povinné sloupce, jinak False
        """
        required = ['prijmeni', 'jmeno', 'datum_narozeni', 'cislo_pasu',
                    'statni_obcanstvi', 'datum_prijezdu', 'datum_odjezdu']

        missing = [col for col in required if col not in df.columns]

        if missing:
            error_msg = f"Chybějící povinné sloupce: {', '.join(missing)}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False

        return True

    def _validate_datum_narozeni(self, datum: str) -> Optional[str]:
        """
        Validuje formát data narození (DDMMRRRR nebo 0000RRRR nebo 00DDRRRR).

        INTELIGENTNÍ OPRAVA:
        - Pokud má datum 7 znaků (chybí nula na začátku), automaticky ji doplní
        - Pokud dostane datetime objekt z Excelu, převede ho na DDMMRRRR formát
        - Automaticky odstraní oddělovače (tečky, pomlčky, lomítka)
          Příklad: DD.MM.YYYY → DDMMYYYY, DD-MM-YYYY → DDMMYYYY

        Args:
            datum: Datum narození jako string nebo datetime objekt

        Returns:
            Validované datum ve formátu DDMMRRRR nebo None
        """
        if pd.isna(datum):
            return None

        # NOVÉ: Pokud je to datetime/Timestamp objekt, převeď na DDMMRRRR
        if isinstance(datum, (datetime, pd.Timestamp)):
            datum_str = datum.strftime('%d%m%Y')
            logger.info(f"Auto-konverze datetime na DDMMRRRR: {datum} → {datum_str}")
            # Pokračujeme validací níže
        else:
            # Převod na string a odstranění mezer
            # Pokud je to int/float (Excel často ukládá jako číslo), použij zfill(8) pro zachování úvodní nuly
            if isinstance(datum, (int, float)):
                datum_str = str(int(datum)).zfill(8)
            else:
                datum_str = str(datum).strip().replace(' ', '')

            # Odstranění oddělovačů (tečky, pomlčky, lomítka)
            # Formáty: DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY → DDMMYYYY
            datum_str = datum_str.replace('.', '').replace('-', '').replace('/', '')

        # Kontrola, že jsou to čísla
        if not datum_str.isdigit():
            return None

        # INTELIGENTNÍ OPRAVA: Pokud má datum 7 znaků, doplň nulu na začátek
        # (Excel často odstraňuje úvodní nuly)
        if len(datum_str) == 7:
            datum_str = '0' + datum_str
            logger.info(f"Auto-oprava data narození: přidána chybějící nula → {datum_str}")

        # Kontrola délky (musí být přesně 8)
        if len(datum_str) != 8:
            return None

        # Kontrola validních formátů
        day = datum_str[:2]
        month = datum_str[2:4]
        year = datum_str[4:]

        # Formát 0000RRRR
        if day == '00' and month == '00':
            return datum_str

        # Formát 00DDRRRR (měsíc jako den, když není znám přesný měsíc)
        if day == '00' and 1 <= int(month) <= 31:
            return datum_str

        # Formát DDMMRRRR (standardní formát)
        if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
            return datum_str

        return None

    def _validate_statni_obcanstvi(self, kod: str) -> Optional[str]:
        """
        Validuje 3písmenný kód státní příslušnosti.

        DŮLEŽITÉ: Systém Ubyport je pouze pro CIZINCE!
        České občanství (CZE/CZ) není povoleno.

        Args:
            kod: Kód státní příslušnosti nebo název země

        Returns:
            Validovaný kód (uppercase) nebo None
        """
        if pd.isna(kod):
            return None

        kod_str = str(kod).strip().upper()

        # Mapování názvů zemí na kódy (pro pohodlí uživatele)
        ZEME_MAPPING = {
            'UKRAJINA': 'UKR',
            'UKRAINE': 'UKR',
            'UKRAINA': 'UKR',
            'SLOVENSKO': 'SVK',
            'SLOVAKIA': 'SVK',
            'POLSKO': 'POL',
            'POLAND': 'POL',
            'NĚMECKO': 'DEU',
            'NEMECKO': 'DEU',
            'GERMANY': 'DEU',
            'RUMUNSKO': 'ROU',
            'ROMANIA': 'ROU',
            'MAĎARSKO': 'HUN',
            'MADARSKO': 'HUN',
            'HUNGARY': 'HUN',
            'RAKOUSKO': 'AUT',
            'AUSTRIA': 'AUT',
        }

        # Pokud je to název země, převeď na kód
        if kod_str in ZEME_MAPPING:
            kod_str = ZEME_MAPPING[kod_str]
            logger.info(f"Auto-konverze názvu země na kód: {kod} → {kod_str}")

        # ZAKÁZANÉ KÓDY: Česká republika není cizí země!
        ZAKAZANE_KODY = ['CZE', 'CZ', 'CZK', 'CZECH', 'ČESKO', 'CESKO', 'ČESKÁ REPUBLIKA', 'CESKA REPUBLIKA']
        if kod_str in ZAKAZANE_KODY or kod.upper() in ZAKAZANE_KODY:
            logger.error(f"Česká republika ({kod}) není povolena - systém Ubyport je pouze pro cizince!")
            return None

        # Musí být 3 písmena
        if len(kod_str) == 3 and kod_str.isalpha():
            return kod_str

        return None

    def _validate_cislo_pasu(self, cislo: str) -> Optional[str]:
        """
        Validuje číslo pasu (4-30 znaků).

        Args:
            cislo: Číslo pasu

        Returns:
            Validované číslo nebo None
        """
        if pd.isna(cislo):
            return None

        cislo_str = str(cislo).strip().upper()

        # Délka 4-30 znaků
        if 4 <= len(cislo_str) <= 30:
            return cislo_str

        return None

    def _validate_jmeno_prijmeni(self, text: str) -> Optional[str]:
        """
        Validuje jméno/příjmení (jen písmena, apostrof, spojník).

        Args:
            text: Jméno nebo příjmení

        Returns:
            Validovaný text nebo None
        """
        if pd.isna(text):
            return None

        text_str = str(text).strip()

        # Povolené znaky: písmena, apostrof, spojník, mezera
        if re.match(r"^[a-zA-ZÀ-ž\s'-]+$", text_str):
            return text_str

        return None

    def _convert_datum(self, datum) -> Optional[datetime]:
        """
        Konvertuje datum do datetime objektu.

        Args:
            datum: Datum (může být string, datetime, apod.)

        Returns:
            datetime objekt nebo None
        """
        if pd.isna(datum):
            return None

        # Pokud je to už datetime
        if isinstance(datum, datetime):
            return datum

        # Pokud je to pandas Timestamp
        if isinstance(datum, pd.Timestamp):
            return datum.to_pydatetime()

        # Pokud je to string, zkusíme parsovat
        if isinstance(datum, str):
            try:
                dt = pd.to_datetime(datum, dayfirst=True)
                return dt.to_pydatetime()
            except:
                logger.warning(f"Nelze parsovat datum: {datum}")
                return None

        return None

    def nacti_excel(self) -> bool:
        """
        Načte Excel soubor do DataFrame.

        Returns:
            True při úspěchu, False při chybě
        """
        try:
            if not self.excel_path.exists():
                error_msg = f"Excel soubor nenalezen: {self.excel_path}"
                self.errors.append(error_msg)
                logger.error(error_msg)
                return False

            # Načtení Excelu
            self.df = pd.read_excel(self.excel_path, engine='openpyxl')

            # Odstranění prázdných řádků
            self.df = self.df.dropna(how='all')

            logger.info(f"Načteno {len(self.df)} řádků z Excelu")

            # Normalizace názvů sloupců
            self.df = self._normalize_column_names(self.df)

            # Zpracování všech řádků z Excelu
            logger.info(f"Automatický režim: zpracování všech {len(self.df)} řádků z Excelu")

            # Validace povinných sloupců
            if not self._validate_required_columns(self.df):
                return False

            return True

        except Exception as e:
            error_msg = f"Chyba při čtení Excelu: {e}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False

    def validuj_a_preved(self) -> List[Dict]:
        """
        Validuje a převádí data z DataFrame do seznamu slovníků.

        Returns:
            Seznam validovaných zaměstnanců
        """
        if self.df is None:
            logger.error("DataFrame není načten")
            return []

        validovani = []
        chybne_radky = []

        for idx, row in self.df.iterrows():
            radek_chyby = []

            # Validace jména a příjmení
            jmeno = self._validate_jmeno_prijmeni(row.get('jmeno'))
            if not jmeno:
                radek_chyby.append(f"Neplatné jméno")

            prijmeni = self._validate_jmeno_prijmeni(row.get('prijmeni'))
            if not prijmeni:
                radek_chyby.append(f"Neplatné příjmení")

            # Validace data narození
            datum_narozeni = self._validate_datum_narozeni(row.get('datum_narozeni'))
            if not datum_narozeni:
                radek_chyby.append(f"Neplatné datum narození (musí být DDMMRRRR)")

            # Validace čísla pasu
            cislo_pasu = self._validate_cislo_pasu(row.get('cislo_pasu'))
            if not cislo_pasu:
                radek_chyby.append(f"Neplatné číslo pasu (4-30 znaků)")

            # Validace státní příslušnosti
            statni_obcanstvi_raw = row.get('statni_obcanstvi')
            statni_obcanstvi = self._validate_statni_obcanstvi(statni_obcanstvi_raw)
            if not statni_obcanstvi:
                # Zkontroluj, zda je problém v českém občanství
                if pd.notna(statni_obcanstvi_raw):
                    kod_upper = str(statni_obcanstvi_raw).strip().upper()
                    ZAKAZANE_KODY = ['CZE', 'CZ', 'CZK', 'CZECH', 'ČESKO', 'CESKO', 'ČESKÁ REPUBLIKA', 'CESKA REPUBLIKA']
                    if kod_upper in ZAKAZANE_KODY:
                        radek_chyby.append(f"České občanství není povoleno (systém Ubyport je pouze pro cizince)")
                    else:
                        radek_chyby.append(f"Neplatná státní příslušnost (musí být 3 písmena, např. DEU, POL, UKR)")
                else:
                    radek_chyby.append(f"Neplatná státní příslušnost (musí být 3 písmena, např. DEU, POL, UKR)")

            # Konverze datumů
            datum_prijezdu = self._convert_datum(row.get('datum_prijezdu'))
            if not datum_prijezdu:
                radek_chyby.append(f"Neplatné datum příjezdu")

            datum_odjezdu = self._convert_datum(row.get('datum_odjezdu'))
            if not datum_odjezdu:
                radek_chyby.append(f"Neplatné datum odjezdu")

            # Pokud jsou chyby, zaznamenej a pokračuj
            if radek_chyby:
                chybne_radky.append({
                    'radek': idx + 2,  # +2 protože Excel začíná od 1 a máme hlavičku
                    'chyby': radek_chyby,
                    'data': f"{jmeno} {prijmeni}"
                })
                continue

            # Vytvoření validovaného záznamu
            # Poznámka: datum_prijezdu a datum_odjezdu jsou datetime objekty pro SOAP API,
            # ale v databázi se ukládají jako ISO string
            zamestnanec = {
                'prijmeni': prijmeni,
                'jmeno': jmeno,
                'datum_narozeni': datum_narozeni,
                'cislo_pasu': cislo_pasu,
                'statni_obcanstvi': statni_obcanstvi,
                'datum_prijezdu': datum_prijezdu,  # datetime objekt
                'datum_odjezdu': datum_odjezdu,  # datetime objekt
                'cislo_viza': str(row.get('cislo_viza', '')).strip() if pd.notna(row.get('cislo_viza')) else None,
                'bydliste_domov': str(row.get('bydliste_domov', '')).strip() if pd.notna(row.get('bydliste_domov')) else None,
                'ucel_pobytu': int(row.get('ucel_pobytu', 99)) if pd.notna(row.get('ucel_pobytu')) else 99,
                'poznamka': str(row.get('poznamka', '')).strip() if pd.notna(row.get('poznamka')) else None
            }

            validovani.append(zamestnanec)

        # Logování chybných řádků
        if chybne_radky:
            logger.warning(f"Počet chybných řádků: {len(chybne_radky)}")
            for chyba in chybne_radky:
                logger.warning(f"  Řádek {chyba['radek']} ({chyba['data']}): {', '.join(chyba['chyby'])}")
                self.errors.append(f"Řádek {chyba['radek']}: {', '.join(chyba['chyby'])}")

        logger.info(f"Validováno: {len(validovani)} zaměstnanců, {len(chybne_radky)} chyb")

        return validovani

    def get_errors(self) -> List[str]:
        """
        Vrátí seznam všech chyb.

        Returns:
            Seznam chybových zpráv
        """
        return self.errors


if __name__ == "__main__":
    """
    Testovací skript pro čtení Excelu.
    """
    # Nastavení logování pro samostatné spuštění
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("EXCEL READER - TEST")
    print("=" * 60)

    print("\n[INFO] Pro test je potreba vytvorit Excel soubor:")
    print("       data/zamestnanci.xlsx")
    print("\n[INFO] Excel musi obsahovat sloupce:")
    print("       - Příjmení, Jméno, Datum narození (DDMMRRRR),")
    print("       - Číslo pasu, Státní občanství (3 písmena),")
    print("       - Datum příjezdu, Datum odjezdu")
    print("\n" + "=" * 60)
