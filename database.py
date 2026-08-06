from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class Panel:
    navn: str
    tykkelse_mm: int
    u_verdi: float
    pris_nok_m2: float
    co2_kg_m2: float

    def as_legacy(self) -> dict:
        return dict(t=self.tykkelse_mm, u=self.u_verdi, pris=self.pris_nok_m2,
                    co2=self.co2_kg_m2, label=self.navn)

@dataclass(frozen=True)
class FloorType:
    pris: float
    co2: float
    label: str
    beskrivelse: str

    def as_legacy(self) -> dict:
        return dict(pris=self.pris, co2=self.co2, label=self.label,
                    beskrivelse=self.beskrivelse)

@dataclass(frozen=True)
class Beslag:
    pris: float
    antall_per_dor: int
    label: str

    def as_legacy(self) -> dict:
        return dict(pris=self.pris, ape=self.antall_per_dor, label=self.label)

@dataclass(frozen=True)
class Door:
    bredde_mm: int
    hoyde_mm: int
    pris: float
    label: str

    def as_legacy(self) -> dict:
        return dict(bw=self.bredde_mm, bh=self.hoyde_mm, pris=self.pris, label=self.label)

@dataclass(frozen=True)
class FormMal:
    besk: str
    func: Optional[Callable[[float, float, float, float], list[tuple[float, float]]]] = None

    def as_legacy(self) -> dict:
        return dict(besk=self.besk, func=self.func)

PANELER = {
    "PIR 80 mm":  Panel("PIR 80 mm", 80, 0.28, 1250, 8.5),
    "PIR 100 mm": Panel("PIR 100 mm", 100, 0.22, 1480, 10.2),
    "PIR 120 mm": Panel("PIR 120 mm", 120, 0.18, 1720, 12.1),
    "PIR 150 mm": Panel("PIR 150 mm", 150, 0.15, 2050, 14.8),
    "PUR 100 mm": Panel("PUR 100 mm", 100, 0.23, 1350, 11.0),
    "PUR 150 mm": Panel("PUR 150 mm", 150, 0.15, 1900, 15.5),
}

GULV_KJOL = FloorType(450, 12.0, "Avrettet betong (kjølerom – panel direkte på gulv)",
                      "80 mm PIR-panel monteres direkte på avrettet betong. Ingen gulvisolasjon.")
GULV_FRYS = FloorType(980, 28.0, "100 mm PIR gulvpanel + sponplate m/ plastbelegg (fryserom)",
                      "100 mm PIR-panel på gulv. Dekkes med sponplate med plastbelegg.")

BESLAG = {
    "Hengsel – tung kjøledør (rustfritt)": Beslag(850, 3, "Hengsel rustfritt"),
    "Lukkemekanisme / låsekasse kjøl": Beslag(2200, 1, "Låsekasse kjøl"),
    "Trykkventil / trykkutligningsplugg": Beslag(480, 1, "Trykkventil"),
    "Varmekabel dørkarm (m)": Beslag(320, 3, "Varmekabel pr. m"),
    "Terskel / rampe rustfritt stål": Beslag(1400, 1, "Terskel rustfritt"),
    "Dørpumpe / selvlukker": Beslag(1850, 1, "Dørpumpe"),
    "Innvendig nødåpner": Beslag(750, 1, "Innvendig nødåpner"),
    "Magnetpakning komplett": Beslag(980, 1, "Magnetpakning"),
}

DOR_STANDARD_HOYDE_MM = 2100  # alle dører har denne standardhøyden

DORER = {
    "Enkel kjøledør 900×2100 mm": Door(900, DOR_STANDARD_HOYDE_MM, 12500, "Enkel 900×2100"),
    "Enkel kjøledør 1200×2100 mm": Door(1200, DOR_STANDARD_HOYDE_MM, 15800, "Enkel 1200×2100"),
    "Dobbelddør 1600×2100 mm": Door(1600, DOR_STANDARD_HOYDE_MM, 24500, "Dobbel 1600×2100"),
    "Skyvedør 1000×2100 mm": Door(1000, DOR_STANDARD_HOYDE_MM, 18900, "Skyvedør 1000×2100"),
    "Fryserom enkel 900×2100 mm": Door(900, DOR_STANDARD_HOYDE_MM, 17500, "Fryserom enkel 900×2100"),
    "Fryserom dobbel 1600×2100 mm": Door(1600, DOR_STANDARD_HOYDE_MM, 31000, "Fryserom dobbel 1600×2100"),
}

FORMER = {
    "Femkant – avskåret hjørne": FormMal("Rektangel med skrå hjørnevegg", lambda l,b,cx,cy:[(0,0),(l,0),(l,b-cy),(l-cx,b),(0,b)]),
    "Rektangel": FormMal("Standard rektangulært kjølerom", lambda l,b,cx,cy:[(0,0),(l,0),(l,b),(0,b)]),
    "Trekant": FormMal("Trekantformet rom", lambda l,b,cx,cy:[(0,0),(l,0),(0,b)]),
    "L-form": FormMal("L-formet rom", lambda l,b,cx,cy:[(0,0),(l,0),(l,b*.5),(l*.5,b*.5),(l*.5,b),(0,b)]),
    "T-form": FormMal("T-formet rom", lambda l,b,cx,cy:[(l*.25,0),(l*.75,0),(l*.75,b*.4),(l,b*.4),(l,b),(0,b),(0,b*.4),(l*.25,b*.4)]),
    "Egendefinert polygon": FormMal("Definer egne hjørnepunkter", None),
}

# Legacy-navn beholdes slik at appen og eldre kode fortsatt virker.
PANEL_DB = {k: v.as_legacy() for k, v in PANELER.items()}
GULV_DB_KJOL = GULV_KJOL.as_legacy()
GULV_DB_FRYS = GULV_FRYS.as_legacy()
BESLAG_DB = {k: v.as_legacy() for k, v in BESLAG.items()}
DOR_DB = {k: v.as_legacy() for k, v in DORER.items()}
FORM_MALER = {k: v.as_legacy() for k, v in FORMER.items()}

def load_databases() -> dict:
    """Returnerer alle databaser samlet. Brukes av app.py og tester."""
    return dict(
        panel_db=PANEL_DB,
        gulv_db_kjol=GULV_DB_KJOL,
        gulv_db_frys=GULV_DB_FRYS,
        beslag_db=BESLAG_DB,
        dor_db=DOR_DB,
        form_maler=FORM_MALER,
    )
