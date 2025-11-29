# 🏢 Aidaro Ubyport Connector (Unofficial)

Automatizovaný systém pro hlášení ubytování cizinců do systému Ubyport (Policie ČR).
Projekt není oficiálně spojen s PČR; ‘Ubyport’ je použit jen k popisu kompatibility.
V projektu se často mluví o zaměstnancích jako o lidech pro ubytování (pojmenování vychází z původní potřeby autora tohoto projektu).
V excelovávh tabulkách se nachází testovací fiktivní jména a data o fiktivníh lidech. 

**Status:** Funkční a otestováno na testovacím API

---

## 📋 Popis

Aplikace automaticky:
1. Načítá data zaměstnanců z Excel souboru (podporuje různé formáty datumů)
2. Ukládá je do SQLite databáze
3. Detekuje nové zaměstnance (kteří ještě nejsou přihlášeni)
4. Hlásí je prostřednictvím SOAP API s NTLM autentizací do systému Ubyport
5. Stahuje PDF potvrzení
6. **Parsuje PDF a kontroluje skutečné přijetí/odmítnutí policií**
7. Zaznamenává transakce pro audit
8. **Vytváří 2 Excel exporty**: kompletní přehled + pouze potvrzení od policie

---

## 🗂️ Struktura projektu

```
/ubyport/
├── venv/                       # Virtuální prostředí Python 3.12
├── logs/                       # Logy běhu programu (timestampované)
├── config/
│   └── credentials.json        # Přihlašovací údaje (test + production)
├── src/
│   ├── __init__.py
│   ├── config.py               # Konfigurace cest (lokální, v .gitignore)
│   ├── config.py.example       # Šablona konfigurace
│   ├── excel_reader.py         # Čtení a validace Excelu
│   ├── database.py             # SQLite databáze + CRUD
│   ├── soap_client.py          # SOAP klient s NTLM auth
│   ├── export_excel.py         # Export do Excelu
│   └── main.py                 # Hlavní orchestrační program
├── zd/                         # Zadávací dokumentace
│   ├── Technicky-popis-webove-sluzby.pdf
│   └── url-pro-vyvojare.txt
├── requirements.txt            # Python závislosti
├── README.md                   # Tento soubor
├── POPIS_PROJEKTU.md           # Technická dokumentace
└── .gitignore                  # Git ignore soubor
```

**📁 Datový adresář (nastavitelný v `src/config.py`):**
```
<DATA_ROOT>/
├── data/
│   ├── ubyport_people_to_send.xlsx  # Vstupní Excel soubor
│   ├── ubyport.db                   # SQLite databáze
│   ├── backup/                      # Automatické zálohy databáze (max 10)
│   └── potvrzeni/                   # PDF potvrzení z API
└── export/                          # Excel exporty (timestampované)
    ├── export_kompletni_*.xlsx       # Kompletní export
    └── potvrzeni_policie_*.xlsx      # Pouze potvrzení policií
```

**Poznámka:** Data a exporty jsou uloženy mimo projekt, cesty se nastavují v `src/config.py`.

---

## 🚀 Instalace

### 1. Vytvoř virtuální prostředí:
```bash
python -m venv venv
```

**Požadavek:** Python 3.12+ (doporučeno Python 3.12.3 na Ubuntu 24.04)

### 2. Aktivuj virtuální prostředí:
```bash
# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate
```

### 3. Nainstaluj závislosti:
```bash
pip install -r requirements.txt
```

**Hlavní knihovny:**
- `zeep==4.3.2` - SOAP klient (kompatibilní s Python 3.9-3.13)
- `requests-ntlm` - NTLM autentizace pro Windows domény
- `pandas` + `openpyxl` - práce s Excelem
- `sqlalchemy` - SQLite databáze
- `PyPDF2` - parsování PDF potvrzení

---

## ⚙️ Konfigurace

### 1. Konfigurace cest (`src/config.py`)

**DŮLEŽITÉ:** Před prvním spuštěním je potřeba vytvořit `src/config.py`:

