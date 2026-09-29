import { useCallback, useEffect, useState } from "react";

export type DirtySection = "anamnesis" | "vital-signs" | "diagnoses" | "prescriptions" | "orders";

export function useConsultationDirtyState(episodeId: number) {
  const [dirtySections, setDirtySections] = useState<Set<DirtySection>>(() => new Set());

  useEffect(() => { setDirtySections(new Set()); }, [episodeId]);

  const setSectionDirty = useCallback((section: DirtySection, dirty: boolean) => {
    setDirtySections((current) => {
      const hasSection = current.has(section);
      if (hasSection === dirty) return current;
      const next = new Set(current);
      if (dirty) next.add(section);
      else next.delete(section);
      return next;
    });
  }, []);

  const hasDirtyChanges = dirtySections.size > 0;

  useEffect(() => {
    if (!hasDirtyChanges) return;
    const preventUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", preventUnload);
    return () => window.removeEventListener("beforeunload", preventUnload);
  }, [hasDirtyChanges]);

  const clearDirty = useCallback(() => setDirtySections(new Set()), []);

  return { dirtySections, hasDirtyChanges, setSectionDirty, clearDirty };
}
