import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { BrandingView } from "./contracts";

export const defaultBranding: BrandingView = {
  display_name: "OCI Tenancy Manager",
  logo_url: null,
  icon_url: null,
};

// Restrict public visual assets to the same deployment; branding never accepts executable URLs.
function assetUrl(value: string | null) {
  return value !== null &&
    /^\/branding-assets\/[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\.(png|webp|ico|jpg|jpeg)$/.test(value)
    ? value
    : null;
}

// Public instance identity is independent of administrator sessions and uses a generic outage fallback.
export function useBranding() {
  const result = useQuery({
    queryKey: ["branding"],
    queryFn: ({ signal }) => api.branding(signal),
    retry: false,
    staleTime: 300_000,
    refetchOnWindowFocus: false,
  });
  const branding = result.data ?? defaultBranding;
  useEffect(() => {
    const previousTitle = document.title;
    document.title = branding.display_name;
    const icon = assetUrl(branding.icon_url);
    const link = icon ? document.createElement("link") : null;
    if (link) {
      link.rel = "icon";
      link.href = icon!;
      link.dataset.applicationBranding = "true";
      document.head.append(link);
    }
    return () => {
      document.title = previousTitle;
      link?.remove();
    };
  }, [branding.display_name, branding.icon_url]);
  return branding;
}

// A missing or unloadable logo keeps the configured display name visible instead of a broken image.
export function Brand({ branding }: { branding: BrandingView }) {
  const [failedLogo, setFailedLogo] = useState<string | null>(null);
  const logo = assetUrl(branding.logo_url);
  return logo && failedLogo !== logo ? (
    <img
      className="brand-logo"
      src={logo}
      alt={branding.display_name}
      onError={() => setFailedLogo(logo)}
    />
  ) : (
    <span className="brand-name">{branding.display_name}</span>
  );
}
