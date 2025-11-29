# SPDX-FileCopyrightText: 2025 Aidaro s.r.o.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Aidaro-Commercial-1.0

"""
SOAP klient pro komunikaci s Ubyport API.

Tento modul obsahuje třídu UbyportClient, která zapouzdřuje veškerou komunikaci
s webovou službou Ubyport prostřednictvím SOAP protokolu s NTLM autentizací.
"""

import json
import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from requests_ntlm import HttpNtlmAuth
from zeep import Client, Transport, Settings
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin
from PyPDF2 import PdfReader

from config import PDF_DIR

# Logger pro tento modul (konfigurace se nastaví v main.py)
logger = logging.getLogger(__name__)


class UbyportClient:
    """
    Klient pro komunikaci s Ubyport SOAP API.

    Poskytuje metody pro:
    - Test dostupnosti služby
    - Zápis ubytovaných osob
    - Získání číselníků (státy, účely pobytu, chyby)
    - Získání maximální délky seznamu
    """

    def __init__(self, environment: str = "test", config_path: str = "config/credentials.json"):
        """
        Inicializace SOAP klienta.

        Args:
            environment: Prostředí ("test" nebo "production")
            config_path: Cesta k souboru s credentials
        """
        self.environment = environment
        self.config = self._load_config(config_path)
        self.history = HistoryPlugin()  # Pro debugging SOAP zpráv
        self.client = self._create_client()

        logger.info(f"UbyportClient inicializován pro prostředí: {environment}")

    def _load_config(self, config_path: str) -> Dict:
        """Načte konfiguraci z JSON souboru."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config[self.environment]
        except FileNotFoundError:
            logger.error(f"Konfigurační soubor nenalezen: {config_path}")
            raise
        except KeyError:
            logger.error(f"Prostředí '{self.environment}' nenalezeno v konfiguraci")
            raise
        except json.JSONDecodeError:
            logger.error(f"Chyba při parsování JSON souboru: {config_path}")
            raise

    def _create_client(self) -> Client:
        """
        Vytvoří SOAP klienta s NTLM autentizací.

        Returns:
            Zeep Client objekt
        """
        # Vytvoření session s NTLM autentizací
        session = requests.Session()
        session.auth = HttpNtlmAuth(
            f"{self.config['domain']}\\{self.config['username']}",
            self.config['password']
        )

        # Vytvoření transportu
        transport = Transport(session=session)

        # Nastavení klienta (vypnutí strict mode kvůli starému WSDL)
        settings = Settings(strict=False, xml_huge_tree=True)

        # Vytvoření SOAP klienta s history pluginem
        client = Client(
            wsdl=self.config['wsdl'],
            transport=transport,
            settings=settings,
            plugins=[self.history]
        )

        return client

    def test_dostupnosti(self) -> bool:
        """
        Otestuje dostupnost služby včetně backendu.

        Returns:
            True pokud je služba dostupná, jinak False
        """
        try:
            # AutentificationCode je formální parametr, použijeme "X"
            result = self.client.service.TestDostupnosti(AutentificationCode="X")
            logger.info(f"Test dostupnosti: {result}")
            return result
        except Fault as e:
            logger.error(f"SOAP Fault při testu dostupnosti: {e}")
            return False
        except Exception as e:
            logger.error(f"Chyba při testu dostupnosti: {e}")
            return False

    def max_delka_seznamu(self) -> int:
        """
        Vrátí maximální počet osob, které lze odeslat v jednom požadavku.

        Returns:
            Maximální počet osob (typicky 32)
        """
        try:
            result = self.client.service.MaximalniDelkaSeznamu(AutentificationCode="X")
            logger.info(f"Maximální délka seznamu: {result}")
            return result
        except Fault as e:
            logger.error(f"SOAP Fault při zjišťování max délky: {e}")
            return 32  # Defaultní hodnota
        except Exception as e:
            logger.error(f"Chyba při zjišťování max délky: {e}")
            return 32  # Defaultní hodnota

    def dej_mi_ciselnik(self, druh: str) -> List[Dict]:
        """
        Získá číselník z API.

        Args:
            druh: Druh číselníku ("Staty", "UcelyPobytu", "Chyby")

        Returns:
            Seznam slovníků s daty číselníku
        """
        try:
            result = self.client.service.DejMiCiselnik(
                AutentificationCode="X",
                CoChci=druh
            )

            # Převod objektů na slovníky
            ciselnik = []
            for item in result:
                ciselnik.append({
                    'Id': item.Id,
                    'Kod2': item.Kod2,
                    'Kod3': item.Kod3,
                    'TextCZ': item.TextCZ,
                    'TextKratkyCZ': item.TextKratkyCZ,
                    'TextENG': item.TextENG,
                    'TextKratkyENG': item.TextKratkyENG,
                    'PlatiOd': item.PlatiOd,
                    'PlatiDo': item.PlatiDo
                })

            logger.info(f"Číselník '{druh}' načten: {len(ciselnik)} položek")
            return ciselnik

        except Fault as e:
            logger.error(f"SOAP Fault při načítání číselníku: {e}")
            return []
        except Exception as e:
            logger.error(f"Chyba při načítání číselníku: {e}")
            return []

    def _vytvor_ubytovany(self, osoba: Dict) -> Dict:
        """
        Vytvoří strukturu Ubytovany pro SOAP požadavek.

        Args:
            osoba: Slovník s daty osoby

        Returns:
            Slovník připravený pro SOAP
        """
        return {
            'cFrom': osoba['datum_prijezdu'].isoformat(),
            'cUntil': osoba['datum_odjezdu'].isoformat(),
            'cSurN': osoba['prijmeni'],
            'cFirstN': osoba['jmeno'],
            'cDate': osoba['datum_narozeni'],  # Formát DDMMRRRR
            'cNati': osoba['statni_obcanstvi'],  # 3písmenný kód
            'cDocN': osoba['cislo_pasu'],
            'cVisN': osoba.get('cislo_viza', None),
            'cResi': osoba.get('bydliste_domov', None),
            'cPurp': osoba.get('ucel_pobytu', 99),  # Default 99
            'cNote': osoba.get('poznamka', None)
        }

    def zapis_ubytovane(
        self,
        osoby: List[Dict],
        vracet_pdf: bool = True
    ) -> Tuple[bool, Dict]:
        """
        Zapíše seznam ubytovaných osob do Ubyportu.

        Args:
            osoby: Seznam slovníků s daty osob
            vracet_pdf: Zda vrátit PDF potvrzení

        Returns:
            Tuple (úspěch, data odpovědi)
            - úspěch: True pokud nedošlo k chybě
            - data: Slovník s chybami, PDF dokumenty atd.
        """
        try:
            # Kontrola počtu osob
            max_delka = self.max_delka_seznamu()
            if len(osoby) > max_delka:
                logger.error(f"Příliš mnoho osob v seznamu: {len(osoby)} > {max_delka}")
                return False, {
                    'ChybyHlavicky': f'Počet osob překračuje limit {max_delka}',
                    'ChybyZaznamu': [],
                    'DokumentPotvrzeni': None,
                    'DokumentChybyPotvrzeni': None,
                    'PseudoRazitko': None
                }

            # Získání typů z WSDL pomocí client.get_type() s plným namespace
            # Správný namespace: http://schemas.datacontract.org/2004/07/WS_UBY
            Ubytovany = self.client.get_type('{http://schemas.datacontract.org/2004/07/WS_UBY}Ubytovany')
            ArrayOfUbytovany = self.client.get_type('{http://schemas.datacontract.org/2004/07/WS_UBY}ArrayOfUbytovany')
            SeznamUbytovanych = self.client.get_type('{http://schemas.datacontract.org/2004/07/WS_UBY}SeznamUbytovanych')

            # Vytvoření seznamu ubytovaných pomocí získaných typů
            ubytovani_list = []
            for osoba in osoby:
                ubytovany_obj = Ubytovany(
                    cFrom=osoba['datum_prijezdu'].isoformat(),
                    cUntil=osoba['datum_odjezdu'].isoformat(),
                    cSurN=osoba['prijmeni'],
                    cFirstN=osoba['jmeno'],
                    cDate=osoba['datum_narozeni'],
                    cNati=osoba['statni_obcanstvi'],
                    cDocN=osoba['cislo_pasu'],
                    cVisN=osoba.get('cislo_viza'),
                    cResi=osoba.get('bydliste_domov'),
                    cPurp=osoba.get('ucel_pobytu', 99),
                    cNote=osoba.get('poznamka')
                )
                ubytovani_list.append(ubytovany_obj)

            # Vytvoření ArrayOfUbytovany
            ubytovani = ArrayOfUbytovany(Ubytovany=ubytovani_list)

            # Vytvoření struktury SeznamUbytovanych pomocí získaného typu
            seznam = SeznamUbytovanych(
                VracetPDF=vracet_pdf,
                uIdub=self.config['idub'],
                uMark=self.config['mark'],
                uName=self.config['name'],
                uCont=self.config['contact'],
                uOkr=self.config['address']['okres'],
                uOb=self.config['address']['obec'],
                uObCa=self.config['address']['cast_obce'],
                uStr=self.config['address']['ulice'],
                uHomN=self.config['address']['cislo_popisne'],
                uOriN=self.config['address']['cislo_orientacni'],
                uPsc=self.config['address']['psc'],
                Ubytovani=ubytovani
            )

            # Volání SOAP služby
            logger.info(f"Odesílám {len(osoby)} osob do Ubyportu...")

            result = self.client.service.ZapisUbytovane(
                AutentificationCode="X",
                Seznam=seznam
            )

            # Zpracování odpovědi
            response_data = {
                'ChybyHlavicky': result.ChybyHlavicky if hasattr(result, 'ChybyHlavicky') else None,
                'ChybyZaznamu': [],
                'DokumentPotvrzeni': None,
                'DokumentChybyPotvrzeni': None,
                'PseudoRazitko': result.PseudoRazitko if hasattr(result, 'PseudoRazitko') else None
            }

            # Zpracování chyb záznamů
            if hasattr(result, 'ChybyZaznamu') and result.ChybyZaznamu:
                response_data['ChybyZaznamu'] = [str(chyba) for chyba in result.ChybyZaznamu]

            # Zpracování PDF dokumentů
            if vracet_pdf:
                if hasattr(result, 'DokumentPotvrzeni') and result.DokumentPotvrzeni:
                    pdf_path = self._uloz_pdf(
                        result.DokumentPotvrzeni,
                        f"potvrzeni_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    )
                    response_data['DokumentPotvrzeni'] = pdf_path

                    # Parsování PDF a přidání do response
                    if pdf_path:
                        pdf_info = self._parsuj_pdf_potvrzeni(pdf_path)
                        response_data['PdfInfo'] = pdf_info

                if hasattr(result, 'DokumentChybyPotvrzeni') and result.DokumentChybyPotvrzeni:
                    response_data['DokumentChybyPotvrzeni'] = self._uloz_pdf(
                        result.DokumentChybyPotvrzeni,
                        f"chyby_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    )

            # Vyhodnocení úspěchu
            # Chyby začínající "1" jsou kritické, "2" jsou varování
            uspech = True
            if response_data['ChybyHlavicky']:
                chyby_hlavicky = response_data['ChybyHlavicky'].split(';')
                kriticky = any(c.startswith('1') for c in chyby_hlavicky if c)
                if kriticky:
                    uspech = False
                    logger.error(f"Kritické chyby v hlavičce: {response_data['ChybyHlavicky']}")

            if response_data['ChybyZaznamu']:
                for chyby_zaznamu in response_data['ChybyZaznamu']:
                    chyby = chyby_zaznamu.split(';')
                    kriticky = any(c.startswith('1') for c in chyby if c)
                    if kriticky:
                        uspech = False
                        logger.error(f"Kritické chyby v záznamu: {chyby_zaznamu}")

            if uspech:
                logger.info("Zápis ubytovaných proběhl úspěšně")

            return uspech, response_data

        except Fault as e:
            logger.error(f"SOAP Fault při zápisu ubytovaných: {e}")

            # Při chybě uložit debug XML pro analýzu
            if self.history.last_sent:
                try:
                    from lxml import etree
                    xml_content = etree.tostring(self.history.last_sent['envelope'], encoding='unicode', pretty_print=True)
                    debug_path = Path("logs/soap_request_error.xml")
                    debug_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(xml_content)
                    logger.info(f"SOAP request uložen do: {debug_path}")
                except Exception as debug_err:
                    logger.warning(f"Nelze uložit debug XML: {debug_err}")

            return False, {
                'ChybyHlavicky': str(e),
                'ChybyZaznamu': [],
                'DokumentPotvrzeni': None,
                'DokumentChybyPotvrzeni': None,
                'PseudoRazitko': None
            }
        except Exception as e:
            logger.error(f"Chyba při zápisu ubytovaných: {e}")
            return False, {
                'ChybyHlavicky': str(e),
                'ChybyZaznamu': [],
                'DokumentPotvrzeni': None,
                'DokumentChybyPotvrzeni': None,
                'PseudoRazitko': None
            }

    def _parsuj_pdf_potvrzeni(self, pdf_path: str) -> Dict:
        """
        Parsuje PDF potvrzení a extrahuje informace o přijatých/nepřijatých záznamech.

        Args:
            pdf_path: Cesta k PDF souboru

        Returns:
            Slovník s informacemi:
            {
                'celkem': int,
                'prijato': int,
                'neprijato': int,
                'neprijati': List[Dict]  # Seznam nepřijatých osob s důvody
            }
        """
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text()

            # Parsování čísel
            celkem_match = re.search(r'Celkový počet záznamů:\s*(\d+)', text)
            prijato_match = re.search(r'Počet přijatých záznamů:\s*(\d+)', text)
            neprijato_match = re.search(r'Seznam nepřijatých záznamů:\s*(\d+)', text)

            celkem = int(celkem_match.group(1)) if celkem_match else 0
            prijato = int(prijato_match.group(1)) if prijato_match else 0
            neprijato = int(neprijato_match.group(1)) if neprijato_match else 0

            # Parsování nepřijatých osob
            neprijati = []
            if neprijato > 0:
                # Najít sekci SEZNAM NEPŘIJATÝCH ZÁZNAMŮ
                neprijati_sekce_match = re.search(
                    r'SEZNAM\s*NEP\wIJAT\wCH\s*Z\wZNAM\w(.*?)(?:POKRA\wOV\wN\w|SEZNAM\s*P\wIJAT\wCH|KONEC)',
                    text,
                    re.DOTALL | re.IGNORECASE
                )

                if neprijati_sekce_match:
                    neprijati_text = neprijati_sekce_match.group(1)

                    # Hledání řádků s ERR: (ignorujeme hlavičku a oddělovače)
                    # Pattern: číslo řádku + ERR + --- následovaný daaty osoby + ERR + chybová zpráva
                    err_pattern = r'(\d+)\s*ERR:.*?\n\s*(\w+)\s*\|\s*(\w+)\s*\|.*?\n.*?ERR:\s*([^\n]+)'
                    for match in re.finditer(err_pattern, neprijati_text, re.DOTALL):
                        prijmeni = match.group(2).strip()
                        jmeno = match.group(3).strip()
                        chyba = match.group(4).strip()

                        # Oprava překlep z PDF policie: "číslocestovního" → "číslo cestovního"
                        chyba = chyba.replace('číslocestovního', 'číslo cestovního')

                        # Ignorovat hlavičku (Příjmení | Jméno)
                        if prijmeni.lower() != 'příjmení' and jmeno.lower() != 'jméno':
                            neprijati.append({
                                'prijmeni': prijmeni,
                                'jmeno': jmeno,
                                'chyba': chyba
                            })

            # Parsování ERR záznamů v sekci PŘIJATÝCH (duplicity apod.)
            # Policie někdy dává duplicitní záznamy do sekce "přijatých" ale s ERR:
            prijati_s_chybou = []
            prijati_sekce_match = re.search(
                r'SEZNAM\s*P\wIJAT\wCH\s*Z\wZNAM\w(.*?)(?:KONEC|$)',
                text,
                re.DOTALL | re.IGNORECASE
            )

            if prijati_sekce_match:
                prijati_text = prijati_sekce_match.group(1)

                # Hledání ERR: záznamů v sekci přijatých
                err_pattern = r'(\d+)\s*ERR:.*?\n\s*(\w+)\s*\|\s*(\w+)\s*\|.*?\n.*?ERR:\s*([^\n]+)'
                for match in re.finditer(err_pattern, prijati_text, re.DOTALL):
                    prijmeni = match.group(2).strip()
                    jmeno = match.group(3).strip()
                    chyba = match.group(4).strip()

                    # Ignorovat hlavičku
                    if prijmeni.lower() != 'příjmení' and jmeno.lower() != 'jméno':
                        prijati_s_chybou.append({
                            'prijmeni': prijmeni,
                            'jmeno': jmeno,
                            'chyba': chyba
                        })

            # Přidat "přijaté s chybou" do nepřijatých a upravit počty
            if prijati_s_chybou:
                neprijati.extend(prijati_s_chybou)
                # Skutečný počet přijatých = deklarovaný - ti s chybou
                prijato = max(0, prijato - len(prijati_s_chybou))
                neprijato = neprijato + len(prijati_s_chybou)

            result = {
                'celkem': celkem,
                'prijato': prijato,
                'neprijato': neprijato,
                'neprijati': neprijati
            }

            logger.info(f"PDF parsováno: {prijato} přijato, {neprijato} nepřijato")
            if neprijati:
                for osoba in neprijati:
                    logger.warning(f"  Nepřijato: {osoba['jmeno']} {osoba['prijmeni']} - {osoba['chyba']}")

            return result

        except Exception as e:
            logger.error(f"Chyba při parsování PDF: {e}")
            return {
                'celkem': 0,
                'prijato': 0,
                'neprijato': 0,
                'neprijati': []
            }

    def _uloz_pdf(self, base64_data: str, filename: str) -> Optional[str]:
        """
        Uloží PDF dokument z base64 dat.

        Args:
            base64_data: PDF v base64 kódování
            filename: Název souboru

        Returns:
            Cesta k uloženému souboru nebo None
        """
        try:
            # Složka se vytváří automaticky v config.py (ensure_directories())
            pdf_dir = PDF_DIR

            # Cesta k souboru
            pdf_path = pdf_dir / filename

            # Dekódování base64 a uložení
            pdf_bytes = base64.b64decode(base64_data)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)

            logger.info(f"PDF uloženo: {pdf_path}")
            return str(pdf_path)

        except Exception as e:
            logger.error(f"Chyba při ukládání PDF: {e}")
            return None


if __name__ == "__main__":
    """
    Testovací skript pro ověření připojení k API.
    Spusť tento soubor samostatně pro rychlý test: python src/soap_client.py
    """
    # Nastavení logování pro samostatné spuštění
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("UBYPORT SOAP CLIENT - TEST PŘIPOJENÍ")
    print("=" * 60)

    try:
        # Vytvoření klienta
        print("\n1. Vytvaření SOAP klienta...")
        client = UbyportClient(environment="test")
        print("   [OK] Klient vytvoren")

        # Test dostupnosti
        print("\n2. Test dostupnosti služby...")
        if client.test_dostupnosti():
            print("   [OK] Služba je dostupna")
        else:
            print("   [ERROR] Služba neni dostupna")

        # Maximální délka seznamu
        print("\n3. Zjisteni maximalni delky seznamu...")
        max_delka = client.max_delka_seznamu()
        print(f"   [OK] Maximalni pocet osob na pozadavek: {max_delka}")

        # Test číselníků
        print("\n4. Nacteni ciselniku...")

        # Státy
        staty = client.dej_mi_ciselnik("Staty")
        print(f"   [OK] Staty nacteny: {len(staty)} polozek")
        if staty:
            print(f"     Priklad: {staty[0]['Kod3']} = {staty[0]['TextCZ']}")

        # Účely pobytu
        ucely = client.dej_mi_ciselnik("UcelyPobytu")
        print(f"   [OK] Ucely pobytu nacteny: {len(ucely)} polozek")
        if ucely:
            print(f"     Priklad: {ucely[0]['Kod2']} = {ucely[0]['TextCZ']}")

        # Chyby
        chyby = client.dej_mi_ciselnik("Chyby")
        print(f"   [OK] Chybovnik nacten: {len(chyby)} polozek")

        print("\n" + "=" * 60)
        print("VSECHNY TESTY PROBEHLY USPESNE!")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] CHYBA: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
