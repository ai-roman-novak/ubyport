# Popis projektu: Aidaro Ubyport Connector (Unofficial)

Technická dokumentace systému pro automatizované hlášení ubytování cizinců do systému Ubyport (Policie ČR).

---

## 1. Přehled projektu

### Co to je
Aidaro Ubyport Connector je systém pro automatické hlášení ubytování cizinců do systému Ubyport provozovaného Policií ČR. Systém načítá data zaměstnanců z Excel souboru, ukládá je do databáze, detekuje nové zaměstnance a automaticky je přihlašuje prostřednictvím SOAP API s NTLM autentizací.

### Pro koho je to určené
- Firmy zaměstnávající cizince
- HR oddělení
- Ubytovatelé povinní hlásit ubytování cizinců na Policii ČR

### Hlavní funkce
- ✅ Automatické načítání dat z Excelu (podpora různých formátů datumů)
- ✅ SQLite databáze pro evidenci přihlášených
- ✅ Detekce nových zaměstnanců (kteří ještě nejsou v databázi)
- ✅ SOAP API komunikace s NTLM autentizací
- ✅ Stahování a parsování PDF potvrzení z policie
- ✅ Kontrola skutečného přijetí/odmítnutí policií
- ✅ Automatické Excel exporty (kompletní přehled + pouze potvrzení)
- ✅ Podrobné logování všech operací

---

## 2. Architektura systému

### Komponenty systému

```
┌─────────────────┐
│  Excel soubor   │  Vstupní data (ubyport_people_to_send.xlsx)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ excel_reader.py │  Načítání a validace
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  database.py    │  SQLite databáze + detekce nových
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ soap_client.py  │  SOAP API + NTLM auth
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PDF potvrzení  │  Parsování a kontrola
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│export_excel.py  │  Generování výstupních Excelů
└─────────────────┘
```

### Datový tok
**Excel → Validace → Databáze → Detekce nových → API → PDF → Export**

### Použité technologie
- **Python 3.12+**
- **zeep 4.3.2** - SOAP klient
- **requests-ntlm** - NTLM autentizace
- **pandas + openpyxl** - práce s Excelem
- **sqlalchemy** - SQLite databáze
- **PyPDF2** - parsování PDF potvrzení

---

## 3. Moduly a komponenty

### 3.1 excel_reader.py
**Účel:** Načítání a validace dat z Excel souborů

**Hlavní funkce:**
- Načte Excel soubor (`ubyport_people_to_send.xlsx`)
- Normalizuje názvy sloupců (podporuje různé varianty)
- Zpracuje všechny řádky z Excelu
- Validuje povinná pole a formáty
- Automaticky opravuje běžné chyby (např. chybějící nula v datu narození)
- Konvertuje názvy zemí na ISO kódy (např. "Ukrajina" → "UKR")

**Klíčová třída:** `ExcelReader`

**Validace:**
- Datum narození: 8 číslic (DDMMYYYY), podpora různých oddělovačů
- Číslo pasu: 4-30 znaků
- Státní občanství: 3 písmena (ISO kód)
- Jméno/Příjmení: pouze písmena, apostrof, spojník

**Umístění:** `src/excel_reader.py:27-465`

---

### 3.2 database.py
**Účel:** Správa SQLite databáze a detekce nových zaměstnanců

**Hlavní funkce:**
- Vytvoření a správa databázového schématu
- CRUD operace nad zaměstnanci
- Zaznamenávání API transakcí
- **Detekce nových zaměstnanců** (kteří ještě nejsou v databázi)

**Klíčová třída:** `UbyportDatabase`

**Databázové tabulky:**

**Tabulka `zamestnanci`:**
- Všichni zaměstnanci z Excelu
- Stav: `NOVY`, `PRIHLASEN`, `CHYBA`
- Timestamp poslední synchronizace
- **UNIQUE constraint:** `(cislo_pasu, datum_narozeni)` - identifikace duplicit

**Tabulka `api_transakce`:**
- Historie všech API volání
- SOAP request/response (pro debugging)
- Chybové zprávy
- Cesty k PDF potvrzením

