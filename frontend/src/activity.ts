import { useEffect, useRef } from "react";
import { api, ApiError } from "./api";

// Renew idle time only on real browser input, at most once per minute; polling never calls this.
export function useActivity(enabled: boolean, onExpired: () => void) {
  const last = useRef(0);
  const expired = useRef(onExpired);
  expired.current = onExpired;
  useEffect(() => {
    if (!enabled) return;
    last.current = Date.now();
    // This client assertion is a convenience; server-side expiry/authorization still governs every API.
    function activity(event: Event) {
      if (!event.isTrusted || Date.now() - last.current < 60_000) return;
      last.current = Date.now();
      void api.activity().catch((error) => {
        if (error instanceof ApiError && error.status === 401)
          expired.current();
      });
    }
    document.addEventListener("pointerdown", activity, { passive: true });
    document.addEventListener("keydown", activity);
    return () => {
      document.removeEventListener("pointerdown", activity);
      document.removeEventListener("keydown", activity);
    };
  }, [enabled]);
}
