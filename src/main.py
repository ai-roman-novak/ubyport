# SPDX-FileCopyrightText: 2025 Aidaro s.r.o.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Aidaro-Commercial-1.0

"""
Hlavní program pro automatizaci Ubyport hlášení.

Tento modul spojuje všechny komponenty dohromady:
1. Načte data z Excelu
2. Porovná s databází (detekce změn)
3. Odešle nová/změněná data do Ubyportu
4. Aktualizuje databázi
5. Vytvoří report
"""

import sys
import logging
import shutil
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Přidání src do path (pro import modulů)
sys.path.insert(0, str(Path(__file__).parent))

from excel_reader import ExcelReader
from database import UbyportDatabase
from soap_client import UbyportClient
from export_excel import ExcelExporter
from config import EXCEL_PATH, DB_PATH, BACKUP_DIR

# Nastavení logování
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"ubyport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def vytvor_backup_databaze(db_path: str) -> str:
    """
    Vytvoří zálohu databáze a udržuje max 10 posledních backupů.

    Args:
        db_path: Cesta k databázi

    Returns:
        Cesta k vytvořenému backupu
    """
    db_path = Path(db_path)

    if not db_path.exists():
        logger.warning(f"Databáze {db_path} neexistuje - backup nebude vytvořen")
        return None

    # Vytvoření názvu backupu
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"ubyport_backup_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name

    # Vytvoření backupu
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"Backup databáze vytvořen: {backup_path}")
    except Exception as e:
        logger.error(f"Chyba při vytváření backupu: {e}")
        return None

    # Vymazání starých backupů (ponechat max 10)
    try:
        backupy = sorted(BACKUP_DIR.glob("ubyport_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)

        if len(backupy) > 10:
            for stary_backup in backupy[10:]:
                stary_backup.unlink()
                logger.info(f"Smazán starý backup: {stary_backup.name}")
    except Exception as e:
        logger.warning(f"Chyba při mazání starých backupů: {e}")

    return str(backup_path)


def zobraz_prehled_a_potvrd(nove: int, zmeneni: int, auto_confirm: bool = False) -> bool:
    """
    Zobrazí přehled a zeptá se uživatele na potvrzení.

    Args:
        nove: Počet nových k přihlášení
        zmeneni: Nepoužívá se (kompatibilita)
        auto_confirm: Pokud True, automaticky potvrdí bez ptaní

    Returns:
        True pokud pokračovat, False pokud ukončit
    """
    print("\n" + "═" * 63)
    print("PŘEHLED K ODESLÁNÍ")
    print("═" * 63)
    print(f"  ▸ Nových k přihlášení:  {nove}")
    print("═" * 63)

    if auto_confirm:
        print("Automatický režim (--yes) - pokračuji bez potvrzení...\n")
        return True

    try:
        odpoved = input("\nPokračovat s odesláním? [y/n]: ").strip().lower()

        if odpoved in ['y', 'yes', 'ano']:
            logger.info("Uživatel potvrdil odeslání")
            return True
        else:
            logger.info("Uživatel zrušil odeslání")
            print("\nOdeslání zrušeno uživatelem.")
            return False
    except (KeyboardInterrupt, EOFError):
        print("\n\nOdeslání zrušeno uživatelem.")
        logger.info("Uživatel zrušil odeslání (Ctrl+C)")
        return False


class UbyportAutomation:
    """
    Hlavní třída pro automatizaci Ubyport hlášení.
    """

    def __init__(
        self,
        excel_path: str = None,
        db_path: str = None,
        environment: str = "test",
        dry_run: bool = False,
        auto_confirm: bool = False
    ):
        """
        Inicializace automatizace.

        Args:
            excel_path: Cesta k Excel souboru (pokud None, použije se cesta z config.py)
            db_path: Cesta k databázi (pokud None, použije se cesta z config.py)
            environment: Prostředí (test/production)
            dry_run: Pokud True, pouze simulace bez odesílání
            auto_confirm: Pokud True, automaticky potvrdí bez ptaní
        """
        if excel_path is None:
            excel_path = str(EXCEL_PATH)
        if db_path is None:
            db_path = str(DB_PATH)

        self.excel_path = excel_path
        self.db_path = db_path
        self.environment = environment
        self.dry_run = dry_run
        self.auto_confirm = auto_confirm

        # Statistiky
        self.stats = {
            'nove_prihlasen': 0,
            'chyby': 0,
            'celkem_zpracovano': 0,
            'preskoceno_validace': 0,
            'validacni_chyby': []
        }

        logger.info("=" * 80)
        logger.info("UBYPORT AUTOMATIZACE - START")
        logger.info(f"Prostředí: {environment}")
        logger.info(f"Režim: {'DRY-RUN (simulace)' if dry_run else 'STANDARDNÍ'}")
        logger.info(f"Potvrzení: {'Automatické (--yes)' if auto_confirm else 'Interaktivní'}")
        logger.info(f"Excel: {excel_path}")
        logger.info(f"Databáze: {db_path}")
        logger.info("=" * 80)

    def _priprav_osobu_pro_api(self, osoba: Dict) -> Dict:
        """
        Připraví data osoby pro odeslání do API.
        Zajišťuje, že datumy jsou datetime objekty.

        Args:
            osoba: Slovník s daty osoby

        Returns:
            Osoba s datetime objekty
        """
        from datetime import datetime

        osoba_copy = osoba.copy()

        # Zajištění, že datumy jsou datetime objekty
        # (data z Excelu už jsou datetime, data z DB jsou ISO stringy)
        prijezd = osoba['datum_prijezdu']
        odjezd = osoba['datum_odjezdu']

        if isinstance(prijezd, str):
            osoba_copy['datum_prijezdu'] = datetime.fromisoformat(prijezd)
        elif not isinstance(prijezd, datetime):
            osoba_copy['datum_prijezdu'] = datetime.fromisoformat(str(prijezd))

        if isinstance(odjezd, str):
            osoba_copy['datum_odjezdu'] = datetime.fromisoformat(odjezd)
        elif not isinstance(odjezd, datetime):
            osoba_copy['datum_odjezdu'] = datetime.fromisoformat(str(odjezd))

        return osoba_copy

    def zpracuj_nove_zamestnance(
        self,
        nove: List[Dict],
        db: UbyportDatabase,
        api: UbyportClient
    ) -> None:
        """
        Zpracuje nové zaměstnance (přihlášení do Ubyportu).

        Args:
            nove: Seznam nových zaměstnanců
            db: Databázové spojení
            api: API klient
        """
        if not nove:
            logger.info("Žádní noví zaměstnanci k přihlášení")
            return

        logger.info(f"\n{'='*60}")
        logger.info(f"PŘIHLAŠOVÁNÍ NOVÝCH ZAMĚSTNANCŮ: {len(nove)}")
        logger.info(f"{'='*60}")

        # Rozdělení do dávek po 32 osobách (limit API)
        batch_size = 32
        for i in range(0, len(nove), batch_size):
            batch = nove[i:i + batch_size]
            logger.info(f"\nDávka {i//batch_size + 1}: {len(batch)} osob")

            # Příprava dat pro API
            batch_api = [self._priprav_osobu_pro_api(osoba) for osoba in batch]

            # Odeslání do API
            uspech, response = api.zapis_ubytovane(batch_api, vracet_pdf=True)

            # Získání PDF info (přijaté/nepřijaté záznamy)
            pdf_info = response.get('PdfInfo', {})
            neprijati_set = set()
            if pdf_info.get('neprijati'):
                for neprijaty in pdf_info['neprijati']:
                    klic = f"{neprijaty['prijmeni']}_{neprijaty['jmeno']}".upper()
                    neprijati_set.add(klic)

            # Zpracování výsledků
            for idx, osoba in enumerate(batch):
                # Vložení do databáze
                zamestnanec_id = db.vloz_zamestnance(osoba)

                if zamestnanec_id:
                    # Kontrola, zda byl přijat policií (z PDF)
                    klic_osoba = f"{osoba['prijmeni']}_{osoba['jmeno']}".upper()
                    byl_neprijat = klic_osoba in neprijati_set

                    # Určení stavu podle výsledku API A PDF
                    if uspech and not byl_neprijat:
                        stav = 'PRIHLASEN'
                        db.aktualizuj_stav(zamestnanec_id, stav)
                        self.stats['nove_prihlasen'] += 1
                        logger.info(f"  ✓ {osoba['jmeno']} {osoba['prijmeni']} - PŘIHLÁŠEN")
                    else:
                        self.stats['chyby'] += 1

                        # Zjištění důvodu chyby a určení stavu
                        if byl_neprijat:
                            chyba_text = next((n['chyba'] for n in pdf_info['neprijati']
                                             if f"{n['prijmeni']}_{n['jmeno']}".upper() == klic_osoba), "Nepřijato")
                            # Rozlišení duplicity od jiných chyb
                            if 'duplicit' in chyba_text.lower():
                                stav = 'ERR_DUPLICITA'
                                logger.error(f"  ✗ {osoba['jmeno']} {osoba['prijmeni']} - ERR_DUPLICITA: již existuje v systému policie")
                            else:
                                stav = 'CHYBA'
                                logger.error(f"  ✗ {osoba['jmeno']} {osoba['prijmeni']} - NEPŘIJATO: {chyba_text}")
                        else:
                            stav = 'CHYBA'
                            logger.error(f"  ✗ {osoba['jmeno']} {osoba['prijmeni']} - CHYBA API")

                        db.aktualizuj_stav(zamestnanec_id, stav)

                    # Zaznamenání transakce
                    chyby_text = None
                    if byl_neprijat:
                        chyby_text = next((n['chyba'] for n in pdf_info['neprijati']
                                         if f"{n['prijmeni']}_{n['jmeno']}".upper() == klic_osoba), None)
                    elif not uspech:
                        chyby_text = str(response.get('ChybyHlavicky'))

                    db.zaznamenej_transakci(
                        zamestnanec_id=zamestnanec_id,
                        typ_operace='PRIHLASENI',
                        success=(uspech and not byl_neprijat),
                        chyby=chyby_text,
                        pdf_potvrzeni_path=response.get('DokumentPotvrzeni')
                    )
                else:
                    self.stats['chyby'] += 1
                    logger.error(f"  ✗ {osoba['jmeno']} {osoba['prijmeni']} - Chyba při vkládání do DB")

                self.stats['celkem_zpracovano'] += 1

    def vytiskni_report(self):
        """Vytiskne závěrečný report."""
        logger.info(f"\n{'='*80}")
        logger.info("ZÁVĚREČNÝ REPORT")
        logger.info(f"{'='*80}")
        logger.info(f"Nově přihlášeno:     {self.stats['nove_prihlasen']:>5}")
        logger.info(f"Chyby při odesílání: {self.stats['chyby']:>5}")
        logger.info(f"{'='*80}")
        logger.info(f"Celkem zpracováno:   {self.stats['celkem_zpracovano']:>5}")

        # REPORT O PŘESKOČENÝCH ZÁZNAMECH
        if self.stats['preskoceno_validace'] > 0:
            logger.warning(f"{'='*80}")
            logger.warning(f"⚠️  PŘESKOČENÉ ZÁZNAMY (VALIDAČNÍ CHYBY)")
            logger.warning(f"{'='*80}")
            logger.warning(f"Počet přeskočených:  {self.stats['preskoceno_validace']:>5}")
            logger.warning(f"\nDůvody:")
            for chyba in self.stats['validacni_chyby']:
                logger.warning(f"  ⊘ {chyba}")
            logger.warning(f"{'='*80}")

        logger.info(f"{'='*80}")
        logger.info(f"Log uložen do: {log_file}")
        logger.info(f"{'='*80}\n")

    def spust(self) -> bool:
        """
        Spustí celý workflow automatizace.

        Returns:
            True při úspěchu, False při chybě
        """
        try:
            # 1. NAČTENÍ EXCELU
            logger.info("\n[1/6] Načítání dat z Excelu...")
            excel = ExcelReader(self.excel_path)

            if not excel.nacti_excel():
                logger.error("Chyba při načítání Excelu")
                for error in excel.get_errors():
                    logger.error(f"  - {error}")
                return False

            excel_data = excel.validuj_a_preved()

            # KONTROLA VALIDAČNÍCH CHYB - VAROVÁNÍ, ale POKRAČUJ
            validacni_chyby = excel.get_errors()
            if validacni_chyby:
                logger.warning(f"\n{'='*80}")
                logger.warning(f"⚠️  VALIDAČNÍ CHYBY - Následující záznamy budou PŘESKOČENY")
                logger.warning(f"{'='*80}")
                logger.warning(f"Nalezeno {len(validacni_chyby)} chybných záznamů:")
                for error in validacni_chyby:
                    logger.warning(f"  ⊘ {error}")
                    self.stats['validacni_chyby'].append(error)
                    self.stats['preskoceno_validace'] += 1
                logger.warning(f"{'='*80}")
                logger.warning(f"Pokračuji se zpracováním {len(excel_data)} validních záznamů...")
                logger.warning(f"{'='*80}\n")

            if not excel_data:
                logger.warning("Žádná validní data v Excelu")
                if validacni_chyby:
                    logger.warning("Všechny záznamy obsahují chyby - nelze pokračovat")
                return False

            logger.info(f"  ✓ Načteno {len(excel_data)} validních zaměstnanců z Excelu")
            if validacni_chyby:
                logger.info(f"  ⊘ Přeskočeno {len(validacni_chyby)} chybných záznamů")

            # 2. PŘIPOJENÍ K DATABÁZI
            logger.info("\n[2/6] Připojení k databázi...")
            with UbyportDatabase(self.db_path) as db:
                logger.info("  ✓ Databáze připravena")

                # 3. DETEKCE NOVÝCH ZAMĚSTNANCŮ
                logger.info("\n[3/6] Detekce nových zaměstnanců...")
                nove = db.detekuj_nove(excel_data)

                logger.info(f"  - Nových k přihlášení: {len(nove)}")

                if not nove:
                    logger.info("\n✓ Žádní noví zaměstnanci k přihlášení!")
                    return True

                # INTERAKTIVNÍ POTVRZENÍ (nebo dry-run report)
                if self.dry_run:
                    print("\n" + "═" * 63)
                    print("DRY-RUN MÓD - PŘEHLED (bez odeslání)")
                    print("═" * 63)
                    print(f"  ▸ Nových k přihlášení:  {len(nove)}")
                    print("═" * 63)
                    print("\nDRY-RUN MÓD - žádná data nebyla odeslána")
                    logger.info("DRY-RUN MÓD - ukončeno bez odeslání")
                    return True

                # Zobrazení přehledu a potvrzení
                if not zobraz_prehled_a_potvrd(len(nove), 0, self.auto_confirm):
                    logger.info("Program ukončen uživatelem")
                    return True

                # BACKUP DATABÁZE (před odesíláním)
                logger.info("\nVytvářím backup databáze...")
                backup_path = vytvor_backup_databaze(self.db_path)
                if backup_path:
                    logger.info(f"  ✓ Backup vytvořen: {backup_path}")
                else:
                    logger.warning("  ! Backup se nepodařilo vytvořit")

                # 4. PŘIPOJENÍ K API
                logger.info("\n[4/6] Připojení k Ubyport API...")
                api = UbyportClient(environment=self.environment)

                # Test dostupnosti
                if not api.test_dostupnosti():
                    logger.error("API není dostupné!")
                    return False

                logger.info("  ✓ API je dostupné")

                # 5. PŘIHLÁŠENÍ NOVÝCH ZAMĚSTNANCŮ
                logger.info("\n[5/6] Přihlašování nových zaměstnanců do Ubyportu...")
                self.zpracuj_nove_zamestnance(nove, db, api)

            # ZÁVĚREČNÝ REPORT
            self.vytiskni_report()

            # EXPORT DO EXCELU
            logger.info("\n[6/6] Export výsledků do Excelu...")
            try:
                exporter = ExcelExporter(self.db_path)

                # Kompletní export (všichni včetně chyb)
                export_result = exporter.export_vse()
                logger.info(f"  ✓ Kompletní export: {export_result['path']}")
                logger.info(f"    - Zaměstnanců: {export_result['zamestnanci']}")
                logger.info(f"    - Transakcí: {export_result['transakce']}")

                # Export potvrzení policie (pouze PRIHLASEN)
                potvrzeni_result = exporter.export_potvrzeni_policie()
                if potvrzeni_result['path']:
                    logger.info(f"  ✓ Export potvrzení policie: {potvrzeni_result['path']}")
                    logger.info(f"    - Potvrzených u policie: {potvrzeni_result['count']}")
                else:
                    logger.info(f"  ⊘ Žádní zaměstnanci se stavem PRIHLASEN")
            except Exception as e:
                logger.warning(f"  ! Chyba při exportu: {e}")

            return True

        except KeyboardInterrupt:
            logger.warning("\n\nProgram přerušen uživatelem (Ctrl+C)")
            return False
        except Exception as e:
            logger.error(f"\n\nNEOČEKÁVANÁ CHYBA: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Hlavní funkce programu."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Ubyport automatizace - hlášení ubytování cizinců'
    )
    parser.add_argument(
        '--excel',
        default=None,
        help='Cesta k Excel souboru (default: cesta z config.py)'
    )
    parser.add_argument(
        '--db',
        default=None,
        help='Cesta k databázi (default: cesta z config.py)'
    )
    parser.add_argument(
        '--env',
        choices=['test', 'production'],
        default='test',
        help='Prostředí (default: test)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulace - zobrazí změny bez odeslání do API'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        dest='auto_confirm',
        help='Automatické potvrzení bez ptaní (pro automatizaci)'
    )

    args = parser.parse_args()

    # Spuštění automatizace
    automation = UbyportAutomation(
        excel_path=args.excel,
        db_path=args.db,
        environment=args.env,
        dry_run=args.dry_run,
        auto_confirm=args.auto_confirm
    )

    uspech = automation.spust()

    # Exit kód
    sys.exit(0 if uspech else 1)


if __name__ == "__main__":
    main()