**Umístění:** `src/database.py:21-440`

---

### 3.3 soap_client.py
**Účel:** Komunikace s Ubyport SOAP API

**Hlavní funkce:**
- Připojení k SOAP API s NTLM autentizací
- Test dostupnosti API
- Získání číselníků (např. seznam států)
- Zápis ubytovaných (max 32 osob na request)
- Stahování PDF potvrzení (base64)
- **Parsování PDF** - extrakce informací o přijatých/nepřijatých záznamech

**Klíčová třída:** `UbyportClient`

**API detaily:**
- Protokol: SOAP 1.1
- Autentizace: NTLM (Windows domain)
- Namespace: `http://schemas.datacontract.org/2004/07/WS_UBY`
- Max osob na request: 32

**PDF parsování:**
- Automatické stažení PDF potvrzení z API
- Parsování textu pomocí PyPDF2
- Detekce přijatých záznamů (oddíl "Přijato")
- Detekce odmítnutých záznamů (oddíl "Nepřijato" s důvodem)

**Umístění:** `src/soap_client.py:28-590`

---

### 3.4 export_excel.py
**Účel:** Generování Excel exportů

**Hlavní funkce:**
- Export kompletního přehledu (všichni včetně chyb)
- Export potvrzení policie (pouze PRIHLASEN)
- Generování timestampovaných názvů souborů

**Klíčová třída:** `ExcelExporter`

**Exporty:**

**1. Kompletní export** (`export_kompletni_YYYYMMDD_HHMMSS.xlsx`):
- Sheet "People": VŠICHNI z databáze
- Sheet "Transakce": Historie API volání
- Účel: Technický dump pro audit

**2. Export potvrzení policie** (`potvrzeni_policie_YYYYMMDD_HHMMSS.xlsx`):
- Pouze zaměstnanci se stavem `PRIHLASEN`
- Datum zápisu u policie
- Cesta k PDF potvrzení
- Účel: Ověřená data pro HR/mzdy

**Umístění:** `src/export_excel.py:20-385`

---

### 3.5 main.py
**Účel:** Orchestrace celého procesu

**Hlavní funkce:**
- Koordinace všech modulů
- Zpracování argumentů příkazové řádky
- Logování všech operací
- Statistiky (přihlášeno/chyby)

**Klíčová třída:** `UbyportAutomation`

**Workflow kroků:**
1. Načtení dat z Excelu
2. Připojení k databázi
3. Detekce nových zaměstnanců
4. Připojení k API
5. Přihlášení nových zaměstnanců do Ubyportu
6. Export výsledků do Excelu

**Umístění:** `src/main.py:43-523`

---

### 3.6 config.py
**Účel:** Centrální konfigurace cest

**Hlavní funkce:**
- Definice cest k datům (synchronizované s pcloud)
- Definice cest k exportům
- Definice cest k logům
- Automatické vytvoření složek

**Klíčové konstanty:**
- `BASE_DATA_DIR` - Základní adresář s daty
- `DATA_DIR` - Složka data/
- `EXPORT_DIR` - Složka export/
- `DB_PATH` - Cesta k databázi
- `EXCEL_PATH` - Cesta k Excel souboru
- `PDF_DIR` - Složka s PDF potvrzeními
- `LOGS_DIR` - Složka s logy

**Poznámka:** `config.py` je v .gitignore (lokální konfigurace), `config.py.example` je v gitu jako šablona.

**Umístění:** `src/config.py:1-42`

---

## 4. Datový tok krok za krokem

### [1/6] Načítání dat z Excelu
1. **ExcelReader** načte soubor `data/ubyport_people_to_send.xlsx`
2. Normalizuje názvy sloupců
3. **Automatický režim:** Zpracuje všechny řádky (bez filtrování)
4. **Validuje** každý záznam:
   - Povinná pole
   - Formáty (datum narození, pas, státní občanství)
   - Automatické opravy (např. doplnění nuly v datu)
5. Vrátí seznam validních zaměstnanců

**Výstup:** Seznam slovníků s validními daty zaměstnanců