```bash
# Zkopíruj šablonu
cp src/config.py.example src/config.py

# Uprav cesty podle svého prostředí (otevři v editoru)
```

**Výchozí nastavení (příklad):**
- Data: `<DATA_ROOT>/data/`
- Export: `<DATA_ROOT>/export/`
- Logy: `<PROJECT_ROOT>/logs/`

**Poznámka:** `config.py` je v .gitignore (lokální konfigurace pro každého uživatele).

---

### 2. Credentials (`config/credentials.json`)

Soubor už obsahuje **testovací credentials** (funkční) (do tohoto souboru README.md nevkládat citlivá data = přístupové údaje):

```json
{
    "test": {
        "url": "https://ubyport.pcr.cz/ws_uby_test/ws_uby.svc",
        "username": "-------",
        "password": "-------",
        "domain": "-------",
        "idub": "-------",
        ...
    }
}
```

Pro **produkční prostředí** doplň sekci `"production"` se správnými údaji.

### 2. Excel soubor (`data/ubyport_people_to_send.xlsx`)

Připrav Excel s následujícími sloupci (viz níže).

---

## 📊 Excel formát

**⭐ AUTOMATICKÝ REŽIM:**
- Aplikace automaticky zpracuje **všechny řádky** v Excelu
- Přihlásí nové osoby, které **ještě nejsou v databázi**
- Osoby již přihlášené **se přeskočí** (vypisuje se do logu)

### Povinné sloupce:

| Sloupec | Formát | Příklad | Poznámka |
|---------|--------|---------|----------|
| **Příjmení** | Text | `Kowalski` | Jen písmena, apostrof, spojník |
| **Jméno** | Text | `Piotr` | Jen písmena, apostrof, spojník |
| **Datum narození** | Text | `15051985` nebo `15.05.1985` | Různé formáty (viz níže) |
| **Číslo pasu** | Text | `PL9876543` | 4-30 znaků |
| **Státní občanství** | Text | `POL` | Přesně 3 písmena (ISO kód) |
| **Datum příjezdu** | Datum | `09.10.2025` | Excel datum |
| **Datum odjezdu** | Datum | `08.12.2025` | Excel datum |

### Nepovinné sloupce:

| Sloupec | Formát | Příklad |
|---------|--------|---------|
| Číslo víza | Text | `VZ123456` |
| Bydliště v domovské zemi | Text | `Warszawa, ul. Marszalkowska 45` |
| Účel pobytu | Číslo 00-99 | `99` (=ostatní) |
| Poznámka | Text | `Vedoucí projektu` |

### ⚠️ DŮLEŽITÉ o datu narození:

Systém podporuje **více formátů** a automaticky je převede na požadovaný formát `DDMMYYYY`:

**Podporované formáty:**
- ✅ `15051985` (bez oddělovačů) → `15051985`
- ✅ `15.05.1985` (tečky) → `15051985`
- ✅ `15-05-1985` (pomlčky) → `15051985`
- ✅ `15/05/1985` (lomítka) → `15051985`

**Automatické opravy:**
- Excel často odstraňuje nuly na začátku:
  - `01011990` → Excel uloží jako `1011990` → Systém opraví na `01011990` ✅
  - `05031992` → Excel uloží jako `5031992` → Systém opraví na `05031992` ✅

**Tip:** Můžeš zapisovat datum narození běžným způsobem `DD.MM.YYYY` - systém automaticky odstraní tečky!

---

## 🎮 Spuštění

### ⚠️ DŮLEŽITÉ: Vždy používej Python z virtuálního prostředí!

