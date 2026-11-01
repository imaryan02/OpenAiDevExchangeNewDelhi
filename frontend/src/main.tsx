import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";

import { App } from "./App";
import { isPersonalAgentPath } from "./personal-agent/state";
import "./styles.css";

const PersonalAgentDemo = lazy(() => import("./personal-agent/PersonalAgentDemo"));
const HospitalOsDemo = lazy(() => import("./hospitalos/HospitalOsDemo"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FluentProvider theme={webLightTheme}>
      {window.location.pathname.replace(/\/$/, "") === "/demo/hospitalos"
        ? <Suspense fallback={<div className="app-loading">Loading facility locator…</div>}><HospitalOsDemo /></Suspense>
        : isPersonalAgentPath(window.location.pathname)
        ? <Suspense fallback={<div className="app-loading">Loading personal workspace…</div>}><PersonalAgentDemo /></Suspense>
        : <App />}
    </FluentProvider>
  </StrictMode>
);