---

### [2/6] Připojení k databázi
1. **UbyportDatabase** se připojí k SQLite databázi
2. Vytvoří tabulky, pokud neexistují
3. Databáze je připravena pro čtení/zápis

**Výstup:** Aktivní databázové spojení

---

### [3/6] Detekce nových zaměstnanců
1. Načte všechny zaměstnance z databáze
2. Porovná s daty z Excelu podle `(cislo_pasu, datum_narozeni)`
3. Kategorizuje záznamy:
   - **Noví:** Neexistují v DB → přihlásit
   - **Již přihlášení:** Existují v DB → přeskočit

**Výstup:** Seznam nových zaměstnanců

**Poznámka:** Systém je určen POUZE pro přihlašování nových zaměstnanců. Jednou přihlášení zaměstnanci se již neaktualizují.

---

### [4/6] Připojení k API
1. **UbyportClient** se připojí k SOAP API
2. Použije NTLM autentizaci (username, password, domain)
3. Testuje dostupnost API (`test_dostupnosti()`)

**Výstup:** Aktivní API klient

---

### [5/6] Odesílání dat do Ubyportu

**Pro nové zaměstnance:**
1. Rozdělení do dávek (max 32 osob)
2. Odeslání do API (`zapis_ubytovane()`)
3. Stažení PDF potvrzení (base64)
4. **Parsování PDF:**
   - Extrakce seznamu přijatých
   - Extrakce seznamu nepřijatých + důvody
5. Aktualizace stavů v DB:
   - Přijato → stav `PRIHLASEN`
   - Odmítnuto → stav `CHYBA`
6. Zaznamenání transakce (typ operace: `PRIHLASENI`)

**Výstup:** Aktualizovaná databáze, PDF potvrzení

---

### [6/6] Export výsledků do Excelu

1. **ExcelExporter** vytvoří kompletní export:
   - Sheet "People": Všichni z DB
   - Sheet "Transakce": Historie API volání
   - Soubor: `export/export_kompletni_YYYYMMDD_HHMMSS.xlsx`

2. **ExcelExporter** vytvoří export potvrzení:
   - Pouze zaměstnanci se stavem `PRIHLASEN`
   - Datum zápisu u policie
   - Cesta k PDF
   - Soubor: `export/potvrzeni_policie_YYYYMMDD_HHMMSS.xlsx`

**Výstup:** 2 Excel soubory ve složce `export/`

---

## 5. Validační pravidla

### Povinná pole
- Příjmení
- Jméno
- Datum narození
- Číslo pasu
- Státní občanství
- Datum příjezdu
- Datum odjezdu

### Formáty

**Datum narození:**
- Musí být 8 číslic (DDMMYYYY)
- Podporované formáty:
  - `15051985` (bez oddělovačů)
  - `15.05.1985` (tečky)
  - `15-05-1985` (pomlčky)
  - `15/05/1985` (lomítka)
- **Automatická oprava:** Doplnění chybějící nuly (`5031992` → `05031992`)

**Číslo pasu:**
- 4-30 znaků
- Žádná další omezení

**Státní občanství:**
- Přesně 3 písmena (ISO kód)
- Automatický převod na velká písmena
- **Konverze názvů zemí:**
  - "Ukrajina" → UKR
  - "Slovensko" → SVK
  - "Polsko" → POL
  - atd.
- **ZAKÁZÁNO:** České občanství (CZE, CZ) - systém je pouze pro cizince

**Jméno/Příjmení:**
- Pouze písmena, apostrof, spojník, mezera
- Regex: `^[a-zA-ZÀ-ž\s'-]+$`

### Automatické opravy
- ✅ Odstranění oddělovačů z data narození
- ✅ Doplnění chybějící nuly v datu narození
- ✅ Převod státního občanství na velká písmena
- ✅ Oříznutí bílých znaků
- ✅ Konverze názvů zemí na ISO kódy