**Linux/Ubuntu:**
```bash
# Základní spuštění (testovací prostředí, s interaktivním potvrzením)
venv/bin/python src/main.py --env test

# Production prostředí
venv/bin/python src/main.py --env production

# DRY-RUN mód - zobrazí co by se stalo, ale nic neodešle
venv/bin/python src/main.py --env test --dry-run

# Automatický režim - bez ptaní (pro cron/automatizaci)
venv/bin/python src/main.py --env test --yes

# Kombinace: automatický režim v produkci
venv/bin/python src/main.py --env production --yes

# Vlastní Excel soubor
venv/bin/python src/main.py --excel cesta/k/souboru.xlsx --env test

# Vlastní databáze
venv/bin/python src/main.py --db cesta/k/databazi.db --env test
```

**Windows (Git Bash / CMD / PowerShell):**
```bash
# Základní spuštění
venv/Scripts/python.exe src/main.py --env test

# Dry-run mód
venv/Scripts/python.exe src/main.py --env test --dry-run

# Automatický režim
venv/Scripts/python.exe src/main.py --env test --yes
```

**Poznámka:** Na Windows v Git Bash používej `/` místo `\` v cestách. PowerShell vyžaduje `.\` na začátku (`.\venv\Scripts\python.exe`).

### 🆕 Nové funkce

**1. Automatické zálohy databáze:**
- Před každým odesláním se automaticky vytvoří záloha databáze do `data/backup/`
- Formát názvu: `ubyport_backup_YYYYMMDD_HHMMSS.db`
- Udržuje se max 10 posledních záloh (starší se automaticky mažou)

**2. Interaktivní potvrzení (výchozí):**
```
═══════════════════════════════════════════════════════════════
PŘEHLED K ODESLÁNÍ
═══════════════════════════════════════════════════════════════
  ▸ Nových k přihlášení:  3
═══════════════════════════════════════════════════════════════

Pokračovat s odesláním? [y/n]:
```
- Program se před odesláním zeptá, zda pokračovat
- Stiskni `y` pro pokračování, `n` pro zrušení

**3. DRY-RUN mód (`--dry-run`):**
- Projde celý proces (načte Excel, detekuje změny)
- Zobrazí přehled co by se stalo
- ALE: **Nepřipojí se k API, nic neodešle, nevytvoří backup**
- Ideální pro testování před ostrým během

**4. Automatický režim (`--yes` nebo `-y`):**
- Přeskočí interaktivní potvrzení
- Rovnou odešle změny
- Vhodné pro automatizaci (cron, scheduled tasks)

### Testovací skripty:

**Linux/Ubuntu:**
```bash
# Test SOAP klienta (připojení, číselníky)
venv/bin/python src/soap_client.py

# Test databáze
venv/bin/python src/database.py

# Test Excel readeru
venv/bin/python src/excel_reader.py
```

**Windows:**
```bash
# Nahraď venv/bin/python za venv/Scripts/python.exe
venv/Scripts/python.exe src/soap_client.py
```

---

## 🔄 Workflow

Aplikace postupuje v 6 krocích:

```
1. [Excel]     Načtení a validace dat z Excelu
                ↓
2. [Databáze]  Připojení k SQLite databázi
                ↓
3. [Detekce]   Detekce nových zaměstnanců
                ↓
4. [API]       Připojení k Ubyport API (NTLM auth)
                ↓
5. [Odeslání]  Zápis do Ubyportu + stažení a parsování PDF
                ↓
6. [Export]    Export výsledků do Excelu (2 soubory)
               - Kompletní export (všichni včetně chyb)
               - Potvrzení policie (pouze PRIHLASEN)
