"use client";

import React, { ReactNode, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard,
  Boxes,
  ShoppingCart,
  Truck,
  Package,
  Building2,
  Warehouse,
  AlertTriangle,
  BarChart2,
  Users,
  LogOut,
  Menu,
  X,
  User as UserIcon,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { NAVIGATION_CONFIG, getVisibleNavItems } from "@/config/navigation";

interface AppLayoutProps {
  children: ReactNode;
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  LayoutDashboard,
  Boxes,
  ShoppingCart,
  Truck,
  Package,
  Building2,
  Warehouse,
  AlertTriangle,
  BarChart2,
  Users,
};

const SECTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Operations: Boxes,
  Catalog: Package,
  Insights: BarChart2,
  Administration: Users,
};

export default function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  const visibleNavItems = user ? getVisibleNavItems(user.role) : [];
  // Filter items within each section too: a section passes only with its
  // visible items, otherwise unauthorized modules leak into the sidebar.
  const visibleSections = NAVIGATION_CONFIG.map((section) => ({
    ...section,
    items: section.items.filter((item) => visibleNavItems.includes(item)),
  })).filter((section) => section.items.length > 0);

  const roleColors: Record<string, string> = {
    ADMIN: "bg-purple-100 text-purple-800 border-purple-200",
    SUPPLY_CHAIN_MANAGER: "bg-blue-100 text-blue-800 border-blue-200",
    WAREHOUSE_MANAGER: "bg-amber-100 text-amber-800 border-amber-200",
    ANALYST: "bg-slate-100 text-slate-800 border-slate-200",
  };

  const isItemActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const isSectionActive = (section: { items: { href: string }[] }) =>
    section.items.some((item) => isItemActive(item.href));

  const toggleSection = (label: string) => {
    setExpandedSections((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  const renderNavItem = (item: { name: string; href: string; icon: React.ComponentType<{ className?: string }> }, isMobile = false) => {
    const isActive = isItemActive(item.href);
    const Icon = item.icon;
    return (
      <Link
        key={item.name}
        href={item.href}
        onClick={isMobile ? () => setMobileMenuOpen(false) : undefined}
        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          isActive
            ? "bg-indigo-50 text-indigo-700 font-semibold"
            : isMobile
            ? "text-slate-600 hover:bg-slate-50"
            : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
        }`}
      >
        <Icon className={`h-4 w-4 ${isActive ? "text-indigo-600" : "text-slate-400"}`} />
        {item.name}
      </Link>
    );
  };

  const renderSection = (section: { label?: string; items: { name: string; href: string; icon: React.ComponentType<{ className?: string }> }[] }, isMobile = false) => {
    if (!section.label) {
      return section.items.map((item) => renderNavItem(item, isMobile));
    }

    const SectionIcon = SECTION_ICONS[section.label] || Boxes;
    const isExpanded = expandedSections[section.label] !== false;
    const isActive = isSectionActive(section);

    if (isMobile) {
      return (
        <div className="space-y-1">
          <button
            onClick={() => toggleSection(section.label!)}
            className={`flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-700 ${
              isActive ? "text-indigo-600" : ""
            }`}
          >
            <span className="flex items-center gap-2">
              <SectionIcon className="h-4 w-4" />
              {section.label}
            </span>
            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
          {isExpanded && (
            <div className="pl-6 space-y-1">
              {section.items.map((item) => renderNavItem(item, true))}
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <SectionIcon className="h-3.5 w-3.5 text-slate-400" />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{section.label}</span>
        </div>
        {section.items.map((item) => renderNavItem(item, false))}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col fixed inset-y-0 z-30 border-r border-slate-200 bg-white">
        <div className="flex h-16 items-center px-6 border-b border-slate-100">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold">
              SC
            </div>
            <span className="font-semibold text-slate-800 text-base tracking-tight">
              Supply Chain
            </span>
          </Link>
        </div>

        <div className="flex flex-1 flex-col justify-between overflow-y-auto px-3 py-4">
          <nav className="space-y-1">
            {visibleSections.map((section) => renderSection(section, false))}
          </nav>

          {/* User Profile in Sidebar Footer */}
          {user && (
            <div className="mt-auto border-t border-slate-100 pt-4 px-2">
              <div className="flex items-center gap-3 mb-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                  <UserIcon className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-slate-800">
                    {user.name}
                  </p>
                  <p className="truncate text-xs text-slate-500">{user.email}</p>
                </div>
              </div>
              <div className="mb-3">
                <span
                  className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider ${
                    roleColors[user.role] || "bg-slate-100 text-slate-700"
                  }`}
                >
                  {user.role.replace(/_/g, " ")}
                </span>
                {user.warehouse_id && (
                  <p className="text-[10px] text-slate-500 mt-1">Warehouse: #{user.warehouse_id}</p>
                )}
              </div>
              <button
                onClick={logout}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-red-50 hover:text-red-700 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-indigo-600 text-white font-bold text-xs">
            SC
          </div>
          <span className="font-semibold text-slate-800 text-sm">Supply Chain</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="rounded p-1 text-slate-600 hover:bg-slate-100"
        >
          {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-30 flex flex-col bg-white pt-14">
          <nav className="flex-1 space-y-1 p-4 overflow-y-auto">
            {visibleSections.map((section) => renderSection(section, true))}
          </nav>
          {user && (
            <div className="border-t border-slate-100 p-4">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <p className="text-sm font-medium text-slate-800">{user.name}</p>
                  <p className="text-xs text-slate-500">{user.email}</p>
                </div>
                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded border uppercase ${
                    roleColors[user.role] || "bg-slate-100"
                  }`}
                >
                  {user.role}
                </span>
              </div>
              {user.warehouse_id && (
                <p className="text-[10px] text-slate-500 mb-2">Warehouse: #{user.warehouse_id}</p>
              )}
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-md bg-slate-100 py-2 text-xs font-medium text-red-600"
              >
                <LogOut className="h-4 w-4" /> Sign out
              </button>
            </div>
          )}
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 md:pl-64 flex flex-col min-h-screen pt-14 md:pt-0">
        <div className="p-4 sm:p-6 md:p-8 max-w-7xl w-full mx-auto">{children}</div>
      </main>
    </div>
  );
}

