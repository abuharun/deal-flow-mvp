import type { AppProps } from "next/app";

// Keeps Next's optional Pages Router rooted beside /app so the retained legacy
// Vite source tree under /src is never interpreted as part of this build.
export default function LegacyPagesBoundary({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}