```

### Co se děje při zpracování:

- **Nový zaměstnanec** (podle čísla pasu + data narození) → Přihlášení do Ubyportu
- **Již přihlášený zaměstnanec** → Přeskočen (vypisuje se do logu)

**Poznámka:** Systém je určen POUZE pro **přihlašování nových zaměstnanců**. Pokud je zaměstnanec již v databázi (stejné číslo pasu + datum narození), nebude znovu odeslán.

---

## 📝 Validační pravidla

Systém **automaticky odmítne** záznamy s chybami:

❌ **Nevalidní data:**
- Chybějící povinná pole
- Datum narození jiné než 7-8 číslic
- Státní občanství jiné než 3 písmena
- Číslo pasu kratší než 4 nebo delší než 30 znaků
- Jméno/příjmení s číslicemi nebo speciálními znaky
- **České občanství (CZE, CZ, ČESKO, atd.)** - systém Ubyport je pouze pro cizince!

✅ **Automatické opravy a konverze:**
- **Odstranění oddělovačů z data narození:** `15.05.1985` → `15051985`, `15-05-1985` → `15051985`
- Doplnění chybějící nuly v datu narození: `5031992` → `05031992`
- Převod státního občanství na velká písmena
- Oříznutí bílých znaků
- **Konverze názvů zemí na kódy:** "Slovensko" → SVK, "Ukrajina" → UKR, "Polsko" → POL

---

## 🔍 Detekce duplicit

Program identifikuje zaměstnance pomocí **kombinace 2 údajů**:

### Kritéria pro duplicitu:
- **Číslo pasu** + **Datum narození**

Dva záznamy jsou považovány za duplicitní, pokud mají shodné oba tyto údaje.

### Implementace:
```sql
UNIQUE(cislo_pasu, datum_narozeni)
```

**Důvod použití těchto kritérií:**
- Číslo pasu je unikátní identifikátor vydaný státem
- Datum narození je neměnný údaj
- Jméno a příjmení nejsou použita (mohou se měnit, mohou obsahovat překlepy)

### Chování při duplicitě:
- Záznam z Excelu se **neodešle** do API
- V logu se zobrazí: `• Jan Novák - již přihlášen (přeskočeno)`

---

## 📋 Logování

Program vytváří detailní logy pro každé spuštění.

### Umístění:
- **Soubor:** `logs/ubyport_YYYYMMDD_HHMMSS.log` (nový soubor při každém spuštění)
- **Konzole:** Paralelní výstup na obrazovku

### Formát:
```
YYYY-MM-DD HH:MM:SS,mmm - modul - ÚROVEŇ - zpráva
```

### Úrovně logování:
- **INFO:** Běžné operace (načtení dat, odesílání do API)
- **WARNING:** Upozornění (validační chyby, přeskočené záznamy)
- **ERROR:** Chyby (selhání API, chyby databáze)

### Obsah logů:
- Načtení dat z Excelu (počet řádků, filtrování)
- **Detekce nových zaměstnanců** s výpisem každého:
  - `• Piotr Kowalski - NOVÝ zaměstnanec (bude přihlášen)`
  - `• Viktor Bondarenko - již přihlášen (přeskočeno)`
- Komunikace s API (připojení, odesílání dat)
- Výsledky z PDF potvrzení (přijato/odmítnuto policií)
- Statistiky (počet přihlášených/chyb)
- Cesty k vytvořeným exportům

---

## 🗄️ Databáze

SQLite databáze (`data/ubyport.db`) obsahuje:

### Tabulka `zamestnanci`:
- Všichni zaměstnanci z Excelu
- Datum příjezdu, odjezdu
- Stav: `NOVY`, `PRIHLASEN`, `CHYBA`
- Timestamp poslední synchronizace

### Tabulka `api_transakce`:
- Historie všech API volání
- SOAP request/response (pro debugging)
- Chybové zprávy
- Cesty k PDF potvrzením

---

## 📄 PDF Potvrzení a validace

API vrací PDF potvrzení jako **base64 encoded string** v SOAP odpovědi.

- **Automatické stažení** při úspěšném zápisu
- **Uložení** do `data/potvrzeni/potvrzeni_YYYYMMDD_HHMMSS.pdf`
- **Automatické parsování PDF** pro kontrolu skutečného stavu
- **Verifikace přijetí/odmítnutí**: Program parsuje PDF a ověří, které záznamy policie skutečně přijala
  - ✅ **Přijato policií** → Stav `PRIHLASEN` v databázi
  - ❌ **Odmítnuto policií** → Stav `CHYBA` v databázi + důvod odmítnutí v logu
- **Formát generuje server** - nelze ovlivnit (úřední dokument)
- **Obvykle 2 osoby na stránku**

### ⚠️ DŮLEŽITÉ:
Program nekontroluje pouze úspěšnost API volání, ale také **skutečné přijetí policií** z PDF.
Zaměstnanec může být technicky odeslán do API, ale policie ho může odmítnout (např. nevalidní datum příjezdu v budoucnosti).

---

## 📊 Excel Exporty

Aplikace vytváří **2 typy Excel exportů** pro různé účely:

### 1. **Kompletní export** (`export_kompletni_YYYYMMDD_HHMMSS.xlsx`)

**Účel:** Technický dump celé databáze pro audit a debugging

**Obsahuje:**
- **Sheet "People"**: VŠICHNI zaměstnanci z databáze
  - ✅ Stav `PRIHLASEN` (potvrzeno policií)
  - ❌ Stav `CHYBA` (odmítnuto policií)
- **Sheet "Transakce"**: Kompletní historie všech API volání
  - Typ operace (PRIHLASENI)
  - Úspěch/neúspěch
  - Chybové zprávy
  - Cesta k PDF potvrzení

**Použití:** Technický přehled, audit trail, debugging problémů

---

### 2. **Export potvrzení policie** (`potvrzeni_policie_YYYYMMDD_HHMMSS.xlsx`)

**Účel:** Vizuální kontrola a ověřená data k dalšímu použití

**Obsahuje:**
- **POUZE zaměstnanci se stavem `PRIHLASEN`** (potvrzení od policie)
- ❌ **NEOBSAHUJE** odmítnuté ani chybové záznamy
- ✅ Datum zápisu u policie (s časem)
- ✅ Cesta k PDF potvrzení
- ✅ Lidsky čitelné formáty datumů (`DD.MM.YYYY`)

**Sloupce:**
- ID, Příjmení, Jméno, Datum narození
- Číslo pasu, Státní občanství
- Datum příjezdu, Datum odjezdu
- Číslo víza, Bydliště, Účel pobytu, Poznámka
- **Datum zápisu u policie** (DD.MM.YYYY HH:MM)
- **PDF potvrzení** (cesta)

**Použití:**
- Vizuální kontrola, kteří zaměstnanci jsou registrováni u policie
- Data ověřená policií pro použití v HR, mzdách, reportingu
- Přehled pouze úspěšně nahlášených zaměstnanců

---

## 🔧 Technické detaily

### SOAP API:
- **Protokol:** SOAP 1.1
- **Autentizace:** NTLM (Windows domain)
- **Namespace:** `http://schemas.datacontract.org/2004/07/WS_UBY`
- **Max osob na request:** 32

