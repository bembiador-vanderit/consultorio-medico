import {useEffect, useState} from "react";
import {api} from "./api";
import type {User} from "../types/user";

export const visibilityFeatures = {
  clinical_safety_full: "Panel completo",
  clinical_safety_critical_alert: "Alertas críticas",
} as const;
export type VisibilityFeature = keyof typeof visibilityFeatures;
export type VisibilityFeatures = Record<VisibilityFeature, boolean>;
const hidden = ():VisibilityFeatures => ({clinical_safety_full:false,clinical_safety_critical_alert:false});

/** UI decisions only. Never use these booleans as an authorization grant. */
export function useFeatureVisibility(user:User, centerId?:number|null, contextCode="ambulatory", enabled=true) {
  const identity = `${user.id}:${user.organization?.id ?? ""}:${[...user.roles].sort().join(",")}`;
  const key=`${identity}:${centerId??"organization"}:${contextCode}:${enabled}`;
  const [state,setState] = useState<{key:string;features:VisibilityFeatures}>({key,features:hidden()});
  useEffect(()=>{
    let live=true, sequence=0;
    const setFeatures=(features:VisibilityFeatures)=>setState({key,features});
    setFeatures(hidden());
    if(!enabled)return;
    async function refresh(){
      const request=++sequence;
      try {
        const {data} = await api.get("/feature-visibility/resolved", {params:{context_code:contextCode,...(centerId?{center_id:centerId}:{})}});
        if(live&&request===sequence)setFeatures({clinical_safety_full:data?.features?.clinical_safety_full===true,
          clinical_safety_critical_alert:data?.features?.clinical_safety_critical_alert===true});
      } catch {if(live&&request===sequence)setFeatures(hidden());}
    }
    void refresh();
    const focus=()=>void refresh();
    const visible=()=>{if(document.visibilityState==="visible")void refresh();};
    window.addEventListener("focus",focus);
    window.addEventListener("atlas-feature-visibility-changed",focus);
    document.addEventListener("visibilitychange",visible);
    // Refresh UI policy, not a source of truth: each decision comes from backend.
    const interval=window.setInterval(()=>{if(document.visibilityState==="visible")void refresh();},60_000);
    return()=>{live=false;sequence++;window.clearInterval(interval);window.removeEventListener("focus",focus);
      window.removeEventListener("atlas-feature-visibility-changed",focus);document.removeEventListener("visibilitychange",visible);};
  },[identity,centerId,contextCode,enabled]);
  return state.key===key?state.features:hidden();
}
