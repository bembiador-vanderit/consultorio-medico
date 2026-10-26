"""Field transcription of the two-page preoperative form supplied by the clinic.

PCB and IVY deliberately retain the source labels; their meaning is not inferred.
All lines are free text so the physician, not Atlas, supplies clinical meaning.
"""

PHYSICAL_EXAM_FIELDS = (
    ("ta", "TA"), ("fc", "FC"), ("fr", "FR"), ("sato2", "SatO2"),
    ("peso", "Peso"), ("pcb", "PCB"), ("ivy", "IVY"), ("apex", "APEX"),
    ("corazon", "Corazón"), ("pulmones", "Pulmones"), ("abdomen", "Abdomen"),
    ("extremidades_inferiores", "Extremidades inferiores"),
)

PREOPERATIVE_SECTIONS = (
    ("Datos generales y procedimiento", (
        ("diagnostico_enfermedad", "Diagnóstico de enfermedad"),
        ("procedimiento", "Procedimiento previsto"),
        ("g", "G"), ("p", "P"), ("c", "C"), ("a", "A"),
    )),
    ("Síntomas cardiovasculares actuales", (
        ("dolor_toracico", "Dolor torácico"), ("dolor_reposo", "Dolor en reposo"),
        ("dolor_esfuerzo", "Dolor con esfuerzo"), ("disnea_esfuerzo", "Disnea de esfuerzo"),
        ("disnea_reposo", "Disnea en reposo"), ("palpitaciones", "Palpitaciones"),
        ("claudicacion", "Claudicación"), ("sincope", "Síncope"),
        ("mareos", "Mareos"), ("cefalea", "Cefalea"),
    )),
    ("Antecedentes de enfermedad cardiovascular", (
        ("hta", "HTA"), ("hta_leve", "HTA leve"), ("hta_moderada", "HTA moderada"),
        ("hta_severa", "HTA severa"), ("valvulopatia", "Valvulopatía"),
        ("preeclampsia", "Pre-eclampsia"), ("eclampsia", "Eclampsia"),
        ("iam", "IAM"), ("acv", "ACV"), ("arritmias", "Arritmias"),
        ("fiebre_reumatica", "Fiebre reumática"), ("angina_estable", "Angina estable"),
        ("angina_inestable", "Angina inestable"), ("anticonceptivos", "Anticonceptivos"),
        ("medicamentos", "Medicamentos"), ("antecedentes_otros", "Otros"),
    )),
    ("Enfermedades no quirúrgicas asociadas", (
        ("obesidad", "Obesidad"), ("tabaquismo", "Tabaquismo"),
        ("alcoholismo", "Alcoholismo"), ("diabetes", "Diabetes"),
        ("hepatitis", "Hepatitis"), ("asma_b", "Asma B"), ("alergia", "Alergia"),
        ("bronquitis", "Bronquitis"), ("enfermedad_tiroidea", "Enfermedad tiroidea"),
        ("falcemia", "Falcemia"), ("enfisema_pulmonar", "Enfisema pulmonar"),
        ("enfermedades_otros", "Otros"),
    )),
    ("Examen físico", PHYSICAL_EXAM_FIELDS),
    ("Laboratorio", (
        ("gb", "GB"), ("gr", "GR"), ("hb", "HB"), ("hcto", "HCTO"),
        ("plaq", "PLAQ"), ("bun", "BUN"), ("urea", "UREA"),
        ("glicemia", "Glicemia"), ("creatinina", "Creatinina"),
        ("tgo", "TGO"), ("tgp", "TGP"), ("tc", "TC"), ("ts", "TS"),
        ("pt", "PT"), ("tpt", "TPT"), ("inr", "INR"), ("hiv", "HIV"),
        ("hbsag", "HBSAG"), ("hcv", "HCV"), ("tipificacion", "Tipificación"),
        ("vdrl", "VDRL"), ("colesterol_total", "Colesterol total"),
        ("trigliceridos", "Triglicéridos"), ("acido_urico", "Ácido úrico"),
        ("examen_orina", "Ex. orina"), ("laboratorio_otros", "Otros"),
    )),
    ("Electrocardiograma", (
        ("ecg_ritmo", "Ritmo"), ("ecg_fc", "FC"), ("ecg_eje", "Eje"),
        ("ecg_onda_q", "Ondas Q patológicas"), ("ecg_fib_auricular", "Fibrilación auricular"),
        ("ecg_otros", "Otros"),
    )),
    ("Radiografía de tórax", (
        ("rx_cardiomegalia", "Cardiomegalia"), ("rx_efusion_pleural", "Efusión pleural"),
        ("rx_congestion", "Estado de congestión"), ("rx_otros", "Otros hallazgos"),
    )),
    ("Ecocardiograma y otros estudios", (
        ("ecocardiograma", "Ecocardiograma"), ("test_esfuerzo", "Test de esfuerzo"),
        ("estudios_otros", "Otros"),
    )),
    ("Conclusiones, riesgos y recomendaciones", (
        ("conclusion_ecocardiograma", "Ecocardiograma"),
        ("otras_patologias", "Otras patologías"),
        ("riesgos_alergicos", "Riesgos alérgicos"),
        ("recomendaciones", "Recomendaciones"),
    )),
)

PREOPERATIVE_KEYS = frozenset(key for _, fields in PREOPERATIVE_SECTIONS for key, _ in fields)
PHYSICAL_KEYS = frozenset(key for key, _ in PHYSICAL_EXAM_FIELDS)
ADMINISTRATIVE_KEYS = frozenset({"procedimiento"})
