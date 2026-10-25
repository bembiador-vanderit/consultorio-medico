import type {User} from "../../types/user";
import {useFeatureVisibility} from "../../services/featureVisibility";
import PatientSafetyProfile from "./PatientSafetyProfile";

/** Ambulatory composition. The underlying profile retains its permission checks. */
export default function ContextualSafetyProfile({patientId,patientName,user,centerId}:{patientId:number;patientName:string;user:User;centerId?:number|null}) {
  const visible=useFeatureVisibility(user,centerId);
  if(!visible.clinical_safety_full&&!visible.clinical_safety_critical_alert)return null;
  return <PatientSafetyProfile key={`${patientId}:${visible.clinical_safety_full}`} patientId={patientId} patientName={patientName} user={user}
    fullVisible={visible.clinical_safety_full} criticalAlertsVisible={visible.clinical_safety_critical_alert}/>;
}
