"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => {
    const scrollRef = React.useRef<HTMLDivElement | null>(null);
    const tableRef = React.useRef<HTMLTableElement | null>(null);
    const [canScroll, setCanScroll] = React.useState(false);

    const setTableRefs = React.useCallback(
      (node: HTMLTableElement | null) => {
        tableRef.current = node;
        if (typeof ref === "function") ref(node);
        else if (ref) ref.current = node;
      },
      [ref]
    );

    React.useEffect(() => {
      const wrapper = scrollRef.current;
      const table = tableRef.current;
      if (!wrapper || !table) return;
      const check = () => setCanScroll(wrapper.scrollWidth > wrapper.clientWidth);
      check();
      // Observe the <table> itself, not the overflow:auto wrapper — the
      // wrapper's own box never changes size (it's the table's *content*
      // that grows wider once rows populate), so a ResizeObserver on the
      // wrapper never fired and the hint never appeared after data loaded.
      const observer = new ResizeObserver(check);
      observer.observe(table);
      return () => observer.disconnect();
    }, []);

    return (
      <div>
        <div className="admin-scroll w-full overflow-auto" ref={scrollRef}>
          <table ref={setTableRefs} className={cn("w-full caption-bottom text-sm", className)} {...props} />
        </div>
        {/* The table already scrolled horizontally without this — nothing
            hinted that it could, so narrow screens just saw truncated
            columns (confirmed in HOMOLOGATION_REPORT_v1.3.1.md). Only shown
            when the table is actually wider than its container. */}
        {canScroll && (
          <p className="mt-2 text-center text-xs text-muted-foreground">
            ← arraste para o lado para ver mais →
          </p>
        )}
      </div>
    );
  }
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} className={cn("[&_tr]:border-b [&_tr]:border-border", className)} {...props} />
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  )
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
);
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        "h-10 px-3 text-left align-middle text-xs font-medium uppercase tracking-wide text-muted-foreground",
        className
      )}
      {...props}
    />
  )
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("p-3 align-middle", className)} {...props} />
  )
);
TableCell.displayName = "TableCell";

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