### Co systém odmítne
- ❌ Chybějící povinná pole
- ❌ Datum narození jiné než 7-8 číslic
- ❌ Státní občanství jiné než 3 písmena
- ❌ Číslo pasu kratší než 4 nebo delší než 30 znaků
- ❌ Jméno/příjmení s číslicemi nebo speciálními znaky
- ❌ České občanství (CZE, CZ)

---

## 6. Excel formáty

### Struktura vstupního Excelu

**⭐ AUTOMATICKÝ REŽIM:**
- Aplikace zpracuje všechny řádky v Excelu
- Přihlásí nové osoby, které ještě nejsou v databázi
- Osoby již přihlášené se přeskočí (vypisuje se do logu)

**Povinné sloupce:**
| Sloupec | Formát | Příklad |
|---------|--------|---------|
| Příjmení | Text | `Kowalski` |
| Jméno | Text | `Piotr` |
| Datum narození | Text | `15051985` nebo `15.05.1985` |
| Číslo pasu | Text | `PL9876543` |
| Státní občanství | Text | `POL` nebo `Polsko` |
| Datum příjezdu | Datum | `09.10.2025` |
| Datum odjezdu | Datum | `08.12.2025` |

**Nepovinné sloupce:**
| Sloupec | Formát | Příklad |
|---------|--------|---------|
| Číslo víza | Text | `VZ123456` |
| Bydliště v domovské zemi | Text | `Warszawa, ul. Marszalkowska 45` |
| Účel pobytu | Číslo 00-99 | `99` (ostatní) |
| Poznámka | Text | `Vedoucí projektu` |

### Podporované varianty názvů sloupců
Systém rozpozná různé varianty názvů:
- "Příjmení" / "prijmeni" / "PRIJMENI" / "Surname"
- "Jméno" / "jmeno" / "JMENO" / "Name"
- "Datum narození" / "datum_narozeni" / "Birth Date"
- atd.

### Podporované formáty datumů
**Datum narození:**
- `15051985` - bez oddělovačů ✅
- `15.05.1985` - tečky ✅
- `15-05-1985` - pomlčky ✅
- `15/05/1985` - lomítka ✅
- `5031992` - chybějící nula → automaticky opraveno ✅

**Datum příjezdu/odjezdu:**
- Excel datum (např. `09.10.2025`)
- Automaticky převedeno na datetime objekt

---

## 7. Export souborů

### 7.1 Kompletní export
**Název souboru:** `export_kompletni_YYYYMMDD_HHMMSS.xlsx`

**Umístění:** `<DATA_ROOT>/export/`

**Obsah:**

**Sheet "People":**
- VŠICHNI zaměstnanci z databáze
- Včetně těch se stavem CHYBA
- Sloupce:
  - ID, Příjmení, Jméno, Datum narození
  - Číslo pasu, Státní občanství
  - Datum příjezdu, Datum odjezdu (formát YYYY-MM-DD)
  - Číslo víza, Bydliště, Účel pobytu, Poznámka
  - Stav, Poslední sync, Vytvořeno, Aktualizováno
- Řazení: podle ID vzestupně (staří nahoře, noví dole)

**Sheet "Transakce":**
- Historie všech API volání
- Sloupce:
  - ID, Datum, Zaměstnanec
  - Operace (PRIHLASENI)
  - Úspěch (Ano/Ne)
  - Chyby
  - PDF (cesta k potvrzení)
- Řazení: podle data odeslání sestupně (nejnovější nahoře)

**Účel:** Technický dump celé databáze pro audit, debugging, kontrolu chyb

---

### 7.2 Export potvrzení policie
**Název souboru:** `potvrzeni_policie_YYYYMMDD_HHMMSS.xlsx`

**Umístění:** `<DATA_ROOT>/export/`

**Obsah:**
- **POUZE** zaměstnanci se stavem `PRIHLASEN`
- ❌ **NEOBSAHUJE** odmítnuté ani chybové záznamy
- Sloupce:
  - ID, Příjmení, Jméno, Datum narození
  - Číslo pasu, Státní občanství
  - Datum příjezdu, Datum odjezdu (formát DD.MM.YYYY - lidsky čitelný)
  - Číslo víza, Bydliště, Účel pobytu, Poznámka
  - **Datum zápisu u policie** (DD.MM.YYYY HH:MM)
  - **PDF potvrzení** (cesta k souboru)
