from collections import Counter
import importlib.util
from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def load_migration(name: str):
    path = VERSIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expanded_laboratory_seed_is_complete_and_has_no_duplicate_names():
    migration_26 = load_migration("0026_clinical_orders")
    migration_27 = load_migration("0027_expand_laboratory_catalog")
    rows = list(migration_26.LABORATORY_TESTS) + list(migration_27.FORM_LABORATORY_TESTS)
    names = [name.casefold().strip() for _, name in rows]
    assert len(names) == len(set(names)) == 321

    counts = Counter(category for category, _ in rows)
    counts["Drogas terapéuticas / abuso"] -= 1
    del counts["Drogas terapéuticas / abuso"]
    counts["Drogas de abuso"] += 1
    assert counts == {
        "Hematología": 21,
        "Coagulación": 16,
        "Química sanguínea": 54,
        "Inmunología / Serología": 42,
        "Hormonas": 36,
        "Marcadores cardíacos": 9,
        "Marcadores tumorales": 10,
        "Marcadores hepáticos": 15,
        "Enfermedades infecciosas": 21,
        "Microbiología": 25,
        "Biología molecular": 20,
        "Orina": 14,
        "Parasitología": 18,
        "Drogas terapéuticas": 11,
        "Drogas de abuso": 8,
        "Otros": 1,
    }

    expected = {
        "Hematología": "Tipificación sanguínea",
        "Coagulación": "Anticoagulante de lupus",
        "Inmunología / Serología": "Péptido cíclico citrulinado (anti-CCP)",
        "Química sanguínea": "Creatinina",
        "Hormonas": "TSH",
        "Marcadores cardíacos": "Troponina I cuantitativa",
        "Marcadores tumorales": "CA 125",
        "Marcadores hepáticos": "Antígeno australiano (HBsAg)",
        "Enfermedades infecciosas": "Dengue antígeno NS1",
        "Microbiología": "Panel respiratorio FilmArray",
        "Biología molecular": "HIV-1 PCR en tiempo real v2.0",
        "Orina": "Ácido vanilmandélico (VMA)",
        "Parasitología": "Antígeno de Cryptosporidium y Giardia",
        "Drogas terapéuticas": "Ácido valproico",
        "Drogas de abuso": "Benzodiazepinas",
        "Otros": "Prueba de embarazo",
    }
    assert all((category, name) in rows for category, name in expected.items())
