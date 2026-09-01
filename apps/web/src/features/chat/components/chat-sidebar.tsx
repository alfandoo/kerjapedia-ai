import type { ReactNode } from "react";

type ChatSidebarProps = {
  expanded: boolean;
  expandedContent: ReactNode;
  collapsedContent: ReactNode;
};

export function ChatSidebar({ expanded, expandedContent, collapsedContent }: ChatSidebarProps) {
  return expanded ? (
    <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar max-[760px]:hidden">
      {expandedContent}
    </aside>
  ) : (
    <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar p-[14px_8px_12px] max-[760px]:hidden">
      {collapsedContent}
    </aside>
  );
}
