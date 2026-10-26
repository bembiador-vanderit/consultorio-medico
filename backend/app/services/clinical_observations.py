"""Read adapter for the existing reusable VitalSigns capture; no second storage."""
def vital_observations(vitals):
    if vitals is None: return []
    return [{"code":code,"value":getattr(vitals,key),"unit":unit,"source":"vital_signs","source_id":vitals.id,
             "clinical_history_id":vitals.clinical_history_id,"observed_at":vitals.updated_at}
        for key,code,unit in (("systolic_pressure","bp.systolic","mmHg"),("diastolic_pressure","bp.diastolic","mmHg"),
            ("heart_rate","heart_rate","/min"),("respiratory_rate","respiratory_rate","/min"),
            ("oxygen_saturation","oxygen_saturation","%"),("weight_kg","weight","kg"),("height_cm","height","cm"))
        if getattr(vitals,key) is not None]
