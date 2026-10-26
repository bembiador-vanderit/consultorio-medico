"""expand laboratory catalog and support additional clinical orders

Revision ID: 0027_expand_laboratory_catalog
Revises: 0026_clinical_orders
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_expand_laboratory_catalog"
down_revision = "0026_clinical_orders"
branch_labels = None
depends_on = None


# Canonical transcription of the legible, named tests on the supplied
# Referencia Laboratorio Clínico form. Existing 0026 names and clear aliases
# are deliberately not duplicated (for example VSG/eritrosedimentación,
# TPT/aPTT/TTP, HbA1c and uroanálisis/examen general de orina).
FORM_LABORATORY_TESTS = (
    # Hematología
    ("Hematología", "Células LE"),
    ("Hematología", "Conteo de eosinófilos"),
    ("Hematología", "Conteo de reticulocitos"),
    ("Hematología", "Crioaglutininas"),
    ("Hematología", "Eosinófilos en secreción nasal"),
    ("Hematología", "Espermograma completo"),
    ("Hematología", "Estudios de fluidos"),
    ("Hematología", "Falcemia"),
    ("Hematología", "Fructosa en semen"),
    ("Hematología", "G6PD"),
    ("Hematología", "Investigación de filaria"),
    ("Hematología", "Panel de linfocitos (CD4-CD8)"),
    ("Hematología", "Panel de reticulocitos"),
    ("Hematología", "Test de Coombs directo"),
    ("Hematología", "Test de Coombs indirecto"),
    ("Hematología", "Tipificación sanguínea"),
    # Coagulación
    ("Coagulación", "Anticoagulante de lupus"),
    ("Coagulación", "Factor V"),
    ("Coagulación", "Factor VIII"),
    ("Coagulación", "Fibrinógeno"),
    ("Coagulación", "Fragilidad capilar"),
    ("Coagulación", "Fragilidad eritrocítica"),
    ("Coagulación", "Proteína C"),
    ("Coagulación", "Proteína S"),
    ("Coagulación", "Retracción del coágulo"),
    ("Coagulación", "Tiempo de coagulación"),
    ("Coagulación", "Tiempo de sangría"),
    ("Coagulación", "Tiempo de trombina"),
    # Inmunología / Serología
    ("Inmunología / Serología", "Alfa-1-antitripsina"),
    ("Inmunología / Serología", "ANA"),
    ("Inmunología / Serología", "Antígeno de H. pylori en heces"),
    ("Inmunología / Serología", "Aglutininas febriles"),
    ("Inmunología / Serología", "Anticardiolipina IgG/IgM"),
    ("Inmunología / Serología", "Anticardiolipina IgA"),
    ("Inmunología / Serología", "Anti-DNA"),
    ("Inmunología / Serología", "ASO cuantitativo"),
    ("Inmunología / Serología", "ASO látex"),
    ("Inmunología / Serología", "Complemento C3"),
    ("Inmunología / Serología", "Complemento C4"),
    ("Inmunología / Serología", "Calprotectina"),
    ("Inmunología / Serología", "Ceruloplasmina"),
    ("Inmunología / Serología", "Clamidia IgA"),
    ("Inmunología / Serología", "Clamidia IgG"),
    ("Inmunología / Serología", "Clamidia IgM"),
    ("Inmunología / Serología", "Electroforesis de hemoglobina capilar"),
    ("Inmunología / Serología", "Electroforesis de proteína capilar"),
    ("Inmunología / Serología", "Factor reumatoide cuantitativo"),
    ("Inmunología / Serología", "Factor reumatoide látex"),
    ("Inmunología / Serología", "FTA-ABS"),
    ("Inmunología / Serología", "H. pylori"),
    ("Inmunología / Serología", "IgA"),
    ("Inmunología / Serología", "IgG"),
    ("Inmunología / Serología", "IgG subclases"),
    ("Inmunología / Serología", "IgM"),
    ("Inmunología / Serología", "Inmunofijación"),
    ("Inmunología / Serología", "Mycoplasma pneumoniae IgM"),
    ("Inmunología / Serología", "Monotest"),
    ("Inmunología / Serología", "PCR látex"),
    ("Inmunología / Serología", "Panel autoinmune"),
    ("Inmunología / Serología", "Paperas IgG"),
    ("Inmunología / Serología", "Paperas IgM"),
    ("Inmunología / Serología", "Péptido cíclico citrulinado (anti-CCP)"),
    ("Inmunología / Serología", "RPR (VDRL)"),
    ("Inmunología / Serología", "Sarampión IgG"),
    ("Inmunología / Serología", "Sarampión IgM"),
    ("Inmunología / Serología", "VDRL en LCR"),
    ("Inmunología / Serología", "Varicela zóster IgG"),
    ("Inmunología / Serología", "Varicela zóster IgM"),
    # Química sanguínea
    ("Química sanguínea", "Alcohol en saliva"),
    ("Química sanguínea", "Amilasa"),
    ("Química sanguínea", "Amilasa en orina casual"),
    ("Química sanguínea", "Amilasa pancreática"),
    ("Química sanguínea", "Amonio"),
    ("Química sanguínea", "Apolipoproteína A1"),
    ("Química sanguínea", "Apolipoproteína B"),
    ("Química sanguínea", "BUN"),
    ("Química sanguínea", "CO2"),
    ("Química sanguínea", "Colinesterasa plasmática"),
    ("Química sanguínea", "Curva de glucosa"),
    ("Química sanguínea", "Electrolitos"),
    ("Química sanguínea", "Electrolitos en sudor"),
    ("Química sanguínea", "Fosfatasa ácida prostática"),
    ("Química sanguínea", "Fosfatasa ácida"),
    ("Química sanguínea", "Fructosamina"),
    ("Química sanguínea", "Gases arteriales"),
    ("Química sanguínea", "Glucosa posprandial"),
    ("Química sanguínea", "Hierro y captación"),
    ("Química sanguínea", "IgE"),
    ("Química sanguínea", "Lactato"),
    ("Química sanguínea", "Lipasa"),
    ("Química sanguínea", "Lipoproteína(a)"),
    ("Química sanguínea", "Plomo"),
    ("Química sanguínea", "Potasio en orina casual"),
    ("Química sanguínea", "Potasio en orina de 24 horas"),
    ("Química sanguínea", "Prealbúmina"),
    ("Química sanguínea", "Proteínas totales en orina casual"),
    ("Química sanguínea", "Transferrina"),
    ("Química sanguínea", "Zinc"),
    # Hormonas
    ("Hormonas", "17-hidroxiprogesterona"),
    ("Hormonas", "ACTH"),
    ("Hormonas", "Aldosterona"),
    ("Hormonas", "Androstenediona"),
    ("Hormonas", "Antitiroglobulina"),
    ("Hormonas", "Anti-TPO"),
    ("Hormonas", "Anti-TSHR (TSI)"),
    ("Hormonas", "β-hCG cuantitativa"),
    ("Hormonas", "Beta CrossLaps"),
    ("Hormonas", "Cortisol AM"),
    ("Hormonas", "Cortisol PM"),
    ("Hormonas", "DHEA-SO4"),
    ("Hormonas", "Estradiol 17β"),
    ("Hormonas", "Estrógenos totales"),
    ("Hormonas", "FSH"),
    ("Hormonas", "Hormona de crecimiento basal"),
    ("Hormonas", "Hormona de crecimiento con estímulo"),
    ("Hormonas", "IGF-1"),
    ("Hormonas", "Insulina"),
    ("Hormonas", "Curva de insulina"),
    ("Hormonas", "LH"),
    ("Hormonas", "Osteocalcina"),
    ("Hormonas", "P1NP"),
    ("Hormonas", "Péptido C"),
    ("Hormonas", "Progesterona"),
    ("Hormonas", "Prolactina"),
    ("Hormonas", "PTH intacta"),
    ("Hormonas", "SHBG"),
    ("Hormonas", "T3 libre"),
    ("Hormonas", "T4 total"),
    ("Hormonas", "Testosterona"),
    ("Hormonas", "Testosterona libre"),
    ("Hormonas", "Tiroglobulina"),
    # Marcadores tumorales
    ("Marcadores tumorales", "Alfa-fetoproteína"),
    ("Marcadores tumorales", "CA 15-3"),
    ("Marcadores tumorales", "CA 125"),
    ("Marcadores tumorales", "CA 19-9"),
    ("Marcadores tumorales", "CA 72.4"),
    ("Marcadores tumorales", "CEA"),
    ("Marcadores tumorales", "Cyfra 21-1 (citoqueratina 19)"),
    ("Marcadores tumorales", "HE4"),
    ("Marcadores tumorales", "PSA libre y total"),
    # Marcadores hepáticos
    ("Marcadores hepáticos", "Antígeno australiano (HBsAg)"),
    ("Marcadores hepáticos", "Anti-HBc IgM"),
    ("Marcadores hepáticos", "Anti-HAV"),
    ("Marcadores hepáticos", "Anti-HAV IgM"),
    ("Marcadores hepáticos", "Anti-HBc IgG"),
    ("Marcadores hepáticos", "Anti-HBe"),
    ("Marcadores hepáticos", "Anti-HBs"),
    ("Marcadores hepáticos", "HBeAg"),
    ("Marcadores hepáticos", "Hepatitis C"),
    # Marcadores cardíacos
    ("Marcadores cardíacos", "Homocisteína"),
    ("Marcadores cardíacos", "Mioglobina"),
    ("Marcadores cardíacos", "Troponina cualitativa"),
    ("Marcadores cardíacos", "Troponina I cuantitativa"),
    # Infecciosas
    ("Enfermedades infecciosas", "Ameba en suero Ac"),
    ("Enfermedades infecciosas", "Antígeno p24"),
    ("Enfermedades infecciosas", "Anti-HIV 1/2 Ac"),
    ("Enfermedades infecciosas", "Citomegalovirus IgG"),
    ("Enfermedades infecciosas", "Citomegalovirus IgM"),
    ("Enfermedades infecciosas", "Dengue antígeno NS1"),
    ("Enfermedades infecciosas", "Dengue IgG/IgM"),
    ("Enfermedades infecciosas", "Dengue rápido IgG/IgM"),
    ("Enfermedades infecciosas", "Epstein-Barr IgM"),
    ("Enfermedades infecciosas", "Herpes I/II IgG"),
    ("Enfermedades infecciosas", "Herpes I/II IgM"),
    ("Enfermedades infecciosas", "HTLV I/II"),
    ("Enfermedades infecciosas", "Leptospira IgM"),
    ("Enfermedades infecciosas", "Malaria Ac"),
    ("Enfermedades infecciosas", "Panel Epstein-Barr IgG"),
    ("Enfermedades infecciosas", "Panel TORCH IgG/IgM"),
    ("Enfermedades infecciosas", "Procalcitonina"),
    ("Enfermedades infecciosas", "Rubéola IgG/IgM"),
    ("Enfermedades infecciosas", "Toxoplasmosis IgG/IgM"),
    ("Enfermedades infecciosas", "Western Blot"),
    # Microbiología
    ("Microbiología", "ADN de C. difficile citotoxigénico fecal"),
    ("Microbiología", "Antígeno de cólera O1-O139"),
    ("Microbiología", "Antígeno de estreptococo A rápido"),
    ("Microbiología", "Baciloscopia"),
    ("Microbiología", "Clostridium difficile toxina A/B"),
    ("Microbiología", "Coloración de Gram"),
    ("Microbiología", "Coloración de Ziehl-Neelsen"),
    ("Microbiología", "Cultivo"),
    ("Microbiología", "Cultivo de Mycobacterium tuberculosis complex"),
    ("Microbiología", "Estreptococo grupo B"),
    ("Microbiología", "Estreptococo grupo A rápido"),
    ("Microbiología", "GeneXpert GBS"),
    ("Microbiología", "GeneXpert MTB/RIF"),
    ("Microbiología", "Hemocultivos automatizados (BacT/Alert)"),
    ("Microbiología", "Investigación de Demodex folliculorum"),
    ("Microbiología", "Leukotest"),
    ("Microbiología", "Panel de sepsis FilmArray"),
    ("Microbiología", "Panel gastrointestinal FilmArray"),
    ("Microbiología", "Panel respiratorio FilmArray"),
    ("Microbiología", "Preparación de KOH"),
    ("Microbiología", "Rotavirus"),
    ("Microbiología", "Scotch Tape"),
    ("Microbiología", "Shiga toxin (EHEC)"),
    ("Microbiología", "Tuberculina"),
    # Biología molecular
    ("Biología molecular", "Citomegalovirus DNA-PCR"),
    ("Biología molecular", "Dengue virus RNA"),
    ("Biología molecular", "Genotipificación hepatitis B"),
    ("Biología molecular", "Genotipificación hepatitis C"),
    ("Biología molecular", "Genotipificación VIH"),
    ("Biología molecular", "Hepatitis B PCR en tiempo real"),
    ("Biología molecular", "Hepatitis C PCR en tiempo real"),
    ("Biología molecular", "Herpes I/II por PCR"),
    ("Biología molecular", "HIV-1 PCR en tiempo real v2.0"),
    ("Biología molecular", "HPV alto riesgo (16 y 18)"),
    ("Biología molecular", "HPV genotipificación (alto y bajo riesgo)"),
    ("Biología molecular", "IL28B (interleucina)"),
    ("Biología molecular", "Influenza A H1N1 (2009)"),
    ("Biología molecular", "Mycobacterium TB resistencia RIF/INH"),
    ("Biología molecular", "Mycobacterium TB resistencia RIF/INH y XDR"),
    ("Biología molecular", "Neisseria gonorrhoeae en orina"),
    ("Biología molecular", "Neisseria gonorrhoeae endocervical"),
    ("Biología molecular", "Panel ITS"),
    ("Biología molecular", "Virus del papiloma humano (VPH) por PCR"),
    # Orina
    ("Orina", "17-cetosteroides (17-cetos)"),
    ("Orina", "17-hidroxicorticosteroides (17-OH)"),
    ("Orina", "Ácido úrico en orina de 24 horas"),
    ("Orina", "Ácido vanilmandélico (VMA)"),
    ("Orina", "Calcio en orina de 24 horas"),
    ("Orina", "Creatinina en orina de 24 horas"),
    ("Orina", "Depuración de creatinina"),
    ("Orina", "Fósforo en orina de 24 horas"),
    ("Orina", "Microalbúmina cualitativa"),
    ("Orina", "Microalbúmina cuantitativa"),
    ("Orina", "Proteínas de Bence Jones"),
    ("Orina", "Proteínas en orina de 24 horas"),
    ("Orina", "Urea en orina de 24 horas"),
    # Parasitología
    ("Parasitología", "Antígeno de Cryptosporidium y Giardia"),
    ("Parasitología", "Antígeno de Entamoeba histolytica"),
    ("Parasitología", "Conteo de hematíes en heces"),
    ("Parasitología", "Conteo de leucocitos en heces"),
    ("Parasitología", "Coprológico con investigación de amebas"),
    ("Parasitología", "Digestión en materias fecales"),
    ("Parasitología", "Dismorfia eritrocítica"),
    ("Parasitología", "Grasas en heces"),
    ("Parasitología", "Investigación de amebas"),
    ("Parasitología", "Investigación de coccidios intestinales"),
    ("Parasitología", "Investigación de Cryptosporidium"),
    ("Parasitología", "Investigación de oxiuros"),
    ("Parasitología", "Microsporidios"),
    ("Parasitología", "Panel triple para protozoarios"),
    ("Parasitología", "Sangre oculta"),
    ("Parasitología", "Sustancias reductoras en heces"),
    ("Parasitología", "Tripsina en heces"),
    # Drogas terapéuticas
    ("Drogas terapéuticas", "Ácido valproico"),
    ("Drogas terapéuticas", "Ciclosporina"),
    ("Drogas terapéuticas", "Digoxina"),
    ("Drogas terapéuticas", "Fenitoína (Dilantin)"),
    ("Drogas terapéuticas", "Everolimus"),
    ("Drogas terapéuticas", "Fenobarbital"),
    ("Drogas terapéuticas", "Litio"),
    ("Drogas terapéuticas", "Metotrexato"),
    ("Drogas terapéuticas", "Tacrolimus"),
    ("Drogas terapéuticas", "Carbamazepina (Tegretol)"),
    ("Drogas terapéuticas", "Teofilina"),
    # Drogas de abuso
    ("Drogas de abuso", "Anfetaminas"),
    ("Drogas de abuso", "Benzodiazepinas"),
    ("Drogas de abuso", "Cocaína"),
    ("Drogas de abuso", "Éxtasis (MDMA)"),
    ("Drogas de abuso", "Marihuana"),
    ("Drogas de abuso", "Nicotina"),
    ("Drogas de abuso", "Opiatos"),
)


def upgrade() -> None:
    op.add_column("laboratory_tests", sa.Column("seed_key", sa.String(length=120), nullable=True))
    op.create_index("ix_laboratory_tests_seed_key", "laboratory_tests", ["seed_key"])
    op.add_column(
        "laboratory_orders",
        sa.Column("is_additional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_laboratory_orders_is_additional", "laboratory_orders", ["is_additional"])
    op.add_column(
        "study_orders",
        sa.Column("is_additional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_study_orders_is_additional", "study_orders", ["is_additional"])

    # The original combined bucket is split without changing any order-item
    # snapshot already emitted from it.
    op.execute(sa.text(
        "UPDATE laboratory_tests SET category = 'Drogas de abuso' "
        "WHERE lower(name) = lower('Panel toxicológico') "
        "AND category = 'Drogas terapéuticas / abuso'"
    ))

    for index, (category, name) in enumerate(FORM_LABORATORY_TESTS, start=1):
        op.execute(sa.text(
            "INSERT INTO laboratory_tests "
            "(code, name, category, is_active, sort_order, seed_key, created_at, updated_at) "
            "SELECT NULL, :name, :category, true, :sort_order, :seed_key, now(), now() "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM laboratory_tests WHERE lower(trim(name)) = lower(trim(:name))"
            ")"
        ).bindparams(
            name=name,
            category=category,
            sort_order=1000 + index,
            seed_key=f"0027:{index:03d}",
        ))


def downgrade() -> None:
    # Preserve any seeded test that has already acquired a clinical reference;
    # only unused records introduced by this migration are removed.
    op.execute(sa.text(
        "DELETE FROM laboratory_tests t WHERE t.seed_key LIKE '0027:%' "
        "AND NOT EXISTS (SELECT 1 FROM laboratory_order_items i WHERE i.laboratory_test_id = t.id)"
    ))
    op.execute(sa.text(
        "UPDATE laboratory_tests SET category = 'Drogas terapéuticas / abuso' "
        "WHERE lower(name) = lower('Panel toxicológico') AND category = 'Drogas de abuso'"
    ))
    op.drop_index("ix_study_orders_is_additional", table_name="study_orders")
    op.drop_column("study_orders", "is_additional")
    op.drop_index("ix_laboratory_orders_is_additional", table_name="laboratory_orders")
    op.drop_column("laboratory_orders", "is_additional")
    op.drop_index("ix_laboratory_tests_seed_key", table_name="laboratory_tests")
    op.drop_column("laboratory_tests", "seed_key")