- Řazení: podle ID vzestupně

**Účel:** Vizuální kontrola a ověřená data k dalšímu použití (HR, mzdy, reporting)

---

### Kdy se exporty generují
- Automaticky na konci každého běhu programu (krok [6/6])
- Vždy se vytvoří oba soubory (kompletní + potvrzení)
- Timestampované názvy → žádné přepisování starých exportů

---

## 8. PDF potvrzení

### Jak funguje stahování PDF
1. API vrací PDF jako **base64 encoded string** v SOAP odpovědi
2. Systém automaticky:
   - Dekóduje base64 data
   - Uloží jako soubor `potvrzeni_YYYYMMDD_HHMMSS.pdf`
   - Umístění: `<DATA_ROOT>/data/potvrzeni/`

### Parsování obsahu PDF
**Co se extrahuje:**
- **Oddíl "Přijato"**: Seznam zaměstnanců přijatých policií
- **Oddíl "Nepřijato"**: Seznam zaměstnanců odmítnutých policií + důvod odmítnutí

**Proces parsování:**
1. Otevření PDF pomocí PyPDF2
2. Extrakce textu ze všech stránek
3. Hledání oddílů "Přijato" a "Nepřijato"
4. Extrakce jmen (formát: "Příjmení Jméno")
5. Pro nepřijaté: extrakce důvodu odmítnutí

### Kontrola přijetí/odmítnutí
**DŮLEŽITÉ:** Systém nekontroluje pouze úspěšnost API volání, ale i skutečné přijetí policií z PDF!

**Možné scénáře:**
- ✅ **API úspěch + v PDF "Přijato"** → Stav `PRIHLASEN`
- ❌ **API úspěch + v PDF "Nepřijato"** → Stav `CHYBA` + důvod v logu
- ❌ **API chyba** → Stav `CHYBA`

**Příklad odmítnutí:**
```
Zaměstnanec: Oleksandr Boyko
Důvod: "Nekorektní číslo cestovního dokladu"
Stav v DB: CHYBA
```

### Formát PDF
- Generuje server Ubyport (nelze ovlivnit)
- Úřední dokument
- Obvykle 2 osoby na stránku
- Obsahuje informace o ubytování, daty, razítko policie

**Umístění logiky:** `src/soap_client.py:456-590`

---

## 9. Konfigurace

### 9.1 config.py (lokální cesty)
**Účel:** Centrální konfigurace cest k datům

**Umístění:** `src/config.py` (v .gitignore)

**Šablona:** `src/config.py.example` (v gitu)

**Nastavení:**
```python
BASE_DATA_DIR = Path("<DATA_ROOT>")  # Nastavte podle vašeho prostředí
DATA_DIR = BASE_DATA_DIR / "data"
EXPORT_DIR = BASE_DATA_DIR / "export"
DB_PATH = DATA_DIR / "ubyport.db"
EXCEL_PATH = DATA_DIR / "ubyport_people_to_send.xlsx"
PDF_DIR = DATA_DIR / "potvrzeni"
BACKUP_DIR = DATA_DIR / "backup"
LOGS_DIR = PROJECT_ROOT / "logs"
```

**Poznámka:** Data jsou synchronizována s pcloud.

---

### 9.2 credentials.json (přihlašovací údaje)
**Účel:** Uložení přihlašovacích údajů pro API

**Umístění:** `config/credentials.json` (v .gitignore)

**Struktura (do tohoto souboru nevkládat citlivá data = přístupové údaje):**
```json
{
  "test": {
    "url": "https://ubyport.pcr.cz/ws_uby_test/ws_uby.svc",
    "username": "-------",
    "password": "-------",
    "domain": "-------V",
    "idub": "-------"
  },
  "production": {
    "url": "https://ubyport.pcr.cz/ws_uby/ws_uby.svc",
    "username": "xxx",
    "password": "xxx",
    "domain": "xxx",
    "idub": "xxx"
  }
}
```