### Důležité metody:
```python
# Test dostupnosti
client.test_dostupnosti()  # → bool

# Získání číselníků
client.dej_mi_ciselnik("Staty")  # → List[Dict]

# Zápis ubytovaných (vrací PDF)
client.zapis_ubytovane(osoby, vracet_pdf=True)  # → (bool, Dict)
```

### Klíčový problém (VYŘEŠENO v Zeep 4.3.2):

**ArrayOfUbytovany musí být správný SOAP typ**, ne Python list:

```python
# ❌ ŠPATNĚ:
ubytovani = [osoba1, osoba2]

# ✅ SPRÁVNĚ:
ArrayOfUbytovany = client.get_type('{http://schemas.datacontract.org/2004/07/WS_UBY}ArrayOfUbytovany')
ubytovani = ArrayOfUbytovany(Ubytovany=[osoba1, osoba2])
```

---

## 🐛 Troubleshooting

### Chyba: `No module named 'cgi'` (Python 3.13)
**Řešení:** Upgrade Zeep na 4.3.2 (již v requirements.txt):
```bash
pip install --upgrade zeep
```
**Poznámka:** Tento problém se vyskytoval v Python 3.13 se starší verzí Zeep. Zeep 4.3.2 podporuje Python 3.9-3.13.

### Chyba: "Seznam ubytovaných je prázdný"
**Příčina:** Chybné vytvoření SOAP objektů
**Řešení:** Použij `client.get_type()` s plným namespace (viz výše)

