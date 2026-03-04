#!/usr/bin/env bash
# ontology-align.sh — Map entities to ENVO and Battery Data Format ontologies
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-align-batch}"
export PAPER_ID="${2:-}"
export ENTITY_TYPE="${3:-material}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys, yaml

COMMAND = os.environ.get("COMMAND", "align-batch")
PAPER_ID = os.environ.get("PAPER_ID", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

with open(f"{REPO_ROOT}/config/ontologies.yaml") as f:
    ontologies = yaml.safe_load(f)

ENVO_KEYWORDS = ontologies["envo"]["keywords_to_terms"]
BDF_CATEGORIES = ontologies["bdf"]["categories"]

# Build a flat reverse-lookup: lowercase term → (category, original_term)
BDF_LOOKUP = {}
for cat, terms in BDF_CATEGORIES.items():
    for term in terms:
        BDF_LOOKUP[term.lower()] = (cat, term)

# Element symbol → name mapping for chemical formula parsing
ELEMENT_SYMBOLS = {
    "Li": "lithium", "Na": "sodium", "K": "potassium", "Mg": "magnesium",
    "Ca": "calcium", "Al": "aluminum", "Zn": "zinc", "Fe": "iron",
    "Co": "cobalt", "Ni": "nickel", "Mn": "manganese", "Ti": "titanium",
    "V": "vanadium", "Cu": "copper", "Ag": "silver", "Au": "gold",
    "Pt": "platinum", "Pd": "palladium", "Ir": "iridium", "Ru": "ruthenium",
    "Sn": "tin", "Si": "silicon", "C": "carbon", "S": "sulfur",
    "Se": "selenium", "Te": "tellurium", "P": "phosphorus", "N": "nitrogen",
    "O": "oxygen", "H": "hydrogen", "F": "fluorine", "Cl": "chlorine",
    "Br": "bromine", "I": "iodine", "B": "boron", "Ge": "germanium",
    "In": "indium", "Ga": "gallium", "As": "arsenic", "Sb": "antimony",
    "Bi": "bismuth", "Pb": "lead", "Cd": "cadmium", "Cr": "chromium",
    "Mo": "molybdenum", "W": "tungsten", "Nb": "niobium", "Ta": "tantalum",
    "Zr": "zirconium", "Hf": "hafnium", "Y": "yttrium", "La": "lanthanum",
    "Ce": "cerium", "Nd": "neodymium",
}

# Common abbreviation/alias → expanded form
ALIASES = {
    # Battery chemistries
    "li-ion": "lithium-ion", "li ion": "lithium-ion", "lib": "lithium-ion",
    "na-ion": "sodium-ion", "na ion": "sodium-ion", "nib": "sodium-ion",
    "k-ion": "potassium-ion", "k ion": "potassium-ion",
    "mg-ion": "magnesium-ion", "mg ion": "magnesium-ion",
    "ca-ion": "calcium-ion", "ca ion": "calcium-ion",
    "al-ion": "aluminum-ion", "al ion": "aluminum-ion",
    "zn-ion": "zinc-ion", "zn ion": "zinc-ion",
    "li-s": "lithium-sulfur", "li s": "lithium-sulfur",
    "li-air": "lithium-air", "na-s": "sodium-sulfur",
    "zn-air": "zinc-air", "fe-air": "iron-air",
    "nimh": "nickel-metal-hydride", "ni-mh": "nickel-metal-hydride",
    "vrfb": "vanadium redox", "vrb": "vanadium redox",
    # Materials
    "lifepo4": "LiFePO4", "lfp": "LiFePO4",
    "licoo2": "LiCoO2", "lco": "LiCoO2",
    "nmc": "NMC", "lini": "NMC",
    "nca": "NCA", "lto": "LTO",
    "cnt": "carbon nanotube", "cnts": "carbon nanotube",
    "mwcnt": "carbon nanotube", "swcnt": "carbon nanotube",
    "mof": "metal-organic framework", "mofs": "metal-organic framework",
    "cof": "metal-organic framework",
    # Solar
    "psc": "perovskite", "mapbi3": "halide perovskite", "fapbi3": "halide perovskite",
    "cigs": "CIGS", "cigsse": "CIGSSe", "cdte": "CdTe",
    "dssc": "dye-sensitized", "opv": "organic photovoltaic",
    "gaas": "GaAs", "inp": "InP",
    # Devices
    "pv": "photovoltaic", "oled": "OLED", "led": "LED",
    "mtj": "magnetic tunnel junction", "mtjs": "magnetic tunnel junction",
    "pem": "proton exchange membrane", "pemfc": "proton exchange membrane",
    "sofc": "solid oxide fuel cell",
    # Methods
    "xrd": "X-ray diffraction", "sem": "scanning electron microscopy",
    "tem": "transmission electron microscopy", "afm": "atomic force microscopy",
    "xps": "X-ray photoelectron spectroscopy", "ftir": "FTIR",
    "nmr": "NMR", "cv": "cyclic voltammetry", "eis": "impedance spectroscopy",
    "dft": "density functional theory", "md": "molecular dynamics",
    "ml": "machine learning", "dl": "deep learning", "nn": "neural network",
    "cvd": "chemical vapor deposition", "pvd": "physical vapor deposition",
    "ald": "atomic layer deposition",
    "cryo-em": "cryo-electron microscopy",
    "hts": "high-throughput screening",
    # Catalysis
    "oer": "OER", "her": "HER", "orr": "ORR",
    "co2rr": "CO2 reduction", "nrr": "nitrogen fixation",
    "sac": "single-atom catalyst",
    # Biology
    "e. coli": "Escherichia coli", "e.coli": "Escherichia coli",
    "s. cerevisiae": "Saccharomyces",
    "a. vinelandii": "Azotobacter",
    # Software
    "alphafold": "AlphaFold", "matlab": "VASP",
    # Polymers
    "polyethene": "polyethylene", "pe": "polyethylene",
    "polypropene": "polypropylene", "pp": "polypropylene",
    "poly(4-methyl-1-pentene)": "polypropylene",
    "microfibrous polypropylene": "polypropylene",
    # Zeolites
    "silicalite": "silicalite", "zsm-5": "ZSM-5", "zsm5": "ZSM-5",
    # Simulation methods
    "fdtd": "FDTD", "finite-difference-time-domain": "FDTD",
    "gcmc": "GCMC", "gcmc simulations": "GCMC",
    "nsga-ii": "NSGA-II", "nsga": "NSGA-II",
    "mopso": "MOPSO",
}

import re as _re

def extract_element_names(name):
    """Extract element names from chemical formulas like CoFeB, Cu(In,Ga)Se2"""
    elements_found = []
    # Match element symbols (uppercase + optional lowercase)
    for match in _re.finditer(r'([A-Z][a-z]?)', name):
        sym = match.group(1)
        if sym in ELEMENT_SYMBOLS:
            elements_found.append(ELEMENT_SYMBOLS[sym])
    return elements_found

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

def align_entity(name, entity_type):
    """Align an entity to ENVO or BDF with comprehensive matching"""
    name_lower = name.lower().strip()
    # Strip parenthetical element symbols: "Aluminium (Al)" → "aluminium"
    name_clean = _re.sub(r'\s*\([^)]{1,4}\)\s*', ' ', name_lower).strip()

    # === ENVO matching (ecosystem/organism + any entity that mentions an environment) ===
    if entity_type in ("ecosystem", "organism", "method", "metric", "material"):
        for keyword, term_id in ENVO_KEYWORDS.items():
            if keyword in name_lower or keyword in name_clean:
                return "envo", term_id, keyword
            if name_clean in keyword and len(name_clean) > 3:
                return "envo", term_id, keyword

    # === BDF matching — try ALL entity types (not just material/chemical) ===

    # 1. Direct alias expansion
    expanded = name_lower
    for abbr, full in ALIASES.items():
        if abbr == name_lower or abbr == name_clean:
            expanded = full.lower()
            break
        if f" {abbr} " in f" {name_lower} " or name_lower.startswith(abbr + " ") or name_lower.endswith(" " + abbr):
            expanded = name_lower.replace(abbr, full.lower())
            break

    # 2. Exact match against BDF terms
    for term_lower, (cat, orig) in BDF_LOOKUP.items():
        # Exact match
        if term_lower == name_lower or term_lower == name_clean or term_lower == expanded:
            return "bdf", f"bdf:{cat}:{orig}", orig
        # Expanded match
        if term_lower == expanded:
            return "bdf", f"bdf:{cat}:{orig}", orig

    # 3. Substring containment (both directions, with length guards)
    for term_lower, (cat, orig) in BDF_LOOKUP.items():
        if len(term_lower) < 3:
            continue  # Skip very short terms to avoid false matches
        # For short terms (3-4 chars), require word-boundary match
        if len(term_lower) <= 4:
            pattern = r'(?:^|[\s\-_/,;(])' + _re.escape(term_lower) + r'(?:$|[\s\-_/,;)])'
            if _re.search(pattern, name_lower) or _re.search(pattern, expanded):
                return "bdf", f"bdf:{cat}:{orig}", orig
        else:
            if term_lower in name_lower or term_lower in expanded:
                return "bdf", f"bdf:{cat}:{orig}", orig
            if name_lower in term_lower and len(name_lower) > 4:
                return "bdf", f"bdf:{cat}:{orig}", orig
            if name_clean in term_lower and len(name_clean) > 4:
                return "bdf", f"bdf:{cat}:{orig}", orig
            if expanded in term_lower and len(expanded) > 4:
                return "bdf", f"bdf:{cat}:{orig}", orig

    # 4. Element name matching — only for chemical formulas (contain uppercase+lowercase+digits pattern)
    if entity_type in ("material", "chemical") and _re.search(r'[A-Z][a-z]?\d', name):
        elements = extract_element_names(name)
        if elements:
            # Use the first element found in a formula-like name
            elem_lower = elements[0].lower()
            if elem_lower in BDF_LOOKUP:
                cat, orig = BDF_LOOKUP[elem_lower]
                return "bdf", f"bdf:{cat}:{orig}", orig

    # 5. Word-level matching: any word in entity name matches a BDF term
    words = set(_re.split(r'[\s\-_/,;]+', name_lower))
    words.update(_re.split(r'[\s\-_/,;]+', expanded))
    for w in words:
        if len(w) < 3:
            continue
        if w in BDF_LOOKUP:
            cat, orig = BDF_LOOKUP[w]
            return "bdf", f"bdf:{cat}:{orig}", orig

    # 6. Software matching by entity type
    if entity_type == "software":
        # Strip version numbers for matching: "MATLAB R2022b" → "matlab"
        sw_name = _re.sub(r'[\s_]*(v?\d[\d.a-zA-Z]*)\s*$', '', name_lower).strip()
        if sw_name in BDF_LOOKUP:
            cat, orig = BDF_LOOKUP[sw_name]
            return "bdf", f"bdf:{cat}:{orig}", orig
        # Check aliases
        if sw_name in ALIASES:
            expanded_sw = ALIASES[sw_name].lower()
            if expanded_sw in BDF_LOOKUP:
                cat, orig = BDF_LOOKUP[expanded_sw]
                return "bdf", f"bdf:{cat}:{orig}", orig

    # 7. Entity-type-based category assignment (fallback for unmatched but typed entities)
    type_to_category = {
        "organism": "biology",
        "software": "software",
        "institution": None,  # No ontology for institutions
        "dataset": None,
    }
    fallback_cat = type_to_category.get(entity_type)
    if fallback_cat and fallback_cat in BDF_CATEGORIES:
        # Check if any term partially matches
        for term in BDF_CATEGORIES[fallback_cat]:
            term_lower = term.lower()
            if any(w in term_lower for w in words if len(w) > 2):
                return "bdf", f"bdf:{fallback_cat}:{term}", term

    return None, None, name_clean

def align_paper(db, paper_id):
    """Align all unaligned entities for a paper"""
    entities = db.execute(
        "SELECT * FROM entities WHERE paper_id=? AND ontology_id IS NULL",
        (paper_id,)
    ).fetchall()

    aligned = 0
    for entity in entities:
        source, ont_id, canonical = align_entity(entity["name"], entity["entity_type"])
        if source:
            db.execute(
                "UPDATE entities SET ontology_source=?, ontology_id=?, canonical_name=? WHERE entity_id=?",
                (source, ont_id, canonical, entity["entity_id"])
            )
            aligned += 1
        else:
            # Just set canonical name
            db.execute(
                "UPDATE entities SET canonical_name=? WHERE entity_id=?",
                (canonical, entity["entity_id"])
            )

    db.commit()

    # Update paper status
    db.execute(
        "UPDATE papers SET status='aligned', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
        (paper_id,)
    )
    db.commit()

    total = len(entities)
    print(f"[ontology] {paper_id}: {aligned}/{total} entities aligned to ontologies")
    return aligned

# Main
db = get_db()
if COMMAND == "align" and PAPER_ID:
    align_paper(db, PAPER_ID)
elif COMMAND == "align-batch":
    papers = db.execute("SELECT paper_id FROM papers WHERE status='judged' LIMIT 10").fetchall()
    print(f"[ontology] Aligning {len(papers)} papers...")
    for p in papers:
        align_paper(db, p["paper_id"])
elif COMMAND == "lookup":
    name = os.environ.get("PAPER_ID", "")  # reused as lookup name
    etype = os.environ.get("ENTITY_TYPE", "material")
    src, oid, canon = align_entity(name, etype)
    print(json.dumps({"name": name, "source": src, "ontology_id": oid, "canonical": canon}, indent=2))
db.close()
PYEOF