**Prostředí:**
- `test` - testovací API (funkční)
- `production` - produkční API (vyžaduje ostré přihlašovací údaje)

---

### 9.3 Spuštění programu

**Základní použití:**
```bash
venv/bin/python src/main.py --env test
```

**Parametry:**
- `--env` - Prostředí (`test` / `production`)
- `--excel` - Vlastní cesta k Excel souboru (volitelné)
- `--db` - Vlastní cesta k databázi (volitelné)
- `--dry-run` - Simulace - zobrazí přehled bez odeslání (volitelné)
- `--yes` / `-y` - Automatické potvrzení bez ptaní (volitelné)

**Příklady:**
```bash
# Testovací prostředí (s interaktivním potvrzením)
venv/bin/python src/main.py --env test

# DRY-RUN mód - zobrazí přehled bez odeslání
venv/bin/python src/main.py --env test --dry-run

# Automatický režim - bez ptaní (pro automatizaci)
venv/bin/python src/main.py --env test --yes

# Production prostředí s automatickým potvrzením
venv/bin/python src/main.py --env production --yes

# Vlastní Excel soubor
venv/bin/python src/main.py --excel /cesta/k/souboru.xlsx --env test
```

**Nové funkce:**
1. **Automatické zálohy databáze:** Před každým odesláním se vytvoří backup do `data/backup/` (max 10 záloh)
2. **Interaktivní potvrzení:** Program zobrazí přehled a zeptá se na potvrzení před odesláním
3. **DRY-RUN mód:** Simulace běhu bez skutečného odeslání do API
4. **Automatický režim:** Pro plně automatické běhy (např. cron)

---

## 10. Stavy zaměstnanců

### Možné stavy

| Stav | Popis | Kdy se nastaví |
|------|-------|----------------|
| `NOVY` | Nový záznam | Při prvním vložení do DB (přechodný stav) |
| `PRIHLASEN` | Přijato policií | Po úspěšném zápisu + potvrzení v PDF (konečný) |
| `CHYBA` | Chyba při zpracování | API chyba nebo odmítnuto policií (konečný) |

### Přechody stavů

```
[Excel] → [NOVY]
           │
           ▼
    [API + PDF kontrola]
           │
     ┌─────┴─────┐
     ▼           ▼
[PRIHLASEN]  [CHYBA]
  (konečný)  (konečný)
```

### Detailní popis

**NOVY:**
- Zaměstnanec vložen do DB, ale ještě neodeslán do API
- Přechodný stav (během zpracování)

**PRIHLASEN:**
- API volání bylo úspěšné
- PDF potvrzení potvrdilo přijetí policií
- Zaměstnanec je oficielně nahlášen
- **Konečný stav** - již se nebude měnit

**CHYBA:**
- API volání selhalo
- **NEBO** policie odmítla záznam (i když API bylo úspěšné)
- Důvod chyby uložen v `api_transakce.chyby`
- **Konečný stav** - zaměstnanec nebyl přihlášen
- Příklady chyb:
  - "Nekorektní číslo cestovního dokladu"
  - "Nekorektní datum ubytování od"
  - Síťová chyba

### Logika detekce nových zaměstnanců

**Identifikace zaměstnance:**
- Kombinace: `(cislo_pasu, datum_narozeni)`
- UNIQUE constraint v DB

**Detekce nového zaměstnance:**
- Kombinace `(cislo_pasu, datum_narozeni)` neexistuje v DB → přihlásit

**Již přihlášený zaměstnanec:**
- Kombinace existuje v DB → přeskočit

**Poznámka:** Systém je určen POUZE pro přihlašování nových zaměstnanců. Jednou přihlášení zaměstnanci se již neaktualizují ani neodhlašují.

---

## Závěr

Tento dokument popisuje kompletní architekturu a fungování systému Ubyport Automatizace. Pro praktické použití viz [README.md](README.md).

**Verze dokumentu:** 1.0
**Datum:** 29.11.2025
**Autor:** Roman Novak