### Chyba 207: "Nekorektní název Okres"
**Řešení:** Toto je pouze varování od API. Zápis proběhne úspěšně a data budou uložena.

### Excel odstraňuje nuly z data narození
**Řešení:** Systém automaticky doplní chybějící nulu na začátku data narození.

---

## 📚 Dokumentace

- **Technický popis API:** `zd/Technicky popis webove sluzby.pdf`
- **Oficiální info:** https://policie.gov.cz/clanek/informace-pro-vyvojare.aspx

---

## 📊 Testovací výsledky

**Poslední test (24.10.2024 17:14):**
```
✅ PDF parsování funguje správně
✅ Zaměstnanci s validními daty přijati policií → stav PRIHLASEN
✅ Zaměstnanci odmítnutí policií → stav CHYBA + důvod odmítnutí
✅ PDF potvrzení stažena a zparsována
✅ Transakce zaznamenány v DB
✅ Oba Excel exporty funkční (kompletní + potvrzení policie)
✅ Validace formátů data narození (DD.MM.YYYY → DDMMYYYY)
```

**Test příklad - formáty data narození:**
```
- Datum s tečkami: "02.08.1998" → automaticky převedeno na "02081998" ✅
- Datum s pomlčkami: "15-05-1985" → automaticky převedeno na "15051985" ✅
- Chybějící nula: "5031992" → automaticky opraveno na "05031992" ✅
```

**Test příklad - odmítnutí policií:**
```
- Zaměstnanec s budoucím datem příjezdu
- Policie odmítla: "Nekorektní datum ubytování od"
- Systém správně nastavil stav CHYBA (ne PRIHLASEN)
- Důvod odmítnutí zalogován do databáze
```

---

## 🔐 Bezpečnost

⚠️ **POZOR:**
- `config/credentials.json` obsahuje **OSTRÉ přihlašovací údaje**
- **NIKDY** necommituj tento soubor do Git!
- Pro Git tracking použij template s fake údaji

---

## 🎯 Příští kroky (volitelné)

### Priorita 1: Production
- [ ] Doplnit production credentials
- [ ] Otestovat na ostrém API (opatrně!)

### Priorita 2: Vylepšení
- [ ] Email notifikace při chybách
- [ ] Web dashboard pro monitoring
- [ ] Automatické spouštění (Windows Task Scheduler)
- [ ] Template Excel soubor s příklady

---

## 👤 Author

**Roman Novak**

- 🐙 GitHub: [@ai-roman-novak](https://github.com/ai-roman-novak)
- 🌐 Website: [aidaro.ai](https://aidaro.ai)

**Testovací účet:**
- Organizace: XXXXX S.R.O.
- Testovací prostředí: xxxxx
- IDUB: xxxxx

---

## 📞 Kontakt & Podpora

Pro technické dotazy k API kontaktuj:
- **Policie ČR:** https://policie.gov.cz/clanek/informace-pro-vyvojare.aspx

---

## Licencování

Tento projekt je dostupný v režimu **dual-licence**:

- **Open-source**: AGPL-3.0-or-later (soubor `LICENSE`).  
- **Komerční licence**: bez copyleftu, vhodné pro proprietární integrace. Viz `LICENSE-COMMERCIAL.md`.  
  Ceny: **11 000 Kč** jednorázově (v1.*) **nebo 3 300 Kč/rok**.  
  Kontakt: **ai@aidaro.ai** • +420 777 636 676 • `ORDERFORM.md`.

_Disclaimer:_ Projekt není oficiálně spojen s Policií ČR. „Ubyport“ je název systému PČR a je použit pouze k popisu kompatibility.

---

**Verze:** 1.1.0
**Poslední aktualizace:** 29.11.2024
**Status:** Testováno na testovacím API

