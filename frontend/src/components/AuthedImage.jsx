import { useEffect, useState } from "react";
import { getAccessToken } from "../auth/tokenStore.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

/** Renders an <img> for a gateway-proxied, auth-protected asset path
 * (e.g. content.image_url = "/uploads/{content_id}/{filename}"). A plain
 * <img src="..."> can't attach an Authorization header, so this fetches
 * the bytes with the access token and gives the <img> an in-memory
 * blob: URL instead. */
export function AuthedImage({ path, alt = "", className }) {
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!path) return;
    let objectUrl;
    let cancelled = false;
    setFailed(false);

    fetch(`${BASE_URL}/api${path}`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
      credentials: "include",
    })
      .then((res) => {
        if (!res.ok) throw new Error("image fetch failed");
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => { if (!cancelled) setFailed(true); });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (failed) return null;
  if (!src) return <div className={`${className} animate-pulse bg-gray-100`} />;
  return <img src={src} alt={alt} className={className} />;
}