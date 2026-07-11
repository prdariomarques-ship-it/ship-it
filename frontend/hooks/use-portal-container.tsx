"use client";

import * as React from "react";

// Radix `Portal`-based primitives (Dialog, Select, Toast) render into
// `document.body` by default — outside the `.admin-theme` wrapper div that
// scopes every CSS custom property (`--admin-background`, `--admin-card`,
// ...) and the border/button resets. Rendered there, `hsl(var(--admin-card))`
// resolves to nothing and the dialog/select/toast paints with no visible
// background or border. Passing this container (a node that lives *inside*
// `.admin-theme`) as each primitive's `container` prop keeps them in the
// same CSS scope instead.
const PortalContainerContext = React.createContext<HTMLDivElement | null>(null);

export function PortalContainerProvider({
  containerRef,
  children,
}: {
  containerRef: React.RefObject<HTMLDivElement>;
  children: React.ReactNode;
}) {
  const [container, setContainer] = React.useState<HTMLDivElement | null>(null);

  React.useEffect(() => {
    setContainer(containerRef.current);
  }, [containerRef]);

  return <PortalContainerContext.Provider value={container}>{children}</PortalContainerContext.Provider>;
}

export function usePortalContainer(): HTMLDivElement | undefined {
  return React.useContext(PortalContainerContext) ?? undefined;
}
